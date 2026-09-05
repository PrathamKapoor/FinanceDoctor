"""Normalized provider exceptions.

These exceptions abstract Razorpay-specific HTTP errors into domain-relevant categories.
The rest of Financial Doctor should handle these, not raw HTTP details.
"""

from __future__ import annotations

from typing import Any


class ProviderError(Exception):
    """Base class for all provider errors."""

    def __init__(
        self,
        message: str,
        *,
        provider_code: str | None = None,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider_code = provider_code
        self.http_status = http_status
        self.details = details or {}


class ProviderAuthenticationError(ProviderError):
    """Invalid or missing API credentials."""

    def __init__(self, message: str = "Invalid API credentials", **kwargs: Any) -> None:
        super().__init__(message, provider_code="BAD_REQUEST_ERROR", **kwargs)


class ProviderNotFoundError(ProviderError):
    """Resource not found (404)."""

    def __init__(
        self,
        message: str = "Resource not found",
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, provider_code="NOT_FOUND_ERROR", **kwargs)
        self.resource_type = resource_type
        self.resource_id = resource_id


class ProviderValidationError(ProviderError):
    """Request validation failed (400)."""

    def __init__(
        self,
        message: str = "Invalid request parameters",
        *,
        field_errors: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, provider_code="BAD_REQUEST_ERROR", **kwargs)
        self.field_errors = field_errors or {}


class ProviderRateLimitError(ProviderError):
    """Rate limit exceeded (429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        retry_after_seconds: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, provider_code="RATE_LIMIT_ERROR", **kwargs)
        self.retry_after_seconds = retry_after_seconds


class ProviderConflictError(ProviderError):
    """Conflict (409) — e.g., duplicate idempotency key."""

    def __init__(
        self,
        message: str = "Resource conflict",
        *,
        existing_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, provider_code="CONFLICT_ERROR", **kwargs)
        self.existing_id = existing_id


class ProviderUnavailableError(ProviderError):
    """Provider service unavailable (5xx)."""

    def __init__(
        self,
        message: str = "Provider temporarily unavailable",
        *,
        retry_after_seconds: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, provider_code="SERVER_ERROR", **kwargs)
        self.retry_after_seconds = retry_after_seconds


class WebhookSignatureError(ProviderError):
    """Webhook signature validation failed."""

    def __init__(self, message: str = "Invalid webhook signature", **kwargs: Any) -> None:
        super().__init__(message, provider_code="SIGNATURE_VERIFICATION_FAILED", **kwargs)


class ProviderTimeoutError(ProviderError):
    """Request timed out."""

    def __init__(
        self,
        message: str = "Provider request timed out",
        *,
        timeout_seconds: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, provider_code="TIMEOUT_ERROR", **kwargs)
        self.timeout_seconds = timeout_seconds


# Mapping from Razorpay error codes to normalized exceptions
RAZORPAY_ERROR_MAP: dict[str, type[ProviderError]] = {
    "BAD_REQUEST_ERROR": ProviderValidationError,
    "NOT_FOUND_ERROR": ProviderNotFoundError,
    "UNAUTHORIZED_ERROR": ProviderAuthenticationError,
    "FORBIDDEN_ERROR": ProviderAuthenticationError,
    "RATE_LIMIT_ERROR": ProviderRateLimitError,
    "CONFLICT_ERROR": ProviderConflictError,
    "SERVER_ERROR": ProviderUnavailableError,
    "SERVICE_UNAVAILABLE": ProviderUnavailableError,
    "GATEWAY_TIMEOUT": ProviderTimeoutError,
    "SIGNATURE_VERIFICATION_FAILED": WebhookSignatureError,
}


def normalize_razorpay_error(
    http_status: int,
    error_code: str | None,
    description: str | None,
    details: dict[str, Any] | None = None,
) -> ProviderError:
    """Convert a Razorpay API error response to a normalized exception."""
    exc_class = RAZORPAY_ERROR_MAP.get(error_code or "", ProviderError)

    # Override based on HTTP status for common cases
    if http_status == 401:
        exc_class = ProviderAuthenticationError
    elif http_status == 404:
        exc_class = ProviderNotFoundError
    elif http_status == 429:
        exc_class = ProviderRateLimitError
    elif http_status >= 500:
        exc_class = ProviderUnavailableError

    # NOTE: subclasses set their own default provider_code, so it is overlaid
    # after construction rather than passed (avoids duplicate-keyword crash).
    exc = exc_class(
        description or "Provider error",
        http_status=http_status,
        details=details,
    )
    if error_code:
        exc.provider_code = error_code
    return exc