"""
Actor client for GoFetch API.

Provides Apify-compatible interface for running scraper jobs.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from gofetch.constants import (
    DEFAULT_POLL_INTERVAL,
    GOFETCH_TO_APIFY_STATUS,
    MAX_POLL_INTERVAL,
    POLL_BACKOFF_FACTOR,
)
from gofetch.exceptions import JobError, TimeoutError

if TYPE_CHECKING:
    from gofetch.http import AsyncHTTPClient, HTTPClient


class ActorClient:
    """
    Actor client that wraps GoFetch job API with Apify-compatible interface.

    Provides the same methods as Apify's ActorClient:
    - call() for synchronous execution
    - start() for asynchronous execution with webhooks

    Usage:
        client = GoFetchClient(api_key="...")
        actor = client.actor("instagram")

        # Sync execution (blocks until complete)
        run = actor.call(run_input={"directUrls": [...]})

        # Async execution (returns immediately)
        run = actor.start(run_input={...}, webhooks=[...])
    """

    def __init__(
        self,
        http: HTTPClient,
        scraper_type: str,
    ) -> None:
        """
        Initialize actor client.

        Args:
            http: HTTP client for API requests
            scraper_type: GoFetch scraper type (e.g., "instagram", "tiktok")
        """
        self._http = http
        self._scraper_type = scraper_type

    def call(
        self,
        run_input: dict[str, Any],
        timeout_secs: int = 3600,
        memory_mbytes: int | None = None,  # Ignored, for Apify compatibility
        build: str | None = None,  # Ignored, for Apify compatibility
    ) -> dict[str, Any]:
        """
        Run actor synchronously (blocking).

        Equivalent to Apify's actor.call() - blocks until job completes.

        Args:
            run_input: Scraper configuration parameters
            timeout_secs: Maximum wait time in seconds (default 1 hour)
            memory_mbytes: Ignored (Apify compatibility)
            build: Ignored (Apify compatibility)

        Returns:
            Dict in Apify run format with keys:
            - id: Run/job ID
            - actId: Actor ID (e.g., "gofetch/instagram")
            - status: "SUCCEEDED", "FAILED", etc.
            - defaultDatasetId: Dataset ID for fetching results
            - startedAt: Start timestamp
            - finishedAt: Finish timestamp
            - _gofetch_job: Original GoFetch job data

        Raises:
            TimeoutError: If job doesn't complete within timeout_secs
            JobError: If job fails
        """
        _ = memory_mbytes, build  # Unused, for Apify compatibility

        # 1. Create job
        job = self._create_job(run_input)
        job_id = job["id"]

        # 2. Poll until complete
        job = self._wait_for_completion(job_id, timeout_secs)

        # 3. Check for failure
        if job["status"] == "failed":
            raise JobError(
                message="Job failed",
                job_id=job_id,
                status=job["status"],
                error_message=job.get("error_message"),
            )

        # 4. Return in Apify format
        return self._format_as_apify_run(job)

    def start(
        self,
        run_input: dict[str, Any],
        webhooks: list[dict[str, Any]] | None = None,
        memory_mbytes: int | None = None,  # Ignored
        build: str | None = None,  # Ignored
    ) -> dict[str, Any]:
        """
        Start actor asynchronously (non-blocking).

        Equivalent to Apify's actor.start() - returns immediately.
        Use webhooks to get notified when the job completes.

        Args:
            run_input: Scraper configuration parameters
            webhooks: List of webhook configurations. Each webhook should have:
                - request_url: URL to POST to
                - event_types: List of event types (e.g., ["ACTOR.RUN.SUCCEEDED"])
            memory_mbytes: Ignored (Apify compatibility)
            build: Ignored (Apify compatibility)

        Returns:
            Dict in Apify run format with status "RUNNING" or "READY"
        """
        _ = webhooks, memory_mbytes, build  # Unused, for Apify compatibility

        # Create job (don't wait)
        job = self._create_job(run_input)

        # Return in Apify format
        return self._format_as_apify_run(job)

    def _create_job(self, run_input: dict[str, Any]) -> dict[str, Any]:
        """
        Create a scraper job via GoFetch API.

        Args:
            run_input: Scraper configuration parameters

        Returns:
            Job response from API
        """
        # Transform input if needed (most fields are 1:1)
        config = self._transform_input(run_input)

        response = self._http.post(
            "/api/v1/jobs/create/",
            json={
                "scraper_type": self._scraper_type,
                "config": config,
            },
        )
        return response

    def _transform_input(self, run_input: dict[str, Any]) -> dict[str, Any]:
        """
        Transform Apify-style input to GoFetch format.

        Most parameters are the same between Apify and GoFetch,
        but we can add transformations here as needed.

        Args:
            run_input: Apify-style input parameters

        Returns:
            GoFetch-compatible config
        """
        # Currently 1:1, but can add transformations
        return run_input.copy()

    def _wait_for_completion(
        self,
        job_id: str,
        timeout_secs: int,
    ) -> dict[str, Any]:
        """
        Poll job status until complete or timeout.

        Uses exponential backoff starting at 2 seconds, up to 30 seconds.

        Args:
            job_id: Job ID to poll
            timeout_secs: Maximum wait time

        Returns:
            Final job data

        Raises:
            TimeoutError: If timeout exceeded
        """
        start_time = time.time()
        poll_interval = DEFAULT_POLL_INTERVAL

        while time.time() - start_time < timeout_secs:
            job = self._http.get(f"/api/v1/jobs/{job_id}/")

            if job["status"] in ("completed", "failed", "cancelled"):
                return job

            # Wait before next poll
            time.sleep(poll_interval)

            # Exponential backoff
            poll_interval = min(poll_interval * POLL_BACKOFF_FACTOR, MAX_POLL_INTERVAL)

        raise TimeoutError(
            message=f"Job did not complete within {timeout_secs} seconds",
            job_id=job_id,
            timeout_seconds=timeout_secs,
        )

    def _format_as_apify_run(self, job: dict[str, Any]) -> dict[str, Any]:
        """
        Convert GoFetch job to Apify run format.

        Args:
            job: GoFetch job data

        Returns:
            Dict matching Apify run format
        """
        status = GOFETCH_TO_APIFY_STATUS.get(job["status"], "RUNNING")

        return {
            "id": job["id"],
            "actId": f"gofetch/{self._scraper_type}",
            "status": status,
            "defaultDatasetId": job["id"],  # In GoFetch, job_id == dataset_id
            "startedAt": job.get("started_at"),
            "finishedAt": job.get("completed_at"),
            # Apify compat fields (placeholders)
            "buildId": None,
            "buildNumber": None,
            "exitCode": 0 if status == "SUCCEEDED" else None,
            "defaultKeyValueStoreId": None,
            "defaultRequestQueueId": None,
            # Original job data for reference
            "_gofetch_job": job,
        }


class AsyncActorClient:
    """
    Async actor client for GoFetch API.

    Same interface as ActorClient but uses async/await.
    """

    def __init__(
        self,
        http: AsyncHTTPClient,
        scraper_type: str,
    ) -> None:
        """Initialize async actor client."""
        self._http = http
        self._scraper_type = scraper_type

    async def call(
        self,
        run_input: dict[str, Any],
        timeout_secs: int = 3600,
        memory_mbytes: int | None = None,
        build: str | None = None,
    ) -> dict[str, Any]:
        """Run actor synchronously (blocking)."""
        _ = memory_mbytes, build  # Unused

        job = await self._create_job(run_input)
        job_id = job["id"]

        job = await self._wait_for_completion(job_id, timeout_secs)

        if job["status"] == "failed":
            raise JobError(
                message="Job failed",
                job_id=job_id,
                status=job["status"],
                error_message=job.get("error_message"),
            )

        return self._format_as_apify_run(job)

    async def start(
        self,
        run_input: dict[str, Any],
        webhooks: list[dict[str, Any]] | None = None,
        memory_mbytes: int | None = None,
        build: str | None = None,
    ) -> dict[str, Any]:
        """Start actor asynchronously (non-blocking)."""
        _ = webhooks, memory_mbytes, build  # Unused

        job = await self._create_job(run_input)
        return self._format_as_apify_run(job)

    async def _create_job(self, run_input: dict[str, Any]) -> dict[str, Any]:
        """Create a scraper job via GoFetch API."""
        config = run_input.copy()

        response = await self._http.post(
            "/api/v1/jobs/create/",
            json={
                "scraper_type": self._scraper_type,
                "config": config,
            },
        )
        return response

    async def _wait_for_completion(
        self,
        job_id: str,
        timeout_secs: int,
    ) -> dict[str, Any]:
        """Poll job status until complete or timeout."""
        import asyncio

        start_time = time.time()
        poll_interval = DEFAULT_POLL_INTERVAL

        while time.time() - start_time < timeout_secs:
            job = await self._http.get(f"/api/v1/jobs/{job_id}/")

            if job["status"] in ("completed", "failed", "cancelled"):
                return job

            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * POLL_BACKOFF_FACTOR, MAX_POLL_INTERVAL)

        raise TimeoutError(
            message=f"Job did not complete within {timeout_secs} seconds",
            job_id=job_id,
            timeout_seconds=timeout_secs,
        )

    def _format_as_apify_run(self, job: dict[str, Any]) -> dict[str, Any]:
        """Convert GoFetch job to Apify run format."""
        status = GOFETCH_TO_APIFY_STATUS.get(job["status"], "RUNNING")

        return {
            "id": job["id"],
            "actId": f"gofetch/{self._scraper_type}",
            "status": status,
            "defaultDatasetId": job["id"],
            "startedAt": job.get("started_at"),
            "finishedAt": job.get("completed_at"),
            "buildId": None,
            "buildNumber": None,
            "exitCode": 0 if status == "SUCCEEDED" else None,
            "defaultKeyValueStoreId": None,
            "defaultRequestQueueId": None,
            "_gofetch_job": job,
        }
