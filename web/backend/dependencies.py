"""FastAPI dependency providers wiring repositories and services."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from web.backend.repositories.db import DictCursorConnection, get_db_connection
from web.backend.repositories.meta_repository import MetaRepository
from web.backend.repositories.pipeline_repository import PipelineRepository
from web.backend.repositories.restaurant_repository import RestaurantRepository
from web.backend.services.meta_service import MetaService
from web.backend.services.pipeline_service import PipelineService
from web.backend.services.rate_limiter import SlidingWindowRateLimiter
from web.backend.services.restaurant_service import RestaurantService
from web.backend.services.search_service import SearchService
from web.backend.settings import settings

DbConnDep = Annotated[DictCursorConnection | None, Depends(get_db_connection)]


def get_rate_limiter(request: Request) -> SlidingWindowRateLimiter:
    """Return the application-scoped NLP rate limiter instance."""
    limiter: SlidingWindowRateLimiter = request.app.state.nlp_rate_limiter
    return limiter


def get_restaurant_service(conn: DbConnDep) -> RestaurantService:
    """Build a request-scoped RestaurantService."""
    return RestaurantService(RestaurantRepository(conn, settings))


def get_meta_service(conn: DbConnDep) -> MetaService:
    """Build a request-scoped MetaService."""
    return MetaService(MetaRepository(conn, settings))


def get_pipeline_service(conn: DbConnDep) -> PipelineService:
    """Build a request-scoped PipelineService."""
    return PipelineService(PipelineRepository(conn, settings), settings)


def get_search_service(
    conn: DbConnDep,
    rate_limiter: Annotated[SlidingWindowRateLimiter, Depends(get_rate_limiter)],
) -> SearchService:
    """Build a request-scoped SearchService."""
    return SearchService(
        restaurant_repository=RestaurantRepository(conn, settings),
        meta_repository=MetaRepository(conn, settings),
        rate_limiter=rate_limiter,
        app_settings=settings,
    )
