"""Business logic for restaurant search, details, and map markers."""

from __future__ import annotations

from web.backend.constants import DEFAULT_NEARBY_RADIUS_M, NEARBY_LIMIT, SIMILAR_LIMIT
from web.backend.exceptions import NotFoundError, ValidationDomainError
from web.backend.repositories.restaurant_repository import (
    MapPointFilter,
    RestaurantFilter,
    RestaurantRepository,
)
from web.backend.repositories.spatial import bounding_box_wkt
from web.backend.schemas.map import MapPointsOut
from web.backend.schemas.restaurant import (
    PaginatedRestaurantsOut,
    RestaurantDetailOut,
)


def _clean_optional_text(value: str | None) -> str | None:
    """Strip whitespace and treat blank strings as None."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class RestaurantService:
    """Service layer orchestrating restaurant search and spatial queries."""

    def __init__(self, repository: RestaurantRepository) -> None:
        """Initialize RestaurantService with a RestaurantRepository."""
        self._repository = repository

    def list_restaurants(
        self,
        criteria: RestaurantFilter,
    ) -> PaginatedRestaurantsOut:
        """Return paginated restaurants matching the normalized search filter."""
        normalized = RestaurantFilter(
            country=_clean_optional_text(criteria.country),
            city=_clean_optional_text(criteria.city),
            locality=_clean_optional_text(criteria.locality),
            cuisine=tuple(c.strip() for c in criteria.cuisine if c and c.strip()),
            cuisine_group=_clean_optional_text(criteria.cuisine_group),
            min_rating=criteria.min_rating,
            max_cost_for_two=criteria.max_cost_for_two,
            max_cost_usd=criteria.max_cost_usd,
            price_range=criteria.price_range,
            has_online_delivery=criteria.has_online_delivery,
            has_table_booking=criteria.has_table_booking,
            search_query=_clean_optional_text(criteria.search_query),
            sort_by=criteria.sort_by,
            limit=criteria.limit,
            offset=criteria.offset,
        )
        items, total = self._repository.search_restaurants(normalized)
        return PaginatedRestaurantsOut(
            items=items,
            total=total,
            limit=normalized.limit,
            offset=normalized.offset,
        )

    def get_restaurant_detail(self, restaurant_id: int) -> RestaurantDetailOut:
        """Return restaurant detail along with nearby and similar venues."""
        restaurant = self._repository.get_restaurant_by_id(restaurant_id)
        if restaurant is None:
            raise NotFoundError(
                f"Restaurant {restaurant_id} was not found",
            )
        nearby = self._repository.find_nearby(
            restaurant,
            radius_m=DEFAULT_NEARBY_RADIUS_M,
            limit=NEARBY_LIMIT,
        )
        similar = self._repository.find_similar(restaurant, limit=SIMILAR_LIMIT)
        return RestaurantDetailOut(
            restaurant=restaurant,
            nearby=nearby,
            similar=similar,
        )

    def get_map_points(self, criteria: MapPointFilter) -> MapPointsOut:
        """Validate optional spatial circle inputs and return map points."""
        spatial_fields = (
            criteria.latitude is not None,
            criteria.longitude is not None,
            criteria.radius_m is not None,
        )
        if any(spatial_fields) and not all(spatial_fields):
            raise ValidationDomainError(
                "latitude, longitude, and radius_m must all be provided together"
            )
        if (
            criteria.latitude is not None
            and criteria.longitude is not None
            and criteria.radius_m is not None
        ):
            try:
                bounding_box_wkt(
                    criteria.latitude,
                    criteria.longitude,
                    criteria.radius_m,
                )
            except ValueError as exc:
                raise ValidationDomainError(str(exc)) from exc

        normalized = MapPointFilter(
            country=_clean_optional_text(criteria.country),
            city=_clean_optional_text(criteria.city),
            cuisine=tuple(c.strip() for c in criteria.cuisine if c and c.strip()),
            min_rating=criteria.min_rating,
            price_range=criteria.price_range,
            latitude=criteria.latitude,
            longitude=criteria.longitude,
            radius_m=criteria.radius_m,
            limit=criteria.limit,
        )
        items = self._repository.get_map_points(normalized)
        return MapPointsOut(items=items, total=len(items))
