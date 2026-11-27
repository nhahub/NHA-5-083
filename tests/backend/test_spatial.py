"""Unit tests for spatial bounding box and Haversine helpers."""

from __future__ import annotations

import math

import pytest

from web.backend.constants import MAX_ABS_LATITUDE, MAX_SEARCH_RADIUS_M
from web.backend.repositories.spatial import (
    bounding_box_wkt,
    haversine_meters,
    is_valid_coordinate,
)


def _parse_wkt_polygon(wkt: str) -> list[tuple[float, float]]:
    assert wkt.startswith("POLYGON((") and wkt.endswith("))")
    inner = wkt[len("POLYGON((") : -2]
    points: list[tuple[float, float]] = []
    for pair in inner.split(","):
        lat_str, lon_str = pair.strip().split()
        points.append((float(lat_str), float(lon_str)))
    return points


def test_bounding_box_wkt_is_closed_and_latitude_first() -> None:
    center_lat, center_lon, radius_m = 28.631451, 77.216721, 5000.0
    wkt = bounding_box_wkt(center_lat, center_lon, radius_m)
    corners = _parse_wkt_polygon(wkt)

    assert len(corners) == 5
    assert corners[0] == corners[-1]

    south = min(pt[0] for pt in corners)
    north = max(pt[0] for pt in corners)
    west = min(pt[1] for pt in corners)
    east = max(pt[1] for pt in corners)

    assert south < center_lat < north
    assert west < center_lon < east
    assert haversine_meters(center_lat, center_lon, north, center_lon) > radius_m
    assert haversine_meters(center_lat, center_lon, south, center_lon) > radius_m
    assert haversine_meters(center_lat, center_lon, center_lat, east) > radius_m
    assert haversine_meters(center_lat, center_lon, center_lat, west) > radius_m


@pytest.mark.parametrize(
    ("lat", "lon", "radius"),
    [
        (MAX_ABS_LATITUDE + 0.1, 0.0, 1000.0),
        (-MAX_ABS_LATITUDE - 0.1, 0.0, 1000.0),
        (0.0, 180.1, 1000.0),
        (10.0, 10.0, 0.0),
        (10.0, 10.0, -50.0),
        (10.0, 10.0, MAX_SEARCH_RADIUS_M + 1.0),
    ],
)
def test_bounding_box_wkt_rejects_out_of_bounds(
    lat: float,
    lon: float,
    radius: float,
) -> None:
    with pytest.raises(ValueError):
        bounding_box_wkt(lat, lon, radius)


def test_haversine_meters_known_distance_and_zero() -> None:
    assert haversine_meters(28.631451, 77.216721, 28.631451, 77.216721) == 0.0
    dist = haversine_meters(28.631451, 77.216721, 28.633000, 77.219000)
    assert 250.0 < dist < 350.0


def test_is_valid_coordinate() -> None:
    assert is_valid_coordinate(28.631451, 77.216721) is True
    assert is_valid_coordinate(0.0, 0.0) is False
    assert is_valid_coordinate(None, 77.0) is False
    assert is_valid_coordinate(float("nan"), 77.0) is False
    assert is_valid_coordinate(math.nan, 77.0) is False
    assert is_valid_coordinate(95.0, 77.0) is False
    assert is_valid_coordinate(28.0, 185.0) is False
