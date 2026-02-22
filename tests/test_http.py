"""Tests for HTTP client and error handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gofetch.exceptions import APIError, AuthenticationError, RateLimitError
from gofetch.http import HTTPClient, _handle_error_response


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
