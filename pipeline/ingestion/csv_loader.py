"""CSV reader and batch-level validation for raw Zomato ingestion."""

import logging
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from pipeline.constants import (
    RULE_BATCH_EMPTY,
    RULE_FILE_DECODE_FAILED,
    RULE_SCHEMA_COLUMNS_MISSING,
    ZOMATO_EXPECTED_COLUMNS,
)

logger = logging.getLogger(__name__)


class BatchValidationError(Exception):
    """Raised when an ingested file fails a batch-level quality rule."""

    def __init__(self, rule_name: str, reason: str) -> None:
        """Initialize a batch-level validation error.

        Args:
            rule_name: Canonical batch rule constant from ``pipeline.constants``.
            reason: Human-readable explanation of the failure.
        """
        super().__init__(reason)
        self.rule_name = rule_name
        self.reason = reason


def load_zomato_csv(
    file_path: Path,
    *,
    encoding: str = "latin-1",
    expected_columns: Sequence[str] = ZOMATO_EXPECTED_COLUMNS,
) -> pd.DataFrame:
    """Read a Zomato CSV file with explicit encoding and enforce batch checks.

    Args:
        file_path: Path to the CSV file.
        encoding: Expected character encoding (e.g., ``latin-1``).
        expected_columns: Required column headers.

    Returns:
        ``pd.DataFrame`` with all columns loaded as strings.

    Raises:
        BatchValidationError: On decode failure, missing columns, or empty file.
    """
    try:
        raw_df = pd.read_csv(
            file_path,
            encoding=encoding,
            dtype=str,
            keep_default_na=False,
        )
    except (UnicodeDecodeError, LookupError) as exc:
        logger.error(
            "Failed to decode CSV file %s with encoding %s",
            file_path.name,
            encoding,
            extra={"rule_name": RULE_FILE_DECODE_FAILED},
        )
        raise BatchValidationError(
            RULE_FILE_DECODE_FAILED,
            f"failed to decode {file_path.name} as {encoding}: {exc}",
        ) from exc
    except pd.errors.EmptyDataError as exc:
        logger.error(
            "CSV file %s contains no data",
            file_path.name,
            extra={"rule_name": RULE_BATCH_EMPTY},
        )
        raise BatchValidationError(
            RULE_BATCH_EMPTY,
            f"file {file_path.name} is empty",
        ) from exc

    missing_columns = [col for col in expected_columns if col not in raw_df.columns]
    if missing_columns:
        reason = f"missing required columns: {', '.join(missing_columns)}"
        logger.error(
            reason,
            extra={"rule_name": RULE_SCHEMA_COLUMNS_MISSING},
        )
        raise BatchValidationError(RULE_SCHEMA_COLUMNS_MISSING, reason)

    if len(raw_df) == 0:
        reason = f"batch file {file_path.name} has zero data rows"
        logger.error(reason, extra={"rule_name": RULE_BATCH_EMPTY})
        raise BatchValidationError(RULE_BATCH_EMPTY, reason)

    logger.info("Loaded %d raw rows from %s", len(raw_df), file_path.name)
    return raw_df
