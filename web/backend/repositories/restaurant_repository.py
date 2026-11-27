"""Restaurant, map point, and recommendation queries against MySQL or CSV."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

import pymysql

from web.backend.constants import (
    DEFAULT_MAP_LIMIT,
    DEFAULT_NEARBY_RADIUS_M,
    DEFAULT_PAGE_LIMIT,
    NEARBY_LIMIT,
    SIMILAR_LIMIT,
    WGS84_SRID,
)
from web.backend.exceptions import ServiceUnavailableError
from web.backend.repositories.csv_fallback import (
    StandardizedCsvSnapshot,
    get_cached_csv_snapshot,
)
from web.backend.repositories.db import DictCursorConnection
from web.backend.repositories.spatial import (
    bounding_box_wkt,
    haversine_meters,
    is_valid_coordinate,
)
from web.backend.schemas.map import MapPointOut
from web.backend.schemas.restaurant import RestaurantOut, SortByOption
from web.backend.settings import BackendSettings, settings

logger = logging.getLogger(__name__)

_RESTAURANT_SEARCH_SQL = """
SELECT
    grs.restaurant_id,
    grs.source_restaurant_id,
    grs.source_name,
    grs.source_license,
    grs.name,
    grs.country_name,
    grs.iso_code,
    grs.city_name,
    grs.locality,
    grs.address,
    grs.latitude,
    grs.longitude,
    grs.cuisines,
    grs.cuisine_groups,
    grs.avg_cost_for_two,
    grs.currency_code,
    grs.avg_cost_for_two_usd,
    grs.price_range,
    grs.rating,
    grs.rating_text,
    grs.votes,
    grs.has_table_booking,
    grs.has_online_delivery
FROM gold_restaurant_search AS grs
WHERE (%(country)s IS NULL OR LOWER(grs.country_name) = LOWER(%(country)s))
  AND (%(city)s IS NULL OR LOWER(grs.city_name) = LOWER(%(city)s))
  AND (
      %(locality)s IS NULL
      OR LOWER(grs.locality) LIKE CONCAT('%%', LOWER(%(locality)s), '%%')
  )
  AND (
      %(min_rating)s IS NULL
      OR (grs.rating IS NOT NULL AND grs.rating >= %(min_rating)s)
  )
  AND (
      %(max_cost_for_two)s IS NULL
      OR (
          grs.avg_cost_for_two IS NOT NULL
          AND grs.avg_cost_for_two <= %(max_cost_for_two)s
      )
  )
  AND (
      %(max_cost_usd)s IS NULL
      OR (
          grs.avg_cost_for_two_usd IS NOT NULL
          AND grs.avg_cost_for_two_usd <= %(max_cost_usd)s
      )
  )
  AND (%(price_range)s IS NULL OR grs.price_range = %(price_range)s)
  AND (
      %(has_online_delivery)s IS NULL
      OR grs.has_online_delivery = %(has_online_delivery)s
  )
  AND (
      %(has_table_booking)s IS NULL
      OR grs.has_table_booking = %(has_table_booking)s
  )
  AND (
      %(search_query)s IS NULL
      OR LOWER(grs.name) LIKE CONCAT('%%', LOWER(%(search_query)s), '%%')
  )
  AND (
      %(cuisine_group)s IS NULL
      OR EXISTS (
          SELECT 1
          FROM restaurant_cuisines AS rc
          JOIN cuisines AS c ON c.cuisine_id = rc.cuisine_id
          WHERE rc.restaurant_id = grs.restaurant_id
            AND LOWER(c.cuisine_group) = LOWER(%(cuisine_group)s)
      )
  )
  AND (
      %(cuisines_json)s IS NULL
      OR EXISTS (
          SELECT 1
          FROM restaurant_cuisines AS rc
          JOIN cuisines AS c ON c.cuisine_id = rc.cuisine_id
          JOIN JSON_TABLE(
              %(cuisines_json)s,
              '$[*]' COLUMNS (cuisine_name VARCHAR(100) PATH '$')
          ) AS jt ON LOWER(c.cuisine_name) = LOWER(jt.cuisine_name)
          WHERE rc.restaurant_id = grs.restaurant_id
      )
  )
ORDER BY
    CASE WHEN %(sort_by)s = 'rating' THEN grs.rating IS NULL END ASC,
    CASE WHEN %(sort_by)s = 'rating' THEN grs.rating END DESC,
    CASE WHEN %(sort_by)s = 'rating' THEN grs.votes END DESC,
    CASE WHEN %(sort_by)s = 'votes' THEN grs.votes END DESC,
    CASE
        WHEN %(sort_by)s = 'cost_usd_asc' THEN grs.avg_cost_for_two_usd IS NULL
    END ASC,
    CASE WHEN %(sort_by)s = 'cost_usd_asc' THEN grs.avg_cost_for_two_usd END ASC,
    CASE
        WHEN %(sort_by)s = 'cost_usd_desc' THEN grs.avg_cost_for_two_usd IS NULL
    END ASC,
    CASE WHEN %(sort_by)s = 'cost_usd_desc' THEN grs.avg_cost_for_two_usd END DESC,
    CASE WHEN %(sort_by)s = 'name' THEN grs.name END ASC,
    grs.restaurant_id ASC
LIMIT %(limit)s OFFSET %(offset)s
"""

_RESTAURANT_COUNT_SQL = """
SELECT COUNT(*) AS total_count
FROM gold_restaurant_search AS grs
WHERE (%(country)s IS NULL OR LOWER(grs.country_name) = LOWER(%(country)s))
  AND (%(city)s IS NULL OR LOWER(grs.city_name) = LOWER(%(city)s))
  AND (
      %(locality)s IS NULL
      OR LOWER(grs.locality) LIKE CONCAT('%%', LOWER(%(locality)s), '%%')
  )
  AND (
      %(min_rating)s IS NULL
      OR (grs.rating IS NOT NULL AND grs.rating >= %(min_rating)s)
  )
  AND (
      %(max_cost_for_two)s IS NULL
      OR (
          grs.avg_cost_for_two IS NOT NULL
          AND grs.avg_cost_for_two <= %(max_cost_for_two)s
      )
  )
  AND (
      %(max_cost_usd)s IS NULL
      OR (
          grs.avg_cost_for_two_usd IS NOT NULL
          AND grs.avg_cost_for_two_usd <= %(max_cost_usd)s
      )
  )
  AND (%(price_range)s IS NULL OR grs.price_range = %(price_range)s)
  AND (
      %(has_online_delivery)s IS NULL
      OR grs.has_online_delivery = %(has_online_delivery)s
  )
  AND (
      %(has_table_booking)s IS NULL
      OR grs.has_table_booking = %(has_table_booking)s
  )
  AND (
      %(search_query)s IS NULL
      OR LOWER(grs.name) LIKE CONCAT('%%', LOWER(%(search_query)s), '%%')
  )
  AND (
      %(cuisine_group)s IS NULL
      OR EXISTS (
          SELECT 1
          FROM restaurant_cuisines AS rc
          JOIN cuisines AS c ON c.cuisine_id = rc.cuisine_id
          WHERE rc.restaurant_id = grs.restaurant_id
            AND LOWER(c.cuisine_group) = LOWER(%(cuisine_group)s)
      )
  )
  AND (
      %(cuisines_json)s IS NULL
      OR EXISTS (
          SELECT 1
          FROM restaurant_cuisines AS rc
          JOIN cuisines AS c ON c.cuisine_id = rc.cuisine_id
          JOIN JSON_TABLE(
              %(cuisines_json)s,
              '$[*]' COLUMNS (cuisine_name VARCHAR(100) PATH '$')
          ) AS jt ON LOWER(c.cuisine_name) = LOWER(jt.cuisine_name)
          WHERE rc.restaurant_id = grs.restaurant_id
      )
  )
"""

_RESTAURANT_BY_ID_SQL = """
SELECT
    grs.restaurant_id,
    grs.source_restaurant_id,
    grs.source_name,
    grs.source_license,
    grs.name,
    grs.country_name,
    grs.iso_code,
    grs.city_name,
    grs.locality,
    grs.address,
    grs.latitude,
    grs.longitude,
    grs.cuisines,
    grs.cuisine_groups,
    grs.avg_cost_for_two,
    grs.currency_code,
    grs.avg_cost_for_two_usd,
    grs.price_range,
    grs.rating,
    grs.rating_text,
    grs.votes,
    grs.has_table_booking,
    grs.has_online_delivery
FROM gold_restaurant_search AS grs
WHERE grs.restaurant_id = %(restaurant_id)s
LIMIT 1
"""

_NEARBY_SQL = """
SELECT
    grs.restaurant_id,
    grs.source_restaurant_id,
    grs.source_name,
    grs.source_license,
    grs.name,
    grs.country_name,
    grs.iso_code,
    grs.city_name,
    grs.locality,
    grs.address,
    grs.latitude,
    grs.longitude,
    grs.cuisines,
    grs.cuisine_groups,
    grs.avg_cost_for_two,
    grs.currency_code,
    grs.avg_cost_for_two_usd,
    grs.price_range,
    grs.rating,
    grs.rating_text,
    grs.votes,
    grs.has_table_booking,
    grs.has_online_delivery,
    ST_Distance_Sphere(
        gmp.location,
        ST_SRID(POINT(%(longitude)s, %(latitude)s), 4326)
    ) AS distance_m
FROM gold_map_points AS gmp
JOIN gold_restaurant_search AS grs ON grs.restaurant_id = gmp.restaurant_id
WHERE gmp.restaurant_id <> %(exclude_id)s
  AND MBRContains(ST_GeomFromText(%(bounding_box_wkt)s, 4326), gmp.location)
  AND ST_Distance_Sphere(
        gmp.location,
        ST_SRID(POINT(%(longitude)s, %(latitude)s), 4326)
      ) <= %(radius_m)s
ORDER BY distance_m ASC, grs.rating DESC, grs.restaurant_id ASC
LIMIT %(limit)s
"""

_SIMILAR_SQL = """
SELECT
    grs.restaurant_id,
    grs.source_restaurant_id,
    grs.source_name,
    grs.source_license,
    grs.name,
    grs.country_name,
    grs.iso_code,
    grs.city_name,
    grs.locality,
    grs.address,
    grs.latitude,
    grs.longitude,
    grs.cuisines,
    grs.cuisine_groups,
    grs.avg_cost_for_two,
    grs.currency_code,
    grs.avg_cost_for_two_usd,
    grs.price_range,
    grs.rating,
    grs.rating_text,
    grs.votes,
    grs.has_table_booking,
    grs.has_online_delivery,
    COUNT(DISTINCT c.cuisine_id) AS shared_count
FROM gold_restaurant_search AS grs
JOIN restaurant_cuisines AS rc ON rc.restaurant_id = grs.restaurant_id
JOIN cuisines AS c ON c.cuisine_id = rc.cuisine_id
JOIN JSON_TABLE(
    %(cuisines_json)s,
    '$[*]' COLUMNS (cuisine_name VARCHAR(100) PATH '$')
) AS jt ON LOWER(c.cuisine_name) = LOWER(jt.cuisine_name)
WHERE grs.restaurant_id <> %(exclude_id)s
  AND LOWER(grs.city_name) = LOWER(%(city_name)s)
GROUP BY
    grs.restaurant_id,
    grs.source_restaurant_id,
    grs.source_name,
    grs.source_license,
    grs.name,
    grs.country_name,
    grs.iso_code,
    grs.city_name,
    grs.locality,
    grs.address,
    grs.latitude,
    grs.longitude,
    grs.cuisines,
    grs.cuisine_groups,
    grs.avg_cost_for_two,
    grs.currency_code,
    grs.avg_cost_for_two_usd,
    grs.price_range,
    grs.rating,
    grs.rating_text,
    grs.votes,
    grs.has_table_booking,
    grs.has_online_delivery
ORDER BY
    shared_count DESC,
    grs.rating IS NULL ASC,
    grs.rating DESC,
    grs.votes DESC,
    grs.restaurant_id ASC
LIMIT %(limit)s
"""

_MAP_POINTS_SQL = """
SELECT
    gmp.restaurant_id,
    gmp.name,
    gmp.country_name,
    gmp.city_name,
    gmp.locality,
    gmp.latitude,
    gmp.longitude,
    gmp.cuisines,
    gmp.price_range,
    gmp.rating,
    gmp.votes,
    gmp.avg_cost_for_two,
    gmp.currency_code,
    gmp.avg_cost_for_two_usd,
    sm.source_name,
    sm.license AS source_license,
    CASE
        WHEN %(latitude)s IS NOT NULL AND %(longitude)s IS NOT NULL
        THEN ST_Distance_Sphere(
            gmp.location,
            ST_SRID(POINT(%(longitude)s, %(latitude)s), 4326)
        )
        ELSE NULL
    END AS distance_m
FROM gold_map_points AS gmp
JOIN source_metadata AS sm ON sm.source_id = gmp.source_id
WHERE (%(country)s IS NULL OR LOWER(gmp.country_name) = LOWER(%(country)s))
  AND (%(city)s IS NULL OR LOWER(gmp.city_name) = LOWER(%(city)s))
  AND (
      %(min_rating)s IS NULL
      OR (gmp.rating IS NOT NULL AND gmp.rating >= %(min_rating)s)
  )
  AND (%(price_range)s IS NULL OR gmp.price_range = %(price_range)s)
  AND (
      %(cuisines_json)s IS NULL
      OR EXISTS (
          SELECT 1
          FROM restaurant_cuisines AS rc
          JOIN cuisines AS c ON c.cuisine_id = rc.cuisine_id
          JOIN JSON_TABLE(
              %(cuisines_json)s,
              '$[*]' COLUMNS (cuisine_name VARCHAR(100) PATH '$')
          ) AS jt ON LOWER(c.cuisine_name) = LOWER(jt.cuisine_name)
          WHERE rc.restaurant_id = gmp.restaurant_id
      )
  )
  AND (
      %(bounding_box_wkt)s IS NULL
      OR (
          MBRContains(ST_GeomFromText(%(bounding_box_wkt)s, 4326), gmp.location)
          AND ST_Distance_Sphere(
              gmp.location,
              ST_SRID(POINT(%(longitude)s, %(latitude)s), 4326)
          ) <= %(radius_m)s
      )
  )
ORDER BY
    CASE WHEN %(latitude)s IS NOT NULL THEN distance_m END ASC,
    gmp.rating IS NULL ASC,
    gmp.rating DESC,
    gmp.votes DESC,
    gmp.restaurant_id ASC
LIMIT %(limit)s
"""


@dataclass(frozen=True)
class RestaurantFilter:
    """Query criteria for restaurant search."""

    country: str | None = None
    city: str | None = None
    locality: str | None = None
    cuisine: tuple[str, ...] = ()
    cuisine_group: str | None = None
    min_rating: float | None = None
    max_cost_for_two: float | None = None
    max_cost_usd: float | None = None
    price_range: int | None = None
    has_online_delivery: bool | None = None
    has_table_booking: bool | None = None
    search_query: str | None = None
    sort_by: SortByOption = "rating"
    limit: int = DEFAULT_PAGE_LIMIT
    offset: int = 0


@dataclass(frozen=True)
class MapPointFilter:
    """Query criteria for map markers."""

    country: str | None = None
    city: str | None = None
    cuisine: tuple[str, ...] = ()
    min_rating: float | None = None
    price_range: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_m: float | None = None
    limit: int = DEFAULT_MAP_LIMIT


def _split_csv_list(raw_value: object) -> list[str]:
    """Split a GROUP_CONCAT string into a sorted list of non-empty tokens."""
    if raw_value is None:
        return []
    return [token.strip() for token in str(raw_value).split(",") if token.strip()]


def _to_decimal_or_none(value: object) -> Decimal | None:
    """Convert numeric SQL value to Decimal or None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_float_or_none(value: object) -> float | None:
    """Convert numeric SQL value to float or None."""
    if value is None:
        return None
    return float(str(value))


def _row_to_restaurant(
    row: Mapping[str, object],
) -> RestaurantOut:
    """Map a MySQL dictionary row from gold_restaurant_search to RestaurantOut."""
    dist_raw = row.get("distance_m")
    return RestaurantOut(
        restaurant_id=int(str(row["restaurant_id"])),
        source_restaurant_id=str(row["source_restaurant_id"]),
        source_name=str(row["source_name"]),
        source_license=str(row["source_license"]),
        name=str(row["name"]),
        country_name=str(row["country_name"]),
        iso_code=str(row["iso_code"]),
        city_name=str(row["city_name"]),
        locality=str(row["locality"]),
        address=str(row["address"]) if row["address"] is not None else None,
        latitude=_to_float_or_none(row.get("latitude")),
        longitude=_to_float_or_none(row.get("longitude")),
        cuisines=_split_csv_list(row.get("cuisines")),
        cuisine_groups=_split_csv_list(row.get("cuisine_groups")),
        avg_cost_for_two=_to_decimal_or_none(row.get("avg_cost_for_two")),
        currency_code=str(row["currency_code"]),
        avg_cost_for_two_usd=_to_decimal_or_none(row.get("avg_cost_for_two_usd")),
        price_range=int(str(row["price_range"])),
        rating=_to_float_or_none(row.get("rating")),
        rating_text=(
            str(row["rating_text"]) if row.get("rating_text") is not None else None
        ),
        votes=int(str(row["votes"])),
        has_table_booking=bool(row["has_table_booking"]),
        has_online_delivery=bool(row["has_online_delivery"]),
        distance_m=round(float(str(dist_raw)), 2) if dist_raw is not None else None,
    )


def _row_to_map_point(row: Mapping[str, object]) -> MapPointOut:
    """Map a MySQL dictionary row from gold_map_points to MapPointOut."""
    dist_raw = row.get("distance_m")
    return MapPointOut(
        restaurant_id=int(str(row["restaurant_id"])),
        name=str(row["name"]),
        country_name=str(row["country_name"]),
        city_name=str(row["city_name"]),
        locality=str(row["locality"]),
        latitude=float(str(row["latitude"])),
        longitude=float(str(row["longitude"])),
        cuisines=_split_csv_list(row.get("cuisines")),
        price_range=int(str(row["price_range"])),
        rating=_to_float_or_none(row.get("rating")),
        votes=int(str(row["votes"])),
        avg_cost_for_two=_to_decimal_or_none(row.get("avg_cost_for_two")),
        currency_code=str(row["currency_code"]),
        avg_cost_for_two_usd=_to_decimal_or_none(row.get("avg_cost_for_two_usd")),
        source_name=str(row["source_name"]),
        source_license=str(row["source_license"]),
        distance_m=round(float(str(dist_raw)), 2) if dist_raw is not None else None,
    )


def _matches_restaurant_filter(
    item: RestaurantOut,
    criteria: RestaurantFilter,
) -> bool:
    """Return True when an in-memory RestaurantOut satisfies all filter fields."""
    if criteria.country and item.country_name.lower() != criteria.country.lower():
        return False
    if criteria.city and item.city_name.lower() != criteria.city.lower():
        return False
    if criteria.locality and criteria.locality.lower() not in item.locality.lower():
        return False
    if criteria.cuisine:
        requested = {c.lower() for c in criteria.cuisine}
        item_cuisines = {c.lower() for c in item.cuisines}
        if not (requested & item_cuisines):
            return False
    if criteria.cuisine_group:
        item_groups = {g.lower() for g in item.cuisine_groups}
        if criteria.cuisine_group.lower() not in item_groups:
            return False
    if criteria.min_rating is not None and (
        item.rating is None or item.rating < criteria.min_rating
    ):
        return False
    if criteria.max_cost_for_two is not None and (
        item.avg_cost_for_two is None
        or item.avg_cost_for_two > Decimal(str(criteria.max_cost_for_two))
    ):
        return False
    if criteria.max_cost_usd is not None and (
        item.avg_cost_for_two_usd is None
        or item.avg_cost_for_two_usd > Decimal(str(criteria.max_cost_usd))
    ):
        return False
    if criteria.price_range is not None and item.price_range != criteria.price_range:
        return False
    if (
        criteria.has_online_delivery is not None
        and item.has_online_delivery != criteria.has_online_delivery
    ):
        return False
    if (
        criteria.has_table_booking is not None
        and item.has_table_booking != criteria.has_table_booking
    ):
        return False
    return not (
        criteria.search_query and criteria.search_query.lower() not in item.name.lower()
    )


def _sort_restaurants_in_memory(
    items: list[RestaurantOut],
    sort_by: SortByOption,
) -> list[RestaurantOut]:
    """Sort RestaurantOut items deterministically with NULLs sorted last."""
    if sort_by == "votes":
        return sorted(items, key=lambda r: (-r.votes, r.restaurant_id))
    if sort_by == "name":
        return sorted(items, key=lambda r: (r.name.lower(), r.restaurant_id))
    if sort_by == "cost_usd_asc":
        return sorted(
            items,
            key=lambda r: (
                r.avg_cost_for_two_usd is None,
                r.avg_cost_for_two_usd or Decimal("0"),
                r.restaurant_id,
            ),
        )
    if sort_by == "cost_usd_desc":
        return sorted(
            items,
            key=lambda r: (
                r.avg_cost_for_two_usd is None,
                -(r.avg_cost_for_two_usd or Decimal("0")),
                r.restaurant_id,
            ),
        )
    return sorted(
        items,
        key=lambda r: (
            r.rating is None,
            -(r.rating or 0.0),
            -r.votes,
            r.restaurant_id,
        ),
    )


class RestaurantRepository:
    """Repository for searching restaurants, map points, and recommendations."""

    def __init__(
        self,
        conn: DictCursorConnection | None,
        app_settings: BackendSettings | None = None,
    ) -> None:
        """Initialize the restaurant repository with an optional DB connection."""
        self._conn = conn
        self._settings = app_settings or settings

    def _snapshot(self) -> StandardizedCsvSnapshot:
        """Load the cached local CSV fallback snapshot."""
        return get_cached_csv_snapshot(
            self._settings.resolved_fallback_csv_path,
            self._settings.cuisine_map_path,
        )

    def search_restaurants(
        self,
        criteria: RestaurantFilter,
    ) -> tuple[list[RestaurantOut], int]:
        """Search restaurants with filters, sorting, and pagination."""
        if self._conn is None:
            matched = [
                item
                for item in self._snapshot().restaurants
                if _matches_restaurant_filter(item, criteria)
            ]
            ordered = _sort_restaurants_in_memory(matched, criteria.sort_by)
            total = len(ordered)
            page = ordered[criteria.offset : criteria.offset + criteria.limit]
            return page, total

        cuisines_json = json.dumps(list(criteria.cuisine)) if criteria.cuisine else None
        params: dict[str, object] = {
            "country": criteria.country,
            "city": criteria.city,
            "locality": criteria.locality,
            "min_rating": criteria.min_rating,
            "max_cost_for_two": criteria.max_cost_for_two,
            "max_cost_usd": criteria.max_cost_usd,
            "price_range": criteria.price_range,
            "has_online_delivery": criteria.has_online_delivery,
            "has_table_booking": criteria.has_table_booking,
            "search_query": criteria.search_query,
            "cuisine_group": criteria.cuisine_group,
            "cuisines_json": cuisines_json,
            "sort_by": criteria.sort_by,
            "limit": criteria.limit,
            "offset": criteria.offset,
        }
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(_RESTAURANT_COUNT_SQL, params)
                count_row = cursor.fetchone()
                total = int(count_row["total_count"]) if count_row else 0
                cursor.execute(_RESTAURANT_SEARCH_SQL, params)
                rows = cursor.fetchall()
            return [_row_to_restaurant(row) for row in rows], total
        except pymysql.MySQLError as exc:
            logger.error(
                "Restaurant search query failed",
                extra={"details": type(exc).__name__},
            )
            raise ServiceUnavailableError("Database query failed") from exc

    def get_restaurant_by_id(self, restaurant_id: int) -> RestaurantOut | None:
        """Fetch one restaurant by primary key or return None if missing."""
        if self._conn is None:
            return self._snapshot().by_id.get(restaurant_id)

        try:
            with self._conn.cursor() as cursor:
                cursor.execute(
                    _RESTAURANT_BY_ID_SQL,
                    {"restaurant_id": restaurant_id},
                )
                row = cursor.fetchone()
            return _row_to_restaurant(row) if row is not None else None
        except pymysql.MySQLError as exc:
            logger.error(
                "Restaurant detail query failed",
                extra={"details": type(exc).__name__},
            )
            raise ServiceUnavailableError("Database query failed") from exc

    def find_nearby(
        self,
        restaurant: RestaurantOut,
        radius_m: float = DEFAULT_NEARBY_RADIUS_M,
        limit: int = NEARBY_LIMIT,
    ) -> list[RestaurantOut]:
        """Find nearby geolocated restaurants within radius_m of the target venue."""
        if (
            not is_valid_coordinate(restaurant.latitude, restaurant.longitude)
            or restaurant.latitude is None
            or restaurant.longitude is None
        ):
            return []

        if self._conn is None:
            candidates: list[RestaurantOut] = []
            for item in self._snapshot().restaurants:
                if item.restaurant_id == restaurant.restaurant_id:
                    continue
                if (
                    not is_valid_coordinate(item.latitude, item.longitude)
                    or item.latitude is None
                    or item.longitude is None
                ):
                    continue
                dist_m = haversine_meters(
                    restaurant.latitude,
                    restaurant.longitude,
                    item.latitude,
                    item.longitude,
                )
                if dist_m <= radius_m:
                    candidates.append(
                        item.model_copy(update={"distance_m": round(dist_m, 2)})
                    )
            candidates.sort(
                key=lambda r: (
                    r.distance_m if r.distance_m is not None else float("inf"),
                    r.rating is None,
                    -(r.rating or 0.0),
                    r.restaurant_id,
                )
            )
            return candidates[:limit]

        try:
            wkt = bounding_box_wkt(restaurant.latitude, restaurant.longitude, radius_m)
        except ValueError:
            return []

        params: dict[str, object] = {
            "exclude_id": restaurant.restaurant_id,
            "latitude": restaurant.latitude,
            "longitude": restaurant.longitude,
            "radius_m": radius_m,
            "bounding_box_wkt": wkt,
            "srid": WGS84_SRID,
            "limit": limit,
        }
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(_NEARBY_SQL, params)
                rows = cursor.fetchall()
            return [_row_to_restaurant(row) for row in rows]
        except pymysql.MySQLError as exc:
            logger.error(
                "Nearby spatial query failed",
                extra={"details": type(exc).__name__},
            )
            raise ServiceUnavailableError("Database query failed") from exc

    def find_similar(
        self,
        restaurant: RestaurantOut,
        limit: int = SIMILAR_LIMIT,
    ) -> list[RestaurantOut]:
        """Find restaurants in the same city sharing the most cuisines."""
        if not restaurant.cuisines:
            return []

        if self._conn is None:
            target_cuisines = {c.lower() for c in restaurant.cuisines}
            scored: list[tuple[int, RestaurantOut]] = []
            for item in self._snapshot().restaurants:
                if item.restaurant_id == restaurant.restaurant_id:
                    continue
                if item.city_name.lower() != restaurant.city_name.lower():
                    continue
                overlap = len(target_cuisines & {c.lower() for c in item.cuisines})
                if overlap > 0:
                    scored.append((overlap, item))
            scored.sort(
                key=lambda pair: (
                    -pair[0],
                    pair[1].rating is None,
                    -(pair[1].rating or 0.0),
                    -pair[1].votes,
                    pair[1].restaurant_id,
                )
            )
            return [pair[1] for pair in scored[:limit]]

        params: dict[str, object] = {
            "exclude_id": restaurant.restaurant_id,
            "city_name": restaurant.city_name,
            "cuisines_json": json.dumps(restaurant.cuisines),
            "limit": limit,
        }
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(_SIMILAR_SQL, params)
                rows = cursor.fetchall()
            return [_row_to_restaurant(row) for row in rows]
        except pymysql.MySQLError as exc:
            logger.error(
                "Similar restaurants query failed",
                extra={"details": type(exc).__name__},
            )
            raise ServiceUnavailableError("Database query failed") from exc

    def get_map_points(
        self,
        criteria: MapPointFilter,
    ) -> list[MapPointOut]:
        """Return geolocated map markers filtered by attributes and optional radius."""
        wkt: str | None = None
        if (
            criteria.latitude is not None
            and criteria.longitude is not None
            and criteria.radius_m is not None
        ):
            wkt = bounding_box_wkt(
                criteria.latitude,
                criteria.longitude,
                criteria.radius_m,
            )

        if self._conn is None:
            points: list[MapPointOut] = []
            requested_cuisines = {c.lower() for c in criteria.cuisine}
            for item in self._snapshot().restaurants:
                if (
                    not is_valid_coordinate(item.latitude, item.longitude)
                    or item.latitude is None
                    or item.longitude is None
                ):
                    continue
                if criteria.country and (
                    item.country_name.lower() != criteria.country.lower()
                ):
                    continue
                if criteria.city and item.city_name.lower() != criteria.city.lower():
                    continue
                if criteria.min_rating is not None and (
                    item.rating is None or item.rating < criteria.min_rating
                ):
                    continue
                if (
                    criteria.price_range is not None
                    and item.price_range != criteria.price_range
                ):
                    continue
                if requested_cuisines and not (
                    requested_cuisines & {c.lower() for c in item.cuisines}
                ):
                    continue
                dist_m: float | None = None
                if (
                    criteria.latitude is not None
                    and criteria.longitude is not None
                    and criteria.radius_m is not None
                ):
                    dist_m = haversine_meters(
                        criteria.latitude,
                        criteria.longitude,
                        item.latitude,
                        item.longitude,
                    )
                    if dist_m > criteria.radius_m:
                        continue
                    dist_m = round(dist_m, 2)

                points.append(
                    MapPointOut(
                        restaurant_id=item.restaurant_id,
                        name=item.name,
                        country_name=item.country_name,
                        city_name=item.city_name,
                        locality=item.locality,
                        latitude=item.latitude,
                        longitude=item.longitude,
                        cuisines=item.cuisines,
                        price_range=item.price_range,
                        rating=item.rating,
                        votes=item.votes,
                        avg_cost_for_two=item.avg_cost_for_two,
                        currency_code=item.currency_code,
                        avg_cost_for_two_usd=item.avg_cost_for_two_usd,
                        source_name=item.source_name,
                        source_license=item.source_license,
                        distance_m=dist_m,
                    )
                )
            points.sort(
                key=lambda p: (
                    p.distance_m if p.distance_m is not None else 0.0,
                    p.rating is None,
                    -(p.rating or 0.0),
                    -p.votes,
                    p.restaurant_id,
                )
            )
            return points[: criteria.limit]

        cuisines_json = json.dumps(list(criteria.cuisine)) if criteria.cuisine else None
        params: dict[str, object] = {
            "country": criteria.country,
            "city": criteria.city,
            "min_rating": criteria.min_rating,
            "price_range": criteria.price_range,
            "cuisines_json": cuisines_json,
            "latitude": criteria.latitude,
            "longitude": criteria.longitude,
            "radius_m": criteria.radius_m,
            "bounding_box_wkt": wkt,
            "limit": criteria.limit,
        }
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(_MAP_POINTS_SQL, params)
                rows = cursor.fetchall()
            return [_row_to_map_point(row) for row in rows]
        except pymysql.MySQLError as exc:
            logger.error(
                "Map points query failed",
                extra={"details": type(exc).__name__},
            )
            raise ServiceUnavailableError("Database query failed") from exc
