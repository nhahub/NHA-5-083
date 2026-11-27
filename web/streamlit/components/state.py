"""Shared `st.session_state` initialization and cached data loaders."""

from __future__ import annotations

import streamlit as st

from web.streamlit.api_client import (
    AnalyticsSummary,
    CitiesResponse,
    CountriesResponse,
    CuisinesResponse,
    DestinationProfile,
    MapPointsResponse,
    PipelineStatus,
    RestaurantDetailResponse,
    RestaurantItem,
    RestaurantListResponse,
    get_api_client,
)
from web.streamlit.constants import MAX_COMPARE_ITEMS, MAX_JOURNEY_STOPS
from web.streamlit.settings import settings


def ensure_session_state() -> None:
    """Initialize all shared session-state keys if absent."""
    if "saved_restaurants" not in st.session_state:
        st.session_state["saved_restaurants"] = {}
    if "compare_ids" not in st.session_state:
        st.session_state["compare_ids"] = []
    if "compare_items" not in st.session_state:
        st.session_state["compare_items"] = {}
    if "journey_stops" not in st.session_state:
        st.session_state["journey_stops"] = []
    if "explore_offset" not in st.session_state:
        st.session_state["explore_offset"] = 0
    if "map_focus_restaurant" not in st.session_state:
        st.session_state["map_focus_restaurant"] = None
    if "nl_last_query" not in st.session_state:
        st.session_state["nl_last_query"] = ""
    if "nl_last_response" not in st.session_state:
        st.session_state["nl_last_response"] = None
    if "nl_active_params" not in st.session_state:
        st.session_state["nl_active_params"] = None
    if "nl_history" not in st.session_state:
        st.session_state["nl_history"] = []


def toggle_saved_restaurant(restaurant: RestaurantItem) -> None:
    """Bookmark or unbookmark a restaurant in session state."""
    ensure_session_state()
    saved = dict(st.session_state["saved_restaurants"])
    rid = restaurant["restaurant_id"]
    if rid in saved:
        del saved[rid]
        st.session_state["saved_restaurants"] = saved
        st.toast(
            f"Removed {restaurant['name']} from Saved.",
            icon=":material/bookmark_remove:",
        )
    else:
        saved[rid] = restaurant
        st.session_state["saved_restaurants"] = saved
        st.toast(
            f"Saved {restaurant['name']}. Find it in Journey & Compare → "
            "add stops or compare from Saved.",
            icon=":material/bookmark_added:",
        )


def add_to_compare(restaurant: RestaurantItem) -> None:
    """Add or remove a restaurant from the side-by-side comparison tray."""
    ensure_session_state()
    compare_ids = list(st.session_state["compare_ids"])
    compare_items = dict(st.session_state["compare_items"])
    rid = restaurant["restaurant_id"]
    if rid in compare_ids:
        compare_ids.remove(rid)
        compare_items.pop(rid, None)
        st.session_state["compare_ids"] = compare_ids
        st.session_state["compare_items"] = compare_items
        st.toast(
            f"Removed {restaurant['name']} from Compare.",
            icon=":material/compare_arrows:",
        )
        return
    if len(compare_ids) >= MAX_COMPARE_ITEMS:
        st.toast(
            f"Compare tray supports up to {MAX_COMPARE_ITEMS} venues.",
            icon=":material/info:",
        )
        return
    updated_ids = [*compare_ids, rid]
    compare_items[rid] = restaurant
    st.session_state["compare_ids"] = updated_ids
    st.session_state["compare_items"] = compare_items
    st.toast(
        f"Added {restaurant['name']} to Compare "
        f"({len(updated_ids)}/{MAX_COMPARE_ITEMS}).",
        icon=":material/compare_arrows:",
    )


def remove_from_compare(restaurant_id: int) -> None:
    """Remove a restaurant from the side-by-side comparison tray by ID."""
    ensure_session_state()
    compare_ids = [
        rid for rid in st.session_state["compare_ids"] if rid != restaurant_id
    ]
    compare_items = dict(st.session_state["compare_items"])
    compare_items.pop(restaurant_id, None)
    st.session_state["compare_ids"] = compare_ids
    st.session_state["compare_items"] = compare_items


def clear_compare() -> None:
    """Clear all restaurants from the side-by-side comparison tray."""
    ensure_session_state()
    st.session_state["compare_ids"] = []
    st.session_state["compare_items"] = {}


def add_to_journey(restaurant: RestaurantItem) -> None:
    """Append a restaurant to the ordered Journey Planner itinerary."""
    ensure_session_state()
    stops = list(st.session_state["journey_stops"])
    rid = restaurant["restaurant_id"]
    if any(stop["restaurant_id"] == rid for stop in stops):
        st.toast(
            f"{restaurant['name']} is already in your Journey.",
            icon=":material/route:",
        )
        return
    if len(stops) >= MAX_JOURNEY_STOPS:
        st.toast(
            f"Journey Planner supports up to {MAX_JOURNEY_STOPS} stops.",
            icon=":material/info:",
        )
        return
    st.session_state["journey_stops"] = [*stops, restaurant]
    st.toast(
        f"Added {restaurant['name']} to Journey.",
        icon=":material/route:",
    )


def focus_on_map(restaurant: RestaurantItem) -> None:
    """Stage a restaurant as the active focus target for Map Explorer."""
    ensure_session_state()
    st.session_state["map_focus_restaurant"] = restaurant


@st.cache_data(ttl=settings.streamlit_cache_ttl_seconds, show_spinner=False)
def load_countries() -> CountriesResponse:
    """Load cached country metadata from the backend."""
    return get_api_client().list_countries()


@st.cache_data(ttl=settings.streamlit_cache_ttl_seconds, show_spinner=False)
def load_cities(country: str | None = None) -> CitiesResponse:
    """Load cached city metadata from the backend."""
    return get_api_client().list_cities(country=country)


@st.cache_data(ttl=settings.streamlit_cache_ttl_seconds, show_spinner=False)
def load_cuisines() -> CuisinesResponse:
    """Load cached canonical cuisine metadata from the backend."""
    return get_api_client().list_cuisines()


@st.cache_data(ttl=settings.streamlit_cache_ttl_seconds, show_spinner=False)
def load_analytics(country: str | None = None) -> AnalyticsSummary:
    """Load cached analytics summary metrics from the backend."""
    return get_api_client().get_analytics(country=country)


@st.cache_data(ttl=settings.streamlit_cache_ttl_seconds, show_spinner=False)
def load_destination_profile(country: str) -> DestinationProfile:
    """Load cached editorial destination guide for a country."""
    return get_api_client().get_destination_profile(country)


@st.cache_data(ttl=settings.streamlit_cache_ttl_seconds, show_spinner=False)
def load_pipeline_status() -> PipelineStatus:
    """Load cached pipeline run and freshness status."""
    return get_api_client().get_pipeline_status()


@st.cache_data(ttl=settings.streamlit_cache_ttl_seconds, show_spinner=False)
def load_restaurant_detail(restaurant_id: int) -> RestaurantDetailResponse:
    """Load cached restaurant detail, nearby, and similar records."""
    return get_api_client().get_restaurant(restaurant_id)


@st.cache_data(ttl=settings.streamlit_cache_ttl_seconds, show_spinner=False)
def load_restaurants(
    *,
    country: str | None = None,
    city: str | None = None,
    locality: str | None = None,
    cuisine: tuple[str, ...] = (),
    min_rating: float | None = None,
    max_cost_usd: float | None = None,
    price_range: int | None = None,
    has_online_delivery: bool | None = None,
    has_table_booking: bool | None = None,
    search_query: str | None = None,
    sort_by: str = "rating",
    limit: int = 20,
    offset: int = 0,
) -> RestaurantListResponse:
    """Load cached paginated restaurants for a filter signature."""
    return get_api_client().list_restaurants(
        country=country,
        city=city,
        locality=locality,
        cuisine=list(cuisine) if cuisine else None,
        min_rating=min_rating,
        max_cost_usd=max_cost_usd,
        price_range=price_range,
        has_online_delivery=has_online_delivery,
        has_table_booking=has_table_booking,
        search_query=search_query,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )


@st.cache_data(ttl=settings.streamlit_cache_ttl_seconds, show_spinner=False)
def load_map_points(
    *,
    country: str | None = None,
    city: str | None = None,
    cuisine: tuple[str, ...] = (),
    min_rating: float | None = None,
    price_range: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_m: float | None = None,
    limit: int = 500,
) -> MapPointsResponse:
    """Load cached geolocated map points for a spatial filter signature."""
    return get_api_client().get_map_points(
        country=country,
        city=city,
        cuisine=list(cuisine) if cuisine else None,
        min_rating=min_rating,
        price_range=price_range,
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
        limit=limit,
    )
