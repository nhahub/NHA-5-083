"""Pipeline status and data quality telemetry endpoint."""

from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends

from web.backend.dependencies import get_pipeline_service
from web.backend.schemas.common import ErrorResponse
from web.backend.schemas.pipeline import PipelineStatusOut
from web.backend.services.pipeline_service import PipelineService

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

PipelineServiceDep = Annotated[PipelineService, Depends(get_pipeline_service)]


@router.get(
    "/status",
    response_model=PipelineStatusOut,
    summary="Get latest ETL pipeline run status and data quality metrics",
    responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
)
def get_pipeline_status(service: PipelineServiceDep) -> PipelineStatusOut:
    """Return latest pipeline runs, freshness status, and quality rule counts."""
    return service.get_status()
