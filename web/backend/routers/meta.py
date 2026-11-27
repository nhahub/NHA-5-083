"""Metadata, analytics, and destination profile endpoints."""

from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends

from web.backend.dependencies import get_meta_service
from web.backend.schemas.common import ErrorResponse
from web.backend.schemas.meta import (
    AnalyticsSummaryOut,
    CitiesMetaOut,
    CountriesMetaOut,
    CuisinesMetaOut,
    DestinationProfileOut,
)
from web.backend.services.meta_service import MetaService

router = APIRouter(prefix="/meta", tags=["metadata"])

MetaServiceDep = Annotated[MetaService, Depends(get_meta_service)]


@router.get(
    "/countries",
    response_model=CountriesMetaOut,
    summary="List available countries and restaurant counts",
    responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
)
def list_countries(service: MetaServiceDep) -> CountriesMetaOut:
    """Return supported countries, ISO codes, currencies, and venue counts."""
    return service.list_countries()


@router.get(
    "/cities",
    response_model=CitiesMetaOut,
    summary="List available cities optionally filtered by country",
    responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
)
def list_cities(
    service: MetaServiceDep,
    country: str | None = None,
) -> CitiesMetaOut:
    """Return cities and venue counts, optionally narrowed to one country."""
    return service.list_cities(country=country)


@router.get(
    "/cuisines",
    response_model=CuisinesMetaOut,
    summary="List canonical cuisines and cuisine groups",
    responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
)
def list_cuisines(service: MetaServiceDep) -> CuisinesMetaOut:
    """Return canonical cuisines, their groups, and venue counts."""
    return service.list_cuisines()


@router.get(
    "/analytics",
    response_model=AnalyticsSummaryOut,
    summary="Get dataset-wide or country-filtered analytics summary",
    responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
)
def get_analytics(
    service: MetaServiceDep,
    country: str | None = None,
) -> AnalyticsSummaryOut:
    """Return aggregated counts, ratings, and distributions."""
    return service.get_analytics(country=country)


@router.get(
    "/destinations/{country}",
    response_model=DestinationProfileOut,
    summary="Get destination culinary profile and top highlights",
    responses={
        HTTPStatus.NOT_FOUND: {"model": ErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def get_destination_profile(
    country: str,
    service: MetaServiceDep,
) -> DestinationProfileOut:
    """Return cultural editorial context and top venues for a country."""
    return service.get_destination_profile(country)
