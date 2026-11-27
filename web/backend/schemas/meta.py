"""Metadata, analytics, and destination profile schemas."""

from __future__ import annotations

from pydantic import BaseModel

from web.backend.schemas.restaurant import RestaurantOut


class CountryMetaOut(BaseModel):
    """Country filter option with currency and restaurant count."""

    country_name: str
    iso_code: str
    currency_code: str
    restaurant_count: int


class CountriesMetaOut(BaseModel):
    """List wrapper for country metadata."""

    items: list[CountryMetaOut]


class CityMetaOut(BaseModel):
    """City filter option with restaurant count."""

    city_name: str
    country_name: str
    restaurant_count: int


class CitiesMetaOut(BaseModel):
    """List wrapper for city metadata."""

    items: list[CityMetaOut]


class CuisineMetaOut(BaseModel):
    """Canonical cuisine filter option with group and count."""

    cuisine_name: str
    cuisine_group: str
    restaurant_count: int


class CuisinesMetaOut(BaseModel):
    """List wrapper for cuisine metadata."""

    items: list[CuisineMetaOut]


class CountBucketOut(BaseModel):
    """Labeled count bucket for analytics charts and tables."""

    label: str
    count: int


class PriceRangeBucketOut(BaseModel):
    """Price range bucket count."""

    price_range: int
    count: int


class RatingBucketOut(BaseModel):
    """Rating label distribution bucket."""

    rating_label: str
    count: int
    avg_rating: float | None = None


class AnalyticsSummaryOut(BaseModel):
    """Aggregated dataset analytics summary."""

    total_restaurants: int
    total_countries: int
    total_cities: int
    total_cuisines: int
    geolocated_count: int
    rated_count: int
    unrated_count: int
    avg_rating: float | None
    top_cuisines: list[CountBucketOut]
    by_country: list[CountBucketOut]
    by_price_range: list[PriceRangeBucketOut]
    rating_distribution: list[RatingBucketOut]


class DestinationProfileOut(BaseModel):
    """Cultural and data summary for a destination country."""

    country_name: str
    currency_code: str
    tagline: str
    dining_tradition: str
    signature_dishes: list[str]
    attribution: str
    restaurant_count: int
    city_count: int
    avg_rating: float | None
    top_cities: list[str]
    top_cuisines: list[str]
    top_restaurants: list[RestaurantOut]
