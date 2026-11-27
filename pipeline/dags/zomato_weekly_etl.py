"""Airflow 3.x TaskFlow DAG for the weekly change-checked Zomato ETL pipeline."""

from __future__ import annotations

import json
import logging
import tempfile
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ParamSpec, TypeVar

from pipeline.constants import (
    AZURE_BLOB_BRONZE_CONN_ID,
    DEFAULT_EXECUTION_TIMEOUT_MINUTES,
    DEFAULT_RETRY_COUNT,
    DEFAULT_RETRY_DELAY_MINUTES,
    DEFAULT_ZOMATO_DAG_ID,
    DEFAULT_ZOMATO_LICENSE,
    DEFAULT_ZOMATO_SOURCE_ID,
    DEFAULT_ZOMATO_SOURCE_NAME,
    DEFAULT_ZOMATO_URL,
    MYSQL_PIPELINE_CONN_ID,
    RUN_STATUS_FAILED,
    RUN_STATUS_QUALITY_GATE_FAILED,
    RUN_STATUS_SKIPPED_UNCHANGED,
    RUN_STATUS_SUCCESS,
)
from pipeline.ingestion.bronze_storage import (
    LocalBronzeStorage,
    build_bronze_relative_dir,
)
from pipeline.ingestion.csv_loader import load_zomato_csv
from pipeline.ingestion.kaggle_source import fetch_zomato_dataset
from pipeline.load.db import DbConnectionProtocol, open_mysql_connection
from pipeline.load.gold_loader import refresh_gold_layer
from pipeline.load.run_repository import (
    ensure_source_metadata,
    get_latest_successful_batch,
    insert_quality_issues,
    record_ingestion_batch,
    record_pipeline_run_start,
    update_pipeline_run_summary,
)
from pipeline.load.silver_loader import upsert_silver_batch
from pipeline.quality.quarantine import (
    QualityGateFailedError,
    enforce_quality_gate,
    write_quarantine_jsonl,
)
from pipeline.quality.validator import validate_and_standardize_batch
from pipeline.settings import (
    export_kaggle_credentials,
    load_pipeline_runtime_config,
    load_pipeline_settings,
)
from pipeline.transform.cuisines import CuisineVocabulary

logger = logging.getLogger(__name__)

_P = ParamSpec("_P")
_R = TypeVar("_R")


class _FallbackXComArg:
    """Lightweight TaskFlow return reference used only when Airflow is absent."""

    def __init__(self, task: _FallbackTask) -> None:
        self.task = task


class _FallbackTask:
    """Lightweight task descriptor used only when Airflow is absent in unit tests."""

    def __init__(
        self,
        task_id: str,
        fn: Callable[..., object],
        trigger_rule: str = "all_success",
    ) -> None:
        self.task_id = task_id
        self.python_callable = fn
        self.trigger_rule = trigger_rule
        self.upstream_task_ids: set[str] = set()
        self.downstream_task_ids: set[str] = set()
        self._dag: _FallbackDag | None = None

    def set_downstream(self, other: _FallbackTask) -> _FallbackTask:
        self.downstream_task_ids.add(other.task_id)
        other.upstream_task_ids.add(self.task_id)
        return other

    def __rshift__(self, other: _FallbackTask | _FallbackXComArg) -> _FallbackTask:
        target = other.task if isinstance(other, _FallbackXComArg) else other
        return self.set_downstream(target)


class _FallbackDag:
    """Lightweight DAG container used only when Airflow is absent in unit tests."""

    def __init__(
        self,
        *,
        dag_id: str,
        schedule: str,
        catchup: bool,
        max_active_runs: int,
        tags: list[str],
        default_args: dict[str, object],
    ) -> None:
        self.dag_id = dag_id
        self.schedule = schedule
        self.catchup = catchup
        self.max_active_runs = max_active_runs
        self.tags = tags
        self.default_args = default_args
        self.task_dict: dict[str, _FallbackTask] = {}

    @property
    def tasks(self) -> list[_FallbackTask]:
        return list(self.task_dict.values())

    @property
    def task_ids(self) -> list[str]:
        return list(self.task_dict.keys())

    def get_task(self, task_id: str) -> _FallbackTask:
        return self.task_dict[task_id]


_ACTIVE_FALLBACK_DAG: list[_FallbackDag] = []


def _fallback_dag(
    *,
    dag_id: str,
    schedule: str,
    start_date: datetime,
    catchup: bool,
    max_active_runs: int,
    tags: list[str],
    default_args: dict[str, object],
) -> Callable[[Callable[[], None]], Callable[[], _FallbackDag]]:
    del start_date

    def decorator(func: Callable[[], None]) -> Callable[[], _FallbackDag]:
        def wrapper() -> _FallbackDag:
            dag_obj = _FallbackDag(
                dag_id=dag_id,
                schedule=schedule,
                catchup=catchup,
                max_active_runs=max_active_runs,
                tags=tags,
                default_args=default_args,
            )
            _ACTIVE_FALLBACK_DAG.append(dag_obj)
            try:
                func()
            finally:
                _ACTIVE_FALLBACK_DAG.pop()
            return dag_obj

        return wrapper

    return decorator


def _fallback_task(
    *,
    task_id: str | None = None,
    trigger_rule: str = "all_success",
    multiple_outputs: bool = False,
) -> Callable[[Callable[_P, _R]], Callable[..., _FallbackXComArg]]:
    del multiple_outputs

    def decorator(func: Callable[_P, _R]) -> Callable[..., _FallbackXComArg]:
        resolved_id = task_id or func.__name__

        def caller(*args: object, **kwargs: object) -> _FallbackXComArg:
            task_obj = _FallbackTask(
                task_id=resolved_id,
                fn=func,
                trigger_rule=trigger_rule,
            )
            if _ACTIVE_FALLBACK_DAG:
                dag_obj = _ACTIVE_FALLBACK_DAG[-1]
                dag_obj.task_dict[resolved_id] = task_obj
                task_obj._dag = dag_obj
            for val in (*args, *kwargs.values()):
                if isinstance(val, _FallbackXComArg):
                    val.task.set_downstream(task_obj)
            return _FallbackXComArg(task_obj)

        return caller

    return decorator


try:
    from airflow.sdk import dag, task
except ImportError:
    try:
        from airflow.decorators import dag, task
    except ImportError:
        dag = _fallback_dag
        task = _fallback_task


def _open_airflow_mysql_connection() -> DbConnectionProtocol:
    """Resolve ``mysql_pipeline`` via Airflow ``MySqlHook`` and open PyMySQL."""
    from airflow.providers.mysql.hooks.mysql import MySqlHook

    hook = MySqlHook(mysql_conn_id=MYSQL_PIPELINE_CONN_ID)
    conn_model = hook.get_connection(MYSQL_PIPELINE_CONN_ID)
    extra = conn_model.extra_dejson or {}
    tls_enabled = bool(extra.get("ssl") or extra.get("tls", False))
    config = load_pipeline_runtime_config()
    return open_mysql_connection(
        host=str(conn_model.host),
        port=int(conn_model.port or 3306),
        database=str(conn_model.schema),
        user=str(conn_model.login),
        password=str(conn_model.password),
        tls_enabled=tls_enabled,
        connect_timeout=config.database_connect_timeout_seconds,
    )


def _upload_bronze_via_airflow_hook(
    *,
    local_file_path: Path,
    batch_date: datetime,
    batch_id: str,
    metadata: dict[str, object],
) -> str:
    """Upload raw file and ``metadata.json`` to Azure Blob using ``WasbHook``."""
    from airflow.providers.microsoft.azure.hooks.wasb import WasbHook

    config = load_pipeline_runtime_config()
    rel_dir = build_bronze_relative_dir(
        DEFAULT_ZOMATO_SOURCE_NAME, batch_date.date(), batch_id
    )
    data_blob = f"{rel_dir.as_posix()}/{local_file_path.name}"
    meta_blob = f"{rel_dir.as_posix()}/metadata.json"

    hook = WasbHook(wasb_conn_id=AZURE_BLOB_BRONZE_CONN_ID)
    hook.load_file(
        file_path=str(local_file_path),
        container_name=config.pipeline_bronze_container,
        blob_name=data_blob,
        overwrite=False,
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8", delete=False
    ) as tmp_meta:
        tmp_meta.write(json.dumps(metadata, indent=2, default=str) + "\n")
        tmp_meta_path = Path(tmp_meta.name)
    try:
        hook.load_file(
            file_path=str(tmp_meta_path),
            container_name=config.pipeline_bronze_container,
            blob_name=meta_blob,
            overwrite=False,
        )
    finally:
        tmp_meta_path.unlink(missing_ok=True)
    return f"{config.pipeline_bronze_container}/{data_blob}"


_RUNTIME_CONFIG = load_pipeline_runtime_config()
_DEFAULT_ARGS: dict[str, object] = {
    "owner": "data-engineering",
    "retries": DEFAULT_RETRY_COUNT,
    "retry_delay": timedelta(minutes=DEFAULT_RETRY_DELAY_MINUTES),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(minutes=DEFAULT_EXECUTION_TIMEOUT_MINUTES),
}


@dag(
    dag_id=DEFAULT_ZOMATO_DAG_ID,
    schedule=_RUNTIME_CONFIG.sources_zomato_schedule,
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    tags=["zomato", "medallion", "etl"],
    default_args=_DEFAULT_ARGS,
)
def zomato_weekly_etl() -> None:
    """Wire the weekly change-checked Zomato Medallion ETL tasks."""

    # Explicitly disable TaskFlow multiple_outputs so dict payloads containing
    # None fields serialize as a single return_value XCom in Airflow 3.x.
    @task(task_id="check_zomato_version", multiple_outputs=False)
    def check_zomato_version() -> dict[str, object]:
        config = load_pipeline_runtime_config()
        run_id = str(uuid.uuid4())
        batch_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)

        conn = _open_airflow_mysql_connection()
        try:
            source_id = ensure_source_metadata(
                conn,
                source_id=DEFAULT_ZOMATO_SOURCE_ID,
                source_name=DEFAULT_ZOMATO_SOURCE_NAME,
                license_name=DEFAULT_ZOMATO_LICENSE,
                url=DEFAULT_ZOMATO_URL,
            )
            record_pipeline_run_start(
                conn,
                run_id=run_id,
                dag_id=DEFAULT_ZOMATO_DAG_ID,
                source_id=source_id,
                started_at=started_at,
            )
            latest = get_latest_successful_batch(conn, source_id)
        finally:
            conn.close()

        settings = load_pipeline_settings()
        export_kaggle_credentials(settings)
        staging_dir = (
            config.resolve_path(config.pipeline_bronze_local_path)
            / "_staging"
            / batch_id
        )
        fetch_res = fetch_zomato_dataset(
            dataset_slug=config.sources_zomato_kaggle_dataset,
            file_name=config.sources_zomato_file_name,
            target_dir=staging_dir,
            last_version=latest.source_version if latest else None,
            last_updated_at=latest.source_updated_at if latest else None,
            last_checksum=latest.file_checksum if latest else None,
            skip_if_unchanged=config.sources_zomato_skip_if_unchanged,
        )
        return {
            "run_id": run_id,
            "batch_id": batch_id,
            "source_id": source_id,
            "started_at": started_at.isoformat(),
            "status": fetch_res.status,
            "local_file_path": (
                str(fetch_res.local_file_path)
                if fetch_res.local_file_path is not None
                else None
            ),
            "file_checksum": fetch_res.file_checksum,
            "source_version": fetch_res.snapshot.source_version,
            "source_updated_at": (
                fetch_res.snapshot.source_updated_at.isoformat()
                if fetch_res.snapshot.source_updated_at is not None
                else None
            ),
        }

    @task(task_id="fetch_and_store_bronze", multiple_outputs=False)
    def fetch_and_store_bronze(check_ctx: dict[str, object]) -> dict[str, object]:
        if check_ctx["status"] == RUN_STATUS_SKIPPED_UNCHANGED:
            return dict(check_ctx)

        config = load_pipeline_runtime_config()
        settings = load_pipeline_settings()
        local_csv = Path(str(check_ctx["local_file_path"]))
        batch_id = str(check_ctx["batch_id"])
        started_at = datetime.fromisoformat(str(check_ctx["started_at"]))

        metadata: dict[str, object] = {
            "source_name": DEFAULT_ZOMATO_SOURCE_NAME,
            "source_id": check_ctx["source_id"],
            "batch_id": batch_id,
            "run_id": check_ctx["run_id"],
            "source_version": check_ctx["source_version"],
            "source_updated_at": check_ctx["source_updated_at"],
            "file_checksum": check_ctx["file_checksum"],
            "ingested_at": started_at.isoformat(),
        }

        if settings.storage_backend == "azure":
            bronze_uri = _upload_bronze_via_airflow_hook(
                local_file_path=local_csv,
                batch_date=started_at,
                batch_id=batch_id,
                metadata=metadata,
            )
        else:
            storage = LocalBronzeStorage(
                config.resolve_path(config.pipeline_bronze_local_path)
            )
            artifact = storage.write_batch_file(
                source_name=DEFAULT_ZOMATO_SOURCE_NAME,
                batch_date=started_at.date(),
                batch_id=batch_id,
                local_file_path=local_csv,
                metadata=metadata,
            )
            bronze_uri = artifact.uri_or_path

        updated_ctx = dict(check_ctx)
        updated_ctx["bronze_path"] = bronze_uri
        return updated_ctx

    @task(task_id="standardize_and_validate_silver", multiple_outputs=False)
    def standardize_and_validate_silver(
        bronze_ctx: dict[str, object],
    ) -> dict[str, object]:
        if bronze_ctx["status"] == RUN_STATUS_SKIPPED_UNCHANGED:
            return dict(bronze_ctx)

        config = load_pipeline_runtime_config()
        local_csv = Path(str(bronze_ctx["local_file_path"]))
        batch_id = str(bronze_ctx["batch_id"])
        run_id = str(bronze_ctx["run_id"])
        source_id = int(str(bronze_ctx["source_id"]))
        started_at = datetime.fromisoformat(str(bronze_ctx["started_at"]))
        source_updated_raw = bronze_ctx["source_updated_at"]
        source_updated_at = (
            datetime.fromisoformat(str(source_updated_raw))
            if source_updated_raw
            else None
        )

        raw_df = load_zomato_csv(
            local_csv, encoding=config.sources_zomato_file_encoding
        )
        vocabulary = CuisineVocabulary.from_csv()
        validation = validate_and_standardize_batch(
            raw_df,
            source_id=source_id,
            vocabulary=vocabulary,
            config=config,
        )

        quarantine_dir = config.resolve_path(config.pipeline_quarantine_path)
        write_quarantine_jsonl(validation.rejected_records, quarantine_dir, batch_id)

        conn = _open_airflow_mysql_connection()
        try:
            record_ingestion_batch(
                conn,
                batch_id=batch_id,
                source_id=source_id,
                run_id=run_id,
                source_version=(
                    str(bronze_ctx["source_version"])
                    if bronze_ctx["source_version"] is not None
                    else None
                ),
                source_updated_at=source_updated_at,
                file_checksum=str(bronze_ctx["file_checksum"]),
                file_path=str(bronze_ctx["bronze_path"]),
                row_count=validation.records_read,
                status="validated",
                ingested_at=started_at,
            )
            insert_quality_issues(
                conn,
                batch_id=batch_id,
                run_id=run_id,
                issues=validation.issues,
            )
        finally:
            conn.close()

        out_ctx = dict(bronze_ctx)
        out_ctx["rows_read"] = validation.records_read
        out_ctx["rows_quarantined"] = len(validation.rejected_records)
        out_ctx["rows_warned"] = validation.rows_warned
        return out_ctx

    @task(task_id="enforce_quality_gate", multiple_outputs=False)
    def enforce_quality_gate_task(
        val_ctx: dict[str, object],
    ) -> dict[str, object]:
        if val_ctx["status"] == RUN_STATUS_SKIPPED_UNCHANGED:
            return dict(val_ctx)

        config = load_pipeline_runtime_config()
        rows_read = int(str(val_ctx["rows_read"]))
        rows_quarantined = int(str(val_ctx["rows_quarantined"]))
        out_ctx = dict(val_ctx)
        try:
            quarantine_rate = enforce_quality_gate(
                rows_quarantined,
                rows_read,
                config.quality_max_quarantine_rate,
            )
            out_ctx["quarantine_rate"] = quarantine_rate
        except QualityGateFailedError as exc:
            out_ctx["status"] = RUN_STATUS_QUALITY_GATE_FAILED
            out_ctx["quarantine_rate"] = exc.quarantine_rate
            raise
        return out_ctx

    @task(task_id="upsert_silver", multiple_outputs=False)
    def upsert_silver_task(gate_ctx: dict[str, object]) -> dict[str, object]:
        if gate_ctx["status"] == RUN_STATUS_SKIPPED_UNCHANGED:
            return dict(gate_ctx)

        config = load_pipeline_runtime_config()
        local_csv = Path(str(gate_ctx["local_file_path"]))
        batch_id = str(gate_ctx["batch_id"])
        source_id = int(str(gate_ctx["source_id"]))
        started_at = datetime.fromisoformat(str(gate_ctx["started_at"]))

        raw_df = load_zomato_csv(
            local_csv, encoding=config.sources_zomato_file_encoding
        )
        vocabulary = CuisineVocabulary.from_csv()
        validation = validate_and_standardize_batch(
            raw_df,
            source_id=source_id,
            vocabulary=vocabulary,
            config=config,
        )
        conn = _open_airflow_mysql_connection()
        try:
            stats = upsert_silver_batch(
                conn,
                records=validation.valid_records,
                batch_id=batch_id,
                updated_at=started_at,
            )
        finally:
            conn.close()

        out_ctx = dict(gate_ctx)
        out_ctx["rows_inserted"] = stats.rows_inserted
        out_ctx["rows_updated"] = stats.rows_updated
        out_ctx["rows_unchanged"] = stats.rows_unchanged
        return out_ctx

    @task(task_id="refresh_gold", multiple_outputs=False)
    def refresh_gold_task(silver_ctx: dict[str, object]) -> dict[str, object]:
        if silver_ctx["status"] == RUN_STATUS_SKIPPED_UNCHANGED:
            return dict(silver_ctx)

        source_id = int(str(silver_ctx["source_id"]))
        conn = _open_airflow_mysql_connection()
        try:
            gold_count = refresh_gold_layer(conn, source_id=source_id)
        finally:
            conn.close()

        out_ctx = dict(silver_ctx)
        out_ctx["gold_points_count"] = gold_count
        out_ctx["status"] = RUN_STATUS_SUCCESS
        return out_ctx

    @task(
        task_id="record_pipeline_run_summary",
        trigger_rule="all_done",
        multiple_outputs=False,
    )
    def record_pipeline_run_summary_task(
        check_ctx: dict[str, object],
        gold_ctx: dict[str, object] | None = None,
    ) -> dict[str, object]:
        ctx = gold_ctx if isinstance(gold_ctx, dict) else check_ctx
        run_id = str(ctx.get("run_id", ""))
        if not run_id:
            return {"status": RUN_STATUS_FAILED}

        raw_status = str(ctx.get("status", RUN_STATUS_FAILED))
        final_status = (
            raw_status
            if raw_status
            in {
                RUN_STATUS_SUCCESS,
                RUN_STATUS_SKIPPED_UNCHANGED,
                RUN_STATUS_QUALITY_GATE_FAILED,
            }
            else RUN_STATUS_FAILED
        )
        conn = _open_airflow_mysql_connection()
        try:
            update_pipeline_run_summary(
                conn,
                run_id=run_id,
                status=final_status,
                rows_read=int(str(ctx.get("rows_read", 0))),
                rows_inserted=int(str(ctx.get("rows_inserted", 0))),
                rows_updated=int(str(ctx.get("rows_updated", 0))),
                rows_unchanged=int(str(ctx.get("rows_unchanged", 0))),
                rows_quarantined=int(str(ctx.get("rows_quarantined", 0))),
                rows_warned=int(str(ctx.get("rows_warned", 0))),
                quarantine_rate=float(str(ctx.get("quarantine_rate", 0.0))),
                ended_at=datetime.now(UTC),
            )
        finally:
            conn.close()
        return {"run_id": run_id, "status": final_status}

    check_out = check_zomato_version()
    bronze_out = fetch_and_store_bronze(check_out)
    validated_out = standardize_and_validate_silver(bronze_out)
    gated_out = enforce_quality_gate_task(validated_out)
    silver_out = upsert_silver_task(gated_out)
    gold_out = refresh_gold_task(silver_out)
    record_pipeline_run_summary_task(check_out, gold_out)


dag_instance = zomato_weekly_etl()
