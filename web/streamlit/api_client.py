"""Typed HTTP API client for the FastAPI backend.

This is the sole module inside `web/streamlit/` permitted to import an HTTP
client library (`httpx`). All pages and UI components consume backend data
exclusively through `APIClient`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal, NotRequired, TypedDict

import httpx
import streamlit as st
from pydantic import TypeAdapter, ValidationError

from web.streamlit.constants import (
    DEFAULT_MAP_POINTS_LIMIT,
    DEFAULT_PAGE_LIMIT,
    HTTP_STATUS_NOT_FOUND,
    HTTP_STATUS_RATE_LIMITED,
    HTTP_STATUS_SERVER_ERROR_MIN,
    HTTP_STATUS_SERVICE_UNAVAILABLE,
    HTTP_STATUS_UNPROCESSABLE,
)
from web.streamlit.settings import settings, truncate_query_for_log

logger = logging.getLogger(__name__)


class HealthResponse(TypedDict):
    """Response payload for `GET /api/health`."""

    status: str


class RestaurantItem(TypedDict):
    """Normalized restaurant record returned by search and detail endpoints."""

    restaurant_id: int
    source_restaurant_id: str
    source_name: str
    source_license: str
    name: str
    country_name: str
    iso_code: str
    city_name: str
    locality: str | None
    address: str | None
    latitude: float | None
    longitude: float | None
    cuisines: list[str]
    cuisine_groups: list[str]
    avg_cost_for_two: float | None
    currency_code: str | None
    avg_cost_for_two_usd: float | None
    price_range: int | None
    rating: float | None
    rating_text: str | None
    votes: int | None
    has_table_booking: bool
    has_online_delivery: bool
    distance_m: float | None


class RestaurantListResponse(TypedDict):
    """Paginated restaurant list response for `GET /api/restaurants`."""

    items: list[RestaurantItem]
    total: int
    limit: int
    offset: int


class RestaurantDetailResponse(TypedDict):
    """Detail payload for `GET /api/restaurants/{restaurant_id}`."""

    restaurant: RestaurantItem
    nearby: list[RestaurantItem]
    similar: list[RestaurantItem]


class MapPointItem(TypedDict):
    """Map point payload returned by `GET /api/map/points`."""

    restaurant_id: int
    name: str
    country_name: str
    city_name: str
    locality: NotRequired[str | None]
    latitude: float
    longitude: float
    rating: NotRequired[float | None]
    rating_text: NotRequired[str | None]
    price_range: NotRequired[int | None]
    avg_cost_for_two: NotRequired[float | None]
    currency_code: NotRequired[str | None]
    avg_cost_for_two_usd: NotRequired[float | None]
    cuisines: NotRequired[list[str]]
    source_name: NotRequired[str]
    source_license: NotRequired[str]


class MapPointsResponse(TypedDict):
    """Response payload for `GET /api/map/points`."""

    items: list[MapPointItem]
    total: int


class SearchParamsPayload(TypedDict, total=False):
    """Validated SearchParams extracted from natural-language queries."""

    country: str | None
    city: str | None
    locality: str | None
    cuisine: list[str]
    cuisine_group: str | None
    min_rating: float | None
    min_cost_for_two: float | None
    max_cost_for_two: float | None
    max_cost_usd: float | None
    price_range: int | None
    has_online_delivery: bool | None
    has_table_booking: bool | None
    search_query: str | None
    needs_clarification: str | None


class NLSearchResponse(TypedDict):
    """Response payload for `POST /api/search/nl`."""

    query: str
    interpreted_params: SearchParamsPayload
    parser_used: Literal["huggingface", "huggingface_semantic", "rule_based"]
    fallback_used: bool
    items: list[RestaurantItem]
    total: int
    limit: int
    offset: int


class CountryMeta(TypedDict):
    """Country metadata entry from `GET /api/meta/countries`."""

    country_name: str
    iso_code: str
    currency_code: str
    restaurant_count: int


class CountriesResponse(TypedDict):
    """Response payload for `GET /api/meta/countries`."""

    items: list[CountryMeta]


class CityMeta(TypedDict):
    """City metadata entry from `GET /api/meta/cities`."""

    city_name: str
    country_name: str
    restaurant_count: int


class CitiesResponse(TypedDict):
    """Response payload for `GET /api/meta/cities`."""

    items: list[CityMeta]


class CuisineMeta(TypedDict):
    """Cuisine metadata entry from `GET /api/meta/cuisines`."""

    cuisine_name: str
    cuisine_group: str
    restaurant_count: int


class CuisinesResponse(TypedDict):
    """Response payload for `GET /api/meta/cuisines`."""

    items: list[CuisineMeta]


class AnalyticsBucket(TypedDict, total=False):
    """Generic named metric bucket used inside analytics summaries."""

    label: str
    name: str
    cuisine_name: str
    cuisine_group: str
    country_name: str
    city_name: str
    price_range: int
    rating_label: str
    rating_bucket: str
    count: int
    restaurant_count: int
    avg_rating: float | None
    avg_cost_usd: float | None


class AnalyticsSummary(TypedDict):
    """Response payload for `GET /api/meta/analytics`."""

    total_restaurants: int
    total_countries: int
    total_cities: int
    total_cuisines: int
    geolocated_count: int
    rated_count: int
    unrated_count: int
    avg_rating: float | None
    top_cuisines: list[AnalyticsBucket]
    by_country: list[AnalyticsBucket]
    by_price_range: list[AnalyticsBucket]
    rating_distribution: list[AnalyticsBucket]


class DestinationProfile(TypedDict):
    """Response payload for `GET /api/meta/destinations/{country}`."""

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
    top_restaurants: list[RestaurantItem]


class PipelineRunSummary(TypedDict, total=False):
    """Single pipeline run entry inside `PipelineStatus`."""

    run_id: int | str
    dag_id: str
    source_name: str
    status: str
    started_at: str | None
    ended_at: str | None
    rows_read: int
    rows_inserted: int
    rows_updated: int
    rows_unchanged: int
    rows_quarantined: int
    rows_warned: int
    quarantine_rate: float | None


class QualityBreakdownItem(TypedDict, total=False):
    """Data-quality issue breakdown row inside `PipelineStatus`."""

    rule_name: str
    severity: str
    count: int
    issue_count: int
    sample_reason: str | None


class PipelineStatus(TypedDict):
    """Response payload for `GET /api/pipeline/status`."""

    latest_run: PipelineRunSummary | None
    is_stale: bool
    days_since_last_success: float | None
    gold_max_age_days: int
    recent_runs: list[PipelineRunSummary]
    quality_breakdown: list[QualityBreakdownItem]
    data_mode: str


class APIError(Exception):
    """Plain-language API failure raised for presentation-layer handling."""

    def __init__(self, user_message: str, status_code: int | None = None) -> None:
        """Initialize an API error with a safe user-facing message."""
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code


_HEALTH_ADAPTER = TypeAdapter(HealthResponse)
_RESTAURANT_LIST_ADAPTER = TypeAdapter(RestaurantListResponse)
_RESTAURANT_DETAIL_ADAPTER = TypeAdapter(RestaurantDetailResponse)
_MAP_POINTS_ADAPTER = TypeAdapter(MapPointsResponse)
_NL_SEARCH_ADAPTER = TypeAdapter(NLSearchResponse)
_COUNTRIES_ADAPTER = TypeAdapter(CountriesResponse)
_CITIES_ADAPTER = TypeAdapter(CitiesResponse)
_CUISINES_ADAPTER = TypeAdapter(CuisinesResponse)
_ANALYTICS_ADAPTER = TypeAdapter(AnalyticsSummary)
_DESTINATION_ADAPTER = TypeAdapter(DestinationProfile)
_PIPELINE_STATUS_ADAPTER = TypeAdapter(PipelineStatus)


def _friendly_http_message(status_code: int) -> str:
    if status_code == HTTP_STATUS_UNPROCESSABLE:
        return "Please review your filter or search values and try again."
    if status_code == HTTP_STATUS_RATE_LIMITED:
        return "Too many natural-language search requests. Wait a moment and retry."
    if status_code == HTTP_STATUS_NOT_FOUND:
        return "The requested restaurant or destination could not be found."
    if status_code == HTTP_STATUS_SERVICE_UNAVAILABLE:
        return "The restaurant data service is temporarily unavailable."
    if status_code >= HTTP_STATUS_SERVER_ERROR_MIN:
        return "The data service encountered a server error. Please try again shortly."
    return "The request could not be completed. Please try again."


def _compact_params(
    raw_params: dict[str, str | int | float | bool | list[str] | None],
) -> dict[str, str | int | float | bool | list[str]]:
    compacted: dict[str, str | int | float | bool | list[str]] = {}
    for key, value in raw_params.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and not value:
            continue
        compacted[key] = value
    return compacted


class APIClient:
    """Synchronous HTTP client wrapping all FastAPI endpoints."""

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        """Initialize the underlying `httpx.Client` with a base URL and timeout."""
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Accept": "application/json"},
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | float | bool | list[str]] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> object:
        try:
            response = self._client.request(
                method,
                path,
                params=params,
                json=json_body,
            )
        except httpx.TimeoutException as exc:
            logger.warning("API request timed out for %s %s", method, path)
            raise APIError(
                "The data service took too long to respond. Please try again."
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("API connection error for %s %s", method, path)
            raise APIError(
                "Unable to reach the data service right now. Please try again shortly."
            ) from exc

        if not response.is_success:
            logger.warning(
                "API non-2xx response: %s %s status=%d",
                method,
                path,
                response.status_code,
            )
            raise APIError(
                _friendly_http_message(response.status_code),
                status_code=response.status_code,
            )

        try:
            decoded: object = response.json()
        except ValueError as exc:
            logger.warning("API returned invalid JSON for %s %s", method, path)
            raise APIError(
                "Received an unreadable response from the data service."
            ) from exc
        return decoded

    def _validate[T](self, adapter: TypeAdapter[T], payload: object) -> T:
        try:
            return adapter.validate_python(payload)
        except ValidationError as exc:
            logger.warning("API payload validation failed: %s", exc.title)
            raise APIError(
                "Received an unexpected data format from the data service."
            ) from exc

    def health(self) -> HealthResponse:
        """Check backend health status."""
        payload = self._request_json("GET", "/api/health")
        return self._validate(_HEALTH_ADAPTER, payload)

    def list_restaurants(
        self,
        *,
        country: str | None = None,
        city: str | None = None,
        locality: str | None = None,
        cuisine: Sequence[str] | None = None,
        cuisine_group: str | None = None,
        min_rating: float | None = None,
        max_cost_for_two: float | None = None,
        max_cost_usd: float | None = None,
        price_range: int | None = None,
        has_online_delivery: bool | None = None,
        has_table_booking: bool | None = None,
        search_query: str | None = None,
        sort_by: str = "rating",
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> RestaurantListResponse:
        """Fetch paginated restaurants matching the requested filters."""
        params = _compact_params(
            {
                "country": country,
                "city": city,
                "locality": locality,
                "cuisine": list(cuisine) if cuisine else None,
                "cuisine_group": cuisine_group,
                "min_rating": min_rating,
                "max_cost_for_two": max_cost_for_two,
                "max_cost_usd": max_cost_usd,
                "price_range": price_range,
                "has_online_delivery": has_online_delivery,
                "has_table_booking": has_table_booking,
                "search_query": search_query,
                "sort_by": sort_by,
                "limit": limit,
                "offset": offset,
            }
        )
        payload = self._request_json("GET", "/api/restaurants", params=params)
        return self._validate(_RESTAURANT_LIST_ADAPTER, payload)

    def get_restaurant(self, restaurant_id: int) -> RestaurantDetailResponse:
        """Fetch full details, nearby venues, and similar restaurants for an ID."""
        payload = self._request_json("GET", f"/api/restaurants/{restaurant_id}")
        return self._validate(_RESTAURANT_DETAIL_ADAPTER, payload)

    def get_map_points(
        self,
        *,
        country: str | None = None,
        city: str | None = None,
        cuisine: Sequence[str] | None = None,
        min_rating: float | None = None,
        price_range: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_m: float | None = None,
        limit: int = DEFAULT_MAP_POINTS_LIMIT,
    ) -> MapPointsResponse:
        """Fetch map markers matching filters or optional spatial radius bounds."""
        params = _compact_params(
            {
                "country": country,
                "city": city,
                "cuisine": list(cuisine) if cuisine else None,
                "min_rating": min_rating,
                "price_range": price_range,
                "latitude": latitude,
                "longitude": longitude,
                "radius_m": radius_m,
                "limit": limit,
            }
        )
        payload = self._request_json("GET", "/api/map/points", params=params)
        return self._validate(_MAP_POINTS_ADAPTER, payload)

    def search_nl(
        self,
        query: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        previous_params: SearchParamsPayload | None = None,
    ) -> NLSearchResponse:
        """Run a constrained natural-language search against `POST /api/search/nl`."""
        logger.info("Submitting NL search query=%s", truncate_query_for_log(query))
        body: dict[str, object] = {"query": query, "limit": limit, "offset": offset}
        if previous_params is not None:
            body["previous_params"] = previous_params
        payload = self._request_json("POST", "/api/search/nl", json_body=body)
        return self._validate(_NL_SEARCH_ADAPTER, payload)

    def list_countries(self) -> CountriesResponse:
        """Fetch available countries and restaurant counts."""
        payload = self._request_json("GET", "/api/meta/countries")
        return self._validate(_COUNTRIES_ADAPTER, payload)

    def list_cities(self, country: str | None = None) -> CitiesResponse:
        """Fetch available cities, optionally filtered by country."""
        params = _compact_params({"country": country})
        payload = self._request_json("GET", "/api/meta/cities", params=params)
        return self._validate(_CITIES_ADAPTER, payload)

    def list_cuisines(self) -> CuisinesResponse:
        """Fetch canonical cuisines and cuisine groups."""
        payload = self._request_json("GET", "/api/meta/cuisines")
        return self._validate(_CUISINES_ADAPTER, payload)

    def get_analytics(self, country: str | None = None) -> AnalyticsSummary:
        """Fetch dataset coverage, rating, and cost summary metrics."""
        params = _compact_params({"country": country})
        payload = self._request_json("GET", "/api/meta/analytics", params=params)
        return self._validate(_ANALYTICS_ADAPTER, payload)

    def get_destination_profile(self, country: str) -> DestinationProfile:
        """Fetch culinary briefing and top records for a country."""
        payload = self._request_json("GET", f"/api/meta/destinations/{country}")
        return self._validate(_DESTINATION_ADAPTER, payload)

    def get_pipeline_status(self) -> PipelineStatus:
        """Fetch latest pipeline runs, freshness state, and quality breakdown."""
        payload = self._request_json("GET", "/api/pipeline/status")
        return self._validate(_PIPELINE_STATUS_ADAPTER, payload)


_CLIENT_OVERRIDE: APIClient | None = None


def set_api_client_override(client: APIClient | None) -> None:
    """Override the active `APIClient` instance for testing."""
    global _CLIENT_OVERRIDE
    _CLIENT_OVERRIDE = client


@st.cache_resource
def _build_cached_client(base_url: str, timeout_seconds: float) -> APIClient:
    return APIClient(base_url=base_url, timeout_seconds=timeout_seconds)


def get_api_client() -> APIClient:
    """Return the shared cached `APIClient` configured from `settings`."""
    if _CLIENT_OVERRIDE is not None:
        return _CLIENT_OVERRIDE
    return _build_cached_client(
        base_url=settings.streamlit_backend_url,
        timeout_seconds=float(settings.streamlit_api_timeout_seconds),
    )
