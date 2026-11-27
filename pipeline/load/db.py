"""PyMySQL connection manager and SQLite test adapter with named parameters."""

import logging
import re
import sqlite3
import ssl
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast

import pymysql
import pymysql.cursors

from pipeline.constants import DEFAULT_ZOMATO_SOURCE_NAME

logger = logging.getLogger(__name__)

_NAMED_PARAM_PATTERN = re.compile(r"%\(([A-Za-z_][A-Za-z0-9_]*)\)s")


class DbCursorProtocol(Protocol):
    """Database cursor interface shared by PyMySQL and SQLite adapters."""

    @property
    def lastrowid(self) -> int:
        """Return the auto-generated ID of the last inserted row."""

    def execute(
        self,
        query: str,
        args: Mapping[str, object] | Sequence[object] | None = None,
    ) -> object:
        """Execute a single parameterized SQL statement."""

    def executemany(
        self,
        query: str,
        args: Sequence[Mapping[str, object]] | Sequence[Sequence[object]],
    ) -> object:
        """Execute a parameterized SQL statement for multiple parameter sets."""

    def fetchone(self) -> dict[str, object] | None:
        """Fetch the next result row as a column-keyed mapping."""

    def fetchall(self) -> list[dict[str, object]]:
        """Fetch all remaining result rows as column-keyed mappings."""

    def close(self) -> None:
        """Close the cursor."""


class DbConnectionProtocol(Protocol):
    """Database connection interface shared by PyMySQL and SQLite adapters."""

    @property
    def dialect(self) -> str:
        """Return the SQL dialect identifier (``mysql`` or ``sqlite``)."""

    def cursor(self) -> DbCursorProtocol:
        """Open a new dict-returning cursor."""

    def commit(self) -> None:
        """Commit the current transaction."""

    def rollback(self) -> None:
        """Roll back the current transaction."""

    def close(self) -> None:
        """Close the underlying connection."""


class _MySqlCursorWrapper:
    """Thin typed wrapper over ``pymysql.cursors.DictCursor``."""

    def __init__(self, inner: pymysql.cursors.DictCursor) -> None:
        self._inner = inner

    @property
    def lastrowid(self) -> int:
        return int(self._inner.lastrowid)

    def execute(
        self,
        query: str,
        args: Mapping[str, object] | Sequence[object] | None = None,
    ) -> object:
        return self._inner.execute(query, args)

    def executemany(
        self,
        query: str,
        args: Sequence[Mapping[str, object]] | Sequence[Sequence[object]],
    ) -> object:
        return self._inner.executemany(query, args)

    def fetchone(self) -> dict[str, object] | None:
        row = self._inner.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> list[dict[str, object]]:
        rows = self._inner.fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._inner.close()


class MySqlConnectionWrapper:
    """PyMySQL connection wrapper implementing ``DbConnectionProtocol``."""

    def __init__(self, inner: pymysql.connections.Connection) -> None:
        """Initialize wrapper around an open PyMySQL connection.

        Args:
            inner: Open PyMySQL connection configured with ``DictCursor``.
        """
        self._inner = inner

    @property
    def dialect(self) -> str:
        """Return ``mysql``."""
        return "mysql"

    def cursor(self) -> DbCursorProtocol:
        """Return a dictionary cursor."""
        return _MySqlCursorWrapper(self._inner.cursor())

    def commit(self) -> None:
        """Commit the active transaction."""
        self._inner.commit()

    def rollback(self) -> None:
        """Roll back the active transaction."""
        self._inner.rollback()

    def close(self) -> None:
        """Close the MySQL connection."""
        self._inner.close()


def open_mysql_connection(
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    tls_enabled: bool = False,
    connect_timeout: int = 15,
) -> MySqlConnectionWrapper:
    """Open a new PyMySQL connection using ``utf8mb4`` and optional TLS.

    Args:
        host: MySQL hostname.
        port: MySQL TCP port.
        database: Target schema name.
        user: Pipeline DB username.
        password: Pipeline DB password.
        tls_enabled: Enable TLS encryption when ``True``.
        connect_timeout: Connection timeout in seconds.

    Returns:
        ``MySqlConnectionWrapper`` ready for transactional operations.
    """
    ssl_arg: ssl.SSLContext | None = (
        ssl.create_default_context() if tls_enabled else None
    )
    raw_conn = pymysql.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=connect_timeout,
        ssl=ssl_arg,
    )
    return MySqlConnectionWrapper(cast(pymysql.connections.Connection, raw_conn))


def _adapt_param_for_sqlite(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


def _translate_named_params_for_sqlite(
    query: str,
    args: Mapping[str, object] | Sequence[object] | None,
) -> tuple[str, dict[str, object] | tuple[object, ...]]:
    translated_sql = _NAMED_PARAM_PATTERN.sub(r":\1", query)
    if args is None:
        return translated_sql, ()
    if isinstance(args, Mapping):
        adapted = {str(k): _adapt_param_for_sqlite(v) for k, v in args.items()}
        return translated_sql, adapted
    return translated_sql, tuple(_adapt_param_for_sqlite(v) for v in args)


class _SqliteCursorWrapper:
    """Cursor wrapper translating PyMySQL ``%(name)s`` placeholders to SQLite."""

    def __init__(self, inner: sqlite3.Cursor) -> None:
        self._inner = inner

    @property
    def lastrowid(self) -> int:
        return int(self._inner.lastrowid or 0)

    def execute(
        self,
        query: str,
        args: Mapping[str, object] | Sequence[object] | None = None,
    ) -> object:
        sql_text, params = _translate_named_params_for_sqlite(query, args)
        return self._inner.execute(sql_text, params)

    def executemany(
        self,
        query: str,
        args: Sequence[Mapping[str, object]] | Sequence[Sequence[object]],
    ) -> object:
        translated_sql = _NAMED_PARAM_PATTERN.sub(r":\1", query)
        adapted_rows = [
            _translate_named_params_for_sqlite(query, item)[1] for item in args
        ]
        return self._inner.executemany(translated_sql, adapted_rows)

    def fetchone(self) -> dict[str, object] | None:
        row = self._inner.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> list[dict[str, object]]:
        rows = self._inner.fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._inner.close()


class SqliteConnection:
    """SQLite connection adapter strictly for unit and integration testing."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        """Open a SQLite connection with foreign keys enabled.

        Args:
            database: SQLite database file path or ``:memory:``.
        """
        self._inner = sqlite3.connect(str(database))
        self._inner.row_factory = sqlite3.Row
        self._inner.execute("PRAGMA foreign_keys = ON;")

    @property
    def dialect(self) -> str:
        """Return ``sqlite``."""
        return "sqlite"

    def cursor(self) -> DbCursorProtocol:
        """Return a dict-returning SQLite cursor wrapper."""
        return _SqliteCursorWrapper(self._inner.cursor())

    def commit(self) -> None:
        """Commit the current SQLite transaction."""
        self._inner.commit()

    def rollback(self) -> None:
        """Roll back the current SQLite transaction."""
        self._inner.rollback()

    def close(self) -> None:
        """Close the SQLite connection."""
        self._inner.close()


def execute_sql_script(conn: DbConnectionProtocol, sql_path: Path) -> None:
    """Execute semicolon-delimited SQL statements from a script file.

    Args:
        conn: Active database connection.
        sql_path: Path to the ``.sql`` script file.
    """
    raw_sql = sql_path.read_text(encoding="utf-8")
    lines = [line for line in raw_sql.splitlines() if not line.strip().startswith("--")]
    cleaned = "\n".join(lines)
    cursor = conn.cursor()
    try:
        for statement in cleaned.split(";"):
            stmt = statement.strip()
            if not stmt:
                continue
            if conn.dialect == "sqlite" and stmt.upper().startswith("USE "):
                continue
            cursor.execute(stmt)
        conn.commit()
    finally:
        cursor.close()


def initialize_sqlite_test_schema(conn: SqliteConnection) -> None:
    """Create the Silver/Operational/Gold tables in an in-memory SQLite DB.

    Args:
        conn: Open ``SqliteConnection`` instance for testing.
    """
    ddl_statements = (
        """
        CREATE TABLE IF NOT EXISTS source_metadata (
            source_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL UNIQUE,
            license TEXT NOT NULL,
            url TEXT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id TEXT PRIMARY KEY,
            dag_id TEXT NOT NULL,
            source_id INTEGER NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT NULL,
            status TEXT NOT NULL,
            rows_read INTEGER NOT NULL DEFAULT 0,
            rows_inserted INTEGER NOT NULL DEFAULT 0,
            rows_updated INTEGER NOT NULL DEFAULT 0,
            rows_unchanged INTEGER NOT NULL DEFAULT 0,
            rows_quarantined INTEGER NOT NULL DEFAULT 0,
            rows_warned INTEGER NOT NULL DEFAULT 0,
            quarantine_rate TEXT NOT NULL DEFAULT '0.0000'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ingestion_batches (
            batch_id TEXT PRIMARY KEY,
            source_id INTEGER NOT NULL,
            run_id TEXT NOT NULL,
            source_version TEXT NULL,
            source_updated_at TEXT NULL,
            file_checksum TEXT NOT NULL,
            file_path TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            ingested_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS data_quality_issues (
            issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            source_record_id TEXT NULL,
            rule_name TEXT NOT NULL,
            severity TEXT NOT NULL,
            reason TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            detected_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS countries (
            country_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_country_code INTEGER NOT NULL UNIQUE,
            country_name TEXT NOT NULL UNIQUE,
            iso_code TEXT NOT NULL,
            currency_code TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cities (
            city_id INTEGER PRIMARY KEY AUTOINCREMENT,
            country_id INTEGER NOT NULL,
            city_name TEXT NOT NULL,
            UNIQUE (country_id, city_name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS locations (
            location_id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id INTEGER NOT NULL,
            locality TEXT NOT NULL,
            UNIQUE (city_id, locality)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cuisines (
            cuisine_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cuisine_name TEXT NOT NULL UNIQUE,
            cuisine_group TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS restaurants (
            restaurant_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_restaurant_id TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            batch_id TEXT NOT NULL,
            last_seen_batch_id TEXT NOT NULL,
            name TEXT NOT NULL,
            location_id INTEGER NOT NULL,
            address TEXT NULL,
            latitude TEXT NULL,
            longitude TEXT NULL,
            avg_cost_for_two TEXT NULL,
            currency_code TEXT NOT NULL,
            avg_cost_for_two_usd TEXT NULL,
            fx_rate TEXT NULL,
            fx_rate_date TEXT NULL,
            price_range INTEGER NOT NULL,
            rating TEXT NULL,
            rating_color TEXT NULL,
            rating_text TEXT NULL,
            votes INTEGER NOT NULL DEFAULT 0,
            has_table_booking INTEGER NOT NULL DEFAULT 0,
            has_online_delivery INTEGER NOT NULL DEFAULT 0,
            is_delivering_now INTEGER NOT NULL DEFAULT 0,
            switch_to_order_menu INTEGER NOT NULL DEFAULT 0,
            match_group_id INTEGER NULL,
            record_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (source_id, source_restaurant_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS restaurant_cuisines (
            restaurant_id INTEGER NOT NULL,
            cuisine_id INTEGER NOT NULL,
            PRIMARY KEY (restaurant_id, cuisine_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS gold_map_points (
            restaurant_id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            country_name TEXT NOT NULL,
            city_name TEXT NOT NULL,
            locality TEXT NOT NULL,
            cuisines TEXT NULL,
            price_range INTEGER NOT NULL,
            rating TEXT NULL,
            votes INTEGER NOT NULL DEFAULT 0,
            avg_cost_for_two TEXT NULL,
            currency_code TEXT NOT NULL,
            avg_cost_for_two_usd TEXT NULL,
            latitude TEXT NOT NULL,
            longitude TEXT NOT NULL,
            location TEXT NOT NULL
        )
        """,
    )
    cursor = conn.cursor()
    try:
        for stmt in ddl_statements:
            cursor.execute(stmt)
        cursor.execute(
            """
            INSERT OR IGNORE INTO source_metadata (source_id, source_name, license, url)
            VALUES (%(source_id)s, %(source_name)s, %(license)s, %(url)s)
            """,
            {
                "source_id": 1,
                "source_name": DEFAULT_ZOMATO_SOURCE_NAME,
                "license": "CC0 1.0",
                "url": "https://www.kaggle.com/datasets/shrutimehta/zomato-restaurants-data",
            },
        )
        conn.commit()
    finally:
        cursor.close()
