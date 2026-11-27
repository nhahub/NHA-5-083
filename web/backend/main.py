"""FastAPI application factory, exception handlers, and router mounting."""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from web.backend.exceptions import AppError
from web.backend.logging_config import configure_logging
from web.backend.routers import (
    health,
    meta,
    pipeline,
    restaurants,
    search,
)
from web.backend.routers import (
    map as map_router,
)
from web.backend.schemas.common import ErrorResponse
from web.backend.services.rate_limiter import SlidingWindowRateLimiter
from web.backend.settings import BackendSettings, settings

logger = logging.getLogger(__name__)


def _error_json_response(
    status_code: int,
    error_code: str,
    message: str,
    details: str | None = None,
) -> JSONResponse:
    """Build a JSONResponse conforming to ErrorResponse."""
    body = ErrorResponse(
        error_code=error_code,
        message=message,
        details=details,
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


def create_app(app_settings: BackendSettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    resolved_settings = app_settings or settings
    configure_logging(resolved_settings.logging_level)

    application = FastAPI(
        title="Global Restaurant Explorer API",
        version="0.1.0",
        description=(
            "Medallion-backed restaurant discovery, spatial search, "
            "and constrained natural-language search API."
        ),
    )

    application.state.nlp_rate_limiter = SlidingWindowRateLimiter(
        max_requests=resolved_settings.backend_nlp_rate_limit_per_minute
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @application.exception_handler(AppError)
    def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return _error_json_response(
            status_code=exc.status_code,
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        )

    @application.exception_handler(HTTPException)
    def handle_http_exception(_request: Request, exc: HTTPException) -> JSONResponse:
        return _error_json_response(
            status_code=exc.status_code,
            error_code=f"http_{exc.status_code}",
            message=str(exc.detail),
        )

    @application.exception_handler(RequestValidationError)
    def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_json_response(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            error_code="validation_error",
            message="Request validation failed",
            details=str(exc.errors()),
        )

    @application.exception_handler(Exception)
    def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled backend exception",
            extra={"details": type(exc).__name__},
        )
        return _error_json_response(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code="internal_error",
            message="An unexpected internal error occurred",
        )

    api_prefix = "/api"
    application.include_router(health.router, prefix=api_prefix)
    application.include_router(restaurants.router, prefix=api_prefix)
    application.include_router(map_router.router, prefix=api_prefix)
    application.include_router(search.router, prefix=api_prefix)
    application.include_router(meta.router, prefix=api_prefix)
    application.include_router(pipeline.router, prefix=api_prefix)

    return application


app = create_app()
