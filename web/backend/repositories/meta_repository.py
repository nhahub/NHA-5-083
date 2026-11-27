"""Metadata, vocabulary, analytics, and destination queries."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass

import pymysql

from web.backend.constants import (
    DEFAULT_DESTINATION_CULTURE,
    DESTINATION_CULTURE,
    TOP_CITIES_LIMIT,
    TOP_CUISINES_LIMIT,
    TOP_DEST_CUISINES_LIMIT,
    TOP_RESTAURANTS_LIMIT,
)
from web.backend.exceptions import ServiceUnavailableError
from web.backend.repositories.csv_fallback import (
    StandardizedCsvSnapshot,
    get_cached_csv_snapshot,
)
from web.backend.repositories.db import DictCursorConnection
from web.backend.repositories.restaurant_repository import (
    RestaurantFilter,
    RestaurantRepository,
)
from web.backend.repositories.spatial import is_valid_coordinate
from web.backend.schemas.meta import (
    AnalyticsSummaryOut,
    CityMetaOut,
    CountBucketOut,
    CountryMetaOut,
    CuisineMetaOut,
    DestinationProfileOut,
    PriceRangeBucketOut,
    RatingBucketOut,
)
from web.backend.settings import BackendSettings, settings

logger = logging.getLogger(__name__)

_COUNTRIES_SQL = """
SELECT
    co.country_name,
    co.iso_code,
    co.currency_code,
    COUNT(r.restaurant_id) AS restaurant_count
FROM countries AS co
JOIN cities AS ci ON ci.country_id = co.country_id
JOIN locations AS l ON l.city_id = ci.city_id
JOIN restaurants AS r ON r.location_id = l.location_id
GROUP BY co.country_id, co.country_name, co.iso_code, co.currency_code
ORDER BY restaurant_count DESC, co.country_name ASC
"""

_CITIES_SQL = """
SELECT
    ci.city_name,
    co.country_name,
    COUNT(r.restaurant_id) AS restaurant_count
FROM cities AS ci
JOIN countries AS co ON co.country_id = ci.country_id
JOIN locations AS l ON l.city_id = ci.city_id
JOIN restaurants AS r ON r.location_id = l.location_id
WHERE (%(country)s IS NULL OR LOWER(co.country_name) = LOWER(%(country)s))
GROUP BY ci.city_id, ci.city_name, co.country_name
ORDER BY restaurant_count DESC, ci.city_name ASC
"""

_LOCALITIES_SQL = """
SELECT DISTINCT l.locality
FROM locations AS l
ORDER BY l.locality ASC
"""

_CUISINES_SQL = """
SELECT
    c.cuisine_name,
    c.cuisine_group,
    COUNT(rc.restaurant_id) AS restaurant_count
FROM cuisines AS c
JOIN restaurant_cuisines AS rc ON rc.cuisine_id = c.cuisine_id
GROUP BY c.cuisine_id, c.cuisine_name, c.cuisine_group
ORDER BY restaurant_count DESC, c.cuisine_name ASC
"""

_ANALYTICS_CORE_SQL = """
SELECT
    COUNT(r.restaurant_id) AS total_restaurants,
    COUNT(DISTINCT co.country_id) AS total_countries,
    COUNT(DISTINCT ci.city_id) AS total_cities,
    SUM(
        CASE WHEN r.latitude IS NOT NULL AND r.longitude IS NOT NULL THEN 1 ELSE 0 END
    ) AS geolocated_count,
    SUM(CASE WHEN r.rating IS NOT NULL THEN 1 ELSE 0 END) AS rated_count,
    SUM(CASE WHEN r.rating IS NULL THEN 1 ELSE 0 END) AS unrated_count,
    ROUND(AVG(r.rating), 2) AS avg_rating
FROM restaurants AS r
JOIN locations AS l ON l.location_id = r.location_id
JOIN cities AS ci ON ci.city_id = l.city_id
JOIN countries AS co ON co.country_id = ci.country_id
WHERE (%(country)s IS NULL OR LOWER(co.country_name) = LOWER(%(country)s))
"""

_ANALYTICS_CUISINE_COUNT_SQL = """
SELECT COUNT(DISTINCT rc.cuisine_id) AS total_cuisines
FROM restaurant_cuisines AS rc
JOIN restaurants AS r ON r.restaurant_id = rc.restaurant_id
JOIN locations AS l ON l.location_id = r.location_id
JOIN cities AS ci ON ci.city_id = l.city_id
JOIN countries AS co ON co.country_id = ci.country_id
WHERE (%(country)s IS NULL OR LOWER(co.country_name) = LOWER(%(country)s))
"""

_ANALYTICS_TOP_CUISINES_SQL = """
SELECT
    c.cuisine_name AS label,
    COUNT(DISTINCT r.restaurant_id) AS item_count
FROM cuisines AS c
JOIN restaurant_cuisines AS rc ON rc.cuisine_id = c.cuisine_id
JOIN restaurants AS r ON r.restaurant_id = rc.restaurant_id
JOIN locations AS l ON l.location_id = r.location_id
JOIN cities AS ci ON ci.city_id = l.city_id
JOIN countries AS co ON co.country_id = ci.country_id
WHERE (%(country)s IS NULL OR LOWER(co.country_name) = LOWER(%(country)s))
GROUP BY c.cuisine_id, c.cuisine_name
ORDER BY item_count DESC, c.cuisine_name ASC
LIMIT %(limit)s
"""

_ANALYTICS_BY_COUNTRY_SQL = """
SELECT
    co.country_name AS label,
    COUNT(r.restaurant_id) AS item_count
FROM restaurants AS r
JOIN locations AS l ON l.location_id = r.location_id
JOIN cities AS ci ON ci.city_id = l.city_id
JOIN countries AS co ON co.country_id = ci.country_id
WHERE (%(country)s IS NULL OR LOWER(co.country_name) = LOWER(%(country)s))
GROUP BY co.country_id, co.country_name
ORDER BY item_count DESC, co.country_name ASC
"""

_ANALYTICS_BY_PRICE_SQL = """
SELECT
    r.price_range,
    COUNT(r.restaurant_id) AS item_count
FROM restaurants AS r
JOIN locations AS l ON l.location_id = r.location_id
JOIN cities AS ci ON ci.city_id = l.city_id
JOIN countries AS co ON co.country_id = ci.country_id
WHERE (%(country)s IS NULL OR LOWER(co.country_name) = LOWER(%(country)s))
GROUP BY r.price_range
ORDER BY r.price_range ASC
"""

_ANALYTICS_RATING_DIST_SQL = """
SELECT
    COALESCE(r.rating_text, 'Unrated') AS rating_label,
    COUNT(r.restaurant_id) AS item_count,
    ROUND(AVG(r.rating), 2) AS avg_rating
FROM restaurants AS r
JOIN locations AS l ON l.location_id = r.location_id
JOIN cities AS ci ON ci.city_id = l.city_id
JOIN countries AS co ON co.country_id = ci.country_id
WHERE (%(country)s IS NULL OR LOWER(co.country_name) = LOWER(%(country)s))
GROUP BY COALESCE(r.rating_text, 'Unrated')
ORDER BY item_count DESC, rating_label ASC
"""


@dataclass(frozen=True)
class VocabularySnapshot:
    """Known valid entity names used to constrain NLP extraction."""

    countries: tuple[str, ...]
    cities: tuple[str, ...]
    localities: tuple[str, ...]
    cuisines: tuple[str, ...]
    cuisine_groups: tuple[str, ...]
    cuisine_synonyms: dict[str, str]


class MetaRepository:
    """Repository for filter metadata, NLP vocabulary, analytics, and destinations."""

    def __init__(
        self,
        conn: DictCursorConnection | None,
        app_settings: BackendSettings | None = None,
    ) -> None:
        """Initialize the metadata repository with an optional DB connection."""
        self._conn = conn
        self._settings = app_settings or settings

    def _snapshot(self) -> StandardizedCsvSnapshot:
        """Load the cached local CSV fallback snapshot."""
        return get_cached_csv_snapshot(
            self._settings.resolved_fallback_csv_path,
            self._settings.cuisine_map_path,
        )

    def get_countries(self) -> list[CountryMetaOut]:
        """Return countries with ISO code, currency code, and restaurant counts."""
        if self._conn is None:
            counts: Counter[tuple[str, str, str]] = Counter()
            for item in self._snapshot().restaurants:
                counts[(item.country_name, item.iso_code, item.currency_code)] += 1
            return [
                CountryMetaOut(
                    country_name=name,
                    iso_code=iso_code,
                    currency_code=currency_code,
                    restaurant_count=count,
                )
                for (name, iso_code, currency_code), count in sorted(
                    counts.items(),
                    key=lambda pair: (-pair[1], pair[0][0]),
                )
            ]

        try:
            with self._conn.cursor() as cursor:
                cursor.execute(_COUNTRIES_SQL)
                rows = cursor.fetchall()
            return [
                CountryMetaOut(
                    country_name=str(row["country_name"]),
                    iso_code=str(row["iso_code"]),
                    currency_code=str(row["currency_code"]),
                    restaurant_count=int(str(row["restaurant_count"])),
                )
                for row in rows
            ]
        except pymysql.MySQLError as exc:
            logger.error(
                "Countries metadata query failed",
                extra={"details": type(exc).__name__},
            )
            raise ServiceUnavailableError("Database query failed") from exc

    def get_cities(self, country: str | None = None) -> list[CityMetaOut]:
        """Return cities optionally filtered by country, ordered by count DESC."""
        if self._conn is None:
            counts: Counter[tuple[str, str]] = Counter()
            for item in self._snapshot().restaurants:
                if country and item.country_name.lower() != country.lower():
                    continue
                counts[(item.city_name, item.country_name)] += 1
            return [
                CityMetaOut(
                    city_name=city_name,
                    country_name=country_name,
                    restaurant_count=count,
                )
                for (city_name, country_name), count in sorted(
                    counts.items(),
                    key=lambda pair: (-pair[1], pair[0][0]),
                )
            ]

        try:
            with self._conn.cursor() as cursor:
                cursor.execute(_CITIES_SQL, {"country": country})
                rows = cursor.fetchall()
            return [
                CityMetaOut(
                    city_name=str(row["city_name"]),
                    country_name=str(row["country_name"]),
                    restaurant_count=int(str(row["restaurant_count"])),
                )
                for row in rows
            ]
        except pymysql.MySQLError as exc:
            logger.error(
                "Cities metadata query failed",
                extra={"details": type(exc).__name__},
            )
            raise ServiceUnavailableError("Database query failed") from exc

    def get_cuisines(self) -> list[CuisineMetaOut]:
        """Return canonical cuisines with group and restaurant counts."""
        if self._conn is None:
            snapshot = self._snapshot()
            counts: Counter[str] = Counter()
            group_lookup: dict[str, str] = dict(snapshot.cuisine_groups_by_name)
            for item in snapshot.restaurants:
                for idx, cuisine_name in enumerate(item.cuisines):
                    counts[cuisine_name] += 1
                    if cuisine_name not in group_lookup and idx < len(
                        item.cuisine_groups
                    ):
                        group_lookup[cuisine_name] = item.cuisine_groups[idx]
            return [
                CuisineMetaOut(
                    cuisine_name=name,
                    cuisine_group=group_lookup.get(name, "Other"),
                    restaurant_count=count,
                )
                for name, count in sorted(
                    counts.items(),
                    key=lambda pair: (-pair[1], pair[0]),
                )
            ]

        try:
            with self._conn.cursor() as cursor:
                cursor.execute(_CUISINES_SQL)
                rows = cursor.fetchall()
            return [
                CuisineMetaOut(
                    cuisine_name=str(row["cuisine_name"]),
                    cuisine_group=str(row["cuisine_group"]),
                    restaurant_count=int(str(row["restaurant_count"])),
                )
                for row in rows
            ]
        except pymysql.MySQLError as exc:
            logger.error(
                "Cuisines metadata query failed",
                extra={"details": type(exc).__name__},
            )
            raise ServiceUnavailableError("Database query failed") from exc

    def get_vocabulary(self) -> VocabularySnapshot:
        """Return known countries, cities, localities, cuisines, and groups."""
        countries = tuple(c.country_name for c in self.get_countries())
        cities = tuple(c.city_name for c in self.get_cities())
        cuisines_meta = self.get_cuisines()
        cuisines = tuple(c.cuisine_name for c in cuisines_meta)
        cuisine_groups = tuple(sorted({c.cuisine_group for c in cuisines_meta}))

        if self._conn is None:
            localities = tuple(
                sorted({item.locality for item in self._snapshot().restaurants})
            )
        else:
            try:
                with self._conn.cursor() as cursor:
                    cursor.execute(_LOCALITIES_SQL)
                    rows = cursor.fetchall()
                localities = tuple(str(row["locality"]) for row in rows)
            except pymysql.MySQLError as exc:
                logger.error(
                    "Localities vocabulary query failed",
                    extra={"details": type(exc).__name__},
                )
                raise ServiceUnavailableError("Database query failed") from exc

        return VocabularySnapshot(
            countries=countries,
            cities=cities,
            localities=localities,
            cuisines=cuisines,
            cuisine_groups=cuisine_groups,
            cuisine_synonyms={},
        )

    def get_analytics(self, country: str | None = None) -> AnalyticsSummaryOut:
        """Return aggregated counts, ratings, and breakdowns."""
        if self._conn is None:
            items = [
                item
                for item in self._snapshot().restaurants
                if not country or item.country_name.lower() == country.lower()
            ]
            total = len(items)
            countries_set = {item.country_name for item in items}
            cities_set = {item.city_name for item in items}
            cuisines_set = {c for item in items for c in item.cuisines}
            geolocated_count = sum(
                1
                for item in items
                if is_valid_coordinate(item.latitude, item.longitude)
            )
            rated_values = [item.rating for item in items if item.rating is not None]
            rated_count = len(rated_values)
            unrated_count = total - rated_count
            avg_rating = (
                round(sum(rated_values) / rated_count, 2) if rated_count > 0 else None
            )

            cuisine_counts: Counter[str] = Counter()
            country_counts: Counter[str] = Counter()
            price_counts: Counter[int] = Counter()
            rating_buckets: dict[str, list[float | None]] = {}
            for item in items:
                for cuisine in item.cuisines:
                    cuisine_counts[cuisine] += 1
                country_counts[item.country_name] += 1
                price_counts[item.price_range] += 1
                label = item.rating_text or "Unrated"
                rating_buckets.setdefault(label, []).append(item.rating)

            return AnalyticsSummaryOut(
                total_restaurants=total,
                total_countries=len(countries_set),
                total_cities=len(cities_set),
                total_cuisines=len(cuisines_set),
                geolocated_count=geolocated_count,
                rated_count=rated_count,
                unrated_count=unrated_count,
                avg_rating=avg_rating,
                top_cuisines=[
                    CountBucketOut(label=label, count=count)
                    for label, count in sorted(
                        cuisine_counts.items(),
                        key=lambda pair: (-pair[1], pair[0]),
                    )[:TOP_CUISINES_LIMIT]
                ],
                by_country=[
                    CountBucketOut(label=label, count=count)
                    for label, count in sorted(
                        country_counts.items(),
                        key=lambda pair: (-pair[1], pair[0]),
                    )
                ],
                by_price_range=[
                    PriceRangeBucketOut(price_range=pr, count=count)
                    for pr, count in sorted(price_counts.items())
                ],
                rating_distribution=[
                    RatingBucketOut(
                        rating_label=label,
                        count=len(vals),
                        avg_rating=(
                            round(
                                sum(v for v in vals if v is not None)
                                / len([v for v in vals if v is not None]),
                                2,
                            )
                            if any(v is not None for v in vals)
                            else None
                        ),
                    )
                    for label, vals in sorted(
                        rating_buckets.items(),
                        key=lambda pair: (-len(pair[1]), pair[0]),
                    )
                ],
            )

        params = {"country": country}
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(_ANALYTICS_CORE_SQL, params)
                core = cursor.fetchone() or {}
                cursor.execute(_ANALYTICS_CUISINE_COUNT_SQL, params)
                cuisine_count_row = cursor.fetchone() or {}
                cursor.execute(
                    _ANALYTICS_TOP_CUISINES_SQL,
                    {"country": country, "limit": TOP_CUISINES_LIMIT},
                )
                top_cuisines_rows = cursor.fetchall()
                cursor.execute(_ANALYTICS_BY_COUNTRY_SQL, params)
                by_country_rows = cursor.fetchall()
                cursor.execute(_ANALYTICS_BY_PRICE_SQL, params)
                by_price_rows = cursor.fetchall()
                cursor.execute(_ANALYTICS_RATING_DIST_SQL, params)
                rating_dist_rows = cursor.fetchall()

            return AnalyticsSummaryOut(
                total_restaurants=int(str(core.get("total_restaurants") or 0)),
                total_countries=int(str(core.get("total_countries") or 0)),
                total_cities=int(str(core.get("total_cities") or 0)),
                total_cuisines=int(str(cuisine_count_row.get("total_cuisines") or 0)),
                geolocated_count=int(str(core.get("geolocated_count") or 0)),
                rated_count=int(str(core.get("rated_count") or 0)),
                unrated_count=int(str(core.get("unrated_count") or 0)),
                avg_rating=(
                    float(str(core["avg_rating"]))
                    if core.get("avg_rating") is not None
                    else None
                ),
                top_cuisines=[
                    CountBucketOut(
                        label=str(row["label"]),
                        count=int(str(row["item_count"])),
                    )
                    for row in top_cuisines_rows
                ],
                by_country=[
                    CountBucketOut(
                        label=str(row["label"]),
                        count=int(str(row["item_count"])),
                    )
                    for row in by_country_rows
                ],
                by_price_range=[
                    PriceRangeBucketOut(
                        price_range=int(str(row["price_range"])),
                        count=int(str(row["item_count"])),
                    )
                    for row in by_price_rows
                ],
                rating_distribution=[
                    RatingBucketOut(
                        rating_label=str(row["rating_label"]),
                        count=int(str(row["item_count"])),
                        avg_rating=(
                            float(str(row["avg_rating"]))
                            if row.get("avg_rating") is not None
                            else None
                        ),
                    )
                    for row in rating_dist_rows
                ],
            )
        except pymysql.MySQLError as exc:
            logger.error(
                "Analytics query failed",
                extra={"details": type(exc).__name__},
            )
            raise ServiceUnavailableError("Database query failed") from exc

    def get_destination_profile(
        self,
        country: str,
    ) -> DestinationProfileOut | None:
        """Build cultural metadata and live statistics for a single country."""
        countries = {c.country_name.lower(): c for c in self.get_countries()}
        matched_country = countries.get(country.strip().lower())
        if matched_country is None:
            return None

        canonical_country = matched_country.country_name
        cities = self.get_cities(country=canonical_country)
        analytics = self.get_analytics(country=canonical_country)
        restaurant_repo = RestaurantRepository(self._conn, self._settings)
        top_restaurants, _ = restaurant_repo.search_restaurants(
            RestaurantFilter(
                country=canonical_country,
                sort_by="rating",
                limit=TOP_RESTAURANTS_LIMIT,
                offset=0,
            )
        )
        culture = DESTINATION_CULTURE.get(
            canonical_country,
            DEFAULT_DESTINATION_CULTURE,
        )
        return DestinationProfileOut(
            country_name=canonical_country,
            currency_code=matched_country.currency_code,
            tagline=culture["tagline"],
            dining_tradition=culture["dining_tradition"],
            signature_dishes=list(culture["signature_dishes"]),
            attribution=culture["attribution"],
            restaurant_count=matched_country.restaurant_count,
            city_count=len(cities),
            avg_rating=analytics.avg_rating,
            top_cities=[city.city_name for city in cities[:TOP_CITIES_LIMIT]],
            top_cuisines=[
                bucket.label
                for bucket in analytics.top_cuisines[:TOP_DEST_CUISINES_LIMIT]
            ],
            top_restaurants=top_restaurants,
        )
