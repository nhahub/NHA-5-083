"""Shared response and error schemas."""

from __future__ import annotations

from pydantic import BaseModel


class HealthOut(BaseModel):
    """Health check response body."""

    status: str


class ErrorResponse(BaseModel):
    """Unified error payload returned on non-2xx responses."""

    error_code: str
    message: str
    details: str | None = None
