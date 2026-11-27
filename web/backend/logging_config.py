"""Structured JSON-line logging helpers and query truncation."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from web.backend.constants import QUERY_LOG_MAX_CHARS

CONTEXT_FIELDS: tuple[str, ...] = (
    "run_id",
    "batch_id",
    "source_id",
    "rule_name",
    "request_id",
    "parser_used",
    "fallback_used",
    "query_preview",
    "details",
    "status_code",
)


class JsonLineFormatter(logging.Formatter):
    """Format log records as single-line UTC JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a LogRecord into a compact JSON line."""
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level_name: str = "INFO") -> None:
    """Configure root backend logging with JSON line formatting."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLineFormatter())
    root_logger = logging.getLogger("web.backend")
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    root_logger.propagate = False


def truncate_query_for_log(
    query: str,
    max_chars: int = QUERY_LOG_MAX_CHARS,
) -> str:
    """Truncate user NLP query text strictly to the configured log limit."""
    effective_limit = min(max(max_chars, 0), QUERY_LOG_MAX_CHARS)
    return query[:effective_limit]
