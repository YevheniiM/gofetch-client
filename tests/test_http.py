"""Tests for HTTP client and error handling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gofetch.exceptions import (
    APIError,
    AuthenticationError,
    BatchExpiredError,
    DatasetConflictError,
    GoFetchError,
    InsufficientCreditsError,
    RateLimitError,
)
from gofetch.http import HTTPClient, _handle_error_response


def _response(status_code, body=None, *, text=None, headers=None):
    """A MagicMock shaped like the httpx.Response the parser reads."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    if body is None:
        response.json.side_effect = ValueError("Bad JSON")
        response.text = text
    else:
        response.json.return_value = body
    return response


# ---------------------------------------------------------------------------
# _handle_error_response tests
# ---------------------------------------------------------------------------


class TestHandleErrorResponse:
    """Tests for the standalone _handle_error_response function."""

    def test_401_raises_authentication_error(self) -> None:
        """A 401 response raises AuthenticationError."""
        response = MagicMock()
        response.status_code = 401
        response.json.return_value = {"message": "Unauthorized"}
        response.headers = {}

        with pytest.raises(AuthenticationError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.status_code == 401
        assert "Unauthorized" in str(exc_info.value.message)

    def test_429_raises_rate_limit_error(self) -> None:
        """A 429 response raises RateLimitError."""
        response = MagicMock()
        response.status_code = 429
        response.json.return_value = {"message": "Rate limit exceeded"}
        response.headers = {}

        with pytest.raises(RateLimitError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.status_code == 429

    def test_429_with_retry_after_header(self) -> None:
        """A 429 response with Retry-After header populates retry_after."""
        response = MagicMock()
        response.status_code = 429
        response.json.return_value = {"message": "Rate limit exceeded"}
        response.headers = {"Retry-After": "30"}

        with pytest.raises(RateLimitError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.retry_after == 30

    def test_429_with_retry_after_in_body(self) -> None:
        """A 429 response with retry_after in JSON body populates retry_after."""
        response = MagicMock()
        response.status_code = 429
        response.json.return_value = {"message": "Rate limit exceeded", "retry_after": 45}
        response.headers = {}

        with pytest.raises(RateLimitError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.retry_after == 45

    def test_other_status_raises_api_error(self) -> None:
        """A non-401/429 error raises generic APIError."""
        response = MagicMock()
        response.status_code = 500
        response.json.return_value = {"message": "Internal server error"}
        response.headers = {}

        with pytest.raises(APIError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.status_code == 500

    def test_400_raises_api_error(self) -> None:
        """A 400 response raises APIError (not a specialized subclass)."""
        response = MagicMock()
        response.status_code = 400
        response.json.return_value = {"message": "Bad request", "error": "validation_error"}
        response.headers = {}

        with pytest.raises(APIError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.status_code == 400
        assert exc_info.value.error_code == "validation_error"

    def test_403_raises_api_error(self) -> None:
        """A 403 response raises APIError (not AuthenticationError)."""
        response = MagicMock()
        response.status_code = 403
        response.json.return_value = {"message": "Forbidden"}
        response.headers = {}

        with pytest.raises(APIError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.status_code == 403
        # Verify it is NOT an AuthenticationError
        assert not isinstance(exc_info.value, AuthenticationError)

    def test_json_parse_failure_uses_text(self) -> None:
        """When response.json() fails, error message falls back to response.text."""
        response = MagicMock()
        response.status_code = 502
        response.json.side_effect = ValueError("Bad JSON")
        response.text = "Bad Gateway"
        response.headers = {}

        with pytest.raises(APIError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.status_code == 502
        assert "Bad Gateway" in exc_info.value.message

    def test_details_are_captured(self) -> None:
        """Error details from the response body are captured on the exception."""
        response = MagicMock()
        response.status_code = 422
        response.json.return_value = {
            "message": "Validation failed",
            "details": {"field": "config.urls", "reason": "required"},
        }
        response.headers = {}

        with pytest.raises(APIError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.details == {"field": "config.urls", "reason": "required"}


# ---------------------------------------------------------------------------
# Datasets error bodies (real payloads from dev, 2026-09-06)
# ---------------------------------------------------------------------------


class TestDatasetErrorBodies:
    """The datasets API answers with `detail` and `errors.code`, never `message`."""

    def test_detail_is_read_as_the_message(self) -> None:
        """A body carrying only `detail` used to render as 'Unknown error'."""
        response = _response(401, {"detail": "Invalid or expired API key"})

        with pytest.raises(AuthenticationError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.message == "Invalid or expired API key"

    def test_error_code_comes_from_errors_code(self) -> None:
        response = _response(
            400,
            {
                "detail": "Idempotency-Key is required: send a header unique to this download.",
                "errors": {"code": "idempotency_key_required"},
                "quote": {"items": {"new": 0}, "amount": "0.0000"},
            },
        )

        with pytest.raises(APIError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.error_code == "idempotency_key_required"
        assert exc_info.value.details["quote"]["amount"] == "0.0000"

    def test_field_errors_are_not_mistaken_for_a_code(self) -> None:
        """`errors` also holds {field: [messages]}; only a string `code` counts."""
        response = _response(
            400,
            {
                "detail": "limit must be a positive integer, got 0.",
                "message": "limit must be a positive integer, got 0.",
                "errors": {"limit": "limit must be a positive integer, got 0."},
            },
        )

        with pytest.raises(APIError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.error_code is None
        assert "positive integer" in exc_info.value.message

    def test_list_body_does_not_crash(self) -> None:
        """`raise ValidationError('<string>')` renders as a bare JSON list.

        Reading keys off it raised AttributeError, which escaped every
        `except GoFetchError` a caller wrote.
        """
        response = _response(400, ["Could not open a batch; retry the pull."])

        with pytest.raises(GoFetchError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.message == "Could not open a batch; retry the pull."

    def test_html_body_is_truncated(self) -> None:
        """A non-uuid export id never reaches the app and 404s as an HTML page."""
        response = _response(404, None, text="<!doctype html>" + "x" * 5000)

        with pytest.raises(APIError) as exc_info:
            _handle_error_response(response)

        assert len(exc_info.value.message) <= 210
        assert exc_info.value.message.endswith("...")

    def test_402_raises_insufficient_credits_with_constraints(self) -> None:
        response = _response(
            402,
            {
                "detail": "This download costs $15.0000 and your balance is $2.0000.",
                "constraints": [
                    {
                        "code": "insufficient_credits",
                        "message": "This download costs $15.0000 and your balance is $2.0000.",
                    }
                ],
            },
        )

        with pytest.raises(InsufficientCreditsError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.status_code == 402
        assert exc_info.value.constraints[0]["code"] == "insufficient_credits"

    def test_409_raises_dataset_conflict_with_quote(self) -> None:
        response = _response(
            409,
            {
                "detail": "The number of new items changed since you were quoted.",
                "errors": {"code": "quote_stale"},
                "quote": {"items": {"new": 940, "owned": 0, "total": 940}},
            },
        )

        with pytest.raises(DatasetConflictError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.code == "quote_stale"
        assert exc_info.value.quote["items"]["new"] == 940

    def test_409_download_in_progress_carries_no_quote(self) -> None:
        response = _response(
            409,
            {
                "detail": "A download for this key is already running.",
                "errors": {"code": "download_in_progress"},
            },
        )

        with pytest.raises(DatasetConflictError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.code == "download_in_progress"
        assert exc_info.value.quote is None

    def test_409_without_a_code_is_still_a_dataset_conflict(self) -> None:
        """Several 409s carry no `errors.code`; the status decides the class."""
        response = _response(409, {"detail": "Batch api-x expired at ... ."})

        with pytest.raises(DatasetConflictError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.code is None

    def test_410_raises_batch_expired(self) -> None:
        response = _response(
            410,
            {
                "detail": "Batch api-x-20260906-1 expired at 2026-09-06T00:00:00Z without "
                "being acked; its rows were released back to the pool.",
            },
        )

        with pytest.raises(BatchExpiredError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.status_code == 410
        assert "released back to the pool" in exc_info.value.message

    def test_409_is_not_retryable(self) -> None:
        """409 must stay out of the retry set: it is the answer that says stop."""
        from gofetch.constants import RETRYABLE_STATUS_CODES

        assert 409 not in RETRYABLE_STATUS_CODES
        assert 410 not in RETRYABLE_STATUS_CODES
        assert 402 not in RETRYABLE_STATUS_CODES
        # A batch that belongs to another API key on the same org. Retrying it
        # would re-ask a question already answered no.
        assert 403 not in RETRYABLE_STATUS_CODES

    def test_403_batch_not_yours_carries_its_code(self) -> None:
        response = _response(
            403,
            {
                "detail": "Batch api-x-20260907-1: This batch belongs to a different "
                "API key on your organization. Its rows and its ack belong to the "
                "client that pulled it.",
                "errors": {"code": "batch_not_yours"},
            },
        )

        with pytest.raises(APIError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.status_code == 403
        assert exc_info.value.error_code == "batch_not_yours"

    def test_supported_formats_rides_along(self) -> None:
        response = _response(
            400,
            {
                "detail": "Unsupported format 'xml' for this dataset.",
                "errors": {"code": "unsupported_format"},
                "supported_formats": ["jsonl"],
            },
        )

        with pytest.raises(APIError) as exc_info:
            _handle_error_response(response)

        assert exc_info.value.details["supported_formats"] == ["jsonl"]


# ---------------------------------------------------------------------------
# headers= passthrough
# ---------------------------------------------------------------------------


class TestHeadersPassthrough:
    """Every verb forwards `headers` to httpx — that is how Idempotency-Key ships."""

    @pytest.mark.parametrize(
        "method,kwargs",
        [
            ("get", {}),
            ("post", {"json": {"expected_items": 5}}),
            ("patch", {"json": {"daily_quota": 10}}),
            ("delete", {}),
        ],
    )
    def test_verb_forwards_headers(self, method, kwargs) -> None:
        client = HTTPClient(api_key="test", base_url="http://localhost")
        client._client = MagicMock()
        client._client.request.return_value = MagicMock(status_code=200, **{"json.return_value": {}})

        getattr(client, method)("/api/v1/x/", headers={"Idempotency-Key": "k-1"}, **kwargs)

        assert client._client.request.call_args[1]["headers"] == {"Idempotency-Key": "k-1"}

    def test_every_retry_resends_the_same_headers(self) -> None:
        """The retry loop reuses the request, so a key covers its own retries."""
        client = HTTPClient(api_key="test", base_url="http://localhost", max_retries=1)
        client._client = MagicMock()
        failure = MagicMock(status_code=500, headers={})
        failure.json.return_value = {"detail": "boom"}
        success = MagicMock(status_code=202)
        success.json.return_value = {"export_id": "e-1"}
        client._client.request.side_effect = [failure, success]

        with patch("gofetch.http.time.sleep"):
            client.post("/api/v1/x/", json={}, headers={"Idempotency-Key": "k-1"})

        assert client._client.request.call_count == 2
        for call in client._client.request.call_args_list:
            assert call[1]["headers"] == {"Idempotency-Key": "k-1"}


# ---------------------------------------------------------------------------
# HTTPClient structure tests
# ---------------------------------------------------------------------------


class TestHTTPClientStructure:
    """Tests for HTTPClient method existence and structure."""

    def test_patch_method_exists(self) -> None:
        """HTTPClient has a patch() method."""
        client = HTTPClient(api_key="test", base_url="http://localhost")
        assert hasattr(client, "patch")
        assert callable(client.patch)
        client.close()

    def test_get_method_exists(self) -> None:
        """HTTPClient has a get() method."""
        client = HTTPClient(api_key="test", base_url="http://localhost")
        assert hasattr(client, "get")
        assert callable(client.get)
        client.close()

    def test_post_method_exists(self) -> None:
        """HTTPClient has a post() method."""
        client = HTTPClient(api_key="test", base_url="http://localhost")
        assert hasattr(client, "post")
        assert callable(client.post)
        client.close()

    def test_delete_method_exists(self) -> None:
        """HTTPClient has a delete() method."""
        client = HTTPClient(api_key="test", base_url="http://localhost")
        assert hasattr(client, "delete")
        assert callable(client.delete)
        client.close()

    def test_handle_error_response_is_module_level(self) -> None:
        """_handle_error_response is a standalone module-level function."""
        from gofetch import http

        assert hasattr(http, "_handle_error_response")
        assert callable(http._handle_error_response)
        # It should NOT be a bound method on a class
        assert not hasattr(_handle_error_response, "__self__")

    def test_context_manager(self) -> None:
        """HTTPClient supports use as a context manager."""
        with HTTPClient(api_key="test", base_url="http://localhost") as client:
            assert isinstance(client, HTTPClient)
