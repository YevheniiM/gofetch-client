"""Pytest configuration and fixtures."""

from __future__ import annotations

import os
from typing import Any, Generator

import pytest

from gofetch import GoFetchClient


@pytest.fixture
def api_key() -> str:
    return os.environ.get("GOFETCH_API_KEY", "sk_scr_test_xxxxxxxxxxxx")


@pytest.fixture
def base_url() -> str:
    return os.environ.get("GOFETCH_BASE_URL", "https://api.go-fetch.io")


@pytest.fixture
def client(api_key: str, base_url: str) -> Generator[GoFetchClient, None, None]:
    client = GoFetchClient(api_key=api_key, base_url=base_url)
    yield client
    client.close()


@pytest.fixture
def mock_webhook_payload() -> dict[str, Any]:
    return {
        "event": "job.completed",
        "timestamp": "2024-01-01T00:10:00Z",
        "data": {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "organization_id": "org123",
            "scraper_type": "instagram",
            "status": "completed",
            "items_scraped": 10,
            "output_dataset_url": "https://s3.amazonaws.com/...",
            "started_at": "2024-01-01T00:00:01Z",
            "completed_at": "2024-01-01T00:10:00Z",
        },
    }
