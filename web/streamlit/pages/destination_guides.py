"""Destination Guides page with country culinary briefings and top venues."""

from __future__ import annotations

import contextlib

import pandas as pd
import streamlit as st

from web.streamlit.api_client import APIError, DestinationProfile
from web.streamlit.components.feedback import (
    render_api_error,
    render_empty_state,
    render_freshness_banner,
)
from web.streamlit.components.formatters import escape_markdown, format_rating
from web.streamlit.components.restaurant_card import render_restaurant_card
from web.streamlit.components.state import (
    ensure_session_state,
    load_countries,
    load_destination_profile,
    load_pipeline_status,
)

ensure_session_state()

st.title("Destination Guides", anchor=False)
st.caption(
    "Country-level culinary briefings, local currency context, top cities, "
    "and notable restaurants."
)

with contextlib.suppress(APIError):
    render_freshness_banner(load_pipeline_status())

countries_list: list[str] = []
try:
    countries_list = [item["country_name"] for item in load_countries()["items"]]
except APIError as exc:
    render_api_error(exc)

if not countries_list:
    render_empty_state(
        "No destinations available",
        "Country destination metadata is currently unavailable.",
        "Confirm the backend API is running and refresh the page.",
        icon=":material/public_off:",
    )
else:
    selected_country = st.selectbox(
        "Select destination country",
        options=countries_list,
    )
    profile: DestinationProfile | None = None
    try:
        profile = load_destination_profile(selected_country)
    except APIError as exc:
        render_api_error(exc)

    if profile is not None:
        st.header(escape_markdown(profile["country_name"]))
        if profile.get("tagline"):
            st.markdown(f"*{escape_markdown(profile['tagline'])}*")
        if profile.get("dining_tradition"):
            st.text(profile["dining_tradition"])

        mean_rating_label = format_rating(
            profile.get("avg_rating"),
            include_text=False,
        )
        with st.grid(4, min_column_width=180):
            st.metric(
                "Restaurants",
                f"{profile['restaurant_count']:,}",
                border=True,
                height="stretch",
            )
            st.metric(
                "Cities covered",
                f"{profile['city_count']:,}",
                border=True,
                height="stretch",
            )
            st.metric(
                "Mean rating",
                mean_rating_label,
                border=True,
                height="stretch",
            )
            st.metric(
                "Local currency",
                profile["currency_code"],
                border=True,
                height="stretch",
            )

        dishes = profile.get("signature_dishes") or []
        if dishes:
            st.markdown(
                "**Signature dishes:** "
                + ", ".join(escape_markdown(dish) for dish in dishes)
            )
        st.caption(f"Editorial attribution: {escape_markdown(profile['attribution'])}")
        st.divider()

        def _ranked_list_table(
            entries: list[str],
            *,
            col_name: str,
        ) -> pd.DataFrame:
            rows = [
                {"Rank": idx, col_name: entry}
                for idx, entry in enumerate(entries, start=1)
            ]
            return pd.DataFrame(rows)

        col_cities, col_cuisines = st.columns(2, wrap=True)
        with col_cities:
            st.subheader("Top cities")
            top_cities_df = _ranked_list_table(
                profile.get("top_cities") or [],
                col_name="City",
            )
            if top_cities_df.empty:
                st.caption("No city breakdown available.")
            else:
                st.dataframe(
                    top_cities_df,
                    width="stretch",
                    hide_index=True,
                    alt=f"Top cities in {profile['country_name']}",
                )
        with col_cuisines:
            st.subheader("Top cuisines")
            top_cuisines_df = _ranked_list_table(
                profile.get("top_cuisines") or [],
                col_name="Cuisine",
            )
            if top_cuisines_df.empty:
                st.caption("No cuisine breakdown available.")
            else:
                st.dataframe(
                    top_cuisines_df,
                    width="stretch",
                    hide_index=True,
                    alt=f"Top cuisines in {profile['country_name']}",
                )

        top_restaurants = profile.get("top_restaurants") or []
        st.subheader("Notable venues")
        if not top_restaurants:
            st.caption("No featured restaurants returned for this destination.")
        else:
            with st.grid(2, min_column_width=320):
                for venue in top_restaurants:
                    render_restaurant_card(venue, key_prefix="dest")
