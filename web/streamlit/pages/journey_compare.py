"""Journey & Compare page for side-by-side comparison and route planning."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from web.streamlit.api_client import APIError, RestaurantItem
from web.streamlit.components.feedback import render_empty_state
from web.streamlit.components.formatters import (
    build_directions_url,
    escape_markdown,
    estimate_leg_minutes,
    format_cost,
    format_price_tier,
    format_rating,
    format_source_attribution,
    haversine_km,
    is_valid_coordinate,
)
from web.streamlit.components.maps_and_charts import render_journey_route_map
from web.streamlit.components.state import (
    add_to_compare,
    add_to_journey,
    clear_compare,
    ensure_session_state,
    load_restaurant_detail,
    remove_from_compare,
)
from web.streamlit.constants import MAX_COMPARE_ITEMS, MIN_JOURNEY_STOPS

ensure_session_state()

st.title("Journey & Compare", anchor=False)
st.caption(
    "Compare shortlisted venues side by side and assemble multi-stop itineraries "
    "with straight-line Haversine leg estimates."
)

saved_map: dict[int, RestaurantItem] = st.session_state["saved_restaurants"]
compare_ids: list[int] = st.session_state["compare_ids"]
compare_items: dict[int, RestaurantItem] = st.session_state["compare_items"]
journey_stops: list[RestaurantItem] = st.session_state["journey_stops"]

compare_tab, journey_tab = st.tabs(
    [
        f"Compare ({len(compare_ids)}/{MAX_COMPARE_ITEMS})",
        f"Journey Planner ({len(journey_stops)} stops)",
    ]
)

with compare_tab:
    if saved_map:
        available_for_compare = [
            item for rid, item in saved_map.items() if rid not in compare_ids
        ]
        if available_for_compare and len(compare_ids) < MAX_COMPARE_ITEMS:
            pick_col, add_col = st.columns(
                [3, 1], wrap=True, vertical_alignment="bottom"
            )
            with pick_col:
                chosen_cmp = st.selectbox(
                    "Add from Saved restaurants",
                    options=available_for_compare,
                    format_func=lambda r: f"{r['name']} ({r['city_name']})",
                    key="compare_saved_pick",
                )
            with add_col:
                if st.button(
                    "Add to Compare",
                    icon=":material/compare_arrows:",
                    width="stretch",
                ):
                    add_to_compare(chosen_cmp)
                    st.rerun()

    if not compare_ids:
        render_empty_state(
            "Comparison tray is empty",
            "No restaurants are currently queued for side-by-side comparison.",
            "Click Compare on any card in Explore Restaurants or NL Search.",
            icon=":material/compare_arrows:",
        )
    else:
        resolved_items: list[RestaurantItem] = []
        for rid in compare_ids:
            if rid in compare_items:
                resolved_items.append(compare_items[rid])
                continue
            if rid in saved_map:
                resolved_items.append(saved_map[rid])
                continue
            try:
                resolved_items.append(load_restaurant_detail(rid)["restaurant"])
            except APIError:
                continue

        if resolved_items:
            compare_rows = [
                {
                    "Name": item["name"],
                    "Location": f"{item['city_name']}, {item['country_name']}",
                    "Cuisines": ", ".join(item.get("cuisines") or []),
                    "Rating": format_rating(
                        item.get("rating"), item.get("rating_text")
                    ),
                    "Votes": item.get("votes"),
                    "Cost for two": format_cost(
                        item.get("avg_cost_for_two"),
                        item.get("currency_code"),
                        item.get("avg_cost_for_two_usd"),
                    ),
                    "Price tier": format_price_tier(item.get("price_range")),
                    "Table booking": "Yes" if item.get("has_table_booking") else "No",
                    "Online delivery": (
                        "Yes" if item.get("has_online_delivery") else "No"
                    ),
                    "Source & License": format_source_attribution(
                        item.get("source_name"),
                        item.get("source_license"),
                    ),
                }
                for item in resolved_items
            ]
            compare_df = pd.DataFrame(compare_rows)
            st.dataframe(
                compare_df,
                width="stretch",
                hide_index=True,
                alt="Side-by-side comparison of shortlisted restaurants",
            )

            with st.container(horizontal=True):
                for item in resolved_items:
                    st.button(
                        f"Remove {item['name']}",
                        key=f"cmp_remove_{item['restaurant_id']}",
                        icon=":material/close:",
                        on_click=remove_from_compare,
                        args=(item["restaurant_id"],),
                    )
                st.button(
                    "Clear all",
                    key="cmp_clear_all",
                    icon=":material/delete:",
                    on_click=clear_compare,
                )

with journey_tab:
    if saved_map:
        available_for_journey = [
            item
            for item in saved_map.values()
            if all(s["restaurant_id"] != item["restaurant_id"] for s in journey_stops)
        ]
        if available_for_journey:
            j_pick_col, j_add_col = st.columns(
                [3, 1], wrap=True, vertical_alignment="bottom"
            )
            with j_pick_col:
                chosen_stop = st.selectbox(
                    "Add stop from Saved restaurants",
                    options=available_for_journey,
                    format_func=lambda r: f"{r['name']} ({r['city_name']})",
                    key="journey_saved_pick",
                )
            with j_add_col:
                if st.button(
                    "Add stop",
                    icon=":material/add_location_alt:",
                    width="stretch",
                ):
                    add_to_journey(chosen_stop)
                    st.rerun()

    if not journey_stops:
        render_empty_state(
            "No stops in your Journey yet",
            "Your multi-stop dining itinerary currently has zero stops.",
            "Use +Journey on restaurant cards to sequence two or more stops.",
            icon=":material/route:",
        )
    else:
        st.subheader("Itinerary order")
        for idx, stop in enumerate(journey_stops):
            with st.container(border=True, key=f"card_jrn_{stop['restaurant_id']}"):
                info_col, ctrl_col = st.columns(
                    [3, 2], wrap=True, vertical_alignment="center"
                )
                with info_col:
                    st.markdown(
                        f"**Stop {idx + 1}: {escape_markdown(stop['name'])}** · "
                        f"{escape_markdown(stop['city_name'])}, "
                        f"{escape_markdown(stop['country_name'])}"
                    )
                    stop_rating = escape_markdown(
                        format_rating(stop.get("rating"), stop.get("rating_text"))
                    )
                    stop_cost = escape_markdown(
                        format_cost(
                            stop.get("avg_cost_for_two"),
                            stop.get("currency_code"),
                            stop.get("avg_cost_for_two_usd"),
                        )
                    )
                    st.caption(f"{stop_rating} · {stop_cost}")
                with ctrl_col, st.container(horizontal=True):
                    stop_dir_url = build_directions_url(stop)
                    if stop_dir_url:
                        st.link_button(
                            "Directions",
                            url=stop_dir_url,
                            icon=":material/directions:",
                        )
                    if idx > 0 and st.button(
                        "Up",
                        key=f"jrn_up_{stop['restaurant_id']}",
                        icon=":material/arrow_upward:",
                    ):
                        journey_stops[idx - 1], journey_stops[idx] = (
                            journey_stops[idx],
                            journey_stops[idx - 1],
                        )
                        st.rerun()
                    if idx < len(journey_stops) - 1 and st.button(
                        "Down",
                        key=f"jrn_down_{stop['restaurant_id']}",
                        icon=":material/arrow_downward:",
                    ):
                        journey_stops[idx + 1], journey_stops[idx] = (
                            journey_stops[idx],
                            journey_stops[idx + 1],
                        )
                        st.rerun()
                    if st.button(
                        "Remove",
                        key=f"jrn_del_{stop['restaurant_id']}",
                        icon=":material/close:",
                    ):
                        journey_stops.pop(idx)
                        st.rerun()

        if st.button("Clear itinerary", key="jrn_clear_all", icon=":material/delete:"):
            st.session_state["journey_stops"] = []
            st.rerun()

        if len(journey_stops) < MIN_JOURNEY_STOPS:
            st.info(
                "Add at least one more stop to compute legs and map the route.",
                icon=":material/info:",
            )
        else:
            leg_rows: list[dict[str, object]] = []
            total_km = 0.0
            for idx in range(len(journey_stops) - 1):
                origin = journey_stops[idx]
                dest = journey_stops[idx + 1]
                o_lat, o_lon = origin.get("latitude"), origin.get("longitude")
                d_lat, d_lon = dest.get("latitude"), dest.get("longitude")

                if (
                    is_valid_coordinate(o_lat, o_lon)
                    and is_valid_coordinate(d_lat, d_lon)
                    and o_lat is not None
                    and o_lon is not None
                    and d_lat is not None
                    and d_lon is not None
                ):
                    dist_km = haversine_km(
                        float(o_lat), float(o_lon), float(d_lat), float(d_lon)
                    )
                    total_km += dist_km
                    walk_mins, drive_mins = estimate_leg_minutes(dist_km)
                    dist_label = f"{dist_km:.2f} km"
                    walk_label = f"~{walk_mins} min"
                    drive_label = f"~{drive_mins} min"
                    dir_url = build_directions_url(
                        dest,
                        origin_lat=float(o_lat),
                        origin_lon=float(o_lon),
                    )
                else:
                    dist_label = "Coordinates missing"
                    walk_label = "N/A"
                    drive_label = "N/A"
                    dir_url = build_directions_url(dest)

                leg_rows.append(
                    {
                        "Leg": f"Stop {idx + 1} → Stop {idx + 2}",
                        "From": origin["name"],
                        "To": dest["name"],
                        "Straight-line distance": dist_label,
                        "Est. walk": walk_label,
                        "Est. transit/car": drive_label,
                        "Directions": dir_url or "",
                    }
                )

            legs_df = pd.DataFrame(leg_rows)
            st.metric(
                "Total straight-line route distance",
                f"{total_km:.2f} km",
                border=True,
            )
            render_journey_route_map(
                journey_stops,
                legs_df,
                key="journey_route_map",
            )

            st.subheader("External directions")
            with st.container(horizontal=True):
                for leg in leg_rows:
                    url_val = str(leg.get("Directions") or "")
                    if url_val:
                        st.link_button(
                            str(leg["Leg"]),
                            url=url_val,
                            icon=":material/directions:",
                        )
