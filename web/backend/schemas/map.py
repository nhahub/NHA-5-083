"""Spatial map point response schemas."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class MapPointOut(BaseModel):
    """Geolocated restaurant marker returned for map views."""

    restaurant_id: int
    name: str
    country_name: str
    city_name: str
    locality: str
    latitude: float
    longitude: float
    cuisines: list[str]
    price_range: int
    rating: float | None
    votes: int
    avg_cost_for_two: Decimal | None
    currency_code: str
    avg_cost_for_two_usd: Decimal | None
    source_name: str
    source_license: str
    distance_m: float | None = None


class MapPointsOut(BaseModel):
    """Map points collection response."""

    items: list[MapPointOut]
    total: int
