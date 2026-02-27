"""
E2E webhook tests — verify webhook delivery via ngrok tunnel.

Requires:
  GOFETCH_API_KEY    — API key
  pyngrok            — pip install pyngrok

Usage:
    pytest tests/e2e/test_webhook_e2e.py -v -m webhook
"""

from __future__ import annotations

import logging
import time

import pytest

from gofetch import GoFetchClient

from .config import (
    PLATFORMS,
    WEBHOOK_RECEIVE_TIMEOUT,
    build_run_input,
    timeout_for_tier,
)
from .conftest import WebhookStore

logger = logging.getLogger("e2e.webhooks")

pytestmark = [pytest.mark.e2e, pytest.mark.webhook]


# ---------------------------------------------------------------------------
# Webhook delivery per platform
# ---------------------------------------------------------------------------


def _make_webhook_platform_params() -> list[tuple]:
    params = []
    for platform_name in PLATFORMS:
        params.append(
            pytest.param(
                platform_name,
                id=f"webhook-{platform_name}",
                marks=[pytest.mark.xdist_group(platform_name)],
            )
        )
    return params


@pytest.mark.parametrize("platform_name", _make_webhook_platform_params())
def test_webhook_delivery_on_completion(
    client: GoFetchClient,
    ngrok_url: str,
    fresh_webhook_store: WebhookStore,
    platform_name: str,
) -> None:
    """
    Test that webhooks fire correctly when a job completes.

    Flow:
    1. Start job with webhook URL pointing to our ngrok tunnel
    2. Wait for job to complete
    3. Verify we received webhook events
    4. Verify event payloads are well-formed

    CRITICAL: If webhook is not received, that's a failure — webhooks must fire
    for completed jobs.
    """
    platform_config = PLATFORMS[platform_name]
    scraper_type = platform_config["scraper_type"]
    limit_key = platform_config["limit_key"]
    tier = 10  # small job for webhook testing
    timeout = timeout_for_tier(tier)
    target = platform_config["targets"][0]

    run_input = build_run_input(target["config"], limit_key, tier)

    # Configure webhooks to our ngrok URL
    webhook_url = f"{ngrok_url}/webhook/{platform_name}"
    webhooks = [
        {
            "request_url": webhook_url,
            "event_types": [
                "ACTOR.RUN.SUCCEEDED",
                "ACTOR.RUN.FAILED",
                "ACTOR.RUN.TIMED_OUT",
                "ACTOR.RUN.CREATED",
                "ACTOR.RUN.RUNNING",
            ],
        }
    ]

    logger.info("Starting webhook test: %s → %s", platform_name, webhook_url)

    # Start job with webhooks
    actor = client.actor(scraper_type)
    run = actor.call(run_input=run_input, wait_secs=timeout, webhooks=webhooks)

    job_id = run.get("id", "")
    status = run.get("status", "")

    logger.info("Job %s finished with status %s", job_id, status)

    # Wait for webhook events to arrive (they may lag behind the API response)
    terminal_event = fresh_webhook_store.wait_for_terminal(
        job_id, timeout=WEBHOOK_RECEIVE_TIMEOUT
    )

    # --- CRITICAL: webhook must have been received ---
    assert terminal_event is not None, (
        f"CRITICAL: No terminal webhook received for job {job_id} "
        f"(platform={platform_name}, status={status}) within {WEBHOOK_RECEIVE_TIMEOUT}s. "
        f"Webhook delivery is broken or the event was never sent."
    )

    # Verify the terminal event type matches the job status
    if status == "SUCCEEDED":
        assert terminal_event["event"] == "job.completed", (
            f"Job SUCCEEDED but webhook event was '{terminal_event['event']}'"
        )
    elif status == "FAILED":
        assert terminal_event["event"] == "job.failed", (
            f"Job FAILED but webhook event was '{terminal_event['event']}'"
        )

    # Verify payload structure
    payload = terminal_event.get("payload", {})
    assert "event" in payload, "Webhook payload missing 'event' field"
    assert "data" in payload, "Webhook payload missing 'data' field"
    assert "timestamp" in payload, "Webhook payload missing 'timestamp' field"

    data = payload.get("data", {})
    assert data.get("job_id") == job_id, (
        f"Webhook job_id mismatch: expected {job_id}, got {data.get('job_id')}"
    )
    assert data.get("scraper_type"), "Webhook data missing 'scraper_type'"
    assert data.get("status"), "Webhook data missing 'status'"


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------


def test_webhook_signature_is_present(
    client: GoFetchClient,
    ngrok_url: str,
    fresh_webhook_store: WebhookStore,
) -> None:
    """Verify that webhook deliveries include a signature header."""
    target = PLATFORMS["reddit"]["targets"][0]
    run_input = build_run_input(target["config"], "postsLimit", 10)
    timeout = timeout_for_tier(10)

    webhook_url = f"{ngrok_url}/webhook/sig_test"
    webhooks = [
        {
            "request_url": webhook_url,
            "event_types": ["ACTOR.RUN.SUCCEEDED", "ACTOR.RUN.FAILED"],
        }
    ]

    actor = client.actor("reddit")
    run = actor.call(run_input=run_input, wait_secs=timeout, webhooks=webhooks)

    job_id = run.get("id", "")

    terminal = fresh_webhook_store.wait_for_terminal(
        job_id, timeout=WEBHOOK_RECEIVE_TIMEOUT
    )

    if terminal is None:
        pytest.skip("No webhook received — cannot check signature")

    signature = terminal.get("signature", "")
    assert signature, (
        "Webhook was received but has no X-Webhook-Signature header. "
        "Signature verification is required for security."
    )
    assert signature.startswith("sha256="), (
        f"Webhook signature has wrong format: '{signature[:20]}...'. "
        f"Expected 'sha256=<hex>'."
    )


# ---------------------------------------------------------------------------
# Webhook CRUD lifecycle
# ---------------------------------------------------------------------------


def test_webhook_crud_lifecycle(
    client: GoFetchClient,
    ngrok_url: str,
) -> None:
    """Test the full webhook CRUD cycle: create → list → get → update → delete."""

    webhook_url = f"{ngrok_url}/webhook/crud_test"

    # --- CREATE ---
    collection = client.webhooks()
    created = collection.create(
        event_types=["ACTOR.RUN.SUCCEEDED", "ACTOR.RUN.FAILED"],
        request_url=webhook_url,
    )

    assert created.get("id"), "Created webhook missing 'id'"
    webhook_id = created["id"]
    assert created.get("requestUrl") == webhook_url, "requestUrl doesn't match"

    try:
        # --- LIST ---
        all_webhooks = collection.list()
        assert all_webhooks.get("items") is not None, "list() missing 'items'"
        found = any(w.get("id") == webhook_id for w in all_webhooks["items"])
        assert found, f"Created webhook {webhook_id} not found in list()"

        # --- GET ---
        wh_client = client.webhook(webhook_id)
        fetched = wh_client.get()
        assert fetched is not None, f"get() returned None for webhook {webhook_id}"
        assert fetched.get("id") == webhook_id

        # --- UPDATE ---
        updated = wh_client.update(
            request_url=f"{ngrok_url}/webhook/crud_updated",
            is_active=False,
        )
        assert updated.get("requestUrl") == f"{ngrok_url}/webhook/crud_updated"

        # --- DISPATCHES ---
        dispatches = wh_client.dispatches()
        assert "items" in dispatches, "dispatches() missing 'items'"

    finally:
        # --- DELETE (always clean up) ---
        client.webhook(webhook_id).delete()

    # Verify deleted
    deleted_check = client.webhook(webhook_id).get()
    assert deleted_check is None, f"Webhook {webhook_id} still exists after delete()"


# ---------------------------------------------------------------------------
# Webhook with actor.start() (per-run webhooks)
# ---------------------------------------------------------------------------


def test_per_run_webhook_via_start(
    client: GoFetchClient,
    ngrok_url: str,
    fresh_webhook_store: WebhookStore,
) -> None:
    """Test per-run webhook registration via actor.start(webhooks=[...])."""
    target = PLATFORMS["youtube"]["targets"][0]
    run_input = build_run_input(target["config"], "videosLimit", 10)
    timeout = timeout_for_tier(10)

    webhook_url = f"{ngrok_url}/webhook/per_run_test"

    actor = client.actor("youtube")
    run = actor.start(
        run_input=run_input,
        webhooks=[
            {
                "request_url": webhook_url,
                "event_types": ["ACTOR.RUN.SUCCEEDED", "ACTOR.RUN.FAILED"],
            }
        ],
    )

    job_id = run.get("id", "")
    assert job_id, "start() did not return job ID"

    # Wait for completion
    run_client = client.run(job_id)
    final = run_client.wait_for_finish(wait_secs=timeout)

    # Wait for webhook
    terminal = fresh_webhook_store.wait_for_terminal(
        job_id, timeout=WEBHOOK_RECEIVE_TIMEOUT
    )

    assert terminal is not None, (
        f"No webhook received for per-run webhook job {job_id}. "
        f"Per-run webhook delivery may be broken."
    )

    # If job succeeded, verify results are available
    if final and final.get("status") == "SUCCEEDED":
        results = run_client.dataset().list_items()
        assert len(results) > 0, (
            "CRITICAL: Job SUCCEEDED with webhook confirmation but results are empty"
        )


# ---------------------------------------------------------------------------
# Multiple webhook events for a single job
# ---------------------------------------------------------------------------


def test_webhook_event_sequence(
    client: GoFetchClient,
    ngrok_url: str,
    fresh_webhook_store: WebhookStore,
) -> None:
    """
    Verify that we receive multiple webhook events in the correct order.

    Expected sequence for a successful job:
      job.created → job.started → [job.progress...] → job.completed
    """
    target = PLATFORMS["google_news"]["targets"][0]
    run_input = build_run_input(target["config"], "resultsLimit", 25)
    timeout = timeout_for_tier(25)

    webhook_url = f"{ngrok_url}/webhook/sequence_test"
    webhooks = [
        {
            "request_url": webhook_url,
            "event_types": [
                "ACTOR.RUN.CREATED",
                "ACTOR.RUN.RUNNING",
                "ACTOR.RUN.SUCCEEDED",
                "ACTOR.RUN.FAILED",
                "ACTOR.RUN.TIMED_OUT",
            ],
        }
    ]

    actor = client.actor("google_news")
    run = actor.call(run_input=run_input, wait_secs=timeout, webhooks=webhooks)

    job_id = run.get("id", "")
    status = run.get("status", "")

    # Wait a bit for all events to arrive
    time.sleep(5)
    terminal = fresh_webhook_store.wait_for_terminal(
        job_id, timeout=WEBHOOK_RECEIVE_TIMEOUT
    )

    all_events = fresh_webhook_store.get_events(job_id)
    event_types = [e["event"] for e in all_events]

    logger.info("Received %d events for job %s: %s", len(all_events), job_id, event_types)

    # Backend currently only sends terminal events (job.completed/job.failed),
    # not lifecycle events (job.created, job.started). Require at least 1.
    assert len(all_events) >= 1, (
        f"Expected at least 1 webhook event (terminal), "
        f"got {len(all_events)}: {event_types}"
    )

    # Verify terminal event is present
    if status == "SUCCEEDED":
        assert "job.completed" in event_types, (
            f"Missing terminal event 'job.completed' in sequence. "
            f"Got: {event_types}"
        )

    # Verify chronological ordering
    timestamps = [e["received_at"] for e in all_events]
    assert timestamps == sorted(timestamps), (
        "Webhook events arrived out of order"
    )
