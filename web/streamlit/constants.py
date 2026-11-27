"""Shared constants, bounds, and UI microcopy for the Streamlit application."""

from __future__ import annotations

APP_NAME = "EatoSphere"
APP_SUBTITLE = "Global Restaurant Intelligence & Auditable Culinary Briefing"

GOLD_MAX_AGE_DAYS = 7
QUERY_LOG_MAX_CHARS = 220
MAX_NLP_INPUT_CHARS = 500
MAX_QUARANTINE_RATE_PCT = 15.0

DEFAULT_API_TIMEOUT_SECONDS = 10
DEFAULT_CACHE_TTL_SECONDS = 300
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100
PAGE_LIMIT_OPTIONS: tuple[int, ...] = (10, 20, 50, 100)

DEFAULT_MAP_POINTS_LIMIT = 500
MAX_MAP_POINTS_LIMIT = 1000
MAP_POINTS_MIN_LIMIT = 50
MAP_POINTS_STEP = 50

MIN_RATING = 0.0
MAX_RATING = 5.0
RATING_STEP = 0.5
RATING_TIER_HIGH = 4.0
RATING_TIER_MID = 3.0

MAX_COST_USD_LIMIT = 1000.0
COST_USD_STEP = 5.0

DEFAULT_RADIUS_M = 5000
MIN_RADIUS_M = 500
MAX_RADIUS_M = 50000
RADIUS_STEP_M = 500
METERS_PER_KM = 1000.0

PRICE_TIER_LABELS: dict[int, str] = {
    1: "Tier 1 · Budget",
    2: "Tier 2 · Moderate",
    3: "Tier 3 · Upscale",
    4: "Tier 4 · Fine Dining",
}
PRICE_RANGE_OPTIONS: tuple[int, ...] = (1, 2, 3, 4)

SORT_LABELS: dict[str, str] = {
    "rating": "Highest rated",
    "votes": "Most voted",
    "cost_usd_asc": "Lowest cost (USD)",
    "cost_usd_desc": "Highest cost (USD)",
    "name": "Alphabetical (A–Z)",
}

MAX_COMPARE_ITEMS = 4
MAX_JOURNEY_STOPS = 8
MIN_JOURNEY_STOPS = 2
EARTH_RADIUS_KM = 6371.0
WALKING_SPEED_KMH = 4.5
DRIVING_SPEED_KMH = 25.0
MINUTES_PER_HOUR = 60.0

MAX_ABS_LATITUDE = 90.0
MAX_ABS_LONGITUDE = 180.0

UNRATED_LABEL = "Unrated"
UNRATED_DETAIL_LABEL = "No rating in source"
UNKNOWN_SOURCE_LABEL = "Dataset source"
UNKNOWN_LICENSE_LABEL = "License unspecified"

MAP_VIEW_LABELS: dict[str, str] = {
    "standard": "Standard (OSM)",
    "terrain": "Terrain",
    "satellite": "Satellite",
    "topographic": "Topographic",
    "dark": "Dark",
}
MAP_VIEW_STYLES: dict[str, dict[str, object]] = {
    "standard": {
        "style": "white-bg",
        "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "OpenStreetMap contributors",
        "is_dark_basemap": False,
    },
    "terrain": {
        "style": "white-bg",
        "tile_url": "https://tile.opentopomap.org/{z}/{x}/{y}.png",
        "attribution": "OpenTopoMap (CC-BY-SA) · OpenStreetMap contributors",
        "is_dark_basemap": False,
    },
    "satellite": {
        "style": "white-bg",
        "tile_url": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        "attribution": "Esri World Imagery",
        "is_dark_basemap": True,
    },
    "topographic": {
        "style": "white-bg",
        "tile_url": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
        ),
        "attribution": "Esri World Topographic Map",
        "is_dark_basemap": False,
    },
    "dark": {
        "style": "white-bg",
        "tile_url": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        ),
        "attribution": "Esri Dark Gray Canvas",
        "is_dark_basemap": True,
    },
}
CHART_HEIGHT_PX = 360
MAP_HEIGHT_PX = 480
DEFAULT_MAP_CENTER_LAT = 26.0
DEFAULT_MAP_CENTER_LON = 30.0
DEFAULT_MAP_ZOOM = 2
CITY_MAP_ZOOM = 11
DETAIL_MAP_ZOOM = 13

RATING_TIER_ORDER: tuple[str, ...] = ("4.0+", "3.0–3.9", "Below 3.0", UNRATED_LABEL)

# Light theme (*Warm Paper*) spatial colors aligned with docs/UI_UX.md §3.3
COLOR_HIGH_RATING = "#1E4D3B"
COLOR_MID_RATING = "#A63D2F"
COLOR_LOW_RATING = "#B45309"
COLOR_UNRATED = "#64748B"
COLOR_FOCUS = "#A63D2F"
COLOR_ROUTE_PATH = "#A63D2F"
COLOR_SURFACE_LIGHT = "#FAF9F5"
COLOR_CARD_SURFACE_LIGHT = "#FFFFFF"
COLOR_TEXT_LIGHT = "#1F1E1C"
COLOR_BORDER_LIGHT = "#DDD9D0"

# Dark theme (*Warm Ink*) spatial colors aligned with docs/UI_UX.md §3.3
COLOR_DARK_HIGH_RATING = "#52A88A"
COLOR_DARK_MID_RATING = "#E07A6B"
COLOR_DARK_LOW_RATING = "#E5A14B"
COLOR_DARK_UNRATED = "#A8A29E"
COLOR_DARK_FOCUS = "#C44D3D"
COLOR_DARK_ROUTE_PATH = "#E07A6B"
COLOR_SURFACE_DARK = "#171614"
COLOR_CARD_SURFACE_DARK = "#22201D"
COLOR_TEXT_DARK = "#EDEBE6"
COLOR_BORDER_DARK = "#33302B"

MARKER_SIZE_PX = 10
FOCUS_MARKER_SIZE_PX = 15

HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_UNPROCESSABLE = 422
HTTP_STATUS_RATE_LIMITED = 429
HTTP_STATUS_SERVICE_UNAVAILABLE = 503
HTTP_STATUS_SERVER_ERROR_MIN = 500

NL_EXAMPLE_QUERIES: tuple[str, ...] = (
    "Top rated Italian in Mumbai under $30",
    "Best Indian in Dubai with table booking",
    "Affordable North Indian in New Delhi with online delivery",
    "Fine dining in London rated above 4.5",
)

PIPELINE_STATUS_LABELS: dict[str, tuple[str, str]] = {
    "success": (":material/check_circle:", "Success"),
    "skipped_unchanged": (":material/fast_forward:", "Skipped (unchanged)"),
    "quality_gate_failed": (":material/gpp_bad:", "Quality gate failed"),
    "failed": (":material/error:", "Failed"),
}
