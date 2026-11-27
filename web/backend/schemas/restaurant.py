"""Restaurant search and detail response schemas."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

SortByOption = Literal["rating", "votes", "cost_usd_asc", "cost_usd_desc", "name"]


class RestaurantOut(BaseModel):
    """Standardized restaurant record returned by search and detail endpoints."""

    restaurant_id: int
    source_restaurant_id: str
    source_name: str
    source_license: str
    name: str
    country_name: str
    iso_code: str
    city_name: str
    locality: str
    address: str | None
    latitude: float | None
    longitude: float | None
    cuisines: list[str]
    cuisine_groups: list[str]
    avg_cost_for_two: Decimal | None
    currency_code: str
    avg_cost_for_two_usd: Decimal | None
    price_range: int
    rating: float | None
    rating_text: str | None
    votes: int
    has_table_booking: bool
    has_online_delivery: bool
    distance_m: float | None = None


class PaginatedRestaurantsOut(BaseModel):
    """Paginated list of restaurants."""

    items: list[RestaurantOut]
    total: int
    limit: int
    offset: int


class RestaurantDetailOut(BaseModel):
    """Restaurant detail view with nearby and similar recommendations."""

    restaurant: RestaurantOut
    nearby: list[RestaurantOut]
    similar: list[RestaurantOut]
