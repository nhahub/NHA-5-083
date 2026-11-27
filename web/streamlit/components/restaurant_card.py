"""Editorial restaurant card component with safe text rendering and actions."""

from __future__ import annotations

import streamlit as st

from web.streamlit.api_client import RestaurantItem
from web.streamlit.components.formatters import (
    escape_markdown,
    format_cost,
    format_distance_m,
    format_price_tier,
    format_rating,
    format_source_attribution,
)
from web.streamlit.components.state import (
    add_to_compare,
    add_to_journey,
    ensure_session_state,
    focus_on_map,
    toggle_saved_restaurant,
)
from web.streamlit.constants import RATING_TIER_HIGH, RATING_TIER_MID

_MAX_CARD_CUISINES = 4


def format_location_shorthand(restaurant: RestaurantItem) -> str:
    """Build a concise, scannable location shorthand for card badges."""
    locality = (restaurant.get("locality") or "").strip()
    city = (restaurant.get("city_name") or "").strip()
    country = (restaurant.get("country_name") or "").strip()

    local_parts = [part for part in (locality, city) if part]
    if local_parts and country:
        return f"{', '.join(local_parts)} · {country}"
    if local_parts:
        return ", ".join(local_parts)
    return country or "Location unlisted"


def _rating_badge_color(rating: float | None) -> str:
    if rating is None:
        return "gray"
    if rating >= RATING_TIER_HIGH:
        return "green"
    if rating >= RATING_TIER_MID:
        return "orange"
    return "red"


def _format_cuisines_summary(cuisines: list[str]) -> str:
    if not cuisines:
        return "Cuisine unlisted"
    visible = cuisines[:_MAX_CARD_CUISINES]
    summary = ", ".join(visible)
    remaining = len(cuisines) - len(visible)
    if remaining > 0:
        summary = f"{summary} +{remaining} more"
    return summary


def render_restaurant_card(
    restaurant: RestaurantItem,
    *,
    key_prefix: str,
) -> None:
    """Render a single restaurant card inside a bordered container.

    Args:
        restaurant: Restaurant payload returned by the FastAPI backend.
        key_prefix: Unique prefix to avoid duplicate widget keys across lists.
    """
    ensure_session_state()
    rid = restaurant["restaurant_id"]
    saved_map: dict[int, RestaurantItem] = st.session_state["saved_restaurants"]
    compare_ids: list[int] = st.session_state["compare_ids"]
    journey_stops: list[RestaurantItem] = st.session_state["journey_stops"]

    is_saved = rid in saved_map
    is_comparing = rid in compare_ids
    in_journey = any(stop["restaurant_id"] == rid for stop in journey_stops)

    with st.container(border=True, key=f"card_{key_prefix}_{rid}"):
        st.subheader(escape_markdown(restaurant["name"]), anchor=False)
        st.badge(
            format_location_shorthand(restaurant),
            icon=":material/location_on:",
            color="gray",
        )

        rating = restaurant.get("rating")
        rating_str = format_rating(rating, restaurant.get("rating_text"))
        badge_color = _rating_badge_color(rating)
        votes = restaurant.get("votes")
        votes_label = (
            f"{votes:,} votes" if votes is not None and votes > 0 else "No ratings yet"
        )

        cost_str = format_cost(
            restaurant.get("avg_cost_for_two"),
            restaurant.get("currency_code"),
            restaurant.get("avg_cost_for_two_usd"),
        )
        tier_str = format_price_tier(restaurant.get("price_range"))

        rating_col, cost_col = st.columns(2, wrap=True, vertical_alignment="top")
        with rating_col:
            st.markdown(f":{badge_color}-badge[{escape_markdown(rating_str)}]")
            st.caption(votes_label)
        with cost_col:
            st.markdown(f"**{escape_markdown(cost_str)}**")
            st.caption(tier_str)

        cuisines_summary = _format_cuisines_summary(restaurant.get("cuisines") or [])
        st.caption(
            f":material/restaurant: {escape_markdown(cuisines_summary)}",
            wrap=False,
        )

        address = (restaurant.get("address") or "").strip()
        if address:
            st.text(address, wrap=False)

        footer_parts: list[str] = []
        if restaurant.get("has_table_booking"):
            footer_parts.append("Table booking")
        if restaurant.get("has_online_delivery"):
            footer_parts.append("Online delivery")
        distance_label = format_distance_m(restaurant.get("distance_m"))
        if distance_label:
            footer_parts.append(f"{distance_label} away")
        attribution = format_source_attribution(
            restaurant.get("source_name"),
            restaurant.get("source_license"),
        )
        footer_parts.append(f"Source: {attribution}")
        st.caption(escape_markdown(" · ".join(footer_parts)))

        with st.container(horizontal=True):
            if st.button(
                "Map",
                key=f"{key_prefix}_map_{rid}",
                icon=":material/map:",
                help="Focus this restaurant on Map Explorer",
            ):
                focus_on_map(restaurant)
                st.switch_page("pages/map_explorer.py")

            save_label = "Saved" if is_saved else "Save"
            save_icon = (
                ":material/bookmark_added:" if is_saved else ":material/bookmark:"
            )
            st.button(
                save_label,
                key=f"{key_prefix}_save_{rid}",
                icon=save_icon,
                on_click=toggle_saved_restaurant,
                args=(restaurant,),
            )

            compare_label = "Comparing" if is_comparing else "Compare"
            st.button(
                compare_label,
                key=f"{key_prefix}_cmp_{rid}",
                icon=":material/compare_arrows:",
                on_click=add_to_compare,
                args=(restaurant,),
            )

            journey_label = "In Journey" if in_journey else "+Journey"
            st.button(
                journey_label,
                key=f"{key_prefix}_jrn_{rid}",
                icon=":material/route:",
                on_click=add_to_journey,
                args=(restaurant,),
            )
