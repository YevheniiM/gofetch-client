"""
GoFetch client exceptions.

All exceptions inherit from GoFetchError for easy catching.
"""

from __future__ import annotations

from typing import Any


class GoFetchError(Exception):
    """Base exception for all GoFetch errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class APIError(GoFetchError):
    """
    Raised when the GoFetch API returns an error response.

    Attributes:
        status_code: HTTP status code
        error_code: GoFetch error code (e.g., 'validation_error')
        message: Human-readable error message
    """

    def __init__(
        self,
        message: str,
        status_code: int,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.status_code = status_code
        self.error_code = error_code

    def __str__(self) -> str:
        base = f"[{self.status_code}] {self.message}"
        if self.error_code:
            base = f"[{self.status_code}:{self.error_code}] {self.message}"
        if self.details:
            base += f" - Details: {self.details}"
        return base


class AuthenticationError(APIError):
    """
    Raised when authentication fails (401).

    Common causes:
    - Invalid API key
    - Expired API key
    - Missing API key
    """

    def __init__(
        self,
        message: str = "Authentication failed. Check your API key.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, status_code=401, error_code="authentication_error", details=details)


class RateLimitError(APIError):
    """
    Raised when rate limit is exceeded (429).

    Attributes:
        retry_after: Seconds to wait before retrying
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded.",
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, status_code=429, error_code="rate_limit_exceeded", details=details)
        self.retry_after = retry_after

    def __str__(self) -> str:
        base = super().__str__()
        if self.retry_after:
            base += f" Retry after {self.retry_after} seconds."
        return base


class JobError(GoFetchError):
    """
    Raised when a job fails or encounters an error.

    Attributes:
        job_id: The ID of the failed job
        status: The job status (e.g., 'failed', 'cancelled')
        error_message: Error message from the job
    """

    def __init__(
        self,
        message: str,
        job_id: str | None = None,
        status: str | None = None,
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.job_id = job_id
        self.status = status
        self.error_message = error_message

    def __str__(self) -> str:
        parts = [self.message]
        if self.job_id:
            parts.append(f"Job: {self.job_id}")
        if self.status:
            parts.append(f"Status: {self.status}")
        if self.error_message:
            parts.append(f"Error: {self.error_message}")
        return " | ".join(parts)


class TimeoutError(GoFetchError):
    """
    Raised when an operation times out.

    Attributes:
        job_id: The ID of the job that timed out
        timeout_seconds: The timeout duration
    """

    def __init__(
        self,
        message: str = "Operation timed out.",
        job_id: str | None = None,
        timeout_seconds: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.job_id = job_id
        self.timeout_seconds = timeout_seconds

    def __str__(self) -> str:
        parts = [self.message]
        if self.job_id:
            parts.append(f"Job: {self.job_id}")
        if self.timeout_seconds:
            parts.append(f"Timeout: {self.timeout_seconds}s")
        return " | ".join(parts)


class ValidationError(GoFetchError):
    """
    Raised when input validation fails.

    Attributes:
        field: The field that failed validation
        error: The validation error message
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.field = field

    def __str__(self) -> str:
        if self.field:
            return f"Validation error on '{self.field}': {self.message}"
        return f"Validation error: {self.message}"
