"""Data-honest formatting, escaping, and geospatial helpers for Streamlit UI."""

from __future__ import annotations

import math
from collections.abc import Mapping
from urllib.parse import quote_plus

from web.streamlit.constants import (
    DRIVING_SPEED_KMH,
    EARTH_RADIUS_KM,
    MAX_ABS_LATITUDE,
    MAX_ABS_LONGITUDE,
    METERS_PER_KM,
    MINUTES_PER_HOUR,
    PRICE_TIER_LABELS,
    UNKNOWN_LICENSE_LABEL,
    UNKNOWN_SOURCE_LABEL,
    UNRATED_LABEL,
    WALKING_SPEED_KMH,
)

_MARKDOWN_ESCAPE_CHARS = "\\`*_{}[]()#+-.!|~"


def escape_markdown(text: str | None) -> str:
    """Escape Markdown control characters in untrusted text."""
    if not text:
        return ""
    escaped_chars = [
        f"\\{ch}" if ch in _MARKDOWN_ESCAPE_CHARS else ch for ch in str(text)
    ]
    return "".join(escaped_chars)


def format_rating(
    rating: float | None,
    rating_text: str | None = None,
    *,
    include_text: bool = True,
) -> str:
    """Format a venue rating transparently, displaying `Unrated` for `None`."""
    if rating is None:
        return UNRATED_LABEL
    formatted = f"{rating:.1f} / 5"
    if include_text and rating_text and rating_text.strip().lower() != "not rated":
        return f"{formatted} ({rating_text})"
    return formatted


def _format_amount(value: float) -> str:
    if value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def format_cost(
    avg_cost_for_two: float | None,
    currency_code: str | None,
    avg_cost_for_two_usd: float | None,
) -> str:
    """Format original currency amount alongside batch-standardized USD."""
    if avg_cost_for_two is None:
        if avg_cost_for_two_usd is not None:
            return f"~${avg_cost_for_two_usd:,.2f} USD for two"
        return "Cost unlisted"

    code = (currency_code or "").strip().upper()
    primary = (
        f"{code} {_format_amount(avg_cost_for_two)}"
        if code
        else _format_amount(avg_cost_for_two)
    )
    if avg_cost_for_two_usd is not None and code != "USD":
        return f"{primary} (~${avg_cost_for_two_usd:,.2f} USD for two)"
    return f"{primary} for two"


def format_source_attribution(
    source_name: str | None,
    source_license: str | None,
) -> str:
    """Format source provenance and license attribution."""
    source = (source_name or "").strip() or UNKNOWN_SOURCE_LABEL
    if source.islower():
        source = source.title()
    license_label = (source_license or "").strip() or UNKNOWN_LICENSE_LABEL
    return f"{source} · {license_label}"


def format_price_tier(price_range: int | None) -> str:
    """Format numeric price range `1..4` into a descriptive tier label."""
    if price_range is None:
        return "Price tier unlisted"
    return PRICE_TIER_LABELS.get(price_range, f"Tier {price_range}")


def format_distance_m(distance_m: float | None) -> str:
    """Format a distance in meters into readable meters or kilometers."""
    if distance_m is None:
        return ""
    if distance_m < METERS_PER_KM:
        return f"{round(distance_m)} m"
    return f"{distance_m / METERS_PER_KM:.2f} km"


def is_valid_coordinate(
    latitude: float | None,
    longitude: float | None,
) -> bool:
    """Return True when coordinates are finite, non-zero, and within WGS84 bounds."""
    if latitude is None or longitude is None:
        return False
    if math.isnan(latitude) or math.isnan(longitude):
        return False
    if math.isinf(latitude) or math.isinf(longitude):
        return False
    if latitude == 0.0 and longitude == 0.0:
        return False
    return (
        -MAX_ABS_LATITUDE <= latitude <= MAX_ABS_LATITUDE
        and -MAX_ABS_LONGITUDE <= longitude <= MAX_ABS_LONGITUDE
    )


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate straight-line great-circle distance in kilometers."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    sin_half_phi = math.sin(delta_phi / 2.0)
    sin_half_lambda = math.sin(delta_lambda / 2.0)
    hav = (
        sin_half_phi * sin_half_phi
        + math.cos(phi1) * math.cos(phi2) * sin_half_lambda * sin_half_lambda
    )
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, hav)))


def estimate_leg_minutes(distance_km: float) -> tuple[int, int]:
    """Estimate straight-line walking and city driving minutes for a leg."""
    walk_mins = max(1, round((distance_km / WALKING_SPEED_KMH) * MINUTES_PER_HOUR))
    drive_mins = max(1, round((distance_km / DRIVING_SPEED_KMH) * MINUTES_PER_HOUR))
    return walk_mins, drive_mins


def build_directions_url(
    restaurant: Mapping[str, object],
    origin_lat: float | None = None,
    origin_lon: float | None = None,
) -> str | None:
    """Build an external Google Maps directions URL from coordinates or address."""
    raw_lat = restaurant.get("latitude")
    raw_lon = restaurant.get("longitude")
    lat = float(raw_lat) if isinstance(raw_lat, (int, float)) else None
    lon = float(raw_lon) if isinstance(raw_lon, (int, float)) else None

    if is_valid_coordinate(lat, lon) and lat is not None and lon is not None:
        destination = f"{lat:.6f},{lon:.6f}"
    else:
        name = str(restaurant.get("name") or "")
        address = str(restaurant.get("address") or "")
        city = str(restaurant.get("city_name") or "")
        fallback_text = ", ".join(part for part in (name, address, city) if part)
        if not fallback_text:
            return None
        destination = quote_plus(fallback_text)

    url = f"https://www.google.com/maps/dir/?api=1&destination={destination}"
    if (
        is_valid_coordinate(origin_lat, origin_lon)
        and origin_lat is not None
        and origin_lon is not None
    ):
        url += f"&origin={origin_lat:.6f},{origin_lon:.6f}"
    return url
