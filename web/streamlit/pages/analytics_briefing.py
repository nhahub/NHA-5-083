"""Analytics Briefing page with dataset coverage, ratings, and cuisine charts."""

from __future__ import annotations

import contextlib

import pandas as pd
import streamlit as st

from web.streamlit.api_client import AnalyticsBucket, AnalyticsSummary, APIError
from web.streamlit.components.feedback import render_api_error, render_freshness_banner
from web.streamlit.components.formatters import format_rating
from web.streamlit.components.maps_and_charts import render_bar_chart_with_table
from web.streamlit.components.state import (
    ensure_session_state,
    load_analytics,
    load_countries,
    load_pipeline_status,
)

ensure_session_state()

st.title("Analytics Briefing", anchor=False)
st.caption(
    "Coverage, rating completeness, cuisine concentration, and price tiers "
    "with tabular equivalents."
)

with contextlib.suppress(APIError):
    render_freshness_banner(load_pipeline_status())

countries_list: list[str] = []
try:
    countries_list = [item["country_name"] for item in load_countries()["items"]]
except APIError as exc:
    render_api_error(exc)

selected_country = st.selectbox(
    "Analytics scope",
    options=["All countries", *countries_list],
)
country_param = None if selected_country == "All countries" else selected_country

summary: AnalyticsSummary | None = None
try:
    summary = load_analytics(country=country_param)
except APIError as exc:
    render_api_error(exc)


def _bucket_to_df(
    buckets: list[AnalyticsBucket],
    *,
    label_keys: tuple[str, ...],
    label_col: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for bucket in buckets:
        label_val: object = "Unknown"
        for candidate in label_keys:
            if candidate in bucket and bucket[candidate] is not None:  # type: ignore[literal-required]
                label_val = bucket[candidate]  # type: ignore[literal-required]
                break
        count_val = bucket.get("restaurant_count")
        if count_val is None:
            count_val = bucket.get("count", 0)
        rows.append(
            {
                label_col: str(label_val),
                "Restaurants": int(count_val),
            }
        )
    return pd.DataFrame(rows)


if summary is not None:
    avg_rating_display = format_rating(summary.get("avg_rating"), include_text=False)
    total_restaurants = summary["total_restaurants"]
    rated_count = summary["rated_count"]
    unrated_count = summary["unrated_count"]
    geolocated_count = summary["geolocated_count"]

    with st.grid(4, min_column_width=180):
        st.metric(
            "Verified restaurants",
            f"{total_restaurants:,}",
            border=True,
            height="stretch",
        )
        countries_count = summary["total_countries"]
        cities_count = summary["total_cities"]
        st.metric(
            "Geography covered",
            f"{countries_count} countries · {cities_count} cities",
            border=True,
            height="stretch",
        )
        st.metric(
            "Rated vs. Unrated",
            f"{rated_count:,} / {unrated_count:,}",
            border=True,
            height="stretch",
        )
        st.metric(
            "Mean rating (rated only)",
            avg_rating_display,
            border=True,
            height="stretch",
        )

    st.caption(
        f"Geolocated venues with valid coordinates: {geolocated_count:,} of "
        f"{total_restaurants:,} · Distinct cuisines: {summary['total_cuisines']:,}"
    )
    st.divider()

    cuisines_df = _bucket_to_df(
        summary.get("top_cuisines") or [],
        label_keys=("cuisine_name", "label", "name"),
        label_col="Cuisine",
    )
    countries_df = _bucket_to_df(
        summary.get("by_country") or [],
        label_keys=("country_name", "label", "name"),
        label_col="Country",
    )

    row_charts_top = st.columns(2, wrap=True)
    with row_charts_top[0]:
        render_bar_chart_with_table(
            cuisines_df,
            category_col="Cuisine",
            value_col="Restaurants",
            category_label="Cuisine",
            value_label="Restaurants",
            title="Top cuisines",
            alt_text="Bar chart of top cuisines by restaurant count",
            key="analytics_cuisines_chart",
            horizontal=True,
        )
    with row_charts_top[1]:
        render_bar_chart_with_table(
            countries_df,
            category_col="Country",
            value_col="Restaurants",
            category_label="Country",
            value_label="Restaurants",
            title="Restaurants by country",
            alt_text="Bar chart of restaurant coverage by country",
            key="analytics_countries_chart",
            horizontal=True,
        )

    price_df = _bucket_to_df(
        summary.get("by_price_range") or [],
        label_keys=("label", "price_range", "name"),
        label_col="Price tier",
    )
    rating_dist_df = _bucket_to_df(
        summary.get("rating_distribution") or [],
        label_keys=("rating_label", "rating_bucket", "label", "name"),
        label_col="Rating band",
    )

    row_charts_bottom = st.columns(2, wrap=True)
    with row_charts_bottom[0]:
        render_bar_chart_with_table(
            price_df,
            category_col="Price tier",
            value_col="Restaurants",
            category_label="Price tier",
            value_label="Restaurants",
            title="Price tier distribution",
            alt_text="Bar chart of restaurant counts across price tiers 1 through 4",
            key="analytics_price_chart",
            horizontal=False,
            sort_descending=False,
        )
    with row_charts_bottom[1]:
        render_bar_chart_with_table(
            rating_dist_df,
            category_col="Rating band",
            value_col="Restaurants",
            category_label="Rating band",
            value_label="Restaurants",
            title="Rating distribution (including Unrated)",
            alt_text="Bar chart of rating bands with explicit unrated category",
            key="analytics_rating_chart",
            horizontal=False,
            sort_descending=False,
        )
