"""
HTTP client for GoFetch API.

Provides a robust HTTP client with:
- Automatic retries with exponential backoff
- Rate limit handling
- Error response parsing
- Both sync and async support
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

import httpx

from gofetch.constants import (
    API_KEY_HEADER,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY,
    DEFAULT_TIMEOUT,
    RETRY_BACKOFF_FACTOR,
    RETRYABLE_STATUS_CODES,
)
from gofetch.exceptions import (
    APIError,
    AuthenticationError,
    BatchExpiredError,
    DatasetConflictError,
    InsufficientCreditsError,
    RateLimitError,
)

# A non-JSON error body is a whole document — a Django "Not Found" HTML page for
# a URL that never reached the app — so it is truncated rather than dumped into
# the exception message.
ERROR_TEXT_LIMIT = 200


def _short(text: str | None) -> str:
    """A body that is not JSON, cut to something readable."""
    text = (text or "").strip()
    if not text:
        return "Unknown error"
    return text if len(text) <= ERROR_TEXT_LIMIT else text[:ERROR_TEXT_LIMIT] + "..."


def _error_body(response: httpx.Response) -> dict[str, Any]:
    """The error body as a dict, whatever shape the server actually sent.

    DRF renders ``raise ValidationError('<string>')`` as a bare JSON **list**,
    which the datasets API does on a couple of paths. Reading keys off that
    directly raised ``AttributeError`` — escaping every ``except GoFetchError``
    a caller wrote — so a non-dict body is normalised into one here.
    """
    try:
        data = response.json()
    except Exception:
        return {"message": _short(response.text)}

    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {"message": "; ".join(str(item) for item in data) or "Unknown error"}
    return {"message": str(data)}


def _handle_error_response(response: httpx.Response) -> None:
    """Parse error response and raise appropriate exception."""
    error_data = _error_body(response)

    # `detail` first: it is what DRF and every datasets refusal use. `message`
    # appears only on field-validation errors, `error` only on older job errors.
    error_message = (
        error_data.get("detail")
        or error_data.get("message")
        or error_data.get("error")
        or "Unknown error"
    )
    if not isinstance(error_message, str):
        error_message = str(error_message)

    # The machine-readable code lives at `errors.code`. Field-validation errors
    # put `{field: [messages]}` in the same place, so only a string counts.
    errors = error_data.get("errors")
    code = errors.get("code") if isinstance(errors, dict) else None
    error_code = code if isinstance(code, str) else error_data.get("error")

    # The structured siblings a refusal rides along with, so the caller never
    # has to re-parse the body to find them.
    details = dict(error_data.get("details") or {})
    for key in ("constraints", "quote", "supported_formats"):
        if key in error_data:
            details.setdefault(key, error_data[key])

    if response.status_code == 401:
        raise AuthenticationError(message=error_message, details=details)

    if response.status_code == 402:
        raise InsufficientCreditsError(
            message=error_message,
            constraints=error_data.get("constraints") or [],
            error_code=error_code,
            details=details,
        )

    if response.status_code == 409:
        raise DatasetConflictError(
            message=error_message,
            error_code=error_code,
            quote=error_data.get("quote"),
            details=details,
        )

    if response.status_code == 410:
        raise BatchExpiredError(
            message=error_message,
            error_code=error_code,
            details=details,
        )

    if response.status_code == 429:
        retry_after = None
        if "Retry-After" in response.headers:
            with contextlib.suppress(ValueError):
                retry_after = int(response.headers["Retry-After"])
        retry_after = retry_after or error_data.get("retry_after")
        raise RateLimitError(message=error_message, retry_after=retry_after, details=details)

    raise APIError(
        message=error_message,
        status_code=response.status_code,
        error_code=error_code,
        details=details,
    )


class HTTPClient:
    """
    HTTP client for GoFetch API requests.

    Handles authentication, retries, and error parsing.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        """
        Initialize the HTTP client.

        Args:
            api_key: GoFetch API key (format: sk_scr_...)
            base_url: Base URL for the API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers=self._default_headers(),
        )

    def _default_headers(self) -> dict[str, str]:
        """Get default headers for all requests."""
        from gofetch import __version__

        return {
            API_KEY_HEADER: self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"gofetch-client/{__version__}",
        }

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Make a GET request.

        Args:
            path: API path (e.g., "/api/v1/jobs/")
            params: Query parameters
            headers: Extra headers, merged over the client defaults

        Returns:
            Response JSON as dict

        Raises:
            APIError: If the request fails
            AuthenticationError: If authentication fails (401)
            RateLimitError: If rate limited (429)
        """
        return self._request("GET", path, params=params, headers=headers)

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Make a POST request.

        Args:
            path: API path
            json: Request body as JSON
            params: Query parameters
            headers: Extra headers, merged over the client defaults

        Returns:
            Response JSON as dict
        """
        return self._request("POST", path, json=json, params=params, headers=headers)

    def patch(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a PATCH request."""
        return self._request("PATCH", path, json=json, params=params, headers=headers)

    def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Make a DELETE request.

        Args:
            path: API path
            params: Query parameters
            headers: Extra headers, merged over the client defaults

        Returns:
            Response JSON as dict, or empty dict if no content
        """
        return self._request("DELETE", path, params=params, headers=headers)

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Make an HTTP request with retry logic.

        Every attempt resends the same headers, so an ``Idempotency-Key`` the
        caller set covers the automatic retries too — which is what makes
        retrying a money-moving POST safe.

        Args:
            method: HTTP method
            path: API path
            json: Request body
            params: Query parameters
            headers: Extra headers, merged over the client defaults

        Returns:
            Response JSON

        Raises:
            APIError: On request failure
        """
        last_exception: Exception | None = None
        retry_delay = DEFAULT_RETRY_DELAY

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.request(
                    method=method,
                    url=path,
                    json=json,
                    params=params,
                    headers=headers,
                )

                # Check for errors
                if response.status_code >= 400:
                    _handle_error_response(response)

                # Return JSON response
                if response.status_code == 204:
                    return {}

                return response.json()  # type: ignore[no-any-return]

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < self._max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= RETRY_BACKOFF_FACTOR
                continue

            except RateLimitError as e:
                # Use retry_after if provided, otherwise exponential backoff
                wait_time = e.retry_after if e.retry_after else retry_delay
                if attempt < self._max_retries:
                    time.sleep(wait_time)
                    retry_delay *= RETRY_BACKOFF_FACTOR
                last_exception = e
                continue

            except APIError as e:
                # Retry server errors with retryable status codes
                if e.status_code in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                    last_exception = e
                    time.sleep(retry_delay)
                    retry_delay *= RETRY_BACKOFF_FACTOR
                    continue
                raise

        # If we get here, all retries failed
        if last_exception:
            if isinstance(last_exception, APIError):
                raise last_exception
            raise APIError(
                message=f"Request failed after {self._max_retries + 1} attempts: {last_exception}",
                status_code=0,
            )

        raise APIError(message="Request failed with unknown error", status_code=0)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> HTTPClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class AsyncHTTPClient:
    """
    Async HTTP client for GoFetch API requests.

    Same interface as HTTPClient but uses async/await.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        """Initialize the async HTTP client."""
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers=self._default_headers(),
        )

    def _default_headers(self) -> dict[str, str]:
        """Get default headers for all requests."""
        from gofetch import __version__

        return {
            API_KEY_HEADER: self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"gofetch-client/{__version__}",
        }

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request."""
        return await self._request("GET", path, params=params, headers=headers)

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request."""
        return await self._request("POST", path, json=json, params=params, headers=headers)

    async def patch(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a PATCH request."""
        return await self._request("PATCH", path, json=json, params=params, headers=headers)

    async def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a DELETE request."""
        return await self._request("DELETE", path, params=params, headers=headers)

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with retry logic.

        Every attempt resends the same headers, so an ``Idempotency-Key`` the
        caller set covers the automatic retries too — which is what makes
        retrying a money-moving POST safe.
        """
        import asyncio

        last_exception: Exception | None = None
        retry_delay = DEFAULT_RETRY_DELAY

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    method=method,
                    url=path,
                    json=json,
                    params=params,
                    headers=headers,
                )

                if response.status_code >= 400:
                    _handle_error_response(response)

                if response.status_code == 204:
                    return {}

                return response.json()  # type: ignore[no-any-return]

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < self._max_retries:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= RETRY_BACKOFF_FACTOR
                continue

            except RateLimitError as e:
                wait_time = e.retry_after if e.retry_after else retry_delay
                if attempt < self._max_retries:
                    await asyncio.sleep(wait_time)
                    retry_delay *= RETRY_BACKOFF_FACTOR
                last_exception = e
                continue

            except APIError as e:
                # Retry server errors with retryable status codes
                if e.status_code in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                    last_exception = e
                    await asyncio.sleep(retry_delay)
                    retry_delay *= RETRY_BACKOFF_FACTOR
                    continue
                raise

        if last_exception:
            if isinstance(last_exception, APIError):
                raise last_exception
            raise APIError(
                message=f"Request failed after {self._max_retries + 1} attempts: {last_exception}",
                status_code=0,
            )

        raise APIError(message="Request failed with unknown error", status_code=0)

    async def close(self) -> None:
        """Close the async HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> AsyncHTTPClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
