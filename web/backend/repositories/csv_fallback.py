"""Cached local CSV fallback dataset applying Silver/Gold domain rules."""

from __future__ import annotations

import logging
import threading
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from web.backend.constants import (
    COUNTRY_CODE_TO_METADATA,
    DEFAULT_CSV_ENCODING,
    DEFAULT_PINNED_FX_RATES_TO_USD,
    MAX_ABS_LONGITUDE,
    MAX_GEO_LATITUDE,
    MAX_PRICE_RANGE,
    MAX_RATING,
    MIN_PRICE_RANGE,
    MIN_RATING,
    MOJIBAKE_REPLACEMENTS,
    ZOMATO_SOURCE_ID,
    ZOMATO_SOURCE_LICENSE,
    ZOMATO_SOURCE_NAME,
)
from web.backend.exceptions import ServiceUnavailableError
from web.backend.repositories.spatial import is_valid_coordinate
from web.backend.schemas.pipeline import PipelineRunOut, QualityRuleCountOut
from web.backend.schemas.restaurant import RestaurantOut

logger = logging.getLogger(__name__)

_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOT_CACHE: dict[tuple[Path, Path], StandardizedCsvSnapshot] = {}

ZOMATO_RAW_DTYPES: dict[str, str] = {
    "Restaurant ID": "string",
    "Restaurant Name": "string",
    "Country Code": "string",
    "City": "string",
    "Address": "string",
    "Locality": "string",
    "Locality Verbose": "string",
    "Longitude": "float64",
    "Latitude": "float64",
    "Cuisines": "string",
    "Average Cost for two": "string",
    "Currency": "string",
    "Has Table booking": "string",
    "Has Online delivery": "string",
    "Is delivering now": "string",
    "Switch to order menu": "string",
    "Price range": "string",
    "Aggregate rating": "float64",
    "Rating color": "string",
    "Rating text": "string",
    "Votes": "string",
}


@dataclass(frozen=True)
class CuisineMappingEntry:
    """Canonical cuisine and cuisine group entry."""

    canonical_cuisine: str
    cuisine_group: str


@dataclass(frozen=True)
class StandardizedCsvSnapshot:
    """In-memory standardized representation of the local Zomato CSV."""

    restaurants: tuple[RestaurantOut, ...]
    by_id: dict[int, RestaurantOut]
    cuisine_groups_by_name: dict[str, str]
    synthetic_run: PipelineRunOut
    quality_breakdown: tuple[QualityRuleCountOut, ...]


def _repair_text(raw_value: object, warning_counts: dict[str, int]) -> str:
    """Repair known mojibake sequences and normalize text to Unicode NFC."""
    if raw_value is None or pd.isna(raw_value):
        return ""
    text = str(raw_value).strip()
    repaired = False
    for broken, fixed in MOJIBAKE_REPLACEMENTS.items():
        if broken in text:
            text = text.replace(broken, fixed)
            repaired = True
    if repaired:
        warning_counts["text_mojibake_repaired"] = (
            warning_counts.get("text_mojibake_repaired", 0) + 1
        )
    return unicodedata.normalize("NFC", text)


def _load_cuisine_map(cuisine_map_path: Path) -> dict[str, CuisineMappingEntry]:
    """Load config/cuisine_map.csv into a source-label lookup map."""
    if not cuisine_map_path.is_file():
        return {}
    cuisine_map_df = pd.read_csv(
        cuisine_map_path,
        encoding="utf-8",
        dtype={
            "source_label": "string",
            "canonical_cuisine": "string",
            "cuisine_group": "string",
        },
    )
    mapping: dict[str, CuisineMappingEntry] = {}
    for row in cuisine_map_df.to_dict(orient="records"):
        source_label = unicodedata.normalize("NFC", str(row["source_label"]).strip())
        canonical = unicodedata.normalize("NFC", str(row["canonical_cuisine"]).strip())
        group = unicodedata.normalize("NFC", str(row["cuisine_group"]).strip())
        mapping[source_label] = CuisineMappingEntry(
            canonical_cuisine=canonical,
            cuisine_group=group,
        )
    return mapping


def _parse_cuisines(
    raw_cuisines: object,
    cuisine_map: dict[str, CuisineMappingEntry],
    warning_counts: dict[str, int],
) -> tuple[list[str], list[str]]:
    """Split, repair, and canonicalize comma-separated cuisines."""
    cleaned_raw = _repair_text(raw_cuisines, warning_counts)
    if not cleaned_raw:
        warning_counts["cuisine_missing"] = warning_counts.get("cuisine_missing", 0) + 1
        return [], []

    canonical_set: set[str] = set()
    group_set: set[str] = set()
    for token in cleaned_raw.split(","):
        label = token.strip()
        if not label:
            continue
        entry = cuisine_map.get(label)
        if entry is not None:
            canonical_set.add(entry.canonical_cuisine)
            group_set.add(entry.cuisine_group)
        else:
            canonical_set.add(label)
            group_set.add("Other")
            warning_counts["cuisine_unmapped"] = (
                warning_counts.get("cuisine_unmapped", 0) + 1
            )
    return sorted(canonical_set), sorted(group_set)


def _parse_decimal_cost(
    raw_cost: object,
    currency_code: str,
    warning_counts: dict[str, int],
) -> tuple[Decimal | None, Decimal | None]:
    """Convert raw cost to Decimal, mapping zero to None and computing USD."""
    if raw_cost is None or pd.isna(raw_cost):
        return None, None
    try:
        cost_val = Decimal(str(raw_cost).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None, None
    if cost_val <= Decimal("0.00"):
        warning_counts["cost_zero"] = warning_counts.get("cost_zero", 0) + 1
        return None, None
    fx_rate = DEFAULT_PINNED_FX_RATES_TO_USD.get(currency_code, Decimal("1.000000"))
    cost_usd = (cost_val * fx_rate).quantize(Decimal("0.01"))
    return cost_val, cost_usd


def _parse_coordinates(
    raw_lat: object,
    raw_lon: object,
    warning_counts: dict[str, int],
) -> tuple[float | None, float | None]:
    """Validate WGS84 coordinates, converting missing or zero values to None."""
    if raw_lat is None or raw_lon is None or pd.isna(raw_lat) or pd.isna(raw_lon):
        warning_counts["coordinates_missing"] = (
            warning_counts.get("coordinates_missing", 0) + 1
        )
        return None, None
    lat = float(str(raw_lat))
    lon = float(str(raw_lon))
    if lat == 0.0 or lon == 0.0:
        warning_counts["coordinates_missing"] = (
            warning_counts.get("coordinates_missing", 0) + 1
        )
        return None, None
    if abs(lat) > MAX_GEO_LATITUDE or abs(lon) > MAX_ABS_LONGITUDE:
        warning_counts["coordinates_out_of_range"] = (
            warning_counts.get("coordinates_out_of_range", 0) + 1
        )
        return None, None
    if not is_valid_coordinate(lat, lon):
        return None, None
    return round(lat, 6), round(lon, 6)


def _parse_rating(
    raw_rating: object,
    raw_rating_text: object,
) -> tuple[float | None, str | None]:
    """Convert Zomato rating 0 / 'Not rated' into None."""
    rating_text = (
        str(raw_rating_text).strip()
        if raw_rating_text is not None and not pd.isna(raw_rating_text)
        else None
    )
    if raw_rating is None or pd.isna(raw_rating):
        return None, rating_text or "Not rated"
    rating_val = float(str(raw_rating))
    if (
        rating_val == 0.0
        or (rating_text is not None and rating_text.lower() == "not rated")
        or not (MIN_RATING <= rating_val <= MAX_RATING)
    ):
        return None, rating_text or "Not rated"
    return round(rating_val, 1), rating_text


def _build_snapshot(
    csv_path: Path,
    cuisine_map_path: Path,
) -> StandardizedCsvSnapshot:
    """Read and standardize the local Zomato CSV snapshot into memory."""
    if not csv_path.is_file():
        raise ServiceUnavailableError(
            "Local fallback dataset file was not found",
            details=str(csv_path),
        )

    zomato_df = pd.read_csv(
        csv_path,
        encoding=DEFAULT_CSV_ENCODING,
        dtype=ZOMATO_RAW_DTYPES,
    )
    cuisine_map = _load_cuisine_map(cuisine_map_path)
    cuisine_groups_by_name = {
        entry.canonical_cuisine: entry.cuisine_group for entry in cuisine_map.values()
    }
    warning_counts: dict[str, int] = {}
    restaurants: list[RestaurantOut] = []
    seen_ids: set[int] = set()
    quarantined_count = 0

    for row in zomato_df.to_dict(orient="records"):
        raw_id = str(row.get("Restaurant ID") or "").strip()
        if not raw_id.isdigit():
            quarantined_count += 1
            continue
        restaurant_id = int(raw_id)
        if restaurant_id in seen_ids:
            quarantined_count += 1
            continue

        raw_country_code = str(row.get("Country Code") or "").strip()
        if not raw_country_code.isdigit():
            quarantined_count += 1
            continue
        country_meta = COUNTRY_CODE_TO_METADATA.get(int(raw_country_code))
        if country_meta is None:
            quarantined_count += 1
            continue

        name = _repair_text(row.get("Restaurant Name"), warning_counts)
        city_name = _repair_text(row.get("City"), warning_counts)
        if not name or not city_name:
            quarantined_count += 1
            continue

        raw_price = str(row.get("Price range") or "").strip()
        if not raw_price.isdigit():
            quarantined_count += 1
            continue
        price_range = int(raw_price)
        if not (MIN_PRICE_RANGE <= price_range <= MAX_PRICE_RANGE):
            quarantined_count += 1
            continue

        raw_votes = str(row.get("Votes") or "0").strip()
        votes = int(raw_votes) if raw_votes.isdigit() else 0

        seen_ids.add(restaurant_id)
        locality = _repair_text(row.get("Locality"), warning_counts) or city_name
        address_text = _repair_text(row.get("Address"), warning_counts)
        address = address_text or None

        cuisines, cuisine_groups = _parse_cuisines(
            row.get("Cuisines"),
            cuisine_map,
            warning_counts,
        )
        cost, cost_usd = _parse_decimal_cost(
            row.get("Average Cost for two"),
            country_meta["currency_code"],
            warning_counts,
        )
        lat, lon = _parse_coordinates(
            row.get("Latitude"),
            row.get("Longitude"),
            warning_counts,
        )
        rating, rating_text = _parse_rating(
            row.get("Aggregate rating"),
            row.get("Rating text"),
        )
        has_table_booking = (
            str(row.get("Has Table booking") or "").strip().lower() == "yes"
        )
        has_online_delivery = (
            str(row.get("Has Online delivery") or "").strip().lower() == "yes"
        )

        restaurants.append(
            RestaurantOut(
                restaurant_id=restaurant_id,
                source_restaurant_id=raw_id,
                source_name=ZOMATO_SOURCE_NAME,
                source_license=ZOMATO_SOURCE_LICENSE,
                name=name,
                country_name=country_meta["country_name"],
                iso_code=country_meta["iso_code"],
                city_name=city_name,
                locality=locality,
                address=address,
                latitude=lat,
                longitude=lon,
                cuisines=cuisines,
                cuisine_groups=cuisine_groups,
                avg_cost_for_two=cost,
                currency_code=country_meta["currency_code"],
                avg_cost_for_two_usd=cost_usd,
                price_range=price_range,
                rating=rating,
                rating_text=rating_text,
                votes=votes,
                has_table_booking=has_table_booking,
                has_online_delivery=has_online_delivery,
                distance_m=None,
            )
        )

    now_utc = datetime.now(UTC)
    total_read = len(zomato_df)
    quarantine_rate = (
        (Decimal(quarantined_count) / Decimal(total_read)).quantize(Decimal("0.0001"))
        if total_read > 0
        else Decimal("0.0000")
    )
    total_warned = sum(warning_counts.values())
    synthetic_run = PipelineRunOut(
        run_id="local_csv_fallback",
        dag_id="local_csv_fallback",
        source_id=ZOMATO_SOURCE_ID,
        source_name=ZOMATO_SOURCE_NAME,
        started_at=now_utc,
        ended_at=now_utc,
        status="success",
        rows_read=total_read,
        rows_inserted=len(restaurants),
        rows_updated=0,
        rows_unchanged=0,
        rows_quarantined=quarantined_count,
        rows_warned=total_warned,
        quarantine_rate=quarantine_rate,
    )
    quality_breakdown = tuple(
        QualityRuleCountOut(rule_name=rule, severity="warning", count=count)
        for rule, count in sorted(warning_counts.items())
    )
    by_id = {item.restaurant_id: item for item in restaurants}
    logger.info(
        "Loaded local CSV fallback snapshot",
        extra={
            "run_id": "local_csv_fallback",
            "source_id": ZOMATO_SOURCE_ID,
        },
    )
    return StandardizedCsvSnapshot(
        restaurants=tuple(restaurants),
        by_id=by_id,
        cuisine_groups_by_name=cuisine_groups_by_name,
        synthetic_run=synthetic_run,
        quality_breakdown=quality_breakdown,
    )


def get_cached_csv_snapshot(
    csv_path: Path,
    cuisine_map_path: Path,
) -> StandardizedCsvSnapshot:
    """Return a cached StandardizedCsvSnapshot for the given CSV and cuisine map."""
    key = (csv_path.resolve(), cuisine_map_path.resolve())
    with _SNAPSHOT_LOCK:
        cached = _SNAPSHOT_CACHE.get(key)
        if cached is not None:
            return cached
        snapshot = _build_snapshot(csv_path, cuisine_map_path)
        _SNAPSHOT_CACHE[key] = snapshot
        return snapshot


def clear_csv_snapshot_cache() -> None:
    """Clear the cached CSV fallback snapshot (primarily for testing)."""
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_CACHE.clear()
