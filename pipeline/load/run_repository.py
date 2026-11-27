"""Persistence helpers for pipeline runs, ingestion batches, and quality issues."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pipeline.constants import DEFAULT_SQL_BATCH_SIZE, RUN_STATUS_RUNNING
from pipeline.load.db import DbConnectionProtocol
from pipeline.quality.validator import QualityIssue


@dataclass(frozen=True)
class LatestBatchInfo:
    """Metadata of the latest successfully loaded batch for a source."""

    batch_id: str
    source_version: str | None
    source_updated_at: datetime | None
    file_checksum: str


def _parse_db_datetime(raw_value: object) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is None:
            return raw_value.replace(tzinfo=UTC)
        return raw_value.astimezone(UTC)
    if isinstance(raw_value, str) and raw_value.strip():
        parsed = datetime.fromisoformat(raw_value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _to_mysql_naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def ensure_source_metadata(
    conn: DbConnectionProtocol,
    *,
    source_id: int,
    source_name: str,
    license_name: str,
    url: str | None,
) -> int:
    """Ensure the source row exists in ``source_metadata`` and return its ID.

    Args:
        conn: Active database connection.
        source_id: Preferred numeric source ID.
        source_name: Unique source name (e.g., ``zomato``).
        license_name: License identifier (e.g., ``CC0 1.0``).
        url: Source catalog URL.

    Returns:
        Persisted ``source_id``.
    """
    cursor = conn.cursor()
    try:
        if conn.dialect == "sqlite":
            cursor.execute(
                """
                INSERT OR IGNORE INTO source_metadata (
                    source_id, source_name, license, url
                )
                VALUES (%(source_id)s, %(source_name)s, %(license)s, %(url)s)
                """,
                {
                    "source_id": source_id,
                    "source_name": source_name,
                    "license": license_name,
                    "url": url,
                },
            )
        else:
            cursor.execute(
                """
                INSERT IGNORE INTO source_metadata (
                    source_id, source_name, license, url
                )
                VALUES (%(source_id)s, %(source_name)s, %(license)s, %(url)s)
                """,
                {
                    "source_id": source_id,
                    "source_name": source_name,
                    "license": license_name,
                    "url": url,
                },
            )
        cursor.execute(
            """
            SELECT source_id
            FROM source_metadata
            WHERE source_name = %(source_name)s
            """,
            {"source_name": source_name},
        )
        row = cursor.fetchone()
        conn.commit()
        if row is None:
            return source_id
        return int(str(row["source_id"]))
    finally:
        cursor.close()


def get_latest_successful_batch(
    conn: DbConnectionProtocol,
    source_id: int,
) -> LatestBatchInfo | None:
    """Return the most recent successfully loaded batch for ``source_id``.

    Args:
        conn: Active database connection.
        source_id: Numeric source ID.

    Returns:
        ``LatestBatchInfo`` if a prior successful batch exists, else ``None``.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                batch_id,
                source_version,
                source_updated_at,
                file_checksum
            FROM ingestion_batches
            WHERE source_id = %(source_id)s
              AND status = 'success'
            ORDER BY ingested_at DESC
            LIMIT 1
            """,
            {"source_id": source_id},
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return LatestBatchInfo(
            batch_id=str(row["batch_id"]),
            source_version=(
                str(row["source_version"])
                if row["source_version"] is not None
                else None
            ),
            source_updated_at=_parse_db_datetime(row["source_updated_at"]),
            file_checksum=str(row["file_checksum"]),
        )
    finally:
        cursor.close()


def record_pipeline_run_start(
    conn: DbConnectionProtocol,
    *,
    run_id: str,
    dag_id: str,
    source_id: int | None,
    started_at: datetime,
) -> None:
    """Insert or reset a ``running`` row in ``pipeline_runs``.

    Args:
        conn: Active database connection.
        run_id: Unique pipeline run UUID.
        dag_id: Airflow DAG ID or local runner identifier.
        source_id: Source metadata ID.
        started_at: UTC start timestamp.
    """
    started_param = (
        started_at.isoformat()
        if conn.dialect == "sqlite"
        else _to_mysql_naive_utc(started_at)
    )
    cursor = conn.cursor()
    try:
        if conn.dialect == "sqlite":
            cursor.execute(
                """
                INSERT INTO pipeline_runs (
                    run_id, dag_id, source_id, started_at, status
                )
                VALUES (
                    %(run_id)s, %(dag_id)s, %(source_id)s, %(started_at)s, %(status)s
                )
                ON CONFLICT (run_id) DO UPDATE SET
                    status = excluded.status,
                    started_at = excluded.started_at
                """,
                {
                    "run_id": run_id,
                    "dag_id": dag_id,
                    "source_id": source_id,
                    "started_at": started_param,
                    "status": RUN_STATUS_RUNNING,
                },
            )
        else:
            cursor.execute(
                """
                INSERT INTO pipeline_runs (
                    run_id, dag_id, source_id, started_at, status
                )
                VALUES (
                    %(run_id)s, %(dag_id)s, %(source_id)s, %(started_at)s, %(status)s
                )
                ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    started_at = VALUES(started_at)
                """,
                {
                    "run_id": run_id,
                    "dag_id": dag_id,
                    "source_id": source_id,
                    "started_at": started_param,
                    "status": RUN_STATUS_RUNNING,
                },
            )
        conn.commit()
    finally:
        cursor.close()


def record_ingestion_batch(
    conn: DbConnectionProtocol,
    *,
    batch_id: str,
    source_id: int,
    run_id: str,
    source_version: str | None,
    source_updated_at: datetime | None,
    file_checksum: str,
    file_path: str,
    row_count: int,
    status: str,
    ingested_at: datetime,
) -> None:
    """Insert or update an ``ingestion_batches`` provenance record.

    Args:
        conn: Active database connection.
        batch_id: Unique batch UUID.
        source_id: Source metadata ID.
        run_id: Parent ``pipeline_runs`` ID.
        source_version: Upstream dataset version identifier.
        source_updated_at: Upstream dataset update timestamp.
        file_checksum: SHA-256 hex checksum of the Bronze file.
        file_path: Bronze artifact path or URI.
        row_count: Number of rows read from the Bronze file.
        status: Batch status string.
        ingested_at: UTC ingestion timestamp.
    """
    updated_param = (
        source_updated_at.isoformat()
        if conn.dialect == "sqlite" and source_updated_at is not None
        else _to_mysql_naive_utc(source_updated_at)
    )
    ingested_param = (
        ingested_at.isoformat()
        if conn.dialect == "sqlite"
        else _to_mysql_naive_utc(ingested_at)
    )
    params = {
        "batch_id": batch_id,
        "source_id": source_id,
        "run_id": run_id,
        "source_version": source_version,
        "source_updated_at": updated_param,
        "file_checksum": file_checksum,
        "file_path": file_path,
        "row_count": row_count,
        "status": status,
        "ingested_at": ingested_param,
    }
    cursor = conn.cursor()
    try:
        if conn.dialect == "sqlite":
            cursor.execute(
                """
                INSERT INTO ingestion_batches (
                    batch_id, source_id, run_id, source_version, source_updated_at,
                    file_checksum, file_path, row_count, status, ingested_at
                )
                VALUES (
                    %(batch_id)s, %(source_id)s, %(run_id)s, %(source_version)s,
                    %(source_updated_at)s, %(file_checksum)s, %(file_path)s,
                    %(row_count)s, %(status)s, %(ingested_at)s
                )
                ON CONFLICT (batch_id) DO UPDATE SET
                    row_count = excluded.row_count,
                    status = excluded.status
                """,
                params,
            )
        else:
            cursor.execute(
                """
                INSERT INTO ingestion_batches (
                    batch_id, source_id, run_id, source_version, source_updated_at,
                    file_checksum, file_path, row_count, status, ingested_at
                )
                VALUES (
                    %(batch_id)s, %(source_id)s, %(run_id)s, %(source_version)s,
                    %(source_updated_at)s, %(file_checksum)s, %(file_path)s,
                    %(row_count)s, %(status)s, %(ingested_at)s
                )
                ON DUPLICATE KEY UPDATE
                    row_count = VALUES(row_count),
                    status = VALUES(status)
                """,
                params,
            )
        conn.commit()
    finally:
        cursor.close()


def insert_quality_issues(
    conn: DbConnectionProtocol,
    *,
    batch_id: str,
    run_id: str,
    issues: Sequence[QualityIssue],
) -> int:
    """Persist reject and warning issues into ``data_quality_issues``.

    Args:
        conn: Active database connection.
        batch_id: Batch ID owning the issues.
        run_id: Run ID owning the issues.
        issues: Sequence of ``QualityIssue`` instances.

    Returns:
        Number of inserted issue rows.
    """
    if not issues:
        return 0

    rows = [
        {
            "batch_id": batch_id,
            "run_id": run_id,
            "source_record_id": issue.source_record_id,
            "rule_name": issue.rule_name,
            "severity": issue.severity,
            "reason": issue.reason,
            "raw_payload": json.dumps(issue.raw_payload, ensure_ascii=False),
            "detected_at": (
                issue.detected_at.isoformat()
                if conn.dialect == "sqlite"
                else _to_mysql_naive_utc(issue.detected_at)
            ),
        }
        for issue in issues
    ]
    cursor = conn.cursor()
    try:
        sql = """
            INSERT INTO data_quality_issues (
                batch_id, run_id, source_record_id, rule_name,
                severity, reason, raw_payload, detected_at
            )
            VALUES (
                %(batch_id)s, %(run_id)s, %(source_record_id)s, %(rule_name)s,
                %(severity)s, %(reason)s, %(raw_payload)s, %(detected_at)s
            )
        """
        for idx in range(0, len(rows), DEFAULT_SQL_BATCH_SIZE):
            cursor.executemany(sql, rows[idx : idx + DEFAULT_SQL_BATCH_SIZE])
        conn.commit()
        return len(rows)
    finally:
        cursor.close()


def update_pipeline_run_summary(
    conn: DbConnectionProtocol,
    *,
    run_id: str,
    status: str,
    rows_read: int,
    rows_inserted: int,
    rows_updated: int,
    rows_unchanged: int,
    rows_quarantined: int,
    rows_warned: int,
    quarantine_rate: float,
    ended_at: datetime,
) -> None:
    """Update final counters and status on ``pipeline_runs``.

    Args:
        conn: Active database connection.
        run_id: Target ``pipeline_runs.run_id``.
        status: Terminal run status.
        rows_read: Total input rows read.
        rows_inserted: New Silver rows inserted.
        rows_updated: Existing Silver rows updated due to ``record_hash`` change.
        rows_unchanged: Existing Silver rows skipped with ``last_seen_batch_id`` bump.
        rows_quarantined: Rows rejected by quality rules.
        rows_warned: Valid rows with at least one warning.
        quarantine_rate: Ratio ``rows_quarantined / rows_read``.
        ended_at: UTC completion timestamp.
    """
    ended_param = (
        ended_at.isoformat()
        if conn.dialect == "sqlite"
        else _to_mysql_naive_utc(ended_at)
    )
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE pipeline_runs
            SET
                ended_at = %(ended_at)s,
                status = %(status)s,
                rows_read = %(rows_read)s,
                rows_inserted = %(rows_inserted)s,
                rows_updated = %(rows_updated)s,
                rows_unchanged = %(rows_unchanged)s,
                rows_quarantined = %(rows_quarantined)s,
                rows_warned = %(rows_warned)s,
                quarantine_rate = %(quarantine_rate)s
            WHERE run_id = %(run_id)s
            """,
            {
                "run_id": run_id,
                "ended_at": ended_param,
                "status": status,
                "rows_read": rows_read,
                "rows_inserted": rows_inserted,
                "rows_updated": rows_updated,
                "rows_unchanged": rows_unchanged,
                "rows_quarantined": rows_quarantined,
                "rows_warned": rows_warned,
                "quarantine_rate": f"{quarantine_rate:.4f}",
            },
        )
        conn.commit()
    finally:
        cursor.close()
