"""Gold spatial table refresh and Gold analytical view deployment."""

import logging
from pathlib import Path

from pipeline.constants import (
    MAX_ABS_LONGITUDE,
    MAX_MAP_LATITUDE,
    MAX_VARCHAR_CUISINES_LIST,
)
from pipeline.load.db import DbConnectionProtocol, execute_sql_script
from pipeline.settings import DEFAULT_GOLD_VIEWS_SQL_PATH

logger = logging.getLogger(__name__)


def refresh_gold_layer(
    conn: DbConnectionProtocol,
    *,
    source_id: int,
    gold_views_sql_path: Path | None = None,
) -> int:
    """Rebuild ``gold_map_points`` for ``source_id`` and ensure Gold views exist.

    Rows without valid coordinates or with ``|latitude| > MAX_MAP_LATITUDE`` are
    excluded from ``gold_map_points``. On MySQL, spatial points are constructed
    via ``ST_SRID(POINT(longitude, latitude), 4326)`` and
    ``sql/002_create_gold_views.sql`` is executed.

    Args:
        conn: Active database connection.
        source_id: Numeric source ID whose map points are refreshed.
        gold_views_sql_path: Optional override path for the Gold views SQL script.

    Returns:
        Total number of rows stored in ``gold_map_points`` for ``source_id``.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            DELETE FROM gold_map_points
            WHERE source_id = %(source_id)s
            """,
            {"source_id": source_id},
        )

        if conn.dialect == "mysql":
            cursor.execute(
                """
                INSERT INTO gold_map_points (
                    restaurant_id, source_id, name, country_name, city_name,
                    locality, cuisines, price_range, rating, votes,
                    avg_cost_for_two, currency_code, avg_cost_for_two_usd,
                    latitude, longitude, location
                )
                SELECT
                    r.restaurant_id,
                    r.source_id,
                    r.name,
                    co.country_name,
                    ci.city_name,
                    l.locality,
                    LEFT(
                        GROUP_CONCAT(
                            DISTINCT c.cuisine_name
                            ORDER BY c.cuisine_name
                            SEPARATOR ', '
                        ),
                        %(max_cuisines_len)s
                    ) AS cuisines,
                    r.price_range,
                    r.rating,
                    r.votes,
                    r.avg_cost_for_two,
                    r.currency_code,
                    r.avg_cost_for_two_usd,
                    r.latitude,
                    r.longitude,
                    ST_SRID(POINT(r.longitude, r.latitude), 4326) AS location
                FROM restaurants AS r
                JOIN locations AS l ON l.location_id = r.location_id
                JOIN cities AS ci ON ci.city_id = l.city_id
                JOIN countries AS co ON co.country_id = ci.country_id
                LEFT JOIN restaurant_cuisines AS rc
                    ON rc.restaurant_id = r.restaurant_id
                LEFT JOIN cuisines AS c ON c.cuisine_id = rc.cuisine_id
                WHERE r.source_id = %(source_id)s
                  AND r.latitude IS NOT NULL
                  AND r.longitude IS NOT NULL
                  AND ABS(r.latitude) <= %(max_map_lat)s
                  AND ABS(r.longitude) <= %(max_abs_lng)s
                GROUP BY
                    r.restaurant_id,
                    r.source_id,
                    r.name,
                    co.country_name,
                    ci.city_name,
                    l.locality,
                    r.price_range,
                    r.rating,
                    r.votes,
                    r.avg_cost_for_two,
                    r.currency_code,
                    r.avg_cost_for_two_usd,
                    r.latitude,
                    r.longitude
                """,
                {
                    "source_id": source_id,
                    "max_cuisines_len": MAX_VARCHAR_CUISINES_LIST,
                    "max_map_lat": MAX_MAP_LATITUDE,
                    "max_abs_lng": MAX_ABS_LONGITUDE,
                },
            )
        else:
            cursor.execute(
                """
                SELECT
                    r.restaurant_id,
                    r.source_id,
                    r.name,
                    co.country_name,
                    ci.city_name,
                    l.locality,
                    GROUP_CONCAT(c.cuisine_name, ', ') AS cuisines,
                    r.price_range,
                    r.rating,
                    r.votes,
                    r.avg_cost_for_two,
                    r.currency_code,
                    r.avg_cost_for_two_usd,
                    r.latitude,
                    r.longitude
                FROM restaurants AS r
                JOIN locations AS l ON l.location_id = r.location_id
                JOIN cities AS ci ON ci.city_id = l.city_id
                JOIN countries AS co ON co.country_id = ci.country_id
                LEFT JOIN restaurant_cuisines AS rc
                    ON rc.restaurant_id = r.restaurant_id
                LEFT JOIN cuisines AS c ON c.cuisine_id = rc.cuisine_id
                WHERE r.source_id = %(source_id)s
                  AND r.latitude IS NOT NULL
                  AND r.longitude IS NOT NULL
                  AND ABS(CAST(r.latitude AS REAL)) <= %(max_map_lat)s
                  AND ABS(CAST(r.longitude AS REAL)) <= %(max_abs_lng)s
                GROUP BY r.restaurant_id
                """,
                {
                    "source_id": source_id,
                    "max_map_lat": MAX_MAP_LATITUDE,
                    "max_abs_lng": MAX_ABS_LONGITUDE,
                },
            )
            point_rows = cursor.fetchall()
            insert_sqlite = """
                INSERT INTO gold_map_points (
                    restaurant_id, source_id, name, country_name, city_name,
                    locality, cuisines, price_range, rating, votes,
                    avg_cost_for_two, currency_code, avg_cost_for_two_usd,
                    latitude, longitude, location
                )
                VALUES (
                    %(restaurant_id)s, %(source_id)s, %(name)s, %(country_name)s,
                    %(city_name)s, %(locality)s, %(cuisines)s, %(price_range)s,
                    %(rating)s, %(votes)s, %(avg_cost_for_two)s, %(currency_code)s,
                    %(avg_cost_for_two_usd)s, %(latitude)s, %(longitude)s, %(location)s
                )
            """
            sqlite_params = []
            for row in point_rows:
                cuisines_raw = row["cuisines"]
                cuisines_val = (
                    str(cuisines_raw)[:MAX_VARCHAR_CUISINES_LIST]
                    if cuisines_raw is not None
                    else None
                )
                sqlite_params.append(
                    {
                        "restaurant_id": row["restaurant_id"],
                        "source_id": row["source_id"],
                        "name": row["name"],
                        "country_name": row["country_name"],
                        "city_name": row["city_name"],
                        "locality": row["locality"],
                        "cuisines": cuisines_val,
                        "price_range": row["price_range"],
                        "rating": row["rating"],
                        "votes": row["votes"],
                        "avg_cost_for_two": row["avg_cost_for_two"],
                        "currency_code": row["currency_code"],
                        "avg_cost_for_two_usd": row["avg_cost_for_two_usd"],
                        "latitude": row["latitude"],
                        "longitude": row["longitude"],
                        "location": f"POINT({row['longitude']} {row['latitude']})",
                    }
                )
            if sqlite_params:
                cursor.executemany(insert_sqlite, sqlite_params)

        cursor.execute(
            """
            SELECT COUNT(*) AS total_points
            FROM gold_map_points
            WHERE source_id = %(source_id)s
            """,
            {"source_id": source_id},
        )
        count_row = cursor.fetchone()
        conn.commit()
        total_points = int(str(count_row["total_points"])) if count_row else 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()

    if conn.dialect == "mysql":
        views_path = (
            gold_views_sql_path
            if gold_views_sql_path is not None
            else DEFAULT_GOLD_VIEWS_SQL_PATH
        )
        if views_path.is_file():
            execute_sql_script(conn, views_path)

    logger.info(
        "Refreshed Gold map points: total=%d",
        total_points,
        extra={"source_id": source_id},
    )
    return total_points
