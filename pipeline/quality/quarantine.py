"""Quarantine rate enforcement (15% quality gate) and local JSONL audit sink."""

import json
import logging
from collections.abc import Sequence
from pathlib import Path

from pipeline.constants import MAX_QUARANTINE_RATE, QUARANTINE_RATE_DECIMALS
from pipeline.quality.validator import RejectedRecord

logger = logging.getLogger(__name__)


class QualityGateFailedError(Exception):
    """Raised when ``rejected_records / records_read`` exceeds threshold."""

    def __init__(
        self,
        *,
        quarantine_rate: float,
        max_quarantine_rate: float,
        rejected_count: int,
        records_read: int,
    ) -> None:
        """Initialize a quality gate failure exception.

        Args:
            quarantine_rate: Observed ratio of rejected rows to total rows read.
            max_quarantine_rate: Configured maximum allowed quarantine ratio.
            rejected_count: Total rejected rows in the batch.
            records_read: Total rows read in the batch.
        """
        message = (
            f"Quality gate failed: quarantine rate {quarantine_rate:.4f} "
            f"({rejected_count}/{records_read}) exceeds max {max_quarantine_rate:.4f}"
        )
        super().__init__(message)
        self.quarantine_rate = quarantine_rate
        self.max_quarantine_rate = max_quarantine_rate
        self.rejected_count = rejected_count
        self.records_read = records_read


def compute_quarantine_rate(rejected_count: int, records_read: int) -> float:
    """Compute rounded quarantine rate ``rejected_count / records_read``.

    Args:
        rejected_count: Number of rows rejected by quality rules.
        records_read: Total number of rows read in the batch.

    Returns:
        Ratio rounded to ``QUARANTINE_RATE_DECIMALS`` decimal places.

    Raises:
        ValueError: If ``records_read <= 0`` or ``rejected_count < 0``.
    """
    if records_read <= 0:
        raise ValueError("records_read must be positive")
    if rejected_count < 0:
        raise ValueError("rejected_count cannot be negative")
    return round(rejected_count / records_read, QUARANTINE_RATE_DECIMALS)


def enforce_quality_gate(
    rejected_count: int,
    records_read: int,
    max_quarantine_rate: float = MAX_QUARANTINE_RATE,
) -> float:
    """Enforce the maximum quarantine rate safety gate before Silver/Gold promotion.

    Args:
        rejected_count: Number of rejected rows in the batch.
        records_read: Total rows read in the batch.
        max_quarantine_rate: Maximum inclusive ratio allowed (default ``0.15``).

    Returns:
        Observed quarantine rate when the gate passes.

    Raises:
        QualityGateFailedError: If rejected rate exceeds ``max_quarantine_rate``.
    """
    raw_rate = rejected_count / records_read if records_read > 0 else 1.0
    rounded_rate = compute_quarantine_rate(rejected_count, records_read)
    if raw_rate > max_quarantine_rate:
        logger.error(
            "Quality gate failed: rate=%.4f rejected=%d read=%d max=%.4f",
            raw_rate,
            rejected_count,
            records_read,
            max_quarantine_rate,
        )
        raise QualityGateFailedError(
            quarantine_rate=rounded_rate,
            max_quarantine_rate=max_quarantine_rate,
            rejected_count=rejected_count,
            records_read=records_read,
        )
    return rounded_rate


def write_quarantine_jsonl(
    rejected_records: Sequence[RejectedRecord],
    output_dir: Path,
    batch_id: str,
) -> Path | None:
    """Write rejected records and raw payloads to a local JSONL audit file.

    Args:
        rejected_records: Rejected records from batch validation.
        output_dir: Directory where quarantine JSONL files are stored.
        batch_id: Batch identifier used in the file name.

    Returns:
        Path to the written JSONL file, or ``None`` if there were no rejects.
    """
    if not rejected_records:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"{batch_id}_quarantine.jsonl"
    lines = [
        json.dumps(
            {
                "batch_id": batch_id,
                "source_record_id": rec.source_record_id,
                "rule_name": rec.rule_name,
                "reason": rec.reason,
                "raw_payload": rec.raw_payload,
            },
            ensure_ascii=False,
        )
        for rec in rejected_records
    ]
    target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(
        "Wrote %d quarantined records to %s",
        len(rejected_records),
        target_path,
        extra={"batch_id": batch_id},
    )
    return target_path
