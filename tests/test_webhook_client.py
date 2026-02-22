"""Tests for webhook client (CRUD operations)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from gofetch.exceptions import APIError
from gofetch.webhook_client import (
    AsyncWebhookClient,
    AsyncWebhookCollectionClient,
    WebhookClient,
    WebhookCollectionClient,
    _format_delivery,
    _format_webhook,
)

# ---------------------------------------------------------------------------
# Fixtures / mock data
# ---------------------------------------------------------------------------

MOCK_GOFETCH_WEBHOOK = {
    "id": "wh-123",
    "url": "https://example.com/hook",
    "events": ["job.completed", "job.failed"],
    "is_active": True,
    "signing_secret": "secret-123",
    "failed_deliveries": 0,
    "last_delivery_at": None,
    "created_at": "2024-01-01T00:00:00Z",
}

MOCK_GOFETCH_DELIVERY = {
    "id": "del-123",
    "webhook": "wh-123",
    "job": "job-456",
    "event_type": "job.completed",
    "trigger_source": "event",
    "status": "delivered",
    "attempts": 1,
    "delivered_at": "2024-01-01T00:00:05Z",
    "created_at": "2024-01-01T00:00:00Z",
}


# ---------------------------------------------------------------------------
# _format_webhook / _format_delivery
# ---------------------------------------------------------------------------


class TestFormatWebhook:

    def test_format_webhook(self):
        result = _format_webhook(MOCK_GOFETCH_WEBHOOK)

        assert result["id"] == "wh-123"
        assert result["requestUrl"] == "https://example.com/hook"
        assert "ACTOR.RUN.SUCCEEDED" in result["eventTypes"]
        assert "ACTOR.RUN.FAILED" in result["eventTypes"]
        assert result["isActive"] is True
        assert result["signingSecret"] == "secret-123"
        assert result["failedDeliveries"] == 0
        assert result["lastDeliveryAt"] is None
        assert result["createdAt"] == "2024-01-01T00:00:00Z"

    def test_format_delivery(self):
        result = _format_delivery(MOCK_GOFETCH_DELIVERY)

        assert result["id"] == "del-123"
        assert result["webhookId"] == "wh-123"
        assert result["jobId"] == "job-456"
        assert result["eventType"] == "ACTOR.RUN.SUCCEEDED"
        assert result["triggerSource"] == "event"
        assert result["status"] == "delivered"
        assert result["attempts"] == 1
        assert result["deliveredAt"] == "2024-01-01T00:00:05Z"
        assert result["createdAt"] == "2024-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# WebhookCollectionClient (sync)
# ---------------------------------------------------------------------------


class TestWebhookCollectionClient:

    def test_list_returns_formatted_items(self):
        http = MagicMock()
        http.get.return_value = {
            "results": [MOCK_GOFETCH_WEBHOOK],
            "count": 1,
            "total": 1,
            "offset": 0,
            "limit": 25,
        }

        client = WebhookCollectionClient(http)
        result = client.list()

        http.get.assert_called_once_with(
            "/api/v1/webhooks/",
            params={"limit": 25, "offset": 0},
        )
        assert len(result["items"]) == 1
        assert result["items"][0]["requestUrl"] == "https://example.com/hook"
        assert result["items"][0]["id"] == "wh-123"
        assert result["count"] == 1
        assert result["total"] == 1

    def test_create_translates_event_types(self):
        http = MagicMock()
        http.post.return_value = MOCK_GOFETCH_WEBHOOK

        client = WebhookCollectionClient(http)
        result = client.create(
            event_types=["ACTOR.RUN.SUCCEEDED", "ACTOR.RUN.FAILED"],
            request_url="https://example.com/hook",
        )

        call_args = http.post.call_args
        assert call_args[0][0] == "/api/v1/webhooks/"
        payload = call_args[1]["json"]
        assert "job.completed" in payload["events"]
        assert "job.failed" in payload["events"]
        assert payload["url"] == "https://example.com/hook"
        assert result["requestUrl"] == "https://example.com/hook"

    def test_create_ignores_apify_params(self):
        http = MagicMock()
        http.post.return_value = MOCK_GOFETCH_WEBHOOK

        client = WebhookCollectionClient(http)
        client.create(
            event_types=["ACTOR.RUN.SUCCEEDED"],
            request_url="https://example.com/hook",
            actor_id="some-actor",
            is_ad_hoc=True,
            idempotency_key="key-123",
        )

        payload = http.post.call_args[1]["json"]
        assert "actor_id" not in payload
        assert "is_ad_hoc" not in payload
        assert "idempotency_key" not in payload


# ---------------------------------------------------------------------------
# WebhookClient (sync)
# ---------------------------------------------------------------------------


class TestWebhookClient:

    def test_get_returns_formatted_webhook(self):
        http = MagicMock()
        http.get.return_value = MOCK_GOFETCH_WEBHOOK

        client = WebhookClient(http, "wh-123")
        result = client.get()

        http.get.assert_called_once_with("/api/v1/webhooks/wh-123/")
        assert result is not None
        assert result["id"] == "wh-123"
        assert result["requestUrl"] == "https://example.com/hook"
        assert "ACTOR.RUN.SUCCEEDED" in result["eventTypes"]

    def test_get_returns_none_on_404(self):
        http = MagicMock()
        http.get.side_effect = APIError(message="Not found", status_code=404)

        client = WebhookClient(http, "wh-missing")
        result = client.get()

        assert result is None

    def test_update_uses_patch(self):
        http = MagicMock()
        updated_webhook = {**MOCK_GOFETCH_WEBHOOK, "url": "https://new.example.com/hook"}
        http.patch.return_value = updated_webhook

        client = WebhookClient(http, "wh-123")
        result = client.update(
            request_url="https://new.example.com/hook",
            event_types=["ACTOR.RUN.SUCCEEDED"],
            is_active=False,
        )

        http.patch.assert_called_once()
        call_args = http.patch.call_args
        assert call_args[0][0] == "/api/v1/webhooks/wh-123/"
        payload = call_args[1]["json"]
        assert payload["url"] == "https://new.example.com/hook"
        assert "job.completed" in payload["events"]
        assert payload["is_active"] is False
        assert result["requestUrl"] == "https://new.example.com/hook"

    def test_delete_returns_none(self):
        http = MagicMock()
        http.delete.return_value = None

        client = WebhookClient(http, "wh-123")
        result = client.delete()

        http.delete.assert_called_once_with("/api/v1/webhooks/wh-123/")
        assert result is None

    def test_delete_silent_on_404(self):
        http = MagicMock()
        http.delete.side_effect = APIError(message="Not found", status_code=404)

        client = WebhookClient(http, "wh-missing")
        # Should NOT raise
        result = client.delete()
        assert result is None

    def test_dispatches_returns_formatted_items(self):
        http = MagicMock()
        http.get.return_value = {
            "results": [MOCK_GOFETCH_DELIVERY],
            "count": 1,
            "total": 1,
            "offset": 0,
            "limit": 25,
        }

        client = WebhookClient(http, "wh-123")
        result = client.dispatches()

        http.get.assert_called_once_with(
            "/api/v1/webhooks/wh-123/deliveries/",
            params={"limit": 25, "offset": 0},
        )
        assert len(result["items"]) == 1
        delivery = result["items"][0]
        assert delivery["id"] == "del-123"
        assert delivery["webhookId"] == "wh-123"
        assert delivery["eventType"] == "ACTOR.RUN.SUCCEEDED"
        assert result["count"] == 1
        assert result["total"] == 1


# ---------------------------------------------------------------------------
# Async variants
# ---------------------------------------------------------------------------


class TestAsyncWebhookClient:

    async def test_async_get(self):
        http = AsyncMock()
        http.get.return_value = MOCK_GOFETCH_WEBHOOK

        client = AsyncWebhookClient(http, "wh-123")
        result = await client.get()

        http.get.assert_awaited_once_with("/api/v1/webhooks/wh-123/")
        assert result is not None
        assert result["id"] == "wh-123"
        assert result["requestUrl"] == "https://example.com/hook"

    async def test_async_create(self):
        http = AsyncMock()
        http.post.return_value = MOCK_GOFETCH_WEBHOOK

        client = AsyncWebhookCollectionClient(http)
        result = await client.create(
            event_types=["ACTOR.RUN.SUCCEEDED"],
            request_url="https://example.com/hook",
        )

        http.post.assert_awaited_once()
        payload = http.post.call_args[1]["json"]
        assert "job.completed" in payload["events"]
        assert result["requestUrl"] == "https://example.com/hook"
