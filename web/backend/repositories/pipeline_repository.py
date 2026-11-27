"""Pipeline run telemetry and data quality rule breakdown queries."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pymysql

from web.backend.constants import RECENT_RUNS_LIMIT
from web.backend.exceptions import ServiceUnavailableError
from web.backend.repositories.csv_fallback import get_cached_csv_snapshot
from web.backend.repositories.db import DictCursorConnection
from web.backend.schemas.pipeline import PipelineRunOut, QualityRuleCountOut
from web.backend.settings import BackendSettings, settings

logger = logging.getLogger(__name__)

_RECENT_RUNS_SQL = """
SELECT
    pr.run_id,
    pr.dag_id,
    pr.source_id,
    sm.source_name,
    pr.started_at,
    pr.ended_at,
    pr.status,
    pr.rows_read,
    pr.rows_inserted,
    pr.rows_updated,
    pr.rows_unchanged,
    pr.rows_quarantined,
    pr.rows_warned,
    pr.quarantine_rate
FROM pipeline_runs AS pr
LEFT JOIN source_metadata AS sm ON sm.source_id = pr.source_id
ORDER BY pr.started_at DESC, pr.run_id ASC
LIMIT %(limit)s
"""

_QUALITY_BREAKDOWN_FOR_RUN_SQL = """
SELECT
    dqi.rule_name,
    dqi.severity,
    COUNT(*) AS issue_count
FROM data_quality_issues AS dqi
WHERE dqi.run_id = %(run_id)s
GROUP BY dqi.rule_name, dqi.severity
ORDER BY issue_count DESC, dqi.rule_name ASC
"""


def _ensure_utc(dt_value: datetime) -> datetime:
    """Attach UTC timezone to naive MySQL DATETIME values."""
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=UTC)
    return dt_value.astimezone(UTC)


class PipelineRepository:
    """Repository for pipeline execution history and quality issue counts."""

    def __init__(
        self,
        conn: DictCursorConnection | None,
        app_settings: BackendSettings | None = None,
    ) -> None:
        """Initialize the pipeline repository with an optional DB connection."""
        self._conn = conn
        self._settings = app_settings or settings

    def get_telemetry(
        self,
    ) -> tuple[
        list[PipelineRunOut],
        list[QualityRuleCountOut],
        Literal["mysql", "local_csv_fallback"],
    ]:
        """Return recent pipeline runs, latest run rule breakdown, and data mode."""
        if self._conn is None:
            snapshot = get_cached_csv_snapshot(
                self._settings.resolved_fallback_csv_path,
                self._settings.cuisine_map_path,
            )
            return (
                [snapshot.synthetic_run],
                list(snapshot.quality_breakdown),
                "local_csv_fallback",
            )

        try:
            with self._conn.cursor() as cursor:
                cursor.execute(_RECENT_RUNS_SQL, {"limit": RECENT_RUNS_LIMIT})
                run_rows = cursor.fetchall()
                recent_runs: list[PipelineRunOut] = []
                for row in run_rows:
                    started_at = row["started_at"]
                    ended_at = row.get("ended_at")
                    recent_runs.append(
                        PipelineRunOut(
                            run_id=str(row["run_id"]),
                            dag_id=str(row["dag_id"]),
                            source_id=(
                                int(str(row["source_id"]))
                                if row.get("source_id") is not None
                                else None
                            ),
                            source_name=(
                                str(row["source_name"])
                                if row.get("source_name") is not None
                                else None
                            ),
                            started_at=_ensure_utc(
                                started_at
                                if isinstance(started_at, datetime)
                                else datetime.fromisoformat(str(started_at))
                            ),
                            ended_at=(
                                _ensure_utc(
                                    ended_at
                                    if isinstance(ended_at, datetime)
                                    else datetime.fromisoformat(str(ended_at))
                                )
                                if ended_at is not None
                                else None
                            ),
                            status=str(row["status"]),
                            rows_read=int(str(row["rows_read"])),
                            rows_inserted=int(str(row["rows_inserted"])),
                            rows_updated=int(str(row["rows_updated"])),
                            rows_unchanged=int(str(row["rows_unchanged"])),
                            rows_quarantined=int(str(row["rows_quarantined"])),
                            rows_warned=int(str(row["rows_warned"])),
                            quarantine_rate=Decimal(str(row["quarantine_rate"])),
                        )
                    )

                quality_breakdown: list[QualityRuleCountOut] = []
                if recent_runs:
                    cursor.execute(
                        _QUALITY_BREAKDOWN_FOR_RUN_SQL,
                        {"run_id": recent_runs[0].run_id},
                    )
                    issue_rows = cursor.fetchall()
                    quality_breakdown = [
                        QualityRuleCountOut(
                            rule_name=str(row["rule_name"]),
                            severity=str(row["severity"]),
                            count=int(str(row["issue_count"])),
                        )
                        for row in issue_rows
                    ]

            return recent_runs, quality_breakdown, "mysql"
        except pymysql.MySQLError as exc:
            logger.error(
                "Pipeline telemetry query failed",
                extra={"details": type(exc).__name__},
            )
            raise ServiceUnavailableError("Database query failed") from exc
