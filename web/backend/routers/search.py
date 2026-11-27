"""Natural-language restaurant search endpoint."""

from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from web.backend.dependencies import get_search_service
from web.backend.schemas.common import ErrorResponse
from web.backend.schemas.nlp import NLSearchRequest, NLSearchResponseOut
from web.backend.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])

SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]


def _extract_client_ip(request: Request) -> str:
    """Resolve client IP key for per-client rate limiting."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first_ip = forwarded.split(",")[0].strip()
        if first_ip:
            return first_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post(
    "/nl",
    response_model=NLSearchResponseOut,
    summary="Parse a natural-language query into structured filters and search",
    responses={
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
        HTTPStatus.TOO_MANY_REQUESTS: {"model": ErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def search_natural_language(
    payload: NLSearchRequest,
    request: Request,
    service: SearchServiceDep,
) -> NLSearchResponseOut:
    """Parse a natural-language search query and return matching restaurants."""
    client_key = _extract_client_ip(request)
    return service.search_natural_language(payload, client_key=client_key)
