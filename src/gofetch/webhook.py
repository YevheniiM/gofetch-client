"""
Webhook utilities for GoFetch.

Provides:
- Webhook signature verification
- Payload transformation between GoFetch and Apify formats
- Webhook event type constants
"""

from __future__ import annotations

import hashlib
import hmac
from enum import Enum
from typing import Any


class WebhookEventType(str, Enum):
    """
    Webhook event types.

    Compatible with apify_shared.consts.WebhookEventType for drop-in replacement.

    Usage:
        from gofetch import WebhookEventType

        if event_type == WebhookEventType.ACTOR_RUN_SUCCEEDED:
            process_success()
    """

    # Apify-compatible events
    ACTOR_RUN_CREATED = "ACTOR.RUN.CREATED"
    ACTOR_RUN_SUCCEEDED = "ACTOR.RUN.SUCCEEDED"
    ACTOR_RUN_FAILED = "ACTOR.RUN.FAILED"
    ACTOR_RUN_TIMED_OUT = "ACTOR.RUN.TIMED_OUT"
    ACTOR_RUN_ABORTED = "ACTOR.RUN.ABORTED"
    ACTOR_RUN_RUNNING = "ACTOR.RUN.RUNNING"

    # GoFetch native events (for direct usage)
    JOB_CREATED = "job.created"
    JOB_STARTED = "job.started"
    JOB_PROGRESS = "job.progress"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_TIMED_OUT = "job.timed_out"
    JOB_CANCELLED = "job.cancelled"


# Mapping between GoFetch events and Apify events
GOFETCH_TO_APIFY_EVENTS: dict[str, str] = {
    "job.created": "ACTOR.RUN.CREATED",
    "job.started": "ACTOR.RUN.RUNNING",
    "job.progress": "ACTOR.RUN.RUNNING",
    "job.completed": "ACTOR.RUN.SUCCEEDED",
    "job.failed": "ACTOR.RUN.FAILED",
    "job.timed_out": "ACTOR.RUN.TIMED_OUT",
    "job.cancelled": "ACTOR.RUN.ABORTED",
}

# Manually defined reverse mapping (NOT auto-generated) because
# job.started and job.progress both map to ACTOR.RUN.RUNNING —
# auto-reversing would lose one of them.
APIFY_TO_GOFETCH_EVENTS: dict[str, str] = {
    "ACTOR.RUN.CREATED": "job.created",
    "ACTOR.RUN.RUNNING": "job.started",
    "ACTOR.RUN.SUCCEEDED": "job.completed",
    "ACTOR.RUN.FAILED": "job.failed",
    "ACTOR.RUN.TIMED_OUT": "job.timed_out",
    "ACTOR.RUN.ABORTED": "job.cancelled",
}


def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str,
) -> bool:
    """
    Verify webhook signature from GoFetch.

    GoFetch signs webhook payloads using HMAC-SHA256. Use this function
    to verify that webhooks are authentic.

    Args:
        payload: Raw request body bytes
        signature: X-Webhook-Signature header value (format: "sha256=...")
        secret: Webhook secret from your GoFetch organization settings

    Returns:
        True if signature is valid, False otherwise

    Example:
        # In your webhook handler (Django example)
        def webhook_view(request):
            payload = request.body
            signature = request.headers.get("X-Webhook-Signature", "")
            secret = settings.GOFETCH_WEBHOOK_SECRET

            if not verify_webhook_signature(payload, signature, secret):
                return HttpResponse("Invalid signature", status=401)

            # Process webhook...
    """
    if not signature.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


def transform_webhook_payload(
    gofetch_payload: dict[str, Any],
    event_type: str | None = None,
) -> dict[str, Any]:
    """
    Transform GoFetch webhook payload to Apify-compatible format.

    Use this function to maintain compatibility with code expecting
    Apify webhook payloads.

    GoFetch format (what the API sends):
        {
            "resource": {
                "id": "...",
                "status": "SUCCEEDED",
                "defaultDatasetId": "...",
                "usageTotalUsd": 0.42  # absent from older servers
            }
        }

    Legacy format (still accepted):
        {
            "event": "job.completed",
            "timestamp": "2024-01-01T00:00:00Z",
            "data": {
                "job_id": "...",
                "organization_id": "...",
                "scraper_type": "instagram",
                "status": "completed",
                "items_scraped": 100,
                "output_dataset_url": "https://..."
            }
        }

    Apify format (output):
        {
            "userId": "gofetch",
            "eventType": "ACTOR.RUN.SUCCEEDED",
            "eventData": {
                "actorId": "instagram",
                "actorRunId": "..."
            },
            "resource": {
                "id": "...",
                "actId": "instagram",
                "status": "SUCCEEDED",
                "defaultDatasetId": "...",
                "usageTotalUsd": 0.42  # None when the server did not send it
            },
            "defaultDatasetId": "...",
            "_gofetch_payload": {...}  # Original payload
        }

    Args:
        gofetch_payload: Raw webhook payload from GoFetch
        event_type: X-Event-Type header value (e.g. "job.completed"). The
            body carries no event, so without it the event is derived from
            ``resource.status``.

    Returns:
        Transformed payload in Apify format

    Example:
        # In your webhook handler
        payload = json.loads(request.body)
        apify_payload = transform_webhook_payload(
            payload, request.headers.get("X-Event-Type")
        )

        # Now you can use it with existing Apify-style processing
        if apify_payload["eventType"] == "ACTOR.RUN.SUCCEEDED":
            dataset_id = apify_payload["resource"]["defaultDatasetId"]
            cost = apify_payload["resource"]["usageTotalUsd"]
            # Fetch results...
    """
    # Deferred: gofetch.actor imports this module.
    from gofetch.actor import _usd

    data = gofetch_payload.get("data", {})
    resource = gofetch_payload.get("resource")
    if isinstance(resource, dict):
        # The status is already Apify's; the body has no actor or timings.
        job_id = resource.get("id")
        status = resource.get("status") or "RUNNING"
        event = event_type or "ACTOR.RUN." + status.replace("-", "_")
        dataset_id = resource.get("defaultDatasetId") or job_id
        usage_total_usd = _usd(resource.get("usageTotalUsd"))
    else:
        status_map = {
            "pending": "READY",
            "running": "RUNNING",
            "completed": "SUCCEEDED",
            "failed": "FAILED",
            "timed_out": "TIMED-OUT",
            "cancelled": "ABORTED",
        }
        job_id = data.get("job_id")
        status = status_map.get(data.get("status", ""), data.get("status", "RUNNING"))
        event = event_type or gofetch_payload.get("event", "")
        dataset_id = job_id
        usage_total_usd = None

    return {
        "userId": "gofetch",
        "eventType": GOFETCH_TO_APIFY_EVENTS.get(event, event),
        "eventData": {
            "actorId": data.get("scraper_type"),
            "actorRunId": job_id,
        },
        "resource": {
            "id": job_id,
            "actId": data.get("scraper_type"),
            "userId": "gofetch",
            "status": status,
            "defaultDatasetId": dataset_id,
            "startedAt": data.get("started_at"),
            "finishedAt": data.get("completed_at"),
            "usageTotalUsd": usage_total_usd,
        },
        "defaultDatasetId": dataset_id,
        # Keep original payload for reference
        "_gofetch_payload": gofetch_payload,
    }


def generate_webhook_config(
    base_url: str,
    scraper_type: str,
    bulk_group_id: str | None = None,
    social_profile_id: int | str | None = None,
    events: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate webhook configurations for VWD-style webhook URLs.

    This function generates webhook configs in the format expected by
    the VWD backend's existing webhook system.

    Args:
        base_url: Base URL for webhooks (e.g., "https://api.vwd.ai")
        scraper_type: Scraper type (e.g., "instagram_posts")
        bulk_group_id: Optional bulk group ID
        social_profile_id: Optional social profile ID
        events: List of event types (default: succeeded, failed, timed_out)

    Returns:
        List of webhook configurations

    Example:
        webhooks = generate_webhook_config(
            base_url="https://api.vwd.ai",
            scraper_type="instagram_posts",
            bulk_group_id="group123",
            social_profile_id=456
        )
        # Returns:
        # [
        #     {"request_url": "https://api.vwd.ai/apify/webhook/instagram_posts/succeeded/group123/456", "event_types": ["ACTOR.RUN.SUCCEEDED"]},
        #     {"request_url": "https://api.vwd.ai/apify/webhook/instagram_posts/failed/group123/456", "event_types": ["ACTOR.RUN.FAILED"]},
        #     {"request_url": "https://api.vwd.ai/apify/webhook/instagram_posts/timed_out/group123/456", "event_types": ["ACTOR.RUN.TIMED_OUT"]},
        # ]
    """
    if events is None:
        events = ["succeeded", "failed", "timed_out"]

    base_url = base_url.rstrip("/")
    bulk_id = bulk_group_id or "bulk_group_id_disabled"
    profile_id = str(social_profile_id) if social_profile_id else "none"

    event_type_map = {
        "succeeded": "ACTOR.RUN.SUCCEEDED",
        "failed": "ACTOR.RUN.FAILED",
        "timed_out": "ACTOR.RUN.TIMED_OUT",
    }

    webhooks = []
    for event in events:
        path = f"/apify/webhook/{scraper_type}/{event}/{bulk_id}/{profile_id}"
        webhooks.append({
            "request_url": f"{base_url}{path}",
            "event_types": [event_type_map.get(event, f"ACTOR.RUN.{event.upper()}")],
        })

    return webhooks
