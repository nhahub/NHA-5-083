"""Spatial helpers for SRID 4326 bounding boxes and Haversine distances."""

from __future__ import annotations

import math

from web.backend.constants import (
    BOX_MARGIN,
    EARTH_RADIUS_METERS,
    MAX_ABS_LATITUDE,
    MAX_ABS_LONGITUDE,
    MAX_GEO_LATITUDE,
    MAX_SEARCH_RADIUS_M,
    METERS_PER_DEGREE_LATITUDE,
)


def is_valid_coordinate(latitude: float | None, longitude: float | None) -> bool:
    """Return True when both latitude and longitude are finite non-zero WGS84 coords."""
    if latitude is None or longitude is None:
        return False
    if math.isnan(latitude) or math.isnan(longitude):
        return False
    if latitude == 0.0 and longitude == 0.0:
        return False
    return abs(latitude) <= MAX_GEO_LATITUDE and abs(longitude) <= MAX_ABS_LONGITUDE


def bounding_box_wkt(latitude: float, longitude: float, radius_m: float) -> str:
    """Return a WKT rectangle that fully contains a search circle.

    The text is latitude first, as MySQL expects for SRID 4326. The rectangle
    is slightly larger than the circle, so the exact distance check must still
    run after it. The antimeridian is not handled.

    Args:
        latitude: Circle center latitude in degrees.
        longitude: Circle center longitude in degrees.
        radius_m: Circle radius in meters.

    Returns:
        A closed POLYGON in WKT.

    Raises:
        ValueError: If a value is outside the supported range.
    """
    if abs(latitude) > MAX_ABS_LATITUDE or abs(longitude) > MAX_ABS_LONGITUDE:
        raise ValueError("coordinates outside the supported range")
    if not 0 < radius_m <= MAX_SEARCH_RADIUS_M:
        raise ValueError("radius_m must be positive and within the maximum")

    delta_lat = BOX_MARGIN * radius_m / METERS_PER_DEGREE_LATITUDE
    delta_lon = delta_lat / math.cos(math.radians(latitude))
    south, north = latitude - delta_lat, latitude + delta_lat
    west, east = longitude - delta_lon, longitude + delta_lon
    corners = [
        (south, west),
        (south, east),
        (north, east),
        (north, west),
        (south, west),
    ]
    ring = ",".join(f"{lat} {lon}" for lat, lon in corners)
    return f"POLYGON(({ring}))"


def haversine_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate great-circle distance in meters between two WGS84 coordinates."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    half_chord = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    central_angle = 2.0 * math.asin(math.sqrt(min(1.0, half_chord)))
    return EARTH_RADIUS_METERS * central_angle
