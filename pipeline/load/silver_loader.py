"""Incremental Silver-layer upsert on ``(source_id, source_restaurant_id)``."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pipeline.constants import DEFAULT_SQL_BATCH_SIZE
from pipeline.load.db import DbConnectionProtocol, DbCursorProtocol
from pipeline.transform.standardize import StandardizedRestaurant

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SilverUpsertStats:
    """Counters returned by an incremental Silver batch load."""

    rows_inserted: int
    rows_updated: int
    rows_unchanged: int


def _to_db_datetime(dt: datetime, dialect: str) -> object:
    if dialect == "sqlite":
        return dt.isoformat()
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _sync_countries(
    cursor: DbCursorProtocol,
    dialect: str,
    records: Sequence[StandardizedRestaurant],
) -> dict[int, int]:
    unique_countries: dict[int, tuple[str, str, str]] = {}
    for rec in records:
        unique_countries[rec.source_country_code] = (
            rec.country_name,
            rec.iso_code,
            rec.currency_code,
        )

    insert_sql = (
        """
        INSERT OR IGNORE INTO countries (
            source_country_code, country_name, iso_code, currency_code
        )
        VALUES (
            %(source_country_code)s, %(country_name)s, %(iso_code)s, %(currency_code)s
        )
        """
        if dialect == "sqlite"
        else """
        INSERT IGNORE INTO countries (
            source_country_code, country_name, iso_code, currency_code
        )
        VALUES (
            %(source_country_code)s, %(country_name)s, %(iso_code)s, %(currency_code)s
        )
        """
    )
    params = [
        {
            "source_country_code": code,
            "country_name": meta[0],
            "iso_code": meta[1],
            "currency_code": meta[2],
        }
        for code, meta in unique_countries.items()
    ]
    if params:
        cursor.executemany(insert_sql, params)

    cursor.execute("SELECT country_id, source_country_code FROM countries")
    return {
        int(str(row["source_country_code"])): int(str(row["country_id"]))
        for row in cursor.fetchall()
    }


def _sync_cities(
    cursor: DbCursorProtocol,
    dialect: str,
    records: Sequence[StandardizedRestaurant],
    country_map: dict[int, int],
) -> dict[tuple[int, str], int]:
    pairs = {(country_map[rec.source_country_code], rec.city_name) for rec in records}
    insert_sql = (
        """
        INSERT OR IGNORE INTO cities (country_id, city_name)
        VALUES (%(country_id)s, %(city_name)s)
        """
        if dialect == "sqlite"
        else """
        INSERT IGNORE INTO cities (country_id, city_name)
        VALUES (%(country_id)s, %(city_name)s)
        """
    )
    params = [
        {"country_id": country_id, "city_name": city_name}
        for country_id, city_name in pairs
    ]
    if params:
        cursor.executemany(insert_sql, params)

    cursor.execute("SELECT city_id, country_id, city_name FROM cities")
    return {
        (int(str(row["country_id"])), str(row["city_name"])): int(str(row["city_id"]))
        for row in cursor.fetchall()
    }


def _sync_locations(
    cursor: DbCursorProtocol,
    dialect: str,
    records: Sequence[StandardizedRestaurant],
    country_map: dict[int, int],
    city_map: dict[tuple[int, str], int],
) -> dict[tuple[int, str], int]:
    pairs = {
        (
            city_map[(country_map[rec.source_country_code], rec.city_name)],
            rec.locality,
        )
        for rec in records
    }
    insert_sql = (
        """
        INSERT OR IGNORE INTO locations (city_id, locality)
        VALUES (%(city_id)s, %(locality)s)
        """
        if dialect == "sqlite"
        else """
        INSERT IGNORE INTO locations (city_id, locality)
        VALUES (%(city_id)s, %(locality)s)
        """
    )
    params = [{"city_id": city_id, "locality": locality} for city_id, locality in pairs]
    if params:
        cursor.executemany(insert_sql, params)

    cursor.execute("SELECT location_id, city_id, locality FROM locations")
    return {
        (int(str(row["city_id"])), str(row["locality"])): int(str(row["location_id"]))
        for row in cursor.fetchall()
    }


def _sync_cuisines(
    cursor: DbCursorProtocol,
    dialect: str,
    records: Sequence[StandardizedRestaurant],
) -> dict[str, int]:
    unique_cuisines: dict[str, str] = {}
    for rec in records:
        for mapping in rec.cuisines:
            unique_cuisines[mapping.cuisine_name] = mapping.cuisine_group

    insert_sql = (
        """
        INSERT OR IGNORE INTO cuisines (cuisine_name, cuisine_group)
        VALUES (%(cuisine_name)s, %(cuisine_group)s)
        """
        if dialect == "sqlite"
        else """
        INSERT IGNORE INTO cuisines (cuisine_name, cuisine_group)
        VALUES (%(cuisine_name)s, %(cuisine_group)s)
        """
    )
    params = [
        {"cuisine_name": name, "cuisine_group": group}
        for name, group in unique_cuisines.items()
    ]
    if params:
        cursor.executemany(insert_sql, params)

    cursor.execute("SELECT cuisine_id, cuisine_name FROM cuisines")
    return {
        str(row["cuisine_name"]): int(str(row["cuisine_id"]))
        for row in cursor.fetchall()
    }


def _restaurant_row_params(
    rec: StandardizedRestaurant,
    *,
    location_id: int,
    batch_id: str,
    updated_at_val: object,
) -> dict[str, object]:
    return {
        "source_restaurant_id": rec.source_restaurant_id,
        "source_id": rec.source_id,
        "batch_id": batch_id,
        "last_seen_batch_id": batch_id,
        "name": rec.name,
        "location_id": location_id,
        "address": rec.address,
        "latitude": rec.latitude,
        "longitude": rec.longitude,
        "avg_cost_for_two": rec.avg_cost_for_two,
        "currency_code": rec.currency_code,
        "avg_cost_for_two_usd": rec.avg_cost_for_two_usd,
        "fx_rate": rec.fx_rate,
        "fx_rate_date": rec.fx_rate_date,
        "price_range": rec.price_range,
        "rating": rec.rating,
        "rating_color": rec.rating_color,
        "rating_text": rec.rating_text,
        "votes": rec.votes,
        "has_table_booking": rec.has_table_booking,
        "has_online_delivery": rec.has_online_delivery,
        "is_delivering_now": rec.is_delivering_now,
        "switch_to_order_menu": rec.switch_to_order_menu,
        "record_hash": rec.record_hash,
        "updated_at": updated_at_val,
    }


def _replace_restaurant_cuisines(
    cursor: DbCursorProtocol,
    *,
    restaurant_ids: Sequence[int],
    cuisine_links: Sequence[tuple[int, int]],
) -> None:
    if restaurant_ids:
        delete_sql = """
            DELETE FROM restaurant_cuisines
            WHERE restaurant_id = %(restaurant_id)s
        """
        cursor.executemany(
            delete_sql, [{"restaurant_id": rid} for rid in restaurant_ids]
        )
    if cuisine_links:
        insert_sql = """
            INSERT INTO restaurant_cuisines (restaurant_id, cuisine_id)
            VALUES (%(restaurant_id)s, %(cuisine_id)s)
        """
        params = [
            {"restaurant_id": rid, "cuisine_id": cid} for rid, cid in cuisine_links
        ]
        for idx in range(0, len(params), DEFAULT_SQL_BATCH_SIZE):
            cursor.executemany(insert_sql, params[idx : idx + DEFAULT_SQL_BATCH_SIZE])


def upsert_silver_batch(
    conn: DbConnectionProtocol,
    *,
    records: Sequence[StandardizedRestaurant],
    batch_id: str,
    updated_at: datetime,
) -> SilverUpsertStats:
    """Incrementally upsert Silver restaurants using ``record_hash`` comparison.

    New records are inserted, records with a changed ``record_hash`` are updated
    along with their cuisine links, and unchanged records only advance
    ``last_seen_batch_id`` without rewriting business columns.

    Args:
        conn: Active database connection.
        records: Validated and standardized Silver records.
        batch_id: Current ingestion batch UUID.
        updated_at: UTC timestamp for new or modified rows.

    Returns:
        ``SilverUpsertStats`` with ``rows_inserted``, ``rows_updated``, and
        ``rows_unchanged``.
    """
    if not records:
        return SilverUpsertStats(rows_inserted=0, rows_updated=0, rows_unchanged=0)

    source_ids = {rec.source_id for rec in records}
    if len(source_ids) != 1:
        raise ValueError("upsert_silver_batch expects records from exactly one source")
    source_id = next(iter(source_ids))

    updated_at_val = _to_db_datetime(updated_at, conn.dialect)
    cursor = conn.cursor()
    try:
        country_map = _sync_countries(cursor, conn.dialect, records)
        city_map = _sync_cities(cursor, conn.dialect, records, country_map)
        location_map = _sync_locations(
            cursor, conn.dialect, records, country_map, city_map
        )
        cuisine_map = _sync_cuisines(cursor, conn.dialect, records)

        cursor.execute(
            """
            SELECT restaurant_id, source_restaurant_id, record_hash
            FROM restaurants
            WHERE source_id = %(source_id)s
            """,
            {"source_id": source_id},
        )
        existing: dict[str, tuple[int, str]] = {
            str(row["source_restaurant_id"]): (
                int(str(row["restaurant_id"])),
                str(row["record_hash"]),
            )
            for row in cursor.fetchall()
        }

        to_insert: list[StandardizedRestaurant] = []
        to_update: list[tuple[int, StandardizedRestaurant]] = []
        unchanged_ids: list[int] = []

        for rec in records:
            prior = existing.get(rec.source_restaurant_id)
            if prior is None:
                to_insert.append(rec)
            elif prior[1] == rec.record_hash:
                unchanged_ids.append(prior[0])
            else:
                to_update.append((prior[0], rec))

        if unchanged_ids:
            bump_sql = """
                UPDATE restaurants
                SET last_seen_batch_id = %(last_seen_batch_id)s
                WHERE restaurant_id = %(restaurant_id)s
            """
            bump_params = [
                {"restaurant_id": rid, "last_seen_batch_id": batch_id}
                for rid in unchanged_ids
            ]
            for idx in range(0, len(bump_params), DEFAULT_SQL_BATCH_SIZE):
                cursor.executemany(
                    bump_sql, bump_params[idx : idx + DEFAULT_SQL_BATCH_SIZE]
                )

        if to_insert:
            insert_sql = """
                INSERT INTO restaurants (
                    source_restaurant_id, source_id, batch_id, last_seen_batch_id,
                    name, location_id, address, latitude, longitude,
                    avg_cost_for_two, currency_code, avg_cost_for_two_usd,
                    fx_rate, fx_rate_date, price_range, rating, rating_color,
                    rating_text, votes, has_table_booking, has_online_delivery,
                    is_delivering_now, switch_to_order_menu, record_hash, updated_at
                )
                VALUES (
                    %(source_restaurant_id)s, %(source_id)s, %(batch_id)s,
                    %(last_seen_batch_id)s, %(name)s, %(location_id)s, %(address)s,
                    %(latitude)s, %(longitude)s, %(avg_cost_for_two)s,
                    %(currency_code)s, %(avg_cost_for_two_usd)s, %(fx_rate)s,
                    %(fx_rate_date)s, %(price_range)s, %(rating)s, %(rating_color)s,
                    %(rating_text)s, %(votes)s, %(has_table_booking)s,
                    %(has_online_delivery)s, %(is_delivering_now)s,
                    %(switch_to_order_menu)s, %(record_hash)s, %(updated_at)s
                )
            """
            insert_params = [
                _restaurant_row_params(
                    rec,
                    location_id=location_map[
                        (
                            city_map[
                                (country_map[rec.source_country_code], rec.city_name)
                            ],
                            rec.locality,
                        )
                    ],
                    batch_id=batch_id,
                    updated_at_val=updated_at_val,
                )
                for rec in to_insert
            ]
            for idx in range(0, len(insert_params), DEFAULT_SQL_BATCH_SIZE):
                cursor.executemany(
                    insert_sql, insert_params[idx : idx + DEFAULT_SQL_BATCH_SIZE]
                )

        if to_update:
            update_sql = """
                UPDATE restaurants
                SET
                    batch_id = %(batch_id)s,
                    last_seen_batch_id = %(last_seen_batch_id)s,
                    name = %(name)s,
                    location_id = %(location_id)s,
                    address = %(address)s,
                    latitude = %(latitude)s,
                    longitude = %(longitude)s,
                    avg_cost_for_two = %(avg_cost_for_two)s,
                    currency_code = %(currency_code)s,
                    avg_cost_for_two_usd = %(avg_cost_for_two_usd)s,
                    fx_rate = %(fx_rate)s,
                    fx_rate_date = %(fx_rate_date)s,
                    price_range = %(price_range)s,
                    rating = %(rating)s,
                    rating_color = %(rating_color)s,
                    rating_text = %(rating_text)s,
                    votes = %(votes)s,
                    has_table_booking = %(has_table_booking)s,
                    has_online_delivery = %(has_online_delivery)s,
                    is_delivering_now = %(is_delivering_now)s,
                    switch_to_order_menu = %(switch_to_order_menu)s,
                    record_hash = %(record_hash)s,
                    updated_at = %(updated_at)s
                WHERE restaurant_id = %(restaurant_id)s
            """
            update_params = []
            for rid, rec in to_update:
                row_param = _restaurant_row_params(
                    rec,
                    location_id=location_map[
                        (
                            city_map[
                                (country_map[rec.source_country_code], rec.city_name)
                            ],
                            rec.locality,
                        )
                    ],
                    batch_id=batch_id,
                    updated_at_val=updated_at_val,
                )
                row_param["restaurant_id"] = rid
                update_params.append(row_param)
            for idx in range(0, len(update_params), DEFAULT_SQL_BATCH_SIZE):
                cursor.executemany(
                    update_sql, update_params[idx : idx + DEFAULT_SQL_BATCH_SIZE]
                )

        changed_records = list(to_insert) + [rec for _, rec in to_update]
        if changed_records:
            cursor.execute(
                """
                SELECT restaurant_id, source_restaurant_id
                FROM restaurants
                WHERE source_id = %(source_id)s
                """,
                {"source_id": source_id},
            )
            id_by_source_key = {
                str(row["source_restaurant_id"]): int(str(row["restaurant_id"]))
                for row in cursor.fetchall()
            }
            changed_rids: list[int] = []
            cuisine_links: list[tuple[int, int]] = []
            for rec in changed_records:
                rid = id_by_source_key[rec.source_restaurant_id]
                changed_rids.append(rid)
                for mapping in rec.cuisines:
                    cuisine_links.append((rid, cuisine_map[mapping.cuisine_name]))
            _replace_restaurant_cuisines(
                cursor,
                restaurant_ids=changed_rids,
                cuisine_links=cuisine_links,
            )

        conn.commit()
        stats = SilverUpsertStats(
            rows_inserted=len(to_insert),
            rows_updated=len(to_update),
            rows_unchanged=len(unchanged_ids),
        )
        logger.info(
            "Silver upsert complete: inserted=%d updated=%d unchanged=%d",
            stats.rows_inserted,
            stats.rows_updated,
            stats.rows_unchanged,
            extra={"batch_id": batch_id, "source_id": source_id},
        )
        return stats
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
