"""Field-level standardization, mojibake repair, and deterministic record hashing."""

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pipeline.constants import (
    BOOLEAN_FALSE_LABEL,
    BOOLEAN_TRUE_LABEL,
    COORD_ZERO,
    DECIMAL_COORD_QUANT,
    DECIMAL_RATING_QUANT,
    KNOWN_MOJIBAKE_MAP,
    MAX_ABS_LATITUDE,
    MAX_ABS_LONGITUDE,
    MIN_COST,
    RATING_NOT_RATED_TEXT,
)
from pipeline.transform.cuisines import CuisineMapping


@dataclass(frozen=True)
class StandardizedRestaurant:
    """Canonical Silver-layer representation of a validated restaurant row."""

    source_id: int
    source_restaurant_id: str
    name: str
    source_country_code: int
    country_name: str
    iso_code: str
    city_name: str
    locality: str
    address: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    avg_cost_for_two: Decimal | None
    currency_code: str
    avg_cost_for_two_usd: Decimal | None
    fx_rate: Decimal
    fx_rate_date: date
    price_range: int
    rating: Decimal | None
    rating_color: str | None
    rating_text: str | None
    votes: int
    has_table_booking: bool
    has_online_delivery: bool
    is_delivering_now: bool
    switch_to_order_menu: bool
    cuisines: tuple[CuisineMapping, ...]
    record_hash: str


def repair_text(
    raw_value: str | None, *, max_length: int | None = None
) -> tuple[str, bool]:
    """Repair known mojibake sequences, normalize Unicode to NFC, and trim.

    Args:
        raw_value: Input string or ``None``.
        max_length: Optional maximum character length to truncate after cleanup.

    Returns:
        Tuple of ``(cleaned_text, was_repaired)``.
    """
    if raw_value is None:
        return "", False

    repaired = raw_value
    was_repaired = False
    for broken, fixed in KNOWN_MOJIBAKE_MAP.items():
        if broken in repaired:
            repaired = repaired.replace(broken, fixed)
            was_repaired = True

    normalized = unicodedata.normalize("NFC", repaired).strip()
    if max_length is not None and len(normalized) > max_length:
        normalized = normalized[:max_length].rstrip()
    return normalized, was_repaired


def parse_boolean_flag(raw_value: str | None) -> bool | None:
    """Parse Zomato ``Yes`` / ``No`` boolean strings.

    Args:
        raw_value: Raw field text.

    Returns:
        ``True`` for ``Yes``, ``False`` for ``No``, or ``None`` if invalid.
    """
    if raw_value is None:
        return None
    cleaned = raw_value.strip()
    if cleaned == BOOLEAN_TRUE_LABEL:
        return True
    if cleaned == BOOLEAN_FALSE_LABEL:
        return False
    return None


def parse_rating(
    raw_rating: str | None,
    raw_rating_text: str | None,
    *,
    min_rating: float,
    max_rating: float,
) -> tuple[Decimal | None, bool]:
    """Parse rating, converting Zomato ``0`` + ``Not rated`` to ``None``.

    Args:
        raw_rating: Raw ``Aggregate rating`` text.
        raw_rating_text: Raw ``Rating text`` label.
        min_rating: Inclusive lower rating bound.
        max_rating: Inclusive upper rating bound.

    Returns:
        Tuple of ``(rating_decimal_or_none, is_valid)``.
    """
    if raw_rating is None or not raw_rating.strip():
        return None, True

    try:
        numeric_val = Decimal(raw_rating.strip())
    except InvalidOperation:
        return None, False

    if not numeric_val.is_finite():
        return None, False

    float_val = float(numeric_val)
    if float_val < min_rating or float_val > max_rating:
        return None, False

    normalized_text = (raw_rating_text or "").strip().lower()
    if numeric_val == Decimal("0") and normalized_text == RATING_NOT_RATED_TEXT:
        return None, True

    quantized = numeric_val.quantize(DECIMAL_RATING_QUANT, rounding=ROUND_HALF_UP)
    return quantized, True


def parse_cost(raw_cost: str | None) -> tuple[Decimal | None, str]:
    """Parse ``Average Cost for two`` and classify negative or zero edge cases.

    Args:
        raw_cost: Raw cost text.

    Returns:
        Tuple of ``(cost_decimal_or_none, status)`` where ``status`` is one of
        ``"ok"``, ``"zero"``, ``"negative"``, or ``"invalid"``.
    """
    if raw_cost is None or not raw_cost.strip():
        return None, "ok"

    try:
        cost_val = Decimal(raw_cost.strip())
    except InvalidOperation:
        return None, "invalid"

    if not cost_val.is_finite():
        return None, "invalid"
    if cost_val < MIN_COST:
        return None, "negative"
    if cost_val == MIN_COST:
        return None, "zero"
    return cost_val, "ok"


def parse_coordinates(
    raw_latitude: str | None,
    raw_longitude: str | None,
    *,
    max_abs_lat: float = MAX_ABS_LATITUDE,
    max_abs_lng: float = MAX_ABS_LONGITUDE,
) -> tuple[Decimal | None, Decimal | None, str]:
    """Validate latitude and longitude, returning ``None`` on missing/invalid.

    Args:
        raw_latitude: Raw latitude string.
        raw_longitude: Raw longitude string.
        max_abs_lat: Maximum allowed absolute latitude.
        max_abs_lng: Maximum allowed absolute longitude.

    Returns:
        Tuple of ``(lat_decimal_or_none, lng_decimal_or_none, status)`` where
        ``status`` is ``"ok"``, ``"missing"``, or ``"out_of_range"``.
    """
    lat_str = (raw_latitude or "").strip()
    lng_str = (raw_longitude or "").strip()
    if not lat_str or not lng_str:
        return None, None, "missing"

    try:
        lat_dec = Decimal(lat_str)
        lng_dec = Decimal(lng_str)
    except InvalidOperation:
        return None, None, "out_of_range"

    if not lat_dec.is_finite() or not lng_dec.is_finite():
        return None, None, "out_of_range"

    lat_float = float(lat_dec)
    lng_float = float(lng_dec)
    if lat_float == COORD_ZERO or lng_float == COORD_ZERO:
        return None, None, "missing"

    if abs(lat_float) > max_abs_lat or abs(lng_float) > max_abs_lng:
        return None, None, "out_of_range"

    return (
        lat_dec.quantize(DECIMAL_COORD_QUANT, rounding=ROUND_HALF_UP),
        lng_dec.quantize(DECIMAL_COORD_QUANT, rounding=ROUND_HALF_UP),
        "ok",
    )


def compute_record_hash(
    *,
    source_id: int,
    source_restaurant_id: str,
    name: str,
    source_country_code: int,
    city_name: str,
    locality: str,
    address: str | None,
    latitude: Decimal | None,
    longitude: Decimal | None,
    avg_cost_for_two: Decimal | None,
    currency_code: str,
    avg_cost_for_two_usd: Decimal | None,
    fx_rate: Decimal,
    fx_rate_date: date,
    price_range: int,
    rating: Decimal | None,
    rating_color: str | None,
    rating_text: str | None,
    votes: int,
    has_table_booking: bool,
    has_online_delivery: bool,
    is_delivering_now: bool,
    switch_to_order_menu: bool,
    cuisines: tuple[CuisineMapping, ...],
) -> str:
    """Compute a deterministic SHA-256 hash over standardized Silver fields.

    Args:
        source_id: Source metadata ID.
        source_restaurant_id: Source's restaurant identifier.
        name: Standardized restaurant name.
        source_country_code: Zomato country code.
        city_name: Standardized city name.
        locality: Standardized locality name.
        address: Standardized address or ``None``.
        latitude: Standardized latitude or ``None``.
        longitude: Standardized longitude or ``None``.
        avg_cost_for_two: Local cost or ``None``.
        currency_code: ISO 4217 currency code.
        avg_cost_for_two_usd: USD-converted cost or ``None``.
        fx_rate: Pinned FX rate.
        fx_rate_date: Pinned FX rate date.
        price_range: Integer price bucket (1-4).
        rating: Rating decimal or ``None``.
        rating_color: Rating color label or ``None``.
        rating_text: Rating text label or ``None``.
        votes: Non-negative integer vote count.
        has_table_booking: Table booking availability flag.
        has_online_delivery: Online delivery availability flag.
        is_delivering_now: Current delivery status flag.
        switch_to_order_menu: Menu switch flag.
        cuisines: Normalized canonical cuisine mappings.

    Returns:
        64-character lowercase SHA-256 hex digest.
    """
    payload = {
        "source_id": source_id,
        "source_restaurant_id": source_restaurant_id,
        "name": name,
        "source_country_code": source_country_code,
        "city_name": city_name,
        "locality": locality,
        "address": address,
        "latitude": str(latitude) if latitude is not None else None,
        "longitude": str(longitude) if longitude is not None else None,
        "avg_cost_for_two": (
            str(avg_cost_for_two) if avg_cost_for_two is not None else None
        ),
        "currency_code": currency_code,
        "avg_cost_for_two_usd": (
            str(avg_cost_for_two_usd) if avg_cost_for_two_usd is not None else None
        ),
        "fx_rate": str(fx_rate),
        "fx_rate_date": fx_rate_date.isoformat(),
        "price_range": price_range,
        "rating": str(rating) if rating is not None else None,
        "rating_color": rating_color,
        "rating_text": rating_text,
        "votes": votes,
        "has_table_booking": has_table_booking,
        "has_online_delivery": has_online_delivery,
        "is_delivering_now": is_delivering_now,
        "switch_to_order_menu": switch_to_order_menu,
        "cuisines": [[c.cuisine_name, c.cuisine_group] for c in cuisines],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
