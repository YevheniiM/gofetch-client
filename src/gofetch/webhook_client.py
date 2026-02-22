"""Webhook client for GoFetch API.

Provides Apify-compatible interface for webhook CRUD operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gofetch.exceptions import APIError
from gofetch.webhook import APIFY_TO_GOFETCH_EVENTS, GOFETCH_TO_APIFY_EVENTS

if TYPE_CHECKING:
    import builtins

    from gofetch.http import AsyncHTTPClient, HTTPClient


def _format_webhook(data: dict[str, Any]) -> dict[str, Any]:
    """Convert GoFetch webhook response to Apify-compatible format."""
    gofetch_events = data.get("events", [])
    apify_events = [
        GOFETCH_TO_APIFY_EVENTS.get(e, e) for e in gofetch_events
    ]
    return {
        "id": data.get("id"),
        "requestUrl": data.get("url"),
        "eventTypes": apify_events,
        "isActive": data.get("is_active"),
        "signingSecret": data.get("signing_secret"),
        "failedDeliveries": data.get("failed_deliveries"),
        "lastDeliveryAt": data.get("last_delivery_at"),
        "createdAt": data.get("created_at"),
    }


def _format_delivery(data: dict[str, Any]) -> dict[str, Any]:
    """Convert GoFetch delivery response to Apify-compatible format."""
    gofetch_event = data.get("event_type", "")
    apify_event = GOFETCH_TO_APIFY_EVENTS.get(gofetch_event, gofetch_event)
    return {
        "id": data.get("id"),
        "webhookId": data.get("webhook"),
        "jobId": data.get("job"),
        "eventType": apify_event,
        "triggerSource": data.get("trigger_source"),
        "status": data.get("status"),
        "attempts": data.get("attempts"),
        "deliveredAt": data.get("delivered_at"),
        "createdAt": data.get("created_at"),
    }


class WebhookCollectionClient:
    """Webhook collection client for listing and creating webhooks."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def list(self, *, limit: int = 25, offset: int = 0) -> dict[str, Any]:
        """List webhooks."""
        response = self._http.get(
            "/api/v1/webhooks/",
            params={"limit": limit, "offset": offset},
        )
        results = response.get("results", response.get("items", []))
        return {
            "items": [_format_webhook(w) for w in results],
            "count": len(results),
            "offset": offset,
            "limit": limit,
            "total": response.get("total", response.get("count", len(results))),
        }

    def create(
        self,
        *,
        event_types: builtins.list[str],
        request_url: str,
        is_active: bool = True,
        actor_id: str | None = None,
        actor_task_id: str | None = None,
        actor_run_id: str | None = None,
        is_ad_hoc: bool | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a webhook."""
        _ = actor_id, actor_task_id, actor_run_id, is_ad_hoc, idempotency_key

        gofetch_events = [
            APIFY_TO_GOFETCH_EVENTS.get(et, et) for et in event_types
        ]
        payload: dict[str, Any] = {
            "url": request_url,
            "events": gofetch_events,
            "is_active": is_active,
        }
        response = self._http.post("/api/v1/webhooks/", json=payload)
        return _format_webhook(response)


class WebhookClient:
    """Webhook client for individual webhook operations."""

    def __init__(self, http: HTTPClient, webhook_id: str) -> None:
        self._http = http
        self._webhook_id = webhook_id

    def get(self) -> dict[str, Any] | None:
        """Get webhook by ID. Returns None if not found."""
        try:
            response = self._http.get(f"/api/v1/webhooks/{self._webhook_id}/")
        except APIError as e:
            if e.status_code == 404:
                return None
            raise
        return _format_webhook(response)

    def update(self, **kwargs: Any) -> dict[str, Any]:
        """Update webhook fields."""
        payload: dict[str, Any] = {}

        if "event_types" in kwargs:
            payload["events"] = [
                APIFY_TO_GOFETCH_EVENTS.get(et, et)
                for et in kwargs["event_types"]
            ]
        if "request_url" in kwargs:
            payload["url"] = kwargs["request_url"]
        if "is_active" in kwargs:
            payload["is_active"] = kwargs["is_active"]

        response = self._http.patch(
            f"/api/v1/webhooks/{self._webhook_id}/",
            json=payload,
        )
        return _format_webhook(response)

    def delete(self) -> None:
        """Delete webhook. Idempotent (silent on 404)."""
        try:
            self._http.delete(f"/api/v1/webhooks/{self._webhook_id}/")
        except APIError as e:
            if e.status_code == 404:
                return
            raise

    def dispatches(self, *, limit: int = 25, offset: int = 0) -> dict[str, Any]:
        """List webhook deliveries."""
        response = self._http.get(
            f"/api/v1/webhooks/{self._webhook_id}/deliveries/",
            params={"limit": limit, "offset": offset},
        )
        results = response.get("results", response.get("items", []))
        return {
            "items": [_format_delivery(d) for d in results],
            "count": len(results),
            "offset": offset,
            "limit": limit,
            "total": response.get("total", response.get("count", len(results))),
        }


class AsyncWebhookCollectionClient:
    """Async webhook collection client for listing and creating webhooks."""

    def __init__(self, http: AsyncHTTPClient) -> None:
        self._http = http

    async def list(self, *, limit: int = 25, offset: int = 0) -> dict[str, Any]:
        """List webhooks."""
        response = await self._http.get(
            "/api/v1/webhooks/",
            params={"limit": limit, "offset": offset},
        )
        results = response.get("results", response.get("items", []))
        return {
            "items": [_format_webhook(w) for w in results],
            "count": len(results),
            "offset": offset,
            "limit": limit,
            "total": response.get("total", response.get("count", len(results))),
        }

    async def create(
        self,
        *,
        event_types: builtins.list[str],
        request_url: str,
        is_active: bool = True,
        actor_id: str | None = None,
        actor_task_id: str | None = None,
        actor_run_id: str | None = None,
        is_ad_hoc: bool | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a webhook."""
        _ = actor_id, actor_task_id, actor_run_id, is_ad_hoc, idempotency_key

        gofetch_events = [
            APIFY_TO_GOFETCH_EVENTS.get(et, et) for et in event_types
        ]
        payload: dict[str, Any] = {
            "url": request_url,
            "events": gofetch_events,
            "is_active": is_active,
        }
        response = await self._http.post("/api/v1/webhooks/", json=payload)
        return _format_webhook(response)


class AsyncWebhookClient:
    """Async webhook client for individual webhook operations."""

    def __init__(self, http: AsyncHTTPClient, webhook_id: str) -> None:
        self._http = http
        self._webhook_id = webhook_id

    async def get(self) -> dict[str, Any] | None:
        """Get webhook by ID. Returns None if not found."""
        try:
            response = await self._http.get(
                f"/api/v1/webhooks/{self._webhook_id}/"
            )
        except APIError as e:
            if e.status_code == 404:
                return None
            raise
        return _format_webhook(response)

    async def update(self, **kwargs: Any) -> dict[str, Any]:
        """Update webhook fields."""
        payload: dict[str, Any] = {}

        if "event_types" in kwargs:
            payload["events"] = [
                APIFY_TO_GOFETCH_EVENTS.get(et, et)
                for et in kwargs["event_types"]
            ]
        if "request_url" in kwargs:
            payload["url"] = kwargs["request_url"]
        if "is_active" in kwargs:
            payload["is_active"] = kwargs["is_active"]

        response = await self._http.patch(
            f"/api/v1/webhooks/{self._webhook_id}/",
            json=payload,
        )
        return _format_webhook(response)

    async def delete(self) -> None:
        """Delete webhook. Idempotent (silent on 404)."""
        try:
            await self._http.delete(f"/api/v1/webhooks/{self._webhook_id}/")
        except APIError as e:
            if e.status_code == 404:
                return
            raise

    async def dispatches(
        self, *, limit: int = 25, offset: int = 0
    ) -> dict[str, Any]:
        """List webhook deliveries."""
        response = await self._http.get(
            f"/api/v1/webhooks/{self._webhook_id}/deliveries/",
            params={"limit": limit, "offset": offset},
        )
        results = response.get("results", response.get("items", []))
        return {
            "items": [_format_delivery(d) for d in results],
            "count": len(results),
            "offset": offset,
            "limit": limit,
            "total": response.get("total", response.get("count", len(results))),
        }
