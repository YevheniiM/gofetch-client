"""Tests for RunClient and AsyncRunClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gofetch.dataset import AsyncDatasetClient, DatasetClient
from gofetch.exceptions import APIError
from gofetch.log import AsyncLogClient, LogClient
from gofetch.run import AsyncRunClient, RunClient

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_JOB = {
    "id": "job-123",
    "status": "completed",
    "scraper_type": "instagram",
    "started_at": "2024-01-01T00:00:00Z",
    "completed_at": "2024-01-01T00:10:00Z",
    "items_scraped": 50,
}

MOCK_RUNNING_JOB = {
    "id": "job-123",
    "status": "running",
    "scraper_type": "instagram",
    "started_at": "2024-01-01T00:00:00Z",
    "completed_at": None,
    "items_scraped": 0,
}

MOCK_FAILED_JOB = {
    "id": "job-123",
    "status": "failed",
    "scraper_type": "instagram",
    "started_at": "2024-01-01T00:00:00Z",
    "completed_at": "2024-01-01T00:05:00Z",
    "items_scraped": 0,
}


# ---------------------------------------------------------------------------
# RunClient (sync)
# ---------------------------------------------------------------------------


class TestRunClient:

    def test_get_returns_apify_format(self):
        http = MagicMock()
        http.get.return_value = MOCK_JOB

        client = RunClient(http, "job-123")
        result = client.get()

        http.get.assert_called_once_with("/api/v1/jobs/job-123/")
        assert result is not None
        assert result["id"] == "job-123"
        assert result["actId"] == "gofetch/instagram"
        assert result["status"] == "SUCCEEDED"
        assert result["defaultDatasetId"] == "job-123"
        assert result["startedAt"] == "2024-01-01T00:00:00Z"
        assert result["finishedAt"] == "2024-01-01T00:10:00Z"

    def test_get_returns_none_on_404(self):
        http = MagicMock()
        http.get.side_effect = APIError(message="Not found", status_code=404)

        client = RunClient(http, "job-missing")
        result = client.get()

        assert result is None

    @patch("gofetch.run.time.sleep")
    def test_wait_for_finish_success(self, mock_sleep):
        http = MagicMock()
        http.get.return_value = MOCK_JOB

        client = RunClient(http, "job-123")
        result = client.wait_for_finish()

        assert result is not None
        assert result["status"] == "SUCCEEDED"
        assert result["id"] == "job-123"
        # Sleep should not be called because job is already terminal
        mock_sleep.assert_not_called()

    def test_wait_for_finish_timeout_returns_current_state(self):
        http = MagicMock()
        http.get.return_value = MOCK_RUNNING_JOB

        client = RunClient(http, "job-123")
        # wait_secs=0 should return immediately with current state
        result = client.wait_for_finish(wait_secs=0)

        assert result is not None
        assert result["status"] == "RUNNING"
        assert result["id"] == "job-123"

    @patch("gofetch.run.time.sleep")
    def test_wait_for_finish_returns_none_on_404(self, mock_sleep):
        http = MagicMock()
        http.get.side_effect = APIError(message="Not found", status_code=404)

        client = RunClient(http, "job-missing")
        result = client.wait_for_finish()

        assert result is None

    def test_wait_for_finish_failed_job(self):
        http = MagicMock()
        http.get.return_value = MOCK_FAILED_JOB

        client = RunClient(http, "job-123")
        result = client.wait_for_finish()

        assert result is not None
        assert result["status"] == "FAILED"
        assert result["id"] == "job-123"

    def test_abort_returns_updated_run(self):
        http = MagicMock()
        cancelled_job = {**MOCK_JOB, "status": "cancelled"}
        http.post.return_value = cancelled_job

        client = RunClient(http, "job-123")
        result = client.abort()

        http.post.assert_called_once_with("/api/v1/jobs/job-123/cancel/")
        assert result["id"] == "job-123"
        assert result["status"] == "ABORTED"

    def test_dataset_returns_dataset_client(self):
        http = MagicMock()

        client = RunClient(http, "job-123")
        ds = client.dataset()

        assert isinstance(ds, DatasetClient)

    def test_log_returns_log_client(self):
        http = MagicMock()

        client = RunClient(http, "job-123")
        log = client.log()

        assert isinstance(log, LogClient)

    def test_delete_raises_not_implemented(self):
        http = MagicMock()

        client = RunClient(http, "job-123")
        with pytest.raises(NotImplementedError):
            client.delete()


# ---------------------------------------------------------------------------
# AsyncRunClient
# ---------------------------------------------------------------------------


class TestAsyncRunClient:

    async def test_async_get(self):
        http = AsyncMock()
        http.get.return_value = MOCK_JOB

        client = AsyncRunClient(http, "job-123")
        result = await client.get()

        http.get.assert_awaited_once_with("/api/v1/jobs/job-123/")
        assert result is not None
        assert result["id"] == "job-123"
        assert result["status"] == "SUCCEEDED"
        assert result["actId"] == "gofetch/instagram"

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_async_wait_for_finish(self, mock_sleep):
        http = AsyncMock()
        http.get.return_value = MOCK_JOB

        client = AsyncRunClient(http, "job-123")
        result = await client.wait_for_finish()

        assert result is not None
        assert result["status"] == "SUCCEEDED"
        assert result["id"] == "job-123"
