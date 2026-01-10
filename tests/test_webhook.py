"""Tests for webhook utilities."""

from __future__ import annotations

import pytest

from gofetch import WebhookEventType, verify_webhook_signature, transform_webhook_payload
from gofetch.webhook import generate_webhook_config


class TestWebhookEventType:

    def test_apify_compatible_events(self) -> None:
        assert WebhookEventType.ACTOR_RUN_SUCCEEDED == "ACTOR.RUN.SUCCEEDED"
        assert WebhookEventType.ACTOR_RUN_FAILED == "ACTOR.RUN.FAILED"
        assert WebhookEventType.ACTOR_RUN_TIMED_OUT == "ACTOR.RUN.TIMED_OUT"

    def test_gofetch_native_events(self) -> None:
        assert WebhookEventType.JOB_COMPLETED == "job.completed"
        assert WebhookEventType.JOB_FAILED == "job.failed"


class TestVerifyWebhookSignature:

    def test_valid_signature(self) -> None:
        import hmac
        import hashlib
        payload = b'{"event": "job.completed"}'
        secret = "test-secret"
        expected_sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_webhook_signature(payload, expected_sig, secret) is True

    def test_invalid_signature(self) -> None:
        payload = b'{"event": "job.completed"}'
        assert verify_webhook_signature(payload, "sha256=invalid", "test-secret") is False

    def test_missing_prefix(self) -> None:
        payload = b'{"event": "job.completed"}'
        assert verify_webhook_signature(payload, "abc123", "test-secret") is False

    def test_wrong_secret(self) -> None:
        import hmac
        import hashlib
        payload = b'{"event": "job.completed"}'
        sig = "sha256=" + hmac.new(b"correct", payload, hashlib.sha256).hexdigest()
        assert verify_webhook_signature(payload, sig, "wrong") is False


class TestTransformWebhookPayload:

    def test_transforms_completed_event(self, mock_webhook_payload: dict) -> None:
        result = transform_webhook_payload(mock_webhook_payload)
        assert result["eventType"] == "ACTOR.RUN.SUCCEEDED"
        assert result["resource"]["status"] == "SUCCEEDED"
        assert result["resource"]["id"] == "550e8400-e29b-41d4-a716-446655440000"

    def test_transforms_failed_event(self) -> None:
        payload = {"event": "job.failed", "data": {"job_id": "job123", "status": "failed", "scraper_type": "instagram"}}
        result = transform_webhook_payload(payload)
        assert result["eventType"] == "ACTOR.RUN.FAILED"
        assert result["resource"]["status"] == "FAILED"

    def test_preserves_original_payload(self, mock_webhook_payload: dict) -> None:
        result = transform_webhook_payload(mock_webhook_payload)
        assert "_gofetch_payload" in result
        assert result["_gofetch_payload"] == mock_webhook_payload

    def test_sets_gofetch_user_id(self, mock_webhook_payload: dict) -> None:
        result = transform_webhook_payload(mock_webhook_payload)
        assert result["userId"] == "gofetch"


class TestGenerateWebhookConfig:

    def test_generates_default_events(self) -> None:
        webhooks = generate_webhook_config(base_url="https://api.example.com", scraper_type="instagram_posts")
        assert len(webhooks) == 3
        events = {w["event_types"][0] for w in webhooks}
        assert events == {"ACTOR.RUN.SUCCEEDED", "ACTOR.RUN.FAILED", "ACTOR.RUN.TIMED_OUT"}

    def test_includes_bulk_group_id(self) -> None:
        webhooks = generate_webhook_config(base_url="https://api.example.com", scraper_type="instagram_posts", bulk_group_id="group123")
        for webhook in webhooks:
            assert "group123" in webhook["request_url"]

    def test_includes_social_profile_id(self) -> None:
        webhooks = generate_webhook_config(base_url="https://api.example.com", scraper_type="instagram_posts", social_profile_id=456)
        for webhook in webhooks:
            assert "456" in webhook["request_url"]

    def test_uses_disabled_placeholder_when_no_bulk_group(self) -> None:
        webhooks = generate_webhook_config(base_url="https://api.example.com", scraper_type="instagram_posts")
        for webhook in webhooks:
            assert "bulk_group_id_disabled" in webhook["request_url"]

    def test_uses_none_placeholder_when_no_profile(self) -> None:
        webhooks = generate_webhook_config(base_url="https://api.example.com", scraper_type="instagram_posts")
        for webhook in webhooks:
            assert "/none" in webhook["request_url"]

    def test_strips_trailing_slash_from_base_url(self) -> None:
        webhooks = generate_webhook_config(base_url="https://api.example.com/", scraper_type="instagram_posts")
        for webhook in webhooks:
            assert "api.example.com//" not in webhook["request_url"]
