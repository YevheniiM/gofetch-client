"""
Actor client for GoFetch API.

Provides Apify-compatible interface for running scraper jobs.
"""

from __future__ import annotations

import logging
import time
import warnings
from typing import TYPE_CHECKING, Any

from gofetch.constants import (
    DEFAULT_POLL_INTERVAL,
    GOFETCH_TO_APIFY_STATUS,
    MAX_POLL_INTERVAL,
    POLL_BACKOFF_FACTOR,
)
from gofetch.webhook import APIFY_TO_GOFETCH_EVENTS

if TYPE_CHECKING:
    from gofetch.http import AsyncHTTPClient, HTTPClient

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({"completed", "failed", "timed_out", "cancelled"})


def _is_terminal(status: str) -> bool:
    """Terminality inferred from the status string alone.

    Kept as the fallback for servers that do not send ``is_terminal``. Prefer
    :func:`_job_is_terminal`, which asks the server first — ``failed`` is no
    longer unconditionally terminal (see below).
    """
    return status in TERMINAL_STATUSES


def _job_is_terminal(job: dict[str, Any]) -> bool:
    """Whether a job has reached an outcome the caller can act on.

    The server is authoritative when it answers. ``status`` alone is NOT enough:
    a job that fails an attempt while automatic retries remain reports
    ``status="failed"`` and ``is_terminal=False``, because the platform is about
    to run it again. Treating that as final abandons a run that is still going —
    the retry's results are then produced with nobody polling for them, and
    re-submitting (the natural recovery) duplicates the work and the spend.

    Falls back to the status map when ``is_terminal`` is absent or not a bool, so
    older servers behave exactly as they did before this function existed.
    """
    server_verdict = job.get("is_terminal")
    if isinstance(server_verdict, bool):
        return server_verdict
    return _is_terminal(job.get("status", ""))


def _next_poll_interval(current: float) -> float:
    return min(current * POLL_BACKOFF_FACTOR, MAX_POLL_INTERVAL)


def _usd(value: Any) -> float | None:
    """Cost as a number, whatever shape the server sent it in.

    The server serialises cost from a decimal column, so it arrives over JSON as
    a string ("0.3000"). A caller reading a cost field expects something it can
    sum and compare, and text silently fails both.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_job_as_apify_run(
    job: dict[str, Any],
    scraper_type: str | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert GoFetch job dict to Apify run format.

    IMPORTANT: Any extra fields on the job dict (e.g., scraper_metadata)
    are preserved on the returned run dict.
    """
    scraper_type = scraper_type or job.get("scraper_type", "unknown")
    status = GOFETCH_TO_APIFY_STATUS.get(job.get("status", ""), "RUNNING")

    run: dict[str, Any] = {
        "id": job["id"],
        "actId": f"gofetch/{scraper_type}",
        "status": status,
        "defaultDatasetId": job["id"],
        "startedAt": job.get("started_at"),
        "finishedAt": job.get("completed_at"),
        "buildId": None,
        "buildNumber": None,
        "exitCode": 0 if status == "SUCCEEDED" else None,
        "defaultKeyValueStoreId": None,
        "defaultRequestQueueId": None,
        # Retry-awareness, promoted to the top level. Both are readable at
        # run["_gofetch_job"][...] too, but a field nobody can find is a field
        # nobody uses — `isTerminal` in particular is the one signal that tells a
        # caller whether an Apify-style FAILED status is actually the end of the run.
        "isTerminal": _job_is_terminal(job),
        "willAutoRetry": job.get("will_auto_retry"),
        "attemptHistory": job.get("attempt_history") or [],
        # What the run actually cost. Apify-shaped callers read spend from
        # `usageTotalUsd`; with the key absent every one of them reports $0 per
        # run. None (not 0.0) until the server has settled the job — an unpriced
        # run is unknown spend, not free.
        "usageTotalUsd": _usd(job.get("actual_cost")),
        # Completeness signals (`coverage`, `completeness`, `enrichment`, ...)
        # ride here; without this they were only reachable under _gofetch_job.
        "scraper_metadata": job.get("scraper_metadata"),
        "_gofetch_job": job,
    }
    if extra_fields:
        run.update(extra_fields)
    return run


def _translate_webhooks(webhooks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate Apify-format webhooks to GoFetch format.

    Apify format:
        {"request_url": "https://...", "event_types": ["ACTOR.RUN.SUCCEEDED"]}
    or camelCase:
        {"requestUrl": "https://...", "eventTypes": ["ACTOR.RUN.SUCCEEDED"]}

    GoFetch format:
        {"url": "https://...", "events": ["job.completed"]}
    """
    translated = []
    for wh in webhooks:
        url = wh.get("request_url") or wh.get("requestUrl")
        event_types = wh.get("event_types") or wh.get("eventTypes", [])
        translated.append({
            "url": url,
            "events": [
                APIFY_TO_GOFETCH_EVENTS.get(et, et)
                for et in event_types
            ],
        })
    return translated


class ActorClient:
    """
    Actor client that wraps GoFetch job API with Apify-compatible interface.

    Provides the same methods as Apify's ActorClient:
    - call() for synchronous execution
    - start() for asynchronous execution with webhooks
    """

    def __init__(
        self,
        http: HTTPClient,
        scraper_type: str,
    ) -> None:
        self._http = http
        self._scraper_type = scraper_type

    def call(
        self,
        run_input: dict[str, Any],
        *,
        wait_secs: int | None = None,
        timeout_secs: int | None = None,
        memory_mbytes: int | None = None,
        build: str | None = None,
        webhooks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run actor synchronously (blocking).

        Matches Apify's behavioral contract:
        - Returns run dict regardless of final status (never raises on failure/timeout)
        - On timeout, returns the current run state (status may be "RUNNING")
        - Default wait_secs=None means wait indefinitely

        Args:
            run_input: Scraper configuration parameters
            wait_secs: Maximum wait time in seconds (None = indefinite)
            timeout_secs: Deprecated alias for wait_secs
            memory_mbytes: Ignored (Apify compatibility)
            build: Ignored (Apify compatibility)
            webhooks: Per-run webhooks to register

        Returns:
            Dict in Apify run format
        """
        _ = memory_mbytes, build

        effective_wait = self._resolve_wait_secs(wait_secs, timeout_secs)

        job = self._create_job(run_input, webhooks=webhooks)
        job_id = job["id"]

        return self._wait_for_completion(job_id, effective_wait)

    def start(
        self,
        run_input: dict[str, Any],
        *,
        webhooks: list[dict[str, Any]] | None = None,
        wait_secs: int | None = None,
        timeout_secs: int | None = None,
        memory_mbytes: int | None = None,
        build: str | None = None,
    ) -> dict[str, Any]:
        """Start actor asynchronously (non-blocking).

        Returns immediately after creating the job.
        """
        _ = wait_secs, timeout_secs, memory_mbytes, build

        job = self._create_job(run_input, webhooks=webhooks)
        return _format_job_as_apify_run(job, scraper_type=self._scraper_type)

    def _create_job(
        self,
        run_input: dict[str, Any],
        webhooks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        config = self._transform_input(run_input)
        payload: dict[str, Any] = {
            "scraper_type": self._scraper_type,
            "config": config,
        }
        if webhooks:
            payload["webhooks"] = _translate_webhooks(webhooks)

        return self._http.post("/api/v1/jobs/create/", json=payload)

    def _transform_input(self, run_input: dict[str, Any]) -> dict[str, Any]:
        return run_input.copy()

    def _wait_for_completion(
        self,
        job_id: str,
        wait_secs: int | None,
    ) -> dict[str, Any]:
        """Poll job status until terminal or timeout.

        Returns Apify-format run dict in all cases (never raises).
        On timeout, returns current run state. On 404, returns minimal dict.
        """
        start_time = time.monotonic()
        poll_interval = DEFAULT_POLL_INTERVAL

        while True:
            job = self._http.get(f"/api/v1/jobs/{job_id}/")

            if _job_is_terminal(job):
                return _format_job_as_apify_run(job, scraper_type=self._scraper_type)

            if wait_secs is not None and (time.monotonic() - start_time) >= wait_secs:
                return _format_job_as_apify_run(job, scraper_type=self._scraper_type)

            time.sleep(poll_interval)
            poll_interval = _next_poll_interval(poll_interval)

    @staticmethod
    def _resolve_wait_secs(
        wait_secs: int | None,
        timeout_secs: int | None,
    ) -> int | None:
        if timeout_secs is not None and wait_secs is None:
            warnings.warn(
                "timeout_secs is deprecated, use wait_secs instead",
                DeprecationWarning,
                stacklevel=3,
            )
            return timeout_secs
        return wait_secs


class AsyncActorClient:
    """Async actor client for GoFetch API."""

    def __init__(
        self,
        http: AsyncHTTPClient,
        scraper_type: str,
    ) -> None:
        self._http = http
        self._scraper_type = scraper_type

    async def call(
        self,
        run_input: dict[str, Any],
        *,
        wait_secs: int | None = None,
        timeout_secs: int | None = None,
        memory_mbytes: int | None = None,
        build: str | None = None,
        webhooks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run actor synchronously (blocking). Async version."""
        _ = memory_mbytes, build

        effective_wait = ActorClient._resolve_wait_secs(wait_secs, timeout_secs)

        job = await self._create_job(run_input, webhooks=webhooks)
        job_id = job["id"]

        return await self._wait_for_completion(job_id, effective_wait)

    async def start(
        self,
        run_input: dict[str, Any],
        *,
        webhooks: list[dict[str, Any]] | None = None,
        wait_secs: int | None = None,
        timeout_secs: int | None = None,
        memory_mbytes: int | None = None,
        build: str | None = None,
    ) -> dict[str, Any]:
        """Start actor asynchronously (non-blocking). Async version."""
        _ = wait_secs, timeout_secs, memory_mbytes, build

        job = await self._create_job(run_input, webhooks=webhooks)
        return _format_job_as_apify_run(job, scraper_type=self._scraper_type)

    async def _create_job(
        self,
        run_input: dict[str, Any],
        webhooks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        config = self._transform_input(run_input)
        payload: dict[str, Any] = {
            "scraper_type": self._scraper_type,
            "config": config,
        }
        if webhooks:
            payload["webhooks"] = _translate_webhooks(webhooks)

        return await self._http.post("/api/v1/jobs/create/", json=payload)

    def _transform_input(self, run_input: dict[str, Any]) -> dict[str, Any]:
        return run_input.copy()

    async def _wait_for_completion(
        self,
        job_id: str,
        wait_secs: int | None,
    ) -> dict[str, Any]:
        """Poll job status until terminal or timeout. Async version."""
        import asyncio

        start_time = time.monotonic()
        poll_interval = DEFAULT_POLL_INTERVAL

        while True:
            job = await self._http.get(f"/api/v1/jobs/{job_id}/")

            if _job_is_terminal(job):
                return _format_job_as_apify_run(job, scraper_type=self._scraper_type)

            if wait_secs is not None and (time.monotonic() - start_time) >= wait_secs:
                return _format_job_as_apify_run(job, scraper_type=self._scraper_type)

            await asyncio.sleep(poll_interval)
            poll_interval = _next_poll_interval(poll_interval)
