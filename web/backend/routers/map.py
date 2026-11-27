"""Spatial map markers endpoint."""

from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from web.backend.constants import (
    DEFAULT_MAP_LIMIT,
    MAX_ABS_LONGITUDE,
    MAX_GEO_LATITUDE,
    MAX_MAP_LIMIT,
    MAX_PRICE_RANGE,
    MAX_RATING,
    MAX_SEARCH_RADIUS_M,
    MIN_PAGE_LIMIT,
    MIN_PRICE_RANGE,
    MIN_RATING,
)
from web.backend.dependencies import get_restaurant_service
from web.backend.repositories.restaurant_repository import MapPointFilter
from web.backend.schemas.common import ErrorResponse
from web.backend.schemas.map import MapPointsOut
from web.backend.services.restaurant_service import RestaurantService

router = APIRouter(prefix="/map", tags=["map"])

RestaurantServiceDep = Annotated[RestaurantService, Depends(get_restaurant_service)]


@router.get(
    "/points",
    response_model=MapPointsOut,
    summary="Get geolocated restaurant markers for map visualization",
    responses={
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def get_map_points(
    service: RestaurantServiceDep,
    country: str | None = None,
    city: str | None = None,
    cuisine: Annotated[list[str] | None, Query()] = None,
    min_rating: Annotated[float | None, Query(ge=MIN_RATING, le=MAX_RATING)] = None,
    price_range: Annotated[
        int | None, Query(ge=MIN_PRICE_RANGE, le=MAX_PRICE_RANGE)
    ] = None,
    latitude: Annotated[
        float | None, Query(ge=-MAX_GEO_LATITUDE, le=MAX_GEO_LATITUDE)
    ] = None,
    longitude: Annotated[
        float | None, Query(ge=-MAX_ABS_LONGITUDE, le=MAX_ABS_LONGITUDE)
    ] = None,
    radius_m: Annotated[float | None, Query(gt=0.0, le=MAX_SEARCH_RADIUS_M)] = None,
    limit: Annotated[
        int, Query(ge=MIN_PAGE_LIMIT, le=MAX_MAP_LIMIT)
    ] = DEFAULT_MAP_LIMIT,
) -> MapPointsOut:
    """Return geolocated markers matching filters and optional spatial circle."""
    criteria = MapPointFilter(
        country=country,
        city=city,
        cuisine=tuple(cuisine or ()),
        min_rating=min_rating,
        price_range=price_range,
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
        limit=limit,
    )
    return service.get_map_points(criteria)
