"""End-to-end SQLite integration tests for incremental upsert, Bronze, and Gold."""

import csv
from datetime import UTC, datetime
from pathlib import Path

from pipeline.constants import (
    RUN_STATUS_SKIPPED_UNCHANGED,
    RUN_STATUS_SUCCESS,
    ZOMATO_EXPECTED_COLUMNS,
)
from pipeline.ingestion.bronze_storage import LocalBronzeStorage
from pipeline.ingestion.kaggle_source import (
    SourceMetadataSnapshot,
    fetch_zomato_dataset,
)
from pipeline.load.db import SqliteConnection, initialize_sqlite_test_schema
from pipeline.runner import run_zomato_pipeline
from pipeline.settings import PipelineRuntimeConfig


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="latin-1", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ZOMATO_EXPECTED_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _sample_rows() -> list[dict[str, str]]:
    return [
        {
            "Restaurant ID": "101",
            "Restaurant Name": "Alpha Bistro",
            "Country Code": "1",
            "City": "New Delhi",
            "Address": "1 Main Rd",
            "Locality": "Hauz Khas",
            "Locality Verbose": "Hauz Khas, New Delhi",
            "Longitude": "77.200000",
            "Latitude": "28.550000",
            "Cuisines": "North Indian, Cafe",
            "Average Cost for two": "600",
            "Currency": "Indian Rupees(Rs.)",
            "Has Table booking": "Yes",
            "Has Online delivery": "No",
            "Is delivering now": "No",
            "Switch to order menu": "No",
            "Price range": "2",
            "Aggregate rating": "4.4",
            "Rating color": "Green",
            "Rating text": "Very Good",
            "Votes": "95",
        },
        {
            "Restaurant ID": "102",
            "Restaurant Name": "No Coords Diner",
            "Country Code": "216",
            "City": "Austin",
            "Address": "2 Oak St",
            "Locality": "Downtown",
            "Locality Verbose": "Downtown, Austin",
            "Longitude": "0",
            "Latitude": "0",
            "Cuisines": "American",
            "Average Cost for two": "40",
            "Currency": "Dollar($)",
            "Has Table booking": "No",
            "Has Online delivery": "Yes",
            "Is delivering now": "No",
            "Switch to order menu": "No",
            "Price range": "2",
            "Aggregate rating": "0",
            "Rating color": "White",
            "Rating text": "Not rated",
            "Votes": "0",
        },
    ]


class _FakeKaggleClient:
    """In-memory fake Kaggle client for check-before-download tests."""

    def __init__(self, csv_source_path: Path, version: str) -> None:
        self._csv_source_path = csv_source_path
        self._version = version
        self.download_calls = 0

    def get_dataset_metadata(self, dataset_slug: str) -> SourceMetadataSnapshot:
        return SourceMetadataSnapshot(
            source_name="zomato",
            dataset_slug=dataset_slug,
            source_version=self._version,
            source_updated_at=datetime(2026, 11, 24, 0, 0, tzinfo=UTC),
            title="Zomato Restaurants",
            license_name="CC0 1.0",
        )

    def download_dataset(self, dataset_slug: str, destination_dir: Path) -> Path:
        del dataset_slug
        self.download_calls += 1
        destination_dir.mkdir(parents=True, exist_ok=True)
        target = destination_dir / self._csv_source_path.name
        target.write_bytes(self._csv_source_path.read_bytes())
        return destination_dir


def test_incremental_upsert_and_skip_unchanged(tmp_path: Path) -> None:
    conn = SqliteConnection(":memory:")
    initialize_sqlite_test_schema(conn)

    bronze_dir = tmp_path / "bronze"
    quarantine_dir = tmp_path / "quarantine"
    config = PipelineRuntimeConfig(
        pipeline_bronze_local_path=str(bronze_dir),
        pipeline_quarantine_path=str(quarantine_dir),
    )
    storage = LocalBronzeStorage(bronze_dir)

    csv_v1 = tmp_path / "zomato_v1.csv"
    _write_csv(csv_v1, _sample_rows())

    # Batch 1: initial insert
    summary1 = run_zomato_pipeline(
        source_csv=csv_v1,
        run_id="run-1",
        batch_id="batch-1",
        conn=conn,
        bronze_storage=storage,
        runtime_config=config,
    )
    assert summary1.status == RUN_STATUS_SUCCESS
    assert summary1.rows_read == 2
    assert summary1.rows_inserted == 2
    assert summary1.rows_updated == 0
    assert summary1.rows_unchanged == 0
    assert summary1.rows_warned == 1
    assert summary1.gold_points_count == 1  # Only row 101 has valid coordinates

    # Batch 2: identical checksum with skip_if_unchanged=True skips immediately
    summary2_skip = run_zomato_pipeline(
        source_csv=csv_v1,
        skip_if_unchanged=True,
        run_id="run-2-skip",
        batch_id="batch-2-skip",
        conn=conn,
        bronze_storage=storage,
        runtime_config=config,
    )
    assert summary2_skip.status == RUN_STATUS_SKIPPED_UNCHANGED

    # Batch 2b: forced re-load of identical records -> rows_unchanged only, 0 rewrites
    summary2_force = run_zomato_pipeline(
        source_csv=csv_v1,
        skip_if_unchanged=False,
        run_id="run-2-force",
        batch_id="batch-2-force",
        conn=conn,
        bronze_storage=storage,
        runtime_config=config,
    )
    assert summary2_force.status == RUN_STATUS_SUCCESS
    assert summary2_force.rows_inserted == 0
    assert summary2_force.rows_updated == 0
    assert summary2_force.rows_unchanged == 2

    cur = conn.cursor()
    cur.execute(
        "SELECT batch_id, last_seen_batch_id FROM restaurants "
        "WHERE source_restaurant_id = '101'"
    )
    row_101 = cur.fetchone()
    assert row_101 is not None
    assert row_101["batch_id"] == "batch-1"
    assert row_101["last_seen_batch_id"] == "batch-2-force"

    # Batch 3: modify row 101, keep row 102 unchanged, add row 103
    rows_v2 = _sample_rows()
    rows_v2[0]["Votes"] = "120"
    rows_v2[0]["Cuisines"] = "Mughlai"
    rows_v2.append(
        {
            **rows_v2[0],
            "Restaurant ID": "103",
            "Restaurant Name": "Gamma Grill",
            "Cuisines": "Grill",
        }
    )
    csv_v2 = tmp_path / "zomato_v2.csv"
    _write_csv(csv_v2, rows_v2)

    summary3 = run_zomato_pipeline(
        source_csv=csv_v2,
        run_id="run-3",
        batch_id="batch-3",
        conn=conn,
        bronze_storage=storage,
        runtime_config=config,
    )
    assert summary3.status == RUN_STATUS_SUCCESS
    assert summary3.rows_read == 3
    assert summary3.rows_inserted == 1
    assert summary3.rows_updated == 1
    assert summary3.rows_unchanged == 1
    assert summary3.gold_points_count == 2

    cur.execute(
        """
        SELECT c.cuisine_name
        FROM restaurant_cuisines AS rc
        JOIN restaurants AS r ON r.restaurant_id = rc.restaurant_id
        JOIN cuisines AS c ON c.cuisine_id = rc.cuisine_id
        WHERE r.source_restaurant_id = '101'
        """
    )
    cuisines_101 = [row["cuisine_name"] for row in cur.fetchall()]
    assert cuisines_101 == ["Mughlai"]
    cur.close()
    conn.close()


def test_kaggle_check_before_download_and_checksum_guard(tmp_path: Path) -> None:
    csv_file = tmp_path / "zomato.csv"
    _write_csv(csv_file, _sample_rows())
    fake_client = _FakeKaggleClient(csv_file, version="1")

    first = fetch_zomato_dataset(
        "shrutimehta/zomato-restaurants-data",
        "zomato.csv",
        tmp_path / "dl1",
        client=fake_client,
    )
    assert first.status == "downloaded"
    assert fake_client.download_calls == 1
    assert first.file_checksum is not None

    # Same version and updated_at skips download completely
    second = fetch_zomato_dataset(
        "shrutimehta/zomato-restaurants-data",
        "zomato.csv",
        tmp_path / "dl2",
        client=fake_client,
        last_version="1",
        last_updated_at=datetime(2026, 11, 24, 0, 0, tzinfo=UTC),
        last_checksum=first.file_checksum,
    )
    assert second.status == RUN_STATUS_SKIPPED_UNCHANGED
    assert fake_client.download_calls == 1

    # Changed version but identical file content still skips via SHA-256 guard
    fake_client_v2 = _FakeKaggleClient(csv_file, version="2")
    third = fetch_zomato_dataset(
        "shrutimehta/zomato-restaurants-data",
        "zomato.csv",
        tmp_path / "dl3",
        client=fake_client_v2,
        last_version="1",
        last_updated_at=datetime(2026, 11, 24, 0, 0, tzinfo=UTC),
        last_checksum=first.file_checksum,
    )
    assert third.status == RUN_STATUS_SKIPPED_UNCHANGED
    assert fake_client_v2.download_calls == 1
