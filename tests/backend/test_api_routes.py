"""FastAPI route, error handling, telemetry, and PyMySQL repository tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from unittest.mock import MagicMock

import pymysql
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from web.backend.constants import GOLD_MAX_AGE_DAYS, QUERY_LOG_MAX_CHARS
from web.backend.main import create_app
from web.backend.repositories.db import DictCursorConnection, get_db_connection
from web.backend.repositories.restaurant_repository import (
    RestaurantFilter,
    RestaurantRepository,
)
from web.backend.schemas.pipeline import PipelineRunOut, QualityRuleCountOut
from web.backend.services.pipeline_service import PipelineService
from web.backend.settings import BackendSettings


def test_health_endpoint(api_client: TestClient) -> None:
    response = api_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_restaurants_filters_sorting_and_domain_rules(
    api_client: TestClient,
) -> None:
    all_resp = api_client.get("/api/restaurants", params={"limit": 50})
    assert all_resp.status_code == 200
    payload = all_resp.json()
    assert payload["total"] == 7
    assert len(payload["items"]) == 7

    # Unrated restaurant preserves rating=None (never 0) and zero cost -> None
    unrated = next(item for item in payload["items"] if item["restaurant_id"] == 1003)
    assert unrated["rating"] is None
    assert unrated["rating_text"] == "Not rated"
    assert unrated["avg_cost_for_two"] is None
    assert unrated["avg_cost_for_two_usd"] is None
    assert unrated["latitude"] is None
    assert unrated["longitude"] is None
    assert unrated["cuisines"] == ["Bakery", "Coffee & Tea"]

    # Unrated sorts last when sort_by=rating
    assert payload["items"][-1]["restaurant_id"] == 1003

    # Mojibake repaired and currency derived from country code (162 -> PHP, not Pula)
    istanbul = next(item for item in payload["items"] if item["restaurant_id"] == 1002)
    assert istanbul["city_name"] == "İstanbul"
    assert "Turkish" in istanbul["cuisines"]

    manila = next(item for item in payload["items"] if item["restaurant_id"] == 1007)
    assert manila["currency_code"] == "PHP"
    assert "Malaysian" in manila["cuisines"]

    # Multi-filter query
    filtered = api_client.get(
        "/api/restaurants",
        params={
            "country": "India",
            "city": "New Delhi",
            "cuisine": ["Italian"],
            "min_rating": 4.2,
            "has_online_delivery": True,
        },
    )
    assert filtered.status_code == 200
    filtered_data = filtered.json()
    assert filtered_data["total"] == 1
    assert filtered_data["items"][0]["name"] == "Pasta Palace"


def test_restaurant_detail_and_not_found(api_client: TestClient) -> None:
    detail_resp = api_client.get("/api/restaurants/1001")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["restaurant"]["name"] == "Pasta Palace"
    assert any(item["restaurant_id"] == 1005 for item in detail["nearby"])
    assert all(item["distance_m"] is not None for item in detail["nearby"])
    assert any(item["restaurant_id"] == 1005 for item in detail["similar"])

    missing_resp = api_client.get("/api/restaurants/999999")
    assert missing_resp.status_code == 404
    err = missing_resp.json()
    assert err["error_code"] == "not_found"


def test_map_points_excludes_zero_coords_and_filters_radius(
    api_client: TestClient,
) -> None:
    all_points = api_client.get("/api/map/points")
    assert all_points.status_code == 200
    data = all_points.json()
    assert data["total"] == 6
    assert all(pt["restaurant_id"] != 1003 for pt in data["items"])

    nearby_points = api_client.get(
        "/api/map/points",
        params={"latitude": 28.631451, "longitude": 77.216721, "radius_m": 1000},
    )
    assert nearby_points.status_code == 200
    nearby_data = nearby_points.json()
    ids = {pt["restaurant_id"] for pt in nearby_data["items"]}
    assert ids == {1001, 1005}
    assert all(pt["distance_m"] <= 1000.0 for pt in nearby_data["items"])

    partial_spatial = api_client.get(
        "/api/map/points",
        params={"latitude": 28.63},
    )
    assert partial_spatial.status_code == 422
    assert partial_spatial.json()["error_code"] == "validation_error"


def test_nl_search_endpoint_validation_logging_and_rate_limit(
    test_settings: BackendSettings,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import web.backend.dependencies as deps_mod

    tight_settings = test_settings.model_copy(
        update={"backend_nlp_rate_limit_per_minute": 2}
    )
    monkeypatch.setattr(deps_mod, "settings", tight_settings)
    app = create_app(tight_settings)

    def _override_db() -> Generator[None, None, None]:
        yield None

    app.dependency_overrides[get_db_connection] = _override_db

    with TestClient(app) as client:
        capsys.readouterr()
        long_query = "Italian in New Delhi above 4.2 " + ("a" * 300)
        ok_resp = client.post("/api/search/nl", json={"query": long_query})
        assert ok_resp.status_code == 200
        body = ok_resp.json()
        assert body["parser_used"] == "rule_based"
        assert body["fallback_used"] is True
        assert body["interpreted_params"]["city"] == "New Delhi"
        assert body["total"] == 1

        stdout_lines = capsys.readouterr().out.splitlines()
        parsed_logs = [
            json.loads(line) for line in stdout_lines if line.startswith("{")
        ]
        logged_previews = [
            str(entry["query_preview"])
            for entry in parsed_logs
            if "query_preview" in entry
        ]
        assert logged_previews
        assert len(logged_previews[-1]) == QUERY_LOG_MAX_CHARS

        # Validation 422 on > 500 chars
        too_long = client.post("/api/search/nl", json={"query": "x" * 501})
        assert too_long.status_code == 422
        assert too_long.json()["error_code"] == "validation_error"

        # Second valid request hits limit=2
        second_ok = client.post("/api/search/nl", json={"query": "British in London"})
        assert second_ok.status_code == 200

        # Third request triggers 429 rate limit
        rate_limited = client.post(
            "/api/search/nl", json={"query": "British in London"}
        )
        assert rate_limited.status_code == 429
        assert rate_limited.json()["error_code"] == "rate_limit_exceeded"


def test_meta_and_destination_endpoints(api_client: TestClient) -> None:
    countries = api_client.get("/api/meta/countries").json()
    assert len(countries["items"]) == 4

    cities = api_client.get("/api/meta/cities", params={"country": "India"}).json()
    assert [c["city_name"] for c in cities["items"]] == ["New Delhi"]

    cuisines = api_client.get("/api/meta/cuisines").json()
    assert any(c["cuisine_name"] == "Turkish" for c in cuisines["items"])

    analytics = api_client.get("/api/meta/analytics").json()
    assert analytics["total_restaurants"] == 7
    assert analytics["rated_count"] == 6
    assert analytics["unrated_count"] == 1
    assert analytics["geolocated_count"] == 6

    dest = api_client.get("/api/meta/destinations/India")
    assert dest.status_code == 200
    dest_json = dest.json()
    assert dest_json["currency_code"] == "INR"
    assert dest_json["restaurant_count"] == 4
    assert len(dest_json["top_restaurants"]) == 4

    missing_dest = api_client.get("/api/meta/destinations/Narnia")
    assert missing_dest.status_code == 404
    assert missing_dest.json()["error_code"] == "not_found"


def test_pipeline_status_endpoint_and_staleness_logic(
    api_client: TestClient,
    test_settings: BackendSettings,
) -> None:
    status_resp = api_client.get("/api/pipeline/status")
    assert status_resp.status_code == 200
    payload = status_resp.json()
    assert payload["data_mode"] == "local_csv_fallback"
    assert payload["gold_max_age_days"] == GOLD_MAX_AGE_DAYS
    assert payload["is_stale"] is False
    assert payload["latest_run"]["status"] == "success"
    assert len(payload["quality_breakdown"]) >= 1

    # Verify staleness calculation for >7 days vs skipped_unchanged <=7 days
    stale_ts = datetime.now(UTC) - timedelta(days=8)
    fresh_skipped_ts = datetime.now(UTC) - timedelta(days=2)

    class _StubRepo:
        def __init__(self, runs: list[PipelineRunOut]) -> None:
            self._runs = runs

        def get_telemetry(
            self,
        ) -> tuple[
            list[PipelineRunOut],
            list[QualityRuleCountOut],
            Literal["mysql", "local_csv_fallback"],
        ]:
            return self._runs, [], "mysql"

    stale_run = PipelineRunOut(
        run_id="r1",
        dag_id="zomato_weekly_etl",
        source_id=1,
        source_name="zomato",
        started_at=stale_ts,
        ended_at=stale_ts,
        status="success",
        rows_read=10,
        rows_inserted=10,
        rows_updated=0,
        rows_unchanged=0,
        rows_quarantined=0,
        rows_warned=0,
        quarantine_rate=Decimal("0.0000"),
    )
    stale_out = PipelineService(_StubRepo([stale_run]), test_settings).get_status()  # type: ignore[arg-type]
    assert stale_out.is_stale is True

    skipped_run = stale_run.model_copy(
        update={
            "run_id": "r2",
            "status": "skipped_unchanged",
            "started_at": fresh_skipped_ts,
            "ended_at": fresh_skipped_ts,
        }
    )
    fresh_out = PipelineService(_StubRepo([skipped_run]), test_settings).get_status()  # type: ignore[arg-type]
    assert fresh_out.is_stale is False


def test_ci_db_failure_raises_503(
    test_settings: BackendSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import web.backend.repositories.db as db_mod

    ci_settings = test_settings.model_copy(update={"app_env": "ci"})
    monkeypatch.setattr(db_mod, "settings", ci_settings)

    def fail_connect(_settings: BackendSettings) -> DictCursorConnection:
        raise pymysql.OperationalError(2003, "Can't connect to MySQL")

    monkeypatch.setattr(db_mod, "open_mysql_connection", fail_connect)

    app = create_app(ci_settings)
    with TestClient(app) as client:
        resp = client.get("/api/restaurants")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "service_unavailable"


def test_settings_fail_fast_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYSQL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("HF_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        BackendSettings(_env_file=None)  # type: ignore[call-arg]


def test_openapi_schema_contains_all_routes(api_client: TestClient) -> None:
    resp = api_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    expected_paths = {
        "/api/health",
        "/api/restaurants",
        "/api/restaurants/{restaurant_id}",
        "/api/map/points",
        "/api/search/nl",
        "/api/meta/countries",
        "/api/meta/cities",
        "/api/meta/cuisines",
        "/api/meta/analytics",
        "/api/meta/destinations/{country}",
        "/api/pipeline/status",
    }
    assert expected_paths.issubset(set(paths.keys()))


def test_mysql_repository_executes_parameterized_queries(
    test_settings: BackendSettings,
) -> None:
    fake_cursor = MagicMock()
    fake_cursor.__enter__.return_value = fake_cursor
    fake_cursor.fetchone.return_value = {"total_count": 1}
    fake_cursor.fetchall.return_value = [
        {
            "restaurant_id": 1001,
            "source_restaurant_id": "1001",
            "source_name": "zomato",
            "source_license": "CC0 1.0",
            "name": "Pasta Palace",
            "country_name": "India",
            "iso_code": "IN",
            "city_name": "New Delhi",
            "locality": "Connaught Place",
            "address": "12 Connaught Place",
            "latitude": Decimal("28.631451"),
            "longitude": Decimal("77.216721"),
            "cuisines": "Italian, Pizza",
            "cuisine_groups": "Dish and Format, European",
            "avg_cost_for_two": Decimal("1200.00"),
            "currency_code": "INR",
            "avg_cost_for_two_usd": Decimal("14.40"),
            "price_range": 2,
            "rating": Decimal("4.5"),
            "rating_text": "Excellent",
            "votes": 320,
            "has_table_booking": 1,
            "has_online_delivery": 1,
        }
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    repo = RestaurantRepository(fake_conn, test_settings)
    items, total = repo.search_restaurants(
        RestaurantFilter(country="India", cuisine=("Italian",))
    )

    assert total == 1
    assert len(items) == 1
    assert items[0].name == "Pasta Palace"
    assert items[0].cuisines == ["Italian", "Pizza"]
    assert fake_cursor.execute.call_count == 2


def test_local_mysql_fallback_cooldown_avoids_repeated_connect_probes(
    test_settings: BackendSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After one failed local MySQL connect, subsequent calls use cooldown fallback."""
    from web.backend.repositories import db

    local_settings = test_settings.model_copy(
        update={"app_env": "local", "backend_allow_csv_fallback_in_local": True}
    )
    monkeypatch.setattr(db, "settings", local_settings)
    db.reset_mysql_fallback_cooldown()

    connect_calls = 0

    def _fail_connect(*_args: object, **_kwargs: object) -> object:
        nonlocal connect_calls
        connect_calls += 1
        raise OSError("Connection refused")

    monkeypatch.setattr(db.pymysql, "connect", _fail_connect)

    assert list(db.get_db_connection()) == [None]
    assert list(db.get_db_connection()) == [None]

    assert connect_calls == 1
    db.reset_mysql_fallback_cooldown()
