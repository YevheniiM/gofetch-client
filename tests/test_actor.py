"""Tests for ActorClient and AsyncActorClient."""

from __future__ import annotations

import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gofetch.actor import ActorClient, AsyncActorClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(
    job_id: str = "job-123",
    status: str = "completed",
    scraper_type: str = "instagram",
    started_at: str = "2024-01-01T00:00:00Z",
    completed_at: str | None = "2024-01-01T00:10:00Z",
) -> dict:
    """Build a minimal GoFetch job dict."""
    return {
        "id": job_id,
        "status": status,
        "scraper_type": scraper_type,
        "started_at": started_at,
        "completed_at": completed_at,
    }


def _make_pending_job(job_id: str = "job-123") -> dict:
    return _make_job(job_id=job_id, status="pending", completed_at=None)


def _make_running_job(job_id: str = "job-123") -> dict:
    return _make_job(job_id=job_id, status="running", completed_at=None)


def _make_failed_job(job_id: str = "job-123") -> dict:
    return _make_job(job_id=job_id, status="failed", completed_at="2024-01-01T00:05:00Z")


# ---------------------------------------------------------------------------
# Sync ActorClient tests
# ---------------------------------------------------------------------------


class TestActorClientCall:
    """Tests for ActorClient.call()."""

    @patch("gofetch.actor.time.sleep")
    def test_call_returns_run_dict_on_success(self, mock_sleep: MagicMock) -> None:
        """call() returns an Apify-format run dict when the job completes successfully."""
        http = MagicMock()
        http.post.return_value = _make_pending_job()
        http.get.return_value = _make_job(status="completed")

        actor = ActorClient(http=http, scraper_type="instagram")
        run = actor.call(run_input={"directUrls": ["https://instagram.com/nike"]}, wait_secs=60)

        assert run["id"] == "job-123"
        assert run["status"] == "SUCCEEDED"
        assert run["defaultDatasetId"] == "job-123"
        assert run["actId"] == "gofetch/instagram"
        assert run["exitCode"] == 0

    @patch("gofetch.actor.time.sleep")
    def test_call_returns_run_dict_on_failure_no_raise(self, mock_sleep: MagicMock) -> None:
        """call() returns a run dict with FAILED status -- does NOT raise JobError."""
        http = MagicMock()
        http.post.return_value = _make_pending_job()
        http.get.return_value = _make_failed_job()

        actor = ActorClient(http=http, scraper_type="instagram")
        run = actor.call(run_input={"directUrls": ["https://instagram.com/nike"]}, wait_secs=60)

        assert run["status"] == "FAILED"
        assert run["exitCode"] is None  # non-SUCCEEDED gets None

    @patch("gofetch.actor.time.sleep")
    def test_call_returns_current_state_on_timeout_no_raise(self, mock_sleep: MagicMock) -> None:
        """call() returns the current run state on timeout -- does NOT raise TimeoutError."""
        http = MagicMock()
        http.post.return_value = _make_pending_job()
        http.get.return_value = _make_running_job()

        actor = ActorClient(http=http, scraper_type="instagram")
        # wait_secs=0 means it should return immediately after first poll
        run = actor.call(run_input={"foo": "bar"}, wait_secs=0)

        assert run["status"] == "RUNNING"
        assert run["id"] == "job-123"

    @patch("gofetch.actor.time.sleep")
    def test_call_timeout_secs_deprecated_alias(self, mock_sleep: MagicMock) -> None:
        """call() with timeout_secs emits a DeprecationWarning and uses the value as wait_secs."""
        http = MagicMock()
        http.post.return_value = _make_pending_job()
        http.get.return_value = _make_running_job()

        actor = ActorClient(http=http, scraper_type="instagram")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run = actor.call(run_input={"foo": "bar"}, timeout_secs=0)

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1
        assert "timeout_secs" in str(deprecation_warnings[0].message)
        assert run["status"] == "RUNNING"

    @patch("gofetch.actor.time.sleep")
    def test_call_wait_secs_none_waits_indefinitely(self, mock_sleep: MagicMock) -> None:
        """call() with wait_secs=None waits until the job reaches a terminal status."""
        http = MagicMock()
        http.post.return_value = _make_pending_job()
        # First two polls return running, third returns completed
        http.get.side_effect = [
            _make_running_job(),
            _make_running_job(),
            _make_job(status="completed"),
        ]

        actor = ActorClient(http=http, scraper_type="instagram")
        run = actor.call(run_input={"foo": "bar"}, wait_secs=None)

        assert run["status"] == "SUCCEEDED"
        assert http.get.call_count == 3
        assert mock_sleep.call_count == 2  # slept between each non-terminal poll

    @patch("gofetch.actor.time.sleep")
    def test_call_posts_to_create_endpoint(self, mock_sleep: MagicMock) -> None:
        """call() creates a job via POST /api/v1/jobs/create/."""
        http = MagicMock()
        http.post.return_value = _make_pending_job()
        http.get.return_value = _make_job(status="completed")

        actor = ActorClient(http=http, scraper_type="instagram")
        actor.call(run_input={"directUrls": ["https://instagram.com/nike"]}, wait_secs=60)

        http.post.assert_called_once()
        call_args = http.post.call_args
        assert call_args[0][0] == "/api/v1/jobs/create/"
        payload = call_args[1].get("json") or call_args.kwargs.get("json")
        assert payload["scraper_type"] == "instagram"
        assert payload["config"] == {"directUrls": ["https://instagram.com/nike"]}


class TestActorClientStart:
    """Tests for ActorClient.start()."""

    def test_start_returns_immediately(self) -> None:
        """start() returns immediately with the run dict (no polling)."""
        http = MagicMock()
        http.post.return_value = _make_pending_job()

        actor = ActorClient(http=http, scraper_type="instagram")
        run = actor.start(run_input={"foo": "bar"})

        assert run["id"] == "job-123"
        assert run["status"] == "READY"  # pending -> READY
        http.get.assert_not_called()  # No polling

    def test_start_with_webhooks_includes_translated_webhooks(self) -> None:
        """start() with webhooks translates Apify event types to GoFetch events."""
        http = MagicMock()
        http.post.return_value = _make_pending_job()

        actor = ActorClient(http=http, scraper_type="instagram")
        run = actor.start(
            run_input={"foo": "bar"},
            webhooks=[
                {
                    "request_url": "https://example.com/success",
                    "event_types": ["ACTOR.RUN.SUCCEEDED"],
                },
            ],
        )

        assert run["id"] == "job-123"
        call_args = http.post.call_args
        payload = call_args[1].get("json") or call_args.kwargs.get("json")
        assert "webhooks" in payload
        assert payload["webhooks"][0]["url"] == "https://example.com/success"
        assert payload["webhooks"][0]["events"] == ["job.completed"]

    def test_start_with_camelcase_webhook_keys(self) -> None:
        """start() accepts camelCase webhook keys (requestUrl, eventTypes)."""
        http = MagicMock()
        http.post.return_value = _make_pending_job()

        actor = ActorClient(http=http, scraper_type="instagram")
        actor.start(
            run_input={"foo": "bar"},
            webhooks=[
                {
                    "requestUrl": "https://example.com/failed",
                    "eventTypes": ["ACTOR.RUN.FAILED"],
                },
            ],
        )

        call_args = http.post.call_args
        payload = call_args[1].get("json") or call_args.kwargs.get("json")
        assert payload["webhooks"][0]["url"] == "https://example.com/failed"
        assert payload["webhooks"][0]["events"] == ["job.failed"]


class TestWebhookTranslation:
    """Tests for webhook event translation."""

    def test_multiple_events_translated(self) -> None:
        """Multiple Apify event types are each translated to GoFetch events."""
        http = MagicMock()
        http.post.return_value = _make_pending_job()

        actor = ActorClient(http=http, scraper_type="instagram")
        actor.start(
            run_input={"foo": "bar"},
            webhooks=[
                {
                    "request_url": "https://example.com/hook",
                    "event_types": [
                        "ACTOR.RUN.SUCCEEDED",
                        "ACTOR.RUN.FAILED",
                        "ACTOR.RUN.TIMED_OUT",
                    ],
                },
            ],
        )

        call_args = http.post.call_args
        payload = call_args[1].get("json") or call_args.kwargs.get("json")
        events = payload["webhooks"][0]["events"]
        assert events == ["job.completed", "job.failed", "job.timed_out"]

    def test_unknown_event_passed_through(self) -> None:
        """Unknown event types are passed through unchanged."""
        http = MagicMock()
        http.post.return_value = _make_pending_job()

        actor = ActorClient(http=http, scraper_type="instagram")
        actor.start(
            run_input={"foo": "bar"},
            webhooks=[
                {
                    "request_url": "https://example.com/hook",
                    "event_types": ["CUSTOM.EVENT"],
                },
            ],
        )

        call_args = http.post.call_args
        payload = call_args[1].get("json") or call_args.kwargs.get("json")
        assert payload["webhooks"][0]["events"] == ["CUSTOM.EVENT"]


# ---------------------------------------------------------------------------
# Async ActorClient tests
# ---------------------------------------------------------------------------


class TestAsyncActorClientCall:
    """Tests for AsyncActorClient.call()."""

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_call_returns_run_dict_on_success(self, mock_sleep: AsyncMock) -> None:
        """Async call() returns an Apify-format run dict when the job completes."""
        http = AsyncMock()
        http.post.return_value = _make_pending_job()
        http.get.return_value = _make_job(status="completed")

        actor = AsyncActorClient(http=http, scraper_type="instagram")
        run = await actor.call(
            run_input={"directUrls": ["https://instagram.com/nike"]},
            wait_secs=60,
        )

        assert run["id"] == "job-123"
        assert run["status"] == "SUCCEEDED"

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_call_returns_run_dict_on_failure_no_raise(
        self, mock_sleep: AsyncMock,
    ) -> None:
        """Async call() returns a FAILED run dict -- does NOT raise."""
        http = AsyncMock()
        http.post.return_value = _make_pending_job()
        http.get.return_value = _make_failed_job()

        actor = AsyncActorClient(http=http, scraper_type="instagram")
        run = await actor.call(run_input={"foo": "bar"}, wait_secs=60)

        assert run["status"] == "FAILED"

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_call_returns_current_state_on_timeout_no_raise(
        self, mock_sleep: AsyncMock,
    ) -> None:
        """Async call() returns current run state on timeout -- does NOT raise."""
        http = AsyncMock()
        http.post.return_value = _make_pending_job()
        http.get.return_value = _make_running_job()

        actor = AsyncActorClient(http=http, scraper_type="instagram")
        run = await actor.call(run_input={"foo": "bar"}, wait_secs=0)

        assert run["status"] == "RUNNING"

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_call_timeout_secs_deprecated_alias(
        self, mock_sleep: AsyncMock,
    ) -> None:
        """Async call() with timeout_secs emits a DeprecationWarning."""
        http = AsyncMock()
        http.post.return_value = _make_pending_job()
        http.get.return_value = _make_running_job()

        actor = AsyncActorClient(http=http, scraper_type="instagram")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run = await actor.call(run_input={"foo": "bar"}, timeout_secs=0)

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1
        assert "timeout_secs" in str(deprecation_warnings[0].message)
        assert run["status"] == "RUNNING"

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_call_wait_secs_none_waits_indefinitely(
        self, mock_sleep: AsyncMock,
    ) -> None:
        """Async call() with wait_secs=None polls until terminal status."""
        http = AsyncMock()
        http.post.return_value = _make_pending_job()
        http.get.side_effect = [
            _make_running_job(),
            _make_running_job(),
            _make_job(status="completed"),
        ]

        actor = AsyncActorClient(http=http, scraper_type="instagram")
        run = await actor.call(run_input={"foo": "bar"}, wait_secs=None)

        assert run["status"] == "SUCCEEDED"
        assert http.get.call_count == 3
        assert mock_sleep.call_count == 2


class TestAsyncActorClientStart:
    """Tests for AsyncActorClient.start()."""

    @pytest.mark.asyncio
    async def test_start_returns_immediately(self) -> None:
        """Async start() returns immediately with the run dict."""
        http = AsyncMock()
        http.post.return_value = _make_pending_job()

        actor = AsyncActorClient(http=http, scraper_type="instagram")
        run = await actor.start(run_input={"foo": "bar"})

        assert run["id"] == "job-123"
        assert run["status"] == "READY"
        http.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_with_webhooks_includes_translated_webhooks(self) -> None:
        """Async start() with webhooks translates Apify events to GoFetch events."""
        http = AsyncMock()
        http.post.return_value = _make_pending_job()

        actor = AsyncActorClient(http=http, scraper_type="instagram")
        await actor.start(
            run_input={"foo": "bar"},
            webhooks=[
                {
                    "request_url": "https://example.com/success",
                    "event_types": ["ACTOR.RUN.SUCCEEDED"],
                },
            ],
        )

        call_args = http.post.call_args
        payload = call_args[1].get("json") or call_args.kwargs.get("json")
        assert "webhooks" in payload
        assert payload["webhooks"][0]["url"] == "https://example.com/success"
        assert payload["webhooks"][0]["events"] == ["job.completed"]
