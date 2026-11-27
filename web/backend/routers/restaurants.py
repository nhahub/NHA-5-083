"""Restaurant search and detail endpoints."""

from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from web.backend.constants import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    MAX_PRICE_RANGE,
    MAX_RATING,
    MIN_COST,
    MIN_PAGE_LIMIT,
    MIN_PRICE_RANGE,
    MIN_RATING,
)
from web.backend.dependencies import get_restaurant_service
from web.backend.repositories.restaurant_repository import RestaurantFilter
from web.backend.schemas.common import ErrorResponse
from web.backend.schemas.restaurant import (
    PaginatedRestaurantsOut,
    RestaurantDetailOut,
    SortByOption,
)
from web.backend.services.restaurant_service import RestaurantService

router = APIRouter(prefix="/restaurants", tags=["restaurants"])

RestaurantServiceDep = Annotated[RestaurantService, Depends(get_restaurant_service)]


@router.get(
    "",
    response_model=PaginatedRestaurantsOut,
    summary="Search and filter restaurants",
    responses={
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def list_restaurants(
    service: RestaurantServiceDep,
    country: str | None = None,
    city: str | None = None,
    locality: str | None = None,
    cuisine: Annotated[list[str] | None, Query()] = None,
    cuisine_group: str | None = None,
    min_rating: Annotated[float | None, Query(ge=MIN_RATING, le=MAX_RATING)] = None,
    max_cost_for_two: Annotated[float | None, Query(ge=MIN_COST)] = None,
    max_cost_usd: Annotated[float | None, Query(ge=MIN_COST)] = None,
    price_range: Annotated[
        int | None, Query(ge=MIN_PRICE_RANGE, le=MAX_PRICE_RANGE)
    ] = None,
    has_online_delivery: bool | None = None,
    has_table_booking: bool | None = None,
    search_query: str | None = None,
    sort_by: SortByOption = "rating",
    limit: Annotated[
        int, Query(ge=MIN_PAGE_LIMIT, le=MAX_PAGE_LIMIT)
    ] = DEFAULT_PAGE_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedRestaurantsOut:
    """Return paginated restaurants matching the requested filters."""
    criteria = RestaurantFilter(
        country=country,
        city=city,
        locality=locality,
        cuisine=tuple(cuisine or ()),
        cuisine_group=cuisine_group,
        min_rating=min_rating,
        max_cost_for_two=max_cost_for_two,
        max_cost_usd=max_cost_usd,
        price_range=price_range,
        has_online_delivery=has_online_delivery,
        has_table_booking=has_table_booking,
        search_query=search_query,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )
    return service.list_restaurants(criteria)


@router.get(
    "/{restaurant_id}",
    response_model=RestaurantDetailOut,
    summary="Get restaurant details with nearby and similar recommendations",
    responses={
        HTTPStatus.NOT_FOUND: {"model": ErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def get_restaurant_detail(
    restaurant_id: int,
    service: RestaurantServiceDep,
) -> RestaurantDetailOut:
    """Return full details, nearby venues, and similar venues for a restaurant."""
    return service.get_restaurant_detail(restaurant_id)
