"""Domain and infrastructure exception hierarchy for the FastAPI backend."""

from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    """Base application exception mapped to a unified ErrorResponse."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"

    def __init__(self, message: str, details: str | None = None) -> None:
        """Initialize the error with a public message and optional details."""
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    """Raised when a requested resource does not exist."""

    status_code = HTTPStatus.NOT_FOUND
    error_code = "not_found"


class ValidationDomainError(AppError):
    """Raised when domain-level query or parameter validation fails."""

    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "validation_error"


class RateLimitError(AppError):
    """Raised when a client exceeds the endpoint rate limit."""

    status_code = HTTPStatus.TOO_MANY_REQUESTS
    error_code = "rate_limit_exceeded"


class ServiceUnavailableError(AppError):
    """Raised when a required backing service such as MySQL is unavailable."""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    error_code = "service_unavailable"
