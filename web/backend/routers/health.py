"""Health probe endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from web.backend.schemas.common import HealthOut

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthOut,
    summary="Check backend service health",
)
def get_health() -> HealthOut:
    """Return liveness status for deployment health probes."""
    return HealthOut(status="ok")
