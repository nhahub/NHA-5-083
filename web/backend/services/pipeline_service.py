"""Service layer for pipeline run telemetry and Gold freshness calculation."""

from __future__ import annotations

from datetime import UTC, datetime

from web.backend.constants import (
    GOLD_MAX_AGE_DAYS,
    SECONDS_PER_DAY,
    SUCCESS_RUN_STATUSES,
)
from web.backend.repositories.pipeline_repository import PipelineRepository
from web.backend.schemas.pipeline import PipelineStatusOut
from web.backend.settings import BackendSettings, settings


class PipelineService:
    """Service computing Gold freshness and returning pipeline telemetry."""

    def __init__(
        self,
        repository: PipelineRepository,
        app_settings: BackendSettings | None = None,
    ) -> None:
        """Initialize PipelineService with repository and optional settings."""
        self._repository = repository
        self._settings = app_settings or settings

    def get_status(self) -> PipelineStatusOut:
        """Return pipeline runs, quality breakdown, and staleness evaluation."""
        recent_runs, quality_breakdown, data_mode = self._repository.get_telemetry()
        gold_max_age_days = (
            self._settings.freshness_gold_max_age_days or GOLD_MAX_AGE_DAYS
        )
        latest_run = recent_runs[0] if recent_runs else None

        last_success_ts: datetime | None = None
        for run in recent_runs:
            if run.status in SUCCESS_RUN_STATUSES:
                last_success_ts = run.ended_at or run.started_at
                break

        if last_success_ts is None:
            days_since_last_success: float | None = None
            is_stale = True
        else:
            age_seconds = max(
                0.0,
                (datetime.now(UTC) - last_success_ts).total_seconds(),
            )
            days_since_last_success = round(age_seconds / SECONDS_PER_DAY, 2)
            is_stale = days_since_last_success > float(gold_max_age_days)

        return PipelineStatusOut(
            latest_run=latest_run,
            is_stale=is_stale,
            days_since_last_success=days_since_last_success,
            gold_max_age_days=gold_max_age_days,
            recent_runs=recent_runs,
            quality_breakdown=quality_breakdown,
            data_mode=data_mode,
        )
