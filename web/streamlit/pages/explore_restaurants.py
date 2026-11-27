"""Explore Restaurants page with structured filters, cards, and detail view."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from web.streamlit.api_client import (
    APIError,
    RestaurantListResponse,
)
from web.streamlit.components.feedback import (
    render_api_error,
    render_empty_state,
    render_freshness_banner,
)
from web.streamlit.components.formatters import (
    format_cost,
    format_price_tier,
    format_rating,
    format_source_attribution,
)
from web.streamlit.components.restaurant_card import render_restaurant_card
from web.streamlit.components.state import (
    ensure_session_state,
    load_cities,
    load_countries,
    load_cuisines,
    load_pipeline_status,
    load_restaurants,
)
from web.streamlit.constants import (
    COST_USD_STEP,
    DEFAULT_PAGE_LIMIT,
    MAX_COST_USD_LIMIT,
    MAX_RATING,
    MIN_RATING,
    PAGE_LIMIT_OPTIONS,
    PRICE_RANGE_OPTIONS,
    PRICE_TIER_LABELS,
    RATING_STEP,
    SORT_LABELS,
)

ensure_session_state()

st.title("Explore Restaurants", anchor=False)
st.caption(
    "Filter verified restaurant records by geography, cuisine, rating, "
    "and batch-standardized USD cost."
)

try:
    pipeline_status = load_pipeline_status()
    render_freshness_banner(pipeline_status)
except APIError:
    pass

countries_list: list[str] = []
cities_list: list[str] = []
cuisines_list: list[str] = []

try:
    countries_resp = load_countries()
    countries_list = [item["country_name"] for item in countries_resp["items"]]
    cuisines_resp = load_cuisines()
    cuisines_list = sorted({item["cuisine_name"] for item in cuisines_resp["items"]})
except APIError as exc:
    render_api_error(exc)

with st.form("explore_filters_form"):
    row_top = st.columns(3, wrap=True)
    with row_top[0]:
        search_query = st.text_input(
            "Restaurant or keyword",
            placeholder="e.g., Bistro, Sushi, Zamalek",
        )
    with row_top[1]:
        selected_country = st.selectbox(
            "Country",
            options=["All countries", *countries_list],
        )
    country_param = None if selected_country == "All countries" else selected_country
    if countries_list:
        try:
            cities_resp = load_cities(country=country_param)
            cities_list = [item["city_name"] for item in cities_resp["items"]]
        except APIError:
            cities_list = []

    with row_top[2]:
        selected_city = st.selectbox(
            "City",
            options=["All cities", *cities_list],
        )

    row_mid = st.columns(3, wrap=True)
    with row_mid[0]:
        selected_cuisines = st.multiselect(
            "Cuisines",
            options=cuisines_list,
            placeholder="Any cuisine",
        )
    with row_mid[1]:
        min_rating = st.slider(
            "Minimum rating (0.0 includes Unrated)",
            min_value=MIN_RATING,
            max_value=MAX_RATING,
            value=MIN_RATING,
            step=RATING_STEP,
        )
    with row_mid[2]:
        price_options = [
            "All price tiers",
            *[str(tier) for tier in PRICE_RANGE_OPTIONS],
        ]
        selected_price_label = st.selectbox(
            "Price tier",
            options=price_options,
            format_func=lambda val: (
                val if val == "All price tiers" else PRICE_TIER_LABELS[int(val)]
            ),
        )

    with st.expander("Additional filters and sorting", expanded=False):
        row_adv = st.columns(3, wrap=True)
        with row_adv[0]:
            locality_query = st.text_input(
                "Locality / neighborhood",
                placeholder="e.g., Zamalek, Soho",
            )
            max_cost_usd = st.number_input(
                "Maximum cost for two (USD, 0 = no limit)",
                min_value=0.0,
                max_value=MAX_COST_USD_LIMIT,
                value=0.0,
                step=COST_USD_STEP,
            )
        with row_adv[1]:
            sort_by = st.selectbox(
                "Sort results by",
                options=list(SORT_LABELS.keys()),
                format_func=lambda key: SORT_LABELS[key],
            )
            page_limit = st.selectbox(
                "Results per page",
                options=list(PAGE_LIMIT_OPTIONS),
                index=PAGE_LIMIT_OPTIONS.index(DEFAULT_PAGE_LIMIT),
            )
        with row_adv[2]:
            online_delivery_only = st.checkbox("Online delivery available")
            table_booking_only = st.checkbox("Table booking available")

    submitted = st.form_submit_button(
        "Apply filters",
        type="primary",
        icon=":material/search:",
        width="stretch",
    )

if submitted:
    st.session_state["explore_offset"] = 0

current_offset = int(st.session_state["explore_offset"])
city_param = None if selected_city == "All cities" else selected_city
price_param = (
    None if selected_price_label == "All price tiers" else int(selected_price_label)
)
min_rating_param = None if min_rating <= MIN_RATING else min_rating
max_cost_param = None if max_cost_usd <= 0.0 else float(max_cost_usd)

list_resp: RestaurantListResponse | None = None
try:
    with st.spinner("Loading matching restaurants..."):
        list_resp = load_restaurants(
            country=country_param,
            city=city_param,
            locality=locality_query.strip() or None,
            cuisine=tuple(selected_cuisines),
            min_rating=min_rating_param,
            max_cost_usd=max_cost_param,
            price_range=price_param,
            has_online_delivery=True if online_delivery_only else None,
            has_table_booking=True if table_booking_only else None,
            search_query=search_query.strip() or None,
            sort_by=sort_by,
            limit=page_limit,
            offset=current_offset,
        )
except APIError as exc:
    render_api_error(exc)

if list_resp is not None:
    items = list_resp["items"]
    total = list_resp["total"]

    summary_col, view_col = st.columns([2, 1], wrap=True, vertical_alignment="center")
    with summary_col:
        if total > 0:
            start_idx = current_offset + 1
            end_idx = min(current_offset + len(items), total)
            st.markdown(
                f"Showing **{start_idx}–{end_idx}** of **{total:,}** restaurants · "
                f"Sorted by {SORT_LABELS[sort_by]}"
            )
        else:
            st.markdown("**0** matching restaurants")

    with view_col:
        display_mode = st.segmented_control(
            "Display format",
            options=["Editorial cards", "Data table"],
            default="Editorial cards",
            label_visibility="collapsed",
        )

    if not items:
        render_empty_state(
            "No restaurants matched those filters",
            "No venues in the current dataset satisfy all active filter criteria.",
            "Try clearing one or more filters, lowering the minimum rating, or "
            "broadening the city selection.",
        )
    elif display_mode == "Data table":
        table_rows = [
            {
                "Name": item["name"],
                "City": item["city_name"],
                "Country": item["country_name"],
                "Locality": item.get("locality") or "",
                "Cuisines": ", ".join(item.get("cuisines") or []),
                "Rating": format_rating(item.get("rating"), item.get("rating_text")),
                "Votes": item.get("votes"),
                "Cost for two": format_cost(
                    item.get("avg_cost_for_two"),
                    item.get("currency_code"),
                    item.get("avg_cost_for_two_usd"),
                ),
                "Price tier": format_price_tier(item.get("price_range")),
                "Source & License": format_source_attribution(
                    item.get("source_name"),
                    item.get("source_license"),
                ),
            }
            for item in items
        ]
        restaurants_df = pd.DataFrame(table_rows)
        st.dataframe(
            restaurants_df,
            width="stretch",
            hide_index=True,
            alt="Filtered restaurant directory table",
        )
    else:
        with st.grid(2, min_column_width=320):
            for item in items:
                render_restaurant_card(item, key_prefix="explore")

    if total > page_limit:
        st.divider()
        with st.container(horizontal=True, vertical_alignment="center"):
            prev_disabled = current_offset <= 0
            next_disabled = current_offset + page_limit >= total
            if st.button(
                "Previous page",
                icon=":material/chevron_left:",
                disabled=prev_disabled,
            ):
                st.session_state["explore_offset"] = max(0, current_offset - page_limit)
                st.rerun()
            if st.button(
                "Next page",
                icon=":material/chevron_right:",
                disabled=next_disabled,
            ):
                st.session_state["explore_offset"] = current_offset + page_limit
                st.rerun()
