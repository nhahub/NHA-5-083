"""Structured JSON-lines logging configuration for the ETL pipeline."""

import json
import logging
from datetime import UTC, datetime

_EXTRA_CONTEXT_FIELDS = ("run_id", "batch_id", "source_id", "rule_name")


class JsonLineFormatter(logging.Formatter):
    """Format log records as single-line JSON objects with UTC timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record to a JSON line.

        Args:
            record: Standard library log record.

        Returns:
            JSON-encoded string containing timestamp, level, logger, message,
            and any structured pipeline context attributes.
        """
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _EXTRA_CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_pipeline_logging(level: str = "INFO") -> None:
    """Configure root logging with the pipeline JSON-lines formatter.

    Args:
        level: Logging level name (e.g., ``INFO``, ``DEBUG``, ``WARNING``).
    """
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    formatter = JsonLineFormatter()
    if not root_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)
        return

    for existing_handler in root_logger.handlers:
        existing_handler.setFormatter(formatter)
