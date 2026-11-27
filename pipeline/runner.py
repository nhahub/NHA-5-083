"""End-to-end Zomato Medallion ETL runner and CLI entry point."""

import argparse
import logging
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pipeline.constants import (
    DEFAULT_ZOMATO_DAG_ID,
    DEFAULT_ZOMATO_LICENSE,
    DEFAULT_ZOMATO_SOURCE_ID,
    DEFAULT_ZOMATO_SOURCE_NAME,
    DEFAULT_ZOMATO_URL,
    RUN_STATUS_FAILED,
    RUN_STATUS_QUALITY_GATE_FAILED,
    RUN_STATUS_SKIPPED_UNCHANGED,
    RUN_STATUS_SUCCESS,
)
from pipeline.ingestion.bronze_storage import (
    BronzeArtifact,
    BronzeStorage,
    build_bronze_storage,
)
from pipeline.ingestion.csv_loader import BatchValidationError, load_zomato_csv
from pipeline.ingestion.kaggle_source import (
    KaggleClientProtocol,
    compute_sha256,
    fetch_zomato_dataset,
    is_checksum_unchanged,
)
from pipeline.load.db import (
    DbConnectionProtocol,
    SqliteConnection,
    initialize_sqlite_test_schema,
    open_mysql_connection,
)
from pipeline.load.gold_loader import refresh_gold_layer
from pipeline.load.run_repository import (
    ensure_source_metadata,
    get_latest_successful_batch,
    insert_quality_issues,
    record_ingestion_batch,
    record_pipeline_run_start,
    update_pipeline_run_summary,
)
from pipeline.load.silver_loader import SilverUpsertStats, upsert_silver_batch
from pipeline.logging_config import configure_pipeline_logging
from pipeline.quality.quarantine import (
    QualityGateFailedError,
    compute_quarantine_rate,
    enforce_quality_gate,
    write_quarantine_jsonl,
)
from pipeline.quality.validator import ValidationResult, validate_and_standardize_batch
from pipeline.settings import (
    PipelineRuntimeConfig,
    PipelineSettings,
    export_kaggle_credentials,
    load_pipeline_runtime_config,
    load_pipeline_settings,
)
from pipeline.transform.cuisines import CuisineVocabulary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineRunSummary:
    """Outcome summary emitted by ``run_zomato_pipeline``."""

    run_id: str
    batch_id: str
    status: str
    rows_read: int
    rows_inserted: int
    rows_updated: int
    rows_unchanged: int
    rows_quarantined: int
    rows_warned: int
    quarantine_rate: float
    bronze_path: str | None
    gold_points_count: int


def _resolve_deterministic_ids(
    run_id: str | None,
    batch_id: str | None,
) -> tuple[str, str]:
    resolved_run = run_id if run_id else str(uuid.uuid4())
    resolved_batch = batch_id if batch_id else str(uuid.uuid4())
    return resolved_run, resolved_batch


def _run_dry_mode(
    *,
    csv_path: Path,
    config: PipelineRuntimeConfig,
    run_id: str,
    batch_id: str,
) -> PipelineRunSummary:
    """Validate, standardize, and enforce the 15% gate without DB writes."""
    raw_df = load_zomato_csv(
        csv_path,
        encoding=config.sources_zomato_file_encoding,
    )
    vocabulary = CuisineVocabulary.from_csv()
    validation = validate_and_standardize_batch(
        raw_df,
        source_id=DEFAULT_ZOMATO_SOURCE_ID,
        vocabulary=vocabulary,
        config=config,
    )
    rejected_count = len(validation.rejected_records)
    quarantine_rate = compute_quarantine_rate(rejected_count, validation.records_read)
    status = RUN_STATUS_SUCCESS
    try:
        enforce_quality_gate(
            rejected_count,
            validation.records_read,
            config.quality_max_quarantine_rate,
        )
    except QualityGateFailedError:
        status = RUN_STATUS_QUALITY_GATE_FAILED

    quarantine_dir = config.resolve_path(config.pipeline_quarantine_path)
    write_quarantine_jsonl(validation.rejected_records, quarantine_dir, batch_id)

    summary = PipelineRunSummary(
        run_id=run_id,
        batch_id=batch_id,
        status=status,
        rows_read=validation.records_read,
        rows_inserted=0,
        rows_updated=0,
        rows_unchanged=0,
        rows_quarantined=rejected_count,
        rows_warned=validation.rows_warned,
        quarantine_rate=quarantine_rate,
        bronze_path=None,
        gold_points_count=0,
    )
    logger.info(
        "Dry-run completed: status=%s read=%d valid=%d rejected=%d warned=%d rate=%.4f",
        summary.status,
        summary.rows_read,
        len(validation.valid_records),
        summary.rows_quarantined,
        summary.rows_warned,
        summary.quarantine_rate,
        extra={"run_id": run_id, "batch_id": batch_id},
    )
    return summary


def _persist_batch_and_issues(
    conn: DbConnectionProtocol,
    *,
    batch_id: str,
    source_id: int,
    run_id: str,
    source_version: str | None,
    source_updated_at: datetime | None,
    checksum: str,
    bronze_artifact: BronzeArtifact,
    validation: ValidationResult,
    status: str,
    now_utc: datetime,
) -> None:
    record_ingestion_batch(
        conn,
        batch_id=batch_id,
        source_id=source_id,
        run_id=run_id,
        source_version=source_version,
        source_updated_at=source_updated_at,
        file_checksum=checksum,
        file_path=bronze_artifact.uri_or_path,
        row_count=validation.records_read,
        status=status,
        ingested_at=now_utc,
    )
    insert_quality_issues(
        conn,
        batch_id=batch_id,
        run_id=run_id,
        issues=validation.issues,
    )


def run_zomato_pipeline(
    *,
    source_csv: Path | None = None,
    dry_run: bool = False,
    skip_if_unchanged: bool | None = None,
    run_id: str | None = None,
    batch_id: str | None = None,
    dag_id: str = DEFAULT_ZOMATO_DAG_ID,
    conn: DbConnectionProtocol | None = None,
    kaggle_client: KaggleClientProtocol | None = None,
    bronze_storage: BronzeStorage | None = None,
    settings: PipelineSettings | None = None,
    runtime_config: PipelineRuntimeConfig | None = None,
) -> PipelineRunSummary:
    """Execute the full Zomato ETL pipeline from check/fetch through Gold.

    Args:
        source_csv: Optional local CSV path bypassing Kaggle API download.
        dry_run: When ``True``, validates and enforces the 15% gate without DB I/O.
        skip_if_unchanged: Override ``sources_zomato_skip_if_unchanged`` setting.
        run_id: Optional explicit run UUID.
        batch_id: Optional explicit batch UUID.
        dag_id: DAG or runner identifier recorded in ``pipeline_runs``.
        conn: Optional pre-opened DB connection (for Airflow hooks or tests).
        kaggle_client: Optional Kaggle client for dependency injection.
        bronze_storage: Optional Bronze storage backend for dependency injection.
        settings: Optional full ``PipelineSettings`` instance.
        runtime_config: Optional non-secret ``PipelineRuntimeConfig`` for dry runs.

    Returns:
        ``PipelineRunSummary`` with run status, counts, and Bronze path.
    """
    resolved_run_id, resolved_batch_id = _resolve_deterministic_ids(run_id, batch_id)
    config = (
        settings.to_runtime_config()
        if settings is not None
        else (
            runtime_config
            if runtime_config is not None
            else load_pipeline_runtime_config()
        )
    )
    configure_pipeline_logging(config.logging_level)

    if dry_run:
        if source_csv is None:
            raise ValueError("--dry-run requires --source-csv")
        return _run_dry_mode(
            csv_path=source_csv,
            config=config,
            run_id=resolved_run_id,
            batch_id=resolved_batch_id,
        )

    active_settings = settings
    owns_conn = False
    if conn is None:
        if active_settings is None:
            active_settings = load_pipeline_settings()
        config = active_settings.to_runtime_config()
        conn = open_mysql_connection(
            host=active_settings.mysql_host,
            port=active_settings.mysql_port,
            database=active_settings.mysql_database,
            user=active_settings.mysql_pipeline_user,
            password=active_settings.mysql_pipeline_password.get_secret_value(),
            tls_enabled=active_settings.mysql_tls_enabled,
            connect_timeout=active_settings.database_connect_timeout_seconds,
        )
        owns_conn = True

    if bronze_storage is None:
        storage_backend = (
            active_settings.storage_backend if active_settings is not None else "local"
        )
        conn_str = (
            active_settings.azure_storage_connection_string.get_secret_value()
            if active_settings is not None
            and active_settings.azure_storage_connection_string is not None
            else None
        )
        account_url = (
            active_settings.azure_storage_account_url
            if active_settings is not None
            else None
        )
        bronze_storage = build_bronze_storage(
            storage_backend,
            local_path=config.resolve_path(config.pipeline_bronze_local_path),
            container_name=config.pipeline_bronze_container,
            connection_string=conn_str,
            account_url=account_url,
        )

    effective_skip = (
        skip_if_unchanged
        if skip_if_unchanged is not None
        else config.sources_zomato_skip_if_unchanged
    )
    started_at = datetime.now(UTC)

    source_id = ensure_source_metadata(
        conn,
        source_id=DEFAULT_ZOMATO_SOURCE_ID,
        source_name=DEFAULT_ZOMATO_SOURCE_NAME,
        license_name=DEFAULT_ZOMATO_LICENSE,
        url=DEFAULT_ZOMATO_URL,
    )
    record_pipeline_run_start(
        conn,
        run_id=resolved_run_id,
        dag_id=dag_id,
        source_id=source_id,
        started_at=started_at,
    )

    try:
        latest_batch = get_latest_successful_batch(conn, source_id)
        last_version = latest_batch.source_version if latest_batch else None
        last_updated = latest_batch.source_updated_at if latest_batch else None
        last_checksum = latest_batch.file_checksum if latest_batch else None

        with tempfile.TemporaryDirectory(prefix="zomato_ingest_") as staging_dir:
            if source_csv is not None:
                local_csv = source_csv
                checksum = compute_sha256(local_csv)
                if effective_skip and is_checksum_unchanged(checksum, last_checksum):
                    ended_at = datetime.now(UTC)
                    update_pipeline_run_summary(
                        conn,
                        run_id=resolved_run_id,
                        status=RUN_STATUS_SKIPPED_UNCHANGED,
                        rows_read=0,
                        rows_inserted=0,
                        rows_updated=0,
                        rows_unchanged=0,
                        rows_quarantined=0,
                        rows_warned=0,
                        quarantine_rate=0.0,
                        ended_at=ended_at,
                    )
                    return PipelineRunSummary(
                        run_id=resolved_run_id,
                        batch_id=resolved_batch_id,
                        status=RUN_STATUS_SKIPPED_UNCHANGED,
                        rows_read=0,
                        rows_inserted=0,
                        rows_updated=0,
                        rows_unchanged=0,
                        rows_quarantined=0,
                        rows_warned=0,
                        quarantine_rate=0.0,
                        bronze_path=None,
                        gold_points_count=0,
                    )
                source_version: str | None = checksum[:12]
                source_updated_at: datetime | None = started_at
            else:
                if kaggle_client is None and active_settings is not None:
                    export_kaggle_credentials(active_settings)
                fetch_res = fetch_zomato_dataset(
                    dataset_slug=config.sources_zomato_kaggle_dataset,
                    file_name=config.sources_zomato_file_name,
                    target_dir=Path(staging_dir),
                    client=kaggle_client,
                    last_version=last_version,
                    last_updated_at=last_updated,
                    last_checksum=last_checksum,
                    skip_if_unchanged=effective_skip,
                )
                if (
                    fetch_res.status == RUN_STATUS_SKIPPED_UNCHANGED
                    or fetch_res.local_file_path is None
                ):
                    ended_at = datetime.now(UTC)
                    update_pipeline_run_summary(
                        conn,
                        run_id=resolved_run_id,
                        status=RUN_STATUS_SKIPPED_UNCHANGED,
                        rows_read=0,
                        rows_inserted=0,
                        rows_updated=0,
                        rows_unchanged=0,
                        rows_quarantined=0,
                        rows_warned=0,
                        quarantine_rate=0.0,
                        ended_at=ended_at,
                    )
                    return PipelineRunSummary(
                        run_id=resolved_run_id,
                        batch_id=resolved_batch_id,
                        status=RUN_STATUS_SKIPPED_UNCHANGED,
                        rows_read=0,
                        rows_inserted=0,
                        rows_updated=0,
                        rows_unchanged=0,
                        rows_quarantined=0,
                        rows_warned=0,
                        quarantine_rate=0.0,
                        bronze_path=None,
                        gold_points_count=0,
                    )
                local_csv = fetch_res.local_file_path
                checksum = str(fetch_res.file_checksum)
                source_version = fetch_res.snapshot.source_version
                source_updated_at = fetch_res.snapshot.source_updated_at

            bronze_metadata = {
                "source_name": DEFAULT_ZOMATO_SOURCE_NAME,
                "source_id": source_id,
                "batch_id": resolved_batch_id,
                "run_id": resolved_run_id,
                "source_version": source_version,
                "source_updated_at": (
                    source_updated_at.isoformat() if source_updated_at else None
                ),
                "file_checksum": checksum,
                "ingested_at": started_at.isoformat(),
            }
            bronze_artifact = bronze_storage.write_batch_file(
                source_name=DEFAULT_ZOMATO_SOURCE_NAME,
                batch_date=started_at.date(),
                batch_id=resolved_batch_id,
                local_file_path=local_csv,
                metadata=bronze_metadata,
            )

            raw_df = load_zomato_csv(
                local_csv,
                encoding=config.sources_zomato_file_encoding,
            )

        vocabulary = CuisineVocabulary.from_csv()
        validation = validate_and_standardize_batch(
            raw_df,
            source_id=source_id,
            vocabulary=vocabulary,
            config=config,
        )
        rejected_count = len(validation.rejected_records)
        quarantine_dir = config.resolve_path(config.pipeline_quarantine_path)
        write_quarantine_jsonl(
            validation.rejected_records, quarantine_dir, resolved_batch_id
        )

        try:
            quarantine_rate = enforce_quality_gate(
                rejected_count,
                validation.records_read,
                config.quality_max_quarantine_rate,
            )
        except QualityGateFailedError as gate_err:
            _persist_batch_and_issues(
                conn,
                batch_id=resolved_batch_id,
                source_id=source_id,
                run_id=resolved_run_id,
                source_version=source_version,
                source_updated_at=source_updated_at,
                checksum=checksum,
                bronze_artifact=bronze_artifact,
                validation=validation,
                status=RUN_STATUS_QUALITY_GATE_FAILED,
                now_utc=started_at,
            )
            update_pipeline_run_summary(
                conn,
                run_id=resolved_run_id,
                status=RUN_STATUS_QUALITY_GATE_FAILED,
                rows_read=validation.records_read,
                rows_inserted=0,
                rows_updated=0,
                rows_unchanged=0,
                rows_quarantined=rejected_count,
                rows_warned=validation.rows_warned,
                quarantine_rate=gate_err.quarantine_rate,
                ended_at=datetime.now(UTC),
            )
            return PipelineRunSummary(
                run_id=resolved_run_id,
                batch_id=resolved_batch_id,
                status=RUN_STATUS_QUALITY_GATE_FAILED,
                rows_read=validation.records_read,
                rows_inserted=0,
                rows_updated=0,
                rows_unchanged=0,
                rows_quarantined=rejected_count,
                rows_warned=validation.rows_warned,
                quarantine_rate=gate_err.quarantine_rate,
                bronze_path=bronze_artifact.uri_or_path,
                gold_points_count=0,
            )

        _persist_batch_and_issues(
            conn,
            batch_id=resolved_batch_id,
            source_id=source_id,
            run_id=resolved_run_id,
            source_version=source_version,
            source_updated_at=source_updated_at,
            checksum=checksum,
            bronze_artifact=bronze_artifact,
            validation=validation,
            status=RUN_STATUS_SUCCESS,
            now_utc=started_at,
        )
        upsert_stats: SilverUpsertStats = upsert_silver_batch(
            conn,
            records=validation.valid_records,
            batch_id=resolved_batch_id,
            updated_at=started_at,
        )
        gold_points_count = refresh_gold_layer(conn, source_id=source_id)

        update_pipeline_run_summary(
            conn,
            run_id=resolved_run_id,
            status=RUN_STATUS_SUCCESS,
            rows_read=validation.records_read,
            rows_inserted=upsert_stats.rows_inserted,
            rows_updated=upsert_stats.rows_updated,
            rows_unchanged=upsert_stats.rows_unchanged,
            rows_quarantined=rejected_count,
            rows_warned=validation.rows_warned,
            quarantine_rate=quarantine_rate,
            ended_at=datetime.now(UTC),
        )
        return PipelineRunSummary(
            run_id=resolved_run_id,
            batch_id=resolved_batch_id,
            status=RUN_STATUS_SUCCESS,
            rows_read=validation.records_read,
            rows_inserted=upsert_stats.rows_inserted,
            rows_updated=upsert_stats.rows_updated,
            rows_unchanged=upsert_stats.rows_unchanged,
            rows_quarantined=rejected_count,
            rows_warned=validation.rows_warned,
            quarantine_rate=quarantine_rate,
            bronze_path=bronze_artifact.uri_or_path,
            gold_points_count=gold_points_count,
        )
    except BatchValidationError:
        update_pipeline_run_summary(
            conn,
            run_id=resolved_run_id,
            status=RUN_STATUS_FAILED,
            rows_read=0,
            rows_inserted=0,
            rows_updated=0,
            rows_unchanged=0,
            rows_quarantined=0,
            rows_warned=0,
            quarantine_rate=0.0,
            ended_at=datetime.now(UTC),
        )
        raise
    except Exception:
        update_pipeline_run_summary(
            conn,
            run_id=resolved_run_id,
            status=RUN_STATUS_FAILED,
            rows_read=0,
            rows_inserted=0,
            rows_updated=0,
            rows_unchanged=0,
            rows_quarantined=0,
            rows_warned=0,
            quarantine_rate=0.0,
            ended_at=datetime.now(UTC),
        )
        raise
    finally:
        if owns_conn:
            conn.close()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Zomato Medallion ETL pipeline."
    )
    parser.add_argument(
        "--source-csv",
        type=Path,
        default=None,
        help="Optional local CSV path instead of fetching from Kaggle.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and check the 15%% quality gate without writing to MySQL.",
    )
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        default=None,
        help="Optional SQLite database path for local integration verification.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Process even if upstream version and checksum match the latest batch.",
    )
    parser.add_argument("--run-id", type=str, default=None, help="Explicit run UUID.")
    parser.add_argument(
        "--batch-id", type=str, default=None, help="Explicit batch UUID."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python -m pipeline.runner``.

    Args:
        argv: Optional argument list overriding ``sys.argv``.

    Returns:
        Exit code ``0`` on success/skipped, ``2`` on quality gate failure.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    local_conn: SqliteConnection | None = None
    if args.sqlite_db is not None and not args.dry_run:
        local_conn = SqliteConnection(args.sqlite_db)
        initialize_sqlite_test_schema(local_conn)

    try:
        summary = run_zomato_pipeline(
            source_csv=args.source_csv,
            dry_run=args.dry_run,
            skip_if_unchanged=False if args.force else None,
            run_id=args.run_id,
            batch_id=args.batch_id,
            conn=local_conn,
        )
    finally:
        if local_conn is not None:
            local_conn.close()

    return 2 if summary.status == RUN_STATUS_QUALITY_GATE_FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
