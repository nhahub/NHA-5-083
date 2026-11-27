"""Natural Language Search page with transparent SearchParams inspection."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from web.streamlit.api_client import (
    APIError,
    NLSearchResponse,
    SearchParamsPayload,
    get_api_client,
)
from web.streamlit.components.feedback import render_api_error, render_empty_state
from web.streamlit.components.formatters import (
    escape_markdown,
    format_cost,
    format_price_tier,
    format_rating,
    format_source_attribution,
)
from web.streamlit.components.restaurant_card import render_restaurant_card
from web.streamlit.components.state import ensure_session_state
from web.streamlit.constants import (
    DEFAULT_PAGE_LIMIT,
    MAX_NLP_INPUT_CHARS,
    NL_EXAMPLE_QUERIES,
)

ensure_session_state()

st.title("Natural Language Search", anchor=False)
st.caption(
    "Describe dining criteria in plain English. Queries are parsed into "
    "validated SearchParams and never generate or execute SQL."
)


def _format_interpreted_table(params: SearchParamsPayload) -> dict[str, str]:
    rows: dict[str, str] = {}
    if params.get("country"):
        rows["Country"] = str(params["country"])
    if params.get("city"):
        rows["City"] = str(params["city"])
    if params.get("locality"):
        rows["Locality"] = str(params["locality"])
    cuisines = params.get("cuisine") or []
    if cuisines:
        rows["Cuisines"] = ", ".join(cuisines)
    if params.get("cuisine_group"):
        rows["Cuisine group"] = str(params["cuisine_group"])
    min_rat = params.get("min_rating")
    if min_rat is not None:
        rows["Minimum rating"] = f"{float(min_rat):.1f}"
    max_usd = params.get("max_cost_usd")
    if max_usd is not None:
        rows["Max cost (USD)"] = f"${float(max_usd):,.2f}"
    max_local = params.get("max_cost_for_two")
    if max_local is not None:
        rows["Max cost (local)"] = f"{float(max_local):,.2f}"
    if params.get("price_range") is not None:
        rows["Price tier"] = format_price_tier(params["price_range"])
    if params.get("has_online_delivery") is not None:
        rows["Online delivery"] = "Yes" if params["has_online_delivery"] else "No"
    if params.get("has_table_booking") is not None:
        rows["Table booking"] = "Yes" if params["has_table_booking"] else "No"
    if params.get("search_query"):
        rows["Keyword"] = str(params["search_query"])
    return rows


st.markdown("**Try an example query**")
with st.container(horizontal=True):
    for idx, sample_query in enumerate(NL_EXAMPLE_QUERIES):
        if st.button(
            sample_query,
            key=f"nl_example_{idx}",
            icon=":material/bolt:",
        ):
            st.session_state["nl_last_query"] = sample_query
            st.session_state["nl_active_params"] = None
            st.session_state["nl_history"] = []
            try:
                with st.spinner("Interpreting query..."):
                    resp = get_api_client().search_nl(
                        query=sample_query,
                        limit=DEFAULT_PAGE_LIMIT,
                        offset=0,
                    )
                    st.session_state["nl_last_response"] = resp
                    if not resp["interpreted_params"].get("needs_clarification"):
                        st.session_state["nl_active_params"] = resp[
                            "interpreted_params"
                        ]
                        st.session_state["nl_history"] = [sample_query]
                        st.rerun()
            except APIError as exc:
                render_api_error(exc)

nl_history: list[str] = list(st.session_state.get("nl_history") or [])
active_params: SearchParamsPayload | None = st.session_state.get("nl_active_params")
if nl_history and active_params is not None:
    ctx_col, reset_col = st.columns([4, 1], vertical_alignment="center")
    with ctx_col:
        trail = " -> ".join(
            f"{i + 1}. {escape_markdown(step)}" for i, step in enumerate(nl_history)
        )
        st.caption(f"Follow-up context active: {trail}")
    with reset_col:
        if st.button(
            "New search",
            key="nl_reset_context",
            icon=":material/restart_alt:",
            width="stretch",
        ):
            st.session_state["nl_active_params"] = None
            st.session_state["nl_history"] = []
            st.session_state["nl_last_query"] = ""
            st.session_state["nl_last_response"] = None
            st.rerun()

with st.form("nl_search_form"):
    prompt_label = (
        "Follow-up refinement prompt (refines active filters above)"
        if active_params is not None
        else "Dining search prompt"
    )
    prompt_placeholder = (
        "e.g., in New Delhi, rated above 4.2, with online delivery"
        if active_params is not None
        else "e.g., affordable Italian in New Delhi rated above 4"
    )
    query_input = st.text_input(
        prompt_label,
        value=""
        if active_params is not None
        else str(st.session_state.get("nl_last_query") or ""),
        max_chars=MAX_NLP_INPUT_CHARS,
        placeholder=prompt_placeholder,
    )
    submitted = st.form_submit_button(
        "Refine search"
        if active_params is not None
        else "Search with natural language",
        type="primary",
        icon=":material/search:",
        width="stretch",
    )

if submitted:
    cleaned = query_input.strip()
    if not cleaned:
        st.warning(
            "Enter a dining request before searching.",
            title="Query required",
            icon=":material/edit_note:",
        )
    else:
        st.session_state["nl_last_query"] = cleaned
        try:
            with st.spinner("Interpreting natural-language filters..."):
                resp = get_api_client().search_nl(
                    query=cleaned,
                    limit=DEFAULT_PAGE_LIMIT,
                    offset=0,
                    previous_params=active_params,
                )
                st.session_state["nl_last_response"] = resp
                if not resp["interpreted_params"].get("needs_clarification"):
                    st.session_state["nl_active_params"] = resp["interpreted_params"]
                    st.session_state["nl_history"] = [*nl_history, cleaned]
                    st.rerun()
        except APIError as exc:
            render_api_error(exc)

last_response: NLSearchResponse | None = st.session_state.get("nl_last_response")
if last_response is not None:
    st.divider()
    interpreted = last_response["interpreted_params"]
    parser_used = last_response["parser_used"]
    fallback_used = last_response["fallback_used"]

    st.subheader("Interpreted parameters")
    st.caption(f"Original prompt: {escape_markdown(last_response['query'])}")

    if parser_used == "huggingface_semantic":
        st.caption(
            "Parser: Hugging Face local semantic model "
            "(all-MiniLM-L6-v2 ONNX) + constrained rules."
        )
    elif fallback_used or parser_used == "rule_based":
        st.caption(
            "Parser fallback: handled deterministically by the rule-based parser "
            "instead of the primary LLM provider."
        )
    else:
        st.caption("Parser: Hugging Face constrained extraction")

    clarification = interpreted.get("needs_clarification")
    if clarification:
        st.info(
            escape_markdown(clarification),
            title="Clarification needed",
            icon=":material/help:",
        )

    interpreted_rows = _format_interpreted_table(interpreted)
    if interpreted_rows:
        st.table(interpreted_rows, border="horizontal", width="content")
    else:
        st.caption("No specific structured constraints were extracted from the prompt.")

    items = last_response["items"]
    total = last_response["total"]
    st.subheader(f"Matching restaurants ({total:,})")

    if not items:
        render_empty_state(
            "No restaurants matched the interpreted filters",
            "The extracted criteria returned zero records from the Gold catalog.",
            "Try relaxing the city, cuisine, or budget constraint in your prompt.",
        )
    else:
        cards_tab, table_tab = st.tabs(["Editorial cards", "Data table"])
        with cards_tab, st.grid(2, min_column_width=320):
            for item in items:
                render_restaurant_card(item, key_prefix="nl")
        with table_tab:
            nl_df = pd.DataFrame(
                [
                    {
                        "Name": item["name"],
                        "City": item["city_name"],
                        "Country": item["country_name"],
                        "Cuisines": ", ".join(item.get("cuisines") or []),
                        "Rating": format_rating(
                            item.get("rating"), item.get("rating_text")
                        ),
                        "Cost for two": format_cost(
                            item.get("avg_cost_for_two"),
                            item.get("currency_code"),
                            item.get("avg_cost_for_two_usd"),
                        ),
                        "Source & License": format_source_attribution(
                            item.get("source_name"),
                            item.get("source_license"),
                        ),
                    }
                    for item in items
                ]
            )
            st.dataframe(
                nl_df,
                width="stretch",
                hide_index=True,
                alt="Natural-language search results table",
            )
