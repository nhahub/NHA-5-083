"""User feedback, freshness notice, empty-state, and API error components."""

from __future__ import annotations

import streamlit as st

from web.streamlit.api_client import APIError, PipelineStatus
from web.streamlit.settings import settings


def render_freshness_banner(status: PipelineStatus | None) -> None:
    """Display dataset freshness metadata and warn if Gold data exceeds 7 days."""
    if status is None:
        return

    latest_run = status.get("latest_run")
    days_since = status.get("days_since_last_success")
    max_age_days = (
        status.get("gold_max_age_days") or settings.freshness_gold_max_age_days
    )
    data_mode = status.get("data_mode", "database")

    refresh_text = "No successful run recorded yet"
    if latest_run and latest_run.get("ended_at"):
        refresh_text = f"Last pipeline update: {latest_run['ended_at']}"
    elif latest_run and latest_run.get("started_at"):
        refresh_text = f"Latest pipeline run started: {latest_run['started_at']}"

    if days_since is not None:
        age_note = f"{days_since} day(s) since last successful run"
    else:
        age_note = f"Freshness threshold: {max_age_days} days"

    st.caption(f"{refresh_text} · {age_note} · Mode: {data_mode}")

    is_stale = bool(status.get("is_stale")) or (
        days_since is not None and days_since > max_age_days
    )
    if is_stale:
        st.warning(
            (
                f"Gold data has not completed a successful refresh within the "
                f"{max_age_days}-day freshness threshold. Results may reflect an "
                f"older snapshot."
            ),
            title="Gold data freshness notice",
            icon=":material/schedule:",
        )


def render_empty_state(
    title: str,
    reason: str,
    suggestion: str,
    *,
    icon: str = ":material/search_off:",
) -> None:
    """Render a calm, structured empty state with a concrete next step."""
    st.info(f"{reason}\n\n{suggestion}", title=title, icon=icon)


def render_api_error(error: APIError) -> None:
    """Render a plain-language API error without exposing internal URLs or traces."""
    st.error(
        error.user_message,
        title="Data service notice",
        icon=":material/error_outline:",
    )
