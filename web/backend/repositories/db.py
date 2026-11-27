"""Per-request PyMySQL connection management and local fallback gating."""

from __future__ import annotations

import logging
import ssl
import time
from collections.abc import Generator
from typing import Protocol

import pymysql
from pymysql.cursors import DictCursor

from web.backend.exceptions import ServiceUnavailableError
from web.backend.settings import BackendSettings, settings

logger = logging.getLogger(__name__)

_LOCAL_MYSQL_COOLDOWN_SECONDS = 60.0
_LOCAL_PROBE_TIMEOUT_SECONDS = 2
_mysql_unavailable_until: float = 0.0


def reset_mysql_fallback_cooldown() -> None:
    """Reset the local MySQL unavailability cooldown (used in tests)."""
    global _mysql_unavailable_until
    _mysql_unavailable_until = 0.0


class DictCursorConnection(Protocol):
    """Protocol for a DB connection providing dictionary-row cursors."""

    def cursor(self) -> DictCursor:
        """Return a cursor yielding dict rows."""
        ...

    def close(self) -> None:
        """Close the database connection."""
        ...


def open_mysql_connection(app_settings: BackendSettings) -> DictCursorConnection:
    """Open a single short-lived PyMySQL connection with DictCursor."""
    ssl_params: ssl.SSLContext | None = (
        ssl.create_default_context() if app_settings.mysql_tls_enabled else None
    )
    timeout = app_settings.database_connect_timeout_seconds
    if can_use_csv_fallback(app_settings):
        timeout = min(timeout, _LOCAL_PROBE_TIMEOUT_SECONDS)
    conn: DictCursorConnection = pymysql.connect(
        host=app_settings.mysql_host,
        port=app_settings.mysql_port,
        user=app_settings.mysql_app_user,
        password=app_settings.mysql_app_password.get_secret_value(),
        database=app_settings.mysql_database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=timeout,
        read_timeout=app_settings.database_connect_timeout_seconds,
        write_timeout=app_settings.database_connect_timeout_seconds,
        autocommit=True,
        ssl=ssl_params,
    )
    return conn


def can_use_csv_fallback(app_settings: BackendSettings) -> bool:
    """Return True only in local environment when CSV fallback is explicitly enabled."""
    return (
        app_settings.app_env == "local"
        and app_settings.backend_allow_csv_fallback_in_local
    )


def get_db_connection() -> Generator[DictCursorConnection | None, None, None]:
    """Yield one PyMySQL connection per request, or None for local CSV fallback."""
    global _mysql_unavailable_until
    if can_use_csv_fallback(settings) and time.monotonic() < _mysql_unavailable_until:
        yield None
        return

    conn: DictCursorConnection | None = None
    try:
        conn = open_mysql_connection(settings)
    except (pymysql.MySQLError, OSError) as exc:
        if can_use_csv_fallback(settings):
            _mysql_unavailable_until = time.monotonic() + _LOCAL_MYSQL_COOLDOWN_SECONDS
            logger.warning(
                "MySQL unavailable in local mode; falling back to local CSV snapshot",
                extra={"details": type(exc).__name__},
            )
            yield None
            return
        logger.error(
            "MySQL connection failed in non-fallback environment",
            extra={"details": type(exc).__name__},
        )
        raise ServiceUnavailableError(
            "Database service is currently unavailable"
        ) from exc

    try:
        yield conn
    finally:
        if conn is not None:
            try:
                conn.close()
            except pymysql.MySQLError:
                logger.warning("Failed to close PyMySQL connection cleanly")
