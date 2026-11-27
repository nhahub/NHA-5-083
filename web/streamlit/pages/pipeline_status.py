"""Pipeline Status page showing freshness, runs, and quarantine breakdown."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from web.streamlit.api_client import APIError, PipelineStatus
from web.streamlit.components.feedback import (
    render_api_error,
    render_empty_state,
    render_freshness_banner,
)
from web.streamlit.components.maps_and_charts import render_bar_chart_with_table
from web.streamlit.components.state import ensure_session_state, load_pipeline_status
from web.streamlit.constants import MAX_QUARANTINE_RATE_PCT, PIPELINE_STATUS_LABELS

ensure_session_state()

st.title("Pipeline Status", anchor=False)
st.caption(
    "Monitor Bronze-to-Gold ETL runs, 7-day freshness compliance, and "
    "15% quarantine safety-gate metrics."
)

status: PipelineStatus | None = None
try:
    status = load_pipeline_status()
except APIError as exc:
    render_api_error(exc)

if status is not None:
    render_freshness_banner(status)
    latest_run = status.get("latest_run")
    raw_status = str(latest_run.get("status", "unknown")) if latest_run else "unknown"
    status_icon, status_text = PIPELINE_STATUS_LABELS.get(
        raw_status.lower(),
        (":material/help_outline:", raw_status),
    )

    days_since = status.get("days_since_last_success")
    max_age = status["gold_max_age_days"]
    freshness_value = (
        f"{days_since}d / {max_age}d"
        if days_since is not None
        else f"Unknown / {max_age}d"
    )

    q_rate_raw = latest_run.get("quarantine_rate") if latest_run else None
    if q_rate_raw is not None:
        rate_float = float(q_rate_raw)
        q_pct = rate_float * 100.0 if rate_float <= 1.0 else rate_float
        quarantine_value = f"{q_pct:.2f}% (max {MAX_QUARANTINE_RATE_PCT:.0f}%)"
    else:
        quarantine_value = f"N/A (max {MAX_QUARANTINE_RATE_PCT:.0f}%)"

    with st.grid(4, min_column_width=180):
        st.metric(
            "Latest run status",
            status_text,
            border=True,
            height="stretch",
        )
        st.metric(
            "Gold freshness age",
            freshness_value,
            border=True,
            height="stretch",
        )
        st.metric(
            "Latest quarantine rate",
            quarantine_value,
            border=True,
            height="stretch",
        )
        st.metric(
            "Data mode",
            status.get("data_mode", "database"),
            border=True,
            height="stretch",
        )

    st.markdown(f"{status_icon} **Status detail:** {status_text}")
    st.divider()

    recent_runs = status.get("recent_runs") or []
    st.subheader("Recent pipeline runs")
    if not recent_runs:
        render_empty_state(
            "No pipeline runs recorded",
            "No recent pipeline execution records were returned by the backend.",
            "Trigger the Airflow ETL DAG or check pipeline run persistence.",
            icon=":material/history:",
        )
    else:
        runs_rows = [
            {
                "Run ID": str(run.get("run_id", "")),
                "DAG": str(run.get("dag_id", "")),
                "Source": str(run.get("source_name", "")),
                "Status": PIPELINE_STATUS_LABELS.get(
                    str(run.get("status", "")).lower(),
                    ("", str(run.get("status", ""))),
                )[1],
                "Started (UTC)": str(run.get("started_at") or ""),
                "Ended (UTC)": str(run.get("ended_at") or ""),
                "Read": run.get("rows_read"),
                "Inserted": run.get("rows_inserted"),
                "Updated": run.get("rows_updated"),
                "Unchanged": run.get("rows_unchanged"),
                "Quarantined": run.get("rows_quarantined"),
                "Warned": run.get("rows_warned"),
            }
            for run in recent_runs
        ]
        runs_df = pd.DataFrame(runs_rows)
        st.dataframe(
            runs_df,
            width="stretch",
            hide_index=True,
            alt="Recent pipeline run execution history",
        )

    quality_items = status.get("quality_breakdown") or []
    st.divider()
    if not quality_items:
        st.subheader("Data quality breakdown")
        st.caption("No quarantine or warning issues recorded in the latest snapshot.")
    else:
        quality_rows: list[dict[str, object]] = []
        for item in quality_items:
            raw_count = item.get("count")
            if raw_count is None:
                raw_count = item.get("issue_count", 0)
            quality_rows.append(
                {
                    "Rule": str(item.get("rule_name", "unknown_rule")),
                    "Severity": str(item.get("severity", "unknown")),
                    "Issues": int(raw_count or 0),
                    "Sample reason": str(item.get("sample_reason") or ""),
                }
            )
        quality_df = pd.DataFrame(quality_rows)
        render_bar_chart_with_table(
            quality_df,
            category_col="Rule",
            value_col="Issues",
            category_label="Quality rule",
            value_label="Issue count",
            title="Data quality issue breakdown",
            alt_text="Bar chart of quarantined and warned records by validation rule",
            key="pipeline_quality_chart",
            horizontal=True,
        )
