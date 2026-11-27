"""Pipeline status and data quality telemetry schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class PipelineRunOut(BaseModel):
    """Single ETL pipeline run summary."""

    run_id: str
    dag_id: str
    source_id: int | None
    source_name: str | None = None
    started_at: datetime
    ended_at: datetime | None
    status: str
    rows_read: int
    rows_inserted: int
    rows_updated: int
    rows_unchanged: int
    rows_quarantined: int
    rows_warned: int
    quarantine_rate: Decimal


class QualityRuleCountOut(BaseModel):
    """Per-rule data quality count summary."""

    rule_name: str
    severity: str
    count: int


class PipelineStatusOut(BaseModel):
    """Pipeline freshness, recent runs, and quality rule breakdown."""

    latest_run: PipelineRunOut | None
    is_stale: bool
    days_since_last_success: float | None
    gold_max_age_days: int
    recent_runs: list[PipelineRunOut]
    quality_breakdown: list[QualityRuleCountOut]
    data_mode: Literal["mysql", "local_csv_fallback"]
