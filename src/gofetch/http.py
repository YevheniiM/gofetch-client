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
)
from gofetch.exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
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
        return {
            API_KEY_HEADER: self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "gofetch-client/0.1.0",
        }

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make a GET request.

        Args:
            path: API path (e.g., "/api/v1/jobs/")
            params: Query parameters

        Returns:
            Response JSON as dict

        Raises:
            APIError: If the request fails
            AuthenticationError: If authentication fails (401)
            RateLimitError: If rate limited (429)
        """
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make a POST request.

        Args:
            path: API path
            json: Request body as JSON
            params: Query parameters

        Returns:
            Response JSON as dict
        """
        return self._request("POST", path, json=json, params=params)

    def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make a DELETE request.

        Args:
            path: API path
            params: Query parameters

        Returns:
            Response JSON as dict, or empty dict if no content
        """
        return self._request("DELETE", path, params=params)

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make an HTTP request with retry logic.

        Args:
            method: HTTP method
            path: API path
            json: Request body
            params: Query parameters

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
                )

                # Check for errors
                if response.status_code >= 400:
                    self._handle_error_response(response)

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

            except APIError:
                # Don't retry other API errors
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

    def _handle_error_response(self, response: httpx.Response) -> None:
        """
        Parse error response and raise appropriate exception.

        Args:
            response: HTTP response with error status

        Raises:
            AuthenticationError: For 401 responses
            RateLimitError: For 429 responses
            APIError: For other error responses
        """
        try:
            error_data = response.json()
        except Exception:
            error_data = {"message": response.text or "Unknown error"}

        error_message = error_data.get("message", error_data.get("error", "Unknown error"))
        error_code = error_data.get("error")
        details = error_data.get("details", {})

        if response.status_code == 401:
            raise AuthenticationError(message=error_message, details=details)

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
        return {
            API_KEY_HEADER: self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "gofetch-client/0.1.0",
        }

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request."""
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request."""
        return await self._request("POST", path, json=json, params=params)

    async def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a DELETE request."""
        return await self._request("DELETE", path, params=params)

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with retry logic."""
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
                )

                if response.status_code >= 400:
                    self._handle_error_response(response)

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

            except APIError:
                raise

        if last_exception:
            if isinstance(last_exception, APIError):
                raise last_exception
            raise APIError(
                message=f"Request failed after {self._max_retries + 1} attempts: {last_exception}",
                status_code=0,
            )

        raise APIError(message="Request failed with unknown error", status_code=0)

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Parse error response and raise appropriate exception."""
        try:
            error_data = response.json()
        except Exception:
            error_data = {"message": response.text or "Unknown error"}

        error_message = error_data.get("message", error_data.get("error", "Unknown error"))
        error_code = error_data.get("error")
        details = error_data.get("details", {})

        if response.status_code == 401:
            raise AuthenticationError(message=error_message, details=details)

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

    async def close(self) -> None:
        """Close the async HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> AsyncHTTPClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
