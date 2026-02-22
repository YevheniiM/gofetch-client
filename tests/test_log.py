"""Tests for LogClient and AsyncLogClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from gofetch.exceptions import APIError
from gofetch.log import AsyncLogClient, LogClient

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_LOG_RESPONSE = {
    "results": [
        {
            "id": 1,
            "timestamp": "2024-01-01T00:00:01Z",
            "level": "INFO",
            "message": "Job started",
        },
        {
            "id": 2,
            "timestamp": "2024-01-01T00:00:05Z",
            "level": "INFO",
            "message": "Scraping page 1",
        },
    ],
}


# ---------------------------------------------------------------------------
# LogClient (sync)
# ---------------------------------------------------------------------------


class TestLogClient:

    def test_get_returns_text(self):
        http = MagicMock()
        http.get.return_value = MOCK_LOG_RESPONSE

        client = LogClient(http, "job-123")
        result = client.get()

        http.get.assert_called_once_with("/api/v1/jobs/job-123/logs/")
        assert result is not None
        assert "2024-01-01T00:00:01Z [INFO] Job started" in result
        assert "2024-01-01T00:00:05Z [INFO] Scraping page 1" in result
        lines = result.split("\n")
        assert len(lines) == 2

    def test_get_returns_none_on_404(self):
        http = MagicMock()
        http.get.side_effect = APIError(message="Not found", status_code=404)

        client = LogClient(http, "job-missing")
        result = client.get()

        assert result is None

    def test_list_returns_structured_dicts(self):
        http = MagicMock()
        http.get.return_value = MOCK_LOG_RESPONSE

        client = LogClient(http, "job-123")
        result = client.list()

        http.get.assert_called_once_with("/api/v1/jobs/job-123/logs/")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["level"] == "INFO"
        assert result[0]["message"] == "Job started"
        assert result[1]["id"] == 2
        assert result[1]["message"] == "Scraping page 1"

    def test_list_returns_empty_on_404(self):
        http = MagicMock()
        http.get.side_effect = APIError(message="Not found", status_code=404)

        client = LogClient(http, "job-missing")
        result = client.list()

        assert result == []


# ---------------------------------------------------------------------------
# AsyncLogClient
# ---------------------------------------------------------------------------


class TestAsyncLogClient:

    async def test_async_get(self):
        http = AsyncMock()
        http.get.return_value = MOCK_LOG_RESPONSE

        client = AsyncLogClient(http, "job-123")
        result = await client.get()

        http.get.assert_awaited_once_with("/api/v1/jobs/job-123/logs/")
        assert result is not None
        assert "2024-01-01T00:00:01Z [INFO] Job started" in result
        assert "2024-01-01T00:00:05Z [INFO] Scraping page 1" in result
