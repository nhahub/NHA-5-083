"""Tests for every batch-level and record-level rule in docs/DATA_QUALITY_RULES.md."""

from pathlib import Path

import pandas as pd
import pytest

from pipeline.constants import (
    MAX_QUARANTINE_RATE,
    RULE_BATCH_EMPTY,
    RULE_BOOLEAN_FLAG_INVALID,
    RULE_CITY_MISSING,
    RULE_COORDINATES_MISSING,
    RULE_COORDINATES_OUT_OF_RANGE,
    RULE_COST_NEGATIVE,
    RULE_COST_ZERO,
    RULE_COUNTRY_CODE_UNKNOWN,
    RULE_CUISINE_MISSING,
    RULE_CUISINE_UNMAPPED,
    RULE_CURRENCY_LABEL_MISMATCH,
    RULE_FILE_DECODE_FAILED,
    RULE_NAME_MISSING,
    RULE_PRICE_RANGE_INVALID,
    RULE_RATING_OUT_OF_RANGE,
    RULE_SCHEMA_COLUMNS_MISSING,
    RULE_SOURCE_ID_DUPLICATE_IN_BATCH,
    RULE_SOURCE_ID_MISSING,
    RULE_TEXT_MOJIBAKE_REPAIRED,
    RULE_VOTES_NEGATIVE,
    SEVERITY_REJECT,
    SEVERITY_WARNING,
    ZOMATO_EXPECTED_COLUMNS,
)
from pipeline.ingestion.csv_loader import BatchValidationError, load_zomato_csv
from pipeline.quality.quarantine import (
    QualityGateFailedError,
    enforce_quality_gate,
    write_quarantine_jsonl,
)
from pipeline.quality.validator import ValidationResult, validate_and_standardize_batch
from pipeline.settings import PipelineRuntimeConfig
from pipeline.transform.cuisines import CuisineVocabulary


def _valid_row(**overrides: str) -> dict[str, str]:
    base = {
        "Restaurant ID": "1001",
        "Restaurant Name": "Spice Garden",
        "Country Code": "1",
        "City": "New Delhi",
        "Address": "12 Connaught Place",
        "Locality": "Connaught Place",
        "Locality Verbose": "Connaught Place, New Delhi",
        "Longitude": "77.216721",
        "Latitude": "28.631516",
        "Cuisines": "North Indian, Chinese",
        "Average Cost for two": "800",
        "Currency": "Indian Rupees(Rs.)",
        "Has Table booking": "Yes",
        "Has Online delivery": "No",
        "Is delivering now": "No",
        "Switch to order menu": "No",
        "Price range": "2",
        "Aggregate rating": "4.2",
        "Rating color": "Green",
        "Rating text": "Very Good",
        "Votes": "150",
    }
    base.update(overrides)
    return base


def _validate_rows(rows: list[dict[str, str]]) -> ValidationResult:
    raw_df = pd.DataFrame(rows, columns=list(ZOMATO_EXPECTED_COLUMNS), dtype=str)
    vocab = CuisineVocabulary.from_csv()
    config = PipelineRuntimeConfig()
    return validate_and_standardize_batch(
        raw_df,
        source_id=1,
        vocabulary=vocab,
        config=config,
    )


def test_batch_schema_columns_missing(tmp_path: Path) -> None:
    csv_path = tmp_path / "missing_col.csv"
    csv_path.write_text("Restaurant ID,Restaurant Name\n1,Test\n", encoding="latin-1")
    with pytest.raises(BatchValidationError) as exc_info:
        load_zomato_csv(csv_path)
    assert exc_info.value.rule_name == RULE_SCHEMA_COLUMNS_MISSING


def test_batch_file_decode_failed(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad_decode.csv"
    csv_path.write_bytes(b"\xff\xfe\x00\x00invalid")
    with pytest.raises(BatchValidationError) as exc_info:
        load_zomato_csv(csv_path, encoding="utf-8")
    assert exc_info.value.rule_name == RULE_FILE_DECODE_FAILED


def test_batch_empty(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text(",".join(ZOMATO_EXPECTED_COLUMNS) + "\n", encoding="latin-1")
    with pytest.raises(BatchValidationError) as exc_info:
        load_zomato_csv(csv_path)
    assert exc_info.value.rule_name == RULE_BATCH_EMPTY


def test_valid_baseline_row_has_zero_issues() -> None:
    res = _validate_rows([_valid_row()])
    assert res.records_read == 1
    assert len(res.valid_records) == 1
    assert len(res.rejected_records) == 0
    assert len(res.issues) == 0
    assert res.rows_warned == 0


@pytest.mark.parametrize(
    ("overrides", "expected_rule"),
    [
        ({"Restaurant ID": ""}, RULE_SOURCE_ID_MISSING),
        ({"Restaurant ID": "abc"}, RULE_SOURCE_ID_MISSING),
        ({"Restaurant Name": "   "}, RULE_NAME_MISSING),
        ({"Country Code": "999"}, RULE_COUNTRY_CODE_UNKNOWN),
        ({"City": ""}, RULE_CITY_MISSING),
        ({"Aggregate rating": "5.5"}, RULE_RATING_OUT_OF_RANGE),
        ({"Aggregate rating": "-0.1"}, RULE_RATING_OUT_OF_RANGE),
        ({"Votes": "-3"}, RULE_VOTES_NEGATIVE),
        ({"Votes": "many"}, RULE_VOTES_NEGATIVE),
        ({"Average Cost for two": "-100"}, RULE_COST_NEGATIVE),
        ({"Price range": "5"}, RULE_PRICE_RANGE_INVALID),
        ({"Price range": "0"}, RULE_PRICE_RANGE_INVALID),
        ({"Has Table booking": "Maybe"}, RULE_BOOLEAN_FLAG_INVALID),
        ({"Has Online delivery": "1"}, RULE_BOOLEAN_FLAG_INVALID),
    ],
)
def test_reject_rules(overrides: dict[str, str], expected_rule: str) -> None:
    res = _validate_rows([_valid_row(**overrides)])
    assert len(res.valid_records) == 0
    assert len(res.rejected_records) == 1
    assert res.rejected_records[0].rule_name == expected_rule
    assert any(
        issue.rule_name == expected_rule and issue.severity == SEVERITY_REJECT
        for issue in res.issues
    )


def test_duplicate_source_id_rejects_all_copies() -> None:
    res = _validate_rows(
        [
            _valid_row(**{"Restaurant ID": "2002", "Restaurant Name": "Copy A"}),
            _valid_row(**{"Restaurant ID": "2002", "Restaurant Name": "Copy B"}),
            _valid_row(**{"Restaurant ID": "2003", "Restaurant Name": "Unique"}),
        ]
    )
    assert len(res.valid_records) == 1
    assert res.valid_records[0].source_restaurant_id == "2003"
    assert len(res.rejected_records) == 2
    assert all(
        rec.rule_name == RULE_SOURCE_ID_DUPLICATE_IN_BATCH
        for rec in res.rejected_records
    )


@pytest.mark.parametrize(
    ("overrides", "expected_rule"),
    [
        ({"Latitude": "0", "Longitude": "0"}, RULE_COORDINATES_MISSING),
        ({"Latitude": "", "Longitude": ""}, RULE_COORDINATES_MISSING),
        ({"Latitude": "95.0", "Longitude": "77.2"}, RULE_COORDINATES_OUT_OF_RANGE),
        ({"Latitude": "28.6", "Longitude": "190.0"}, RULE_COORDINATES_OUT_OF_RANGE),
        ({"Average Cost for two": "0"}, RULE_COST_ZERO),
        ({"Cuisines": ""}, RULE_CUISINE_MISSING),
        ({"Cuisines": "Martian Fusion"}, RULE_CUISINE_UNMAPPED),
        (
            {"Country Code": "162", "Currency": "Botswana Pula(P)"},
            RULE_CURRENCY_LABEL_MISMATCH,
        ),
        ({"Restaurant Name": "4 Barrels Cafï¿½ï¿½"}, RULE_TEXT_MOJIBAKE_REPAIRED),
    ],
)
def test_warning_rules_keep_record_in_silver(
    overrides: dict[str, str], expected_rule: str
) -> None:
    res = _validate_rows([_valid_row(**overrides)])
    assert len(res.valid_records) == 1
    assert len(res.rejected_records) == 0
    assert res.rows_warned == 1
    assert any(
        issue.rule_name == expected_rule and issue.severity == SEVERITY_WARNING
        for issue in res.issues
    )


def test_quality_gate_boundaries(tmp_path: Path) -> None:
    # 14.9% passes (149 / 1000)
    rate_below = enforce_quality_gate(149, 1000, MAX_QUARANTINE_RATE)
    assert rate_below == 0.149

    # 15.0% passes (150 / 1000, strict > threshold)
    rate_exact = enforce_quality_gate(150, 1000, MAX_QUARANTINE_RATE)
    assert rate_exact == 0.15

    # 15.1% fails (151 / 1000)
    with pytest.raises(QualityGateFailedError) as exc_info:
        enforce_quality_gate(151, 1000, MAX_QUARANTINE_RATE)
    assert exc_info.value.quarantine_rate == 0.151

    # Quarantine JSONL audit output
    res = _validate_rows([_valid_row(**{"Restaurant Name": ""})])
    jsonl_path = write_quarantine_jsonl(res.rejected_records, tmp_path, "batch-001")
    assert jsonl_path is not None and jsonl_path.is_file()
    content = jsonl_path.read_text(encoding="utf-8")
    assert RULE_NAME_MISSING in content
