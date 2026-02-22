"""
Run client for GoFetch API.

Provides Apify-compatible interface for managing individual job runs.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from gofetch.actor import _format_job_as_apify_run, _is_terminal, _next_poll_interval
from gofetch.constants import DEFAULT_POLL_INTERVAL
from gofetch.exceptions import APIError

if TYPE_CHECKING:
    from gofetch.dataset import AsyncDatasetClient, DatasetClient
    from gofetch.http import AsyncHTTPClient, HTTPClient
    from gofetch.log import AsyncLogClient, LogClient

logger = logging.getLogger(__name__)


class RunClient:
    """
    Run client that wraps GoFetch job API with Apify-compatible interface.

    Provides the same methods as Apify's RunClient:
    - get() for fetching run status
    - wait_for_finish() for polling until completion
    - abort() for cancelling a run
    - dataset() for accessing run results
    - log() for accessing run logs
    """

    def __init__(self, http: HTTPClient, run_id: str) -> None:
        self._http = http
        self._run_id = run_id

    def get(self) -> dict[str, Any] | None:
        """Get run status in Apify format.

        Returns:
            Dict in Apify run format, or None if job not found (404).
        """
        try:
            job = self._http.get(f"/api/v1/jobs/{self._run_id}/")
        except APIError as e:
            if e.status_code == 404:
                return None
            raise
        return _format_job_as_apify_run(job, scraper_type=job.get("scraper_type"))

    def wait_for_finish(self, *, wait_secs: int | None = None) -> dict[str, Any] | None:
        """Poll until job completes or timeout.

        Args:
            wait_secs: Maximum wait time in seconds. None means wait indefinitely.

        Returns:
            Apify run format dict when job reaches terminal state,
            current run state dict on timeout (status still "RUNNING"),
            or None if job not found (404).
        """
        start_time = time.monotonic()
        poll_interval = DEFAULT_POLL_INTERVAL

        while True:
            try:
                job = self._http.get(f"/api/v1/jobs/{self._run_id}/")
            except APIError as e:
                if e.status_code == 404:
                    return None
                raise

            if _is_terminal(job.get("status", "")):
                return _format_job_as_apify_run(
                    job, scraper_type=job.get("scraper_type"),
                )

            if wait_secs is not None and (time.monotonic() - start_time) >= wait_secs:
                return _format_job_as_apify_run(
                    job, scraper_type=job.get("scraper_type"),
                )

            time.sleep(poll_interval)
            poll_interval = _next_poll_interval(poll_interval)

    def abort(self, *, gracefully: bool | None = None) -> dict[str, Any]:
        """Cancel the job.

        Works even if the job is already in a terminal state (returns
        current state).

        Args:
            gracefully: Ignored (Apify compatibility).

        Returns:
            Dict in Apify run format with updated status.
        """
        _ = gracefully

        try:
            job = self._http.post(f"/api/v1/jobs/{self._run_id}/cancel/")
        except APIError as e:
            if e.status_code == 404:
                job = self._http.get(f"/api/v1/jobs/{self._run_id}/")
            else:
                raise
        return _format_job_as_apify_run(job, scraper_type=job.get("scraper_type"))

    def dataset(self) -> DatasetClient:
        """Get dataset client for this run's results."""
        from gofetch.dataset import DatasetClient

        return DatasetClient(http=self._http, job_id=self._run_id)

    def log(self) -> LogClient:
        """Get log client for this run."""
        from gofetch.log import LogClient

        return LogClient(http=self._http, job_id=self._run_id)

    def delete(self) -> None:
        """Not supported in GoFetch."""
        raise NotImplementedError(
            "GoFetch does not support deleting runs. "
            "GoFetch manages job retention automatically."
        )


class AsyncRunClient:
    """Async run client for GoFetch API."""

    def __init__(self, http: AsyncHTTPClient, run_id: str) -> None:
        self._http = http
        self._run_id = run_id

    async def get(self) -> dict[str, Any] | None:
        """Get run status in Apify format. Async version."""
        try:
            job = await self._http.get(f"/api/v1/jobs/{self._run_id}/")
        except APIError as e:
            if e.status_code == 404:
                return None
            raise
        return _format_job_as_apify_run(job, scraper_type=job.get("scraper_type"))

    async def wait_for_finish(
        self, *, wait_secs: int | None = None,
    ) -> dict[str, Any] | None:
        """Poll until job completes or timeout. Async version.

        Args:
            wait_secs: Maximum wait time in seconds. None means wait indefinitely.

        Returns:
            Apify run format dict when job reaches terminal state,
            current run state dict on timeout (status still "RUNNING"),
            or None if job not found (404).
        """
        import asyncio

        start_time = time.monotonic()
        poll_interval = DEFAULT_POLL_INTERVAL

        while True:
            try:
                job = await self._http.get(f"/api/v1/jobs/{self._run_id}/")
            except APIError as e:
                if e.status_code == 404:
                    return None
                raise

            if _is_terminal(job.get("status", "")):
                return _format_job_as_apify_run(
                    job, scraper_type=job.get("scraper_type"),
                )

            if wait_secs is not None and (time.monotonic() - start_time) >= wait_secs:
                return _format_job_as_apify_run(
                    job, scraper_type=job.get("scraper_type"),
                )

            await asyncio.sleep(poll_interval)
            poll_interval = _next_poll_interval(poll_interval)

    async def abort(self, *, gracefully: bool | None = None) -> dict[str, Any]:
        """Cancel the job. Async version.

        Works even if the job is already in a terminal state (returns
        current state).

        Args:
            gracefully: Ignored (Apify compatibility).

        Returns:
            Dict in Apify run format with updated status.
        """
        _ = gracefully

        try:
            job = await self._http.post(f"/api/v1/jobs/{self._run_id}/cancel/")
        except APIError as e:
            if e.status_code == 404:
                job = await self._http.get(f"/api/v1/jobs/{self._run_id}/")
            else:
                raise
        return _format_job_as_apify_run(job, scraper_type=job.get("scraper_type"))

    def dataset(self) -> AsyncDatasetClient:
        """Get async dataset client for this run's results."""
        from gofetch.dataset import AsyncDatasetClient

        return AsyncDatasetClient(http=self._http, job_id=self._run_id)

    def log(self) -> AsyncLogClient:
        """Get async log client for this run."""
        from gofetch.log import AsyncLogClient

        return AsyncLogClient(http=self._http, job_id=self._run_id)

    async def delete(self) -> None:
        """Not supported in GoFetch."""
        raise NotImplementedError(
            "GoFetch does not support deleting runs. "
            "GoFetch manages job retention automatically."
        )
