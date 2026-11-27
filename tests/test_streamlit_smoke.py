"""AppTest smoke tests, UI data-honesty assertions, and formatter/API client tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from web.streamlit import api_client
from web.streamlit.api_client import (
    AnalyticsSummary,
    APIClient,
    APIError,
    CitiesResponse,
    CountriesResponse,
    CuisinesResponse,
    DestinationProfile,
    HealthResponse,
    MapPointItem,
    MapPointsResponse,
    NLSearchResponse,
    PipelineStatus,
    RestaurantDetailResponse,
    RestaurantItem,
    RestaurantListResponse,
)
from web.streamlit.components.formatters import (
    build_directions_url,
    escape_markdown,
    format_cost,
    format_rating,
    format_source_attribution,
    haversine_km,
    is_valid_coordinate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
STREAMLIT_APP = REPO_ROOT / "web" / "streamlit" / "app.py"
PAGES_DIR = REPO_ROOT / "web" / "streamlit" / "pages"

PAGE_FILES: tuple[str, ...] = (
    "explore_restaurants.py",
    "map_explorer.py",
    "nl_search.py",
    "analytics_briefing.py",
    "destination_guides.py",
    "journey_compare.py",
    "pipeline_status.py",
)


def _sample_restaurants() -> list[RestaurantItem]:
    return [
        {
            "restaurant_id": 101,
            "source_restaurant_id": "zmt-101",
            "source_name": "Zomato",
            "source_license": "CC0 1.0",
            "name": "Maison Thomas",
            "country_name": "Egypt",
            "iso_code": "EG",
            "city_name": "Cairo",
            "locality": "Zamalek",
            "address": "157 26th of July St, Zamalek",
            "latitude": 30.0626,
            "longitude": 31.2211,
            "cuisines": ["Italian", "Pizza"],
            "cuisine_groups": ["European"],
            "avg_cost_for_two": 650.0,
            "currency_code": "EGP",
            "avg_cost_for_two_usd": 13.20,
            "price_range": 2,
            "rating": 4.5,
            "rating_text": "Very Good",
            "votes": 2150,
            "has_table_booking": True,
            "has_online_delivery": True,
            "distance_m": None,
        },
        {
            "restaurant_id": 102,
            "source_restaurant_id": "zmt-102",
            "source_name": "Zomato",
            "source_license": "CC0 1.0",
            "name": "Nile Street Kitchen",
            "country_name": "Egypt",
            "iso_code": "EG",
            "city_name": "Cairo",
            "locality": "Downtown",
            "address": "20 Adly St, Downtown Cairo",
            "latitude": 30.0494,
            "longitude": 31.2421,
            "cuisines": ["Egyptian", "Street Food"],
            "cuisine_groups": ["Middle Eastern"],
            "avg_cost_for_two": 320.0,
            "currency_code": "EGP",
            "avg_cost_for_two_usd": 6.50,
            "price_range": 1,
            "rating": None,
            "rating_text": "Not rated",
            "votes": 0,
            "has_table_booking": False,
            "has_online_delivery": True,
            "distance_m": 1250.0,
        },
    ]


class StubAPIClient:
    """In-memory stub mirroring the FastAPI contract for AppTest runs."""

    def __init__(self, *, stale: bool = True) -> None:
        self._items = _sample_restaurants()
        self._stale = stale

    def health(self) -> HealthResponse:
        return {"status": "ok"}

    def list_restaurants(self, **kwargs: object) -> RestaurantListResponse:
        return {
            "items": self._items,
            "total": len(self._items),
            "limit": int(kwargs.get("limit") or 20),  # type: ignore[call-overload]
            "offset": int(kwargs.get("offset") or 0),  # type: ignore[call-overload]
        }

    def get_restaurant(self, restaurant_id: int) -> RestaurantDetailResponse:
        match = next(
            (item for item in self._items if item["restaurant_id"] == restaurant_id),
            self._items[0],
        )
        return {
            "restaurant": match,
            "nearby": [self._items[1]],
            "similar": [self._items[0]],
        }

    def get_map_points(self, **kwargs: object) -> MapPointsResponse:
        points: list[MapPointItem] = [
            {
                "restaurant_id": item["restaurant_id"],
                "name": item["name"],
                "country_name": item["country_name"],
                "city_name": item["city_name"],
                "locality": item["locality"],
                "latitude": float(item["latitude"] or 30.05),
                "longitude": float(item["longitude"] or 31.23),
                "rating": item["rating"],
                "rating_text": item["rating_text"],
                "price_range": item["price_range"],
                "avg_cost_for_two": item["avg_cost_for_two"],
                "currency_code": item["currency_code"],
                "avg_cost_for_two_usd": item["avg_cost_for_two_usd"],
                "cuisines": item["cuisines"],
                "source_name": item["source_name"],
                "source_license": item["source_license"],
            }
            for item in self._items
        ]
        return {"items": points, "total": len(points)}

    def search_nl(
        self,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        previous_params: object = None,
    ) -> NLSearchResponse:
        _ = previous_params
        return {
            "query": query,
            "interpreted_params": {
                "country": "Egypt",
                "city": "Cairo",
                "cuisine": ["Italian"],
                "min_rating": 4.0,
                "max_cost_usd": 30.0,
                "needs_clarification": (
                    "Did you want to include unrated venues as well?"
                ),
            },
            "parser_used": "rule_based",
            "fallback_used": True,
            "items": self._items,
            "total": len(self._items),
            "limit": limit,
            "offset": offset,
        }

    def list_countries(self) -> CountriesResponse:
        return {
            "items": [
                {
                    "country_name": "Egypt",
                    "iso_code": "EG",
                    "currency_code": "EGP",
                    "restaurant_count": 2,
                },
                {
                    "country_name": "India",
                    "iso_code": "IN",
                    "currency_code": "INR",
                    "restaurant_count": 8652,
                },
            ]
        }

    def list_cities(self, country: str | None = None) -> CitiesResponse:
        return {
            "items": [
                {
                    "city_name": "Cairo",
                    "country_name": "Egypt",
                    "restaurant_count": 2,
                }
            ]
        }

    def list_cuisines(self) -> CuisinesResponse:
        return {
            "items": [
                {
                    "cuisine_name": "Italian",
                    "cuisine_group": "European",
                    "restaurant_count": 500,
                },
                {
                    "cuisine_name": "Egyptian",
                    "cuisine_group": "Middle Eastern",
                    "restaurant_count": 120,
                },
            ]
        }

    def get_analytics(self, country: str | None = None) -> AnalyticsSummary:
        return {
            "total_restaurants": 9551,
            "total_countries": 15,
            "total_cities": 141,
            "total_cuisines": 145,
            "geolocated_count": 9050,
            "rated_count": 7403,
            "unrated_count": 2148,
            "avg_rating": 3.44,
            "top_cuisines": [
                {"cuisine_name": "North Indian", "restaurant_count": 3960},
                {"cuisine_name": "Chinese", "restaurant_count": 2735},
            ],
            "by_country": [
                {"country_name": "India", "restaurant_count": 8652},
                {"country_name": "United States", "restaurant_count": 434},
            ],
            "by_price_range": [
                {"label": "Tier 1", "price_range": 1, "restaurant_count": 4444},
                {"label": "Tier 2", "price_range": 2, "restaurant_count": 3113},
            ],
            "rating_distribution": [
                {"rating_label": "Unrated", "count": 2148},
                {"rating_label": "Very Good", "count": 2100},
            ],
        }

    def get_destination_profile(self, country: str) -> DestinationProfile:
        return {
            "country_name": country,
            "currency_code": "EGP",
            "tagline": "Nile-side street classics and late-night mezze culture.",
            "dining_tradition": "Communal mezze and freshly baked baladi bread.",
            "signature_dishes": ["Koshari", "Ta'ameya", "Molokhia"],
            "attribution": "Curated culinary reference (EatoSphere Editorial)",
            "restaurant_count": 2,
            "city_count": 1,
            "avg_rating": 4.5,
            "top_cities": ["Cairo"],
            "top_cuisines": ["Italian"],
            "top_restaurants": self._items,
        }

    def get_pipeline_status(self) -> PipelineStatus:
        return {
            "latest_run": {
                "run_id": 42,
                "dag_id": "zomato_weekly_etl",
                "source_name": "zomato",
                "status": "success",
                "started_at": "2026-11-10T02:00:00Z",
                "ended_at": "2026-11-10T02:01:15Z",
                "rows_read": 9551,
                "rows_inserted": 9500,
                "rows_updated": 0,
                "rows_unchanged": 0,
                "rows_quarantined": 51,
                "rows_warned": 120,
                "quarantine_rate": 0.0053,
            },
            "is_stale": self._stale,
            "days_since_last_success": 9.0 if self._stale else 0.01,
            "gold_max_age_days": 7,
            "recent_runs": [
                {
                    "run_id": 42,
                    "dag_id": "zomato_weekly_etl",
                    "source_name": "zomato",
                    "status": "success",
                    "started_at": "2026-11-10T02:00:00Z",
                    "ended_at": "2026-11-10T02:01:15Z",
                    "rows_read": 9551,
                    "rows_inserted": 9500,
                    "rows_updated": 0,
                    "rows_unchanged": 0,
                    "rows_quarantined": 51,
                    "rows_warned": 120,
                    "quarantine_rate": 0.0053,
                }
            ],
            "quality_breakdown": [
                {
                    "rule_name": "coordinates_missing_or_zero",
                    "severity": "warning",
                    "count": 120,
                    "sample_reason": "latitude=0, longitude=0 converted to NULL",
                }
            ],
            "data_mode": "mysql_gold",
        }


@pytest.fixture(autouse=True)
def stub_streamlit_api_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[StubAPIClient, None, None]:
    """Stub `get_api_client` and clear `st.cache_data` around every test."""
    st.cache_data.clear()
    stub = StubAPIClient(stale=True)
    api_client.set_api_client_override(stub)  # type: ignore[arg-type]
    monkeypatch.setattr(api_client, "get_api_client", lambda: stub)
    try:
        yield stub
    finally:
        api_client.set_api_client_override(None)
        st.cache_data.clear()


def test_app_entrypoint_and_navigation_render_without_exceptions() -> None:
    """Verify `app.py` entrypoint, sidebar categories, and page switching."""
    at = AppTest.from_file(str(STREAMLIT_APP), default_timeout=15).run()
    assert not at.exception
    assert at.title[0].value == "Explore Restaurants"

    sidebar_md = "\n".join(el.value for el in at.sidebar.markdown)
    assert "Discover" in sidebar_md
    assert "Intelligence" in sidebar_md
    assert "Plan & Operations" in sidebar_md

    for page_file in PAGE_FILES[1:]:
        at.switch_page(f"pages/{page_file}").run()
        assert not at.exception, f"Exception on switched page {page_file}"


@pytest.mark.parametrize("page_file", PAGE_FILES)
def test_individual_pages_render_cleanly(page_file: str) -> None:
    """Verify every page file runs standalone in AppTest with zero exceptions."""
    at = AppTest.from_file(str(PAGES_DIR / page_file), default_timeout=15).run()
    assert not at.exception


def test_explore_renders_unrated_multicurrency_and_staleness() -> None:
    """Verify Explore page surfaces Unrated, cost, attribution, and stale banner."""
    at = AppTest.from_file(
        str(PAGES_DIR / "explore_restaurants.py"),
        default_timeout=15,
    ).run()
    assert not at.exception

    markdown_blob = "\n".join(el.value for el in at.markdown).replace("\\", "")
    caption_blob = "\n".join(el.value for el in at.caption).replace("\\", "")
    warning_blob = "\n".join(el.value for el in at.warning)

    assert "Unrated" in markdown_blob
    assert "0.0 / 5" not in markdown_blob
    assert "EGP 650" in markdown_blob
    assert "$13.20 USD" in markdown_blob
    assert "Zomato · CC0 1.0" in caption_blob
    assert "7-day freshness threshold" in warning_blob

    button_labels = [btn.label for btn in at.button]
    assert "Details" not in button_labels
    assert "Directions" not in button_labels


def test_explore_sequential_save_and_compare_realtime_state() -> None:
    """Verify sequential Save and Compare card clicks update state in real time."""
    at = AppTest.from_file(
        str(PAGES_DIR / "explore_restaurants.py"),
        default_timeout=15,
    ).run()
    assert not at.exception

    # Save first and second restaurants sequentially
    next(btn for btn in at.button if btn.key == "explore_save_101").click().run()
    assert not at.exception
    assert set(at.session_state["saved_restaurants"].keys()) == {101}
    assert any("Journey & Compare" in t.value for t in at.toast)

    next(btn for btn in at.button if btn.key == "explore_save_102").click().run()
    assert not at.exception
    assert set(at.session_state["saved_restaurants"].keys()) == {101, 102}
    saved_101 = next(btn for btn in at.button if btn.key == "explore_save_101")
    saved_102 = next(btn for btn in at.button if btn.key == "explore_save_102")
    assert saved_101.label == "Saved"
    assert saved_102.label == "Saved"

    # Compare add/remove sequentially without polluting saved_restaurants
    at2 = AppTest.from_file(
        str(PAGES_DIR / "explore_restaurants.py"),
        default_timeout=15,
    ).run()
    next(btn for btn in at2.button if btn.key == "explore_cmp_101").click().run()
    assert at2.session_state["compare_ids"] == [101]
    assert set(at2.session_state["compare_items"].keys()) == {101}
    assert at2.session_state["saved_restaurants"] == {}

    next(btn for btn in at2.button if btn.key == "explore_cmp_102").click().run()
    assert at2.session_state["compare_ids"] == [101, 102]
    assert set(at2.session_state["compare_items"].keys()) == {101, 102}
    assert (
        next(btn for btn in at2.button if btn.key == "explore_cmp_102").label
        == "Comparing"
    )

    # Remove 101 sequentially
    next(btn for btn in at2.button if btn.key == "explore_cmp_101").click().run()
    assert at2.session_state["compare_ids"] == [102]
    assert set(at2.session_state["compare_items"].keys()) == {102}


def test_map_explorer_renders_focused_venue_detail_card() -> None:
    """Verify Map Explorer renders a venue detail card with actions when focused."""
    sample = _sample_restaurants()[0]
    at = AppTest.from_file(
        str(PAGES_DIR / "map_explorer.py"),
        default_timeout=15,
    )
    at.session_state["map_focus_restaurant"] = sample
    at.run()
    assert not at.exception
    subheaders = [el.value for el in at.subheader]
    assert any("Maison Thomas" in s for s in subheaders)
    assert any(btn.key == "map_card_save_101" for btn in at.button)


def test_nl_search_displays_interpreted_params_fallback_and_clarification() -> None:
    """Verify NL Search form shows SearchParams, fallback note, and clarification."""
    at = AppTest.from_file(str(PAGES_DIR / "nl_search.py"), default_timeout=15).run()
    assert not at.exception

    at.text_input[0].set_value("Italian in Cairo under $30")
    at.form_submit_button[0].click().run()
    assert not at.exception

    info_blob = "\n".join(el.value for el in at.info)
    caption_blob = "\n".join(el.value for el in at.caption)
    assert "Did you want to include unrated venues as well?" in info_blob
    assert "rule-based parser" in caption_blob


def test_nl_search_displays_hf_semantic_caption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify NL Search renders the HF local ONNX semantic parser caption."""

    class SemanticStubClient(StubAPIClient):
        def __init__(self) -> None:
            super().__init__()
            self.received_previous: list[object] = []

        def search_nl(
            self,
            query: str,
            *,
            limit: int = 20,
            offset: int = 0,
            previous_params: object = None,
        ) -> NLSearchResponse:
            self.received_previous.append(previous_params)
            resp = super().search_nl(
                query,
                limit=limit,
                offset=offset,
                previous_params=previous_params,
            )
            resp["parser_used"] = "huggingface_semantic"
            resp["fallback_used"] = True
            resp["interpreted_params"]["needs_clarification"] = None
            return resp

    stub = SemanticStubClient()
    monkeypatch.setattr(api_client, "get_api_client", lambda: stub)
    at = AppTest.from_file(str(PAGES_DIR / "nl_search.py"), default_timeout=15).run()
    at.text_input[0].set_value("spicy curry in London")
    at.form_submit_button[0].click().run()
    assert not at.exception
    caption_blob = "\n".join(el.value for el in at.caption)
    assert "all-MiniLM-L6-v2 ONNX" in caption_blob
    assert "Follow-up context active" in caption_blob
    assert stub.received_previous[-1] is None

    at.text_input[0].set_value("rated above 4.2")
    at.form_submit_button[0].click().run()
    assert not at.exception
    assert stub.received_previous[-1] is not None


def test_journey_compare_renders_seeded_itinerary_and_compare() -> None:
    """Verify seeded Compare and Journey Planner states compute legs without errors."""
    items = _sample_restaurants()
    at = AppTest.from_file(
        str(PAGES_DIR / "journey_compare.py"),
        default_timeout=15,
    )
    at.session_state["saved_restaurants"] = {
        item["restaurant_id"]: item for item in items
    }
    at.session_state["compare_ids"] = [item["restaurant_id"] for item in items]
    at.session_state["journey_stops"] = items
    at.run()
    assert not at.exception
    metric_values = [m.value for m in at.metric]
    assert any("km" in val for val in metric_values)


def test_pipeline_status_displays_staleness_warning() -> None:
    """Verify Pipeline Status renders staleness alert and quality breakdown."""
    at = AppTest.from_file(
        str(PAGES_DIR / "pipeline_status.py"),
        default_timeout=15,
    ).run()
    assert not at.exception
    assert at.warning
    assert any("freshness" in w.value.lower() for w in at.warning)


def test_formatters_data_honesty_and_geospatial_helpers() -> None:
    """Verify formatter helpers handle None ratings, currency, and Haversine."""
    assert format_rating(None, "Not rated") == "Unrated"
    assert format_rating(4.5, "Very Good") == "4.5 / 5 (Very Good)"
    assert format_cost(650.0, "EGP", 13.2) == "EGP 650 (~$13.20 USD for two)"
    assert format_cost(None, "EGP", None) == "Cost unlisted"
    assert format_source_attribution("Zomato", "CC0 1.0") == "Zomato · CC0 1.0"
    assert escape_markdown("<script>*test*") == "<script>\\*test\\*"
    assert is_valid_coordinate(30.0626, 31.2211) is True
    assert is_valid_coordinate(0.0, 0.0) is False
    assert is_valid_coordinate(None, 31.2) is False

    dist = haversine_km(30.0626, 31.2211, 30.0494, 31.2421)
    assert 2.0 < dist < 3.0

    url = build_directions_url(
        {"latitude": 30.0626, "longitude": 31.2211, "name": "Test"},
        origin_lat=30.0494,
        origin_lon=31.2421,
    )
    assert url is not None
    assert "destination=30.062600,31.221100" in url
    assert "origin=30.049400,31.242100" in url


def test_api_client_error_mapping() -> None:
    """Verify APIClient turns HTTP 422/429/404/503 and timeouts into safe APIErrors."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/search/nl":
            return httpx.Response(429, json={"detail": "rate limited"})
        if request.url.path == "/api/restaurants/999":
            return httpx.Response(404, json={"detail": "not found"})
        if request.url.path == "/api/pipeline/status":
            return httpx.Response(503, json={"detail": "unavailable"})
        return httpx.Response(422, json={"detail": "invalid"})

    client = APIClient("http://testserver", timeout_seconds=5)
    client._client = httpx.Client(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    )

    assert client.health() == {"status": "ok"}

    fractional_status = api_client._PIPELINE_STATUS_ADAPTER.validate_python(
        {
            "latest_run": None,
            "is_stale": False,
            "days_since_last_success": 0.01,
            "gold_max_age_days": 7,
            "recent_runs": [],
            "quality_breakdown": [],
            "data_mode": "local_csv_fallback",
        }
    )
    assert fractional_status["days_since_last_success"] == pytest.approx(0.01)

    with pytest.raises(APIError) as err_429:
        client.search_nl("test")
    assert err_429.value.status_code == 429
    assert "Too many" in err_429.value.user_message

    with pytest.raises(APIError) as err_404:
        client.get_restaurant(999)
    assert err_404.value.status_code == 404

    with pytest.raises(APIError) as err_503:
        client.get_pipeline_status()
    assert err_503.value.status_code == 503

    with pytest.raises(APIError) as err_422:
        client.list_restaurants()
    assert err_422.value.status_code == 422


def test_map_basemaps_and_theme_consistent_marker_colors() -> None:
    """Verify native in-map style dropdown views and theme-consistent colors."""
    from web.streamlit.components.maps_and_charts import (
        build_map_layers,
        build_map_points_df,
        build_map_style_updatemenu,
        get_active_basemap,
        get_map_view_spec,
        get_rating_color_map,
    )
    from web.streamlit.constants import (
        COLOR_DARK_HIGH_RATING,
        COLOR_HIGH_RATING,
        MAP_VIEW_LABELS,
    )

    assert set(MAP_VIEW_LABELS.keys()) == {
        "standard",
        "terrain",
        "satellite",
        "topographic",
        "dark",
    }

    for view_key in MAP_VIEW_LABELS:
        assert get_active_basemap(view_key) == "white-bg"
        layers = build_map_layers(view_key)
        assert len(layers) == 1
        assert layers[0]["sourcetype"] == "raster"
        assert str(layers[0]["source"][0]).startswith("https://")  # type: ignore[index]

    assert get_map_view_spec("satellite")["is_dark_basemap"] is True
    assert get_map_view_spec("dark")["is_dark_basemap"] is True
    assert get_map_view_spec("terrain")["is_dark_basemap"] is False
    assert get_map_view_spec("standard")["is_dark_basemap"] is False

    menu = build_map_style_updatemenu(
        default_view="standard",
        dark_mode=False,
        trace_names=("4.0+", "Focused venue"),
    )
    assert menu["type"] == "dropdown"
    assert menu["active"] == 0
    buttons = menu["buttons"]
    assert isinstance(buttons, list)
    assert [btn["label"] for btn in buttons] == list(MAP_VIEW_LABELS.values())
    for btn in buttons:
        assert btn["method"] == "update"
        trace_update, relayout_payload = btn["args"]
        assert "marker.color" in trace_update
        assert relayout_payload["map.style"] == "white-bg"
        assert "map.layers" in relayout_payload

    dark_btn = buttons[-1]
    assert dark_btn["label"] == "Dark"
    assert dark_btn["args"][0]["marker.color"][0] == COLOR_DARK_HIGH_RATING

    sample_points: list[MapPointItem] = [
        {
            "restaurant_id": 1,
            "name": "Nile Bistro",
            "latitude": 30.0626,
            "longitude": 31.2211,
            "rating": 4.5,
            "rating_text": "Very Good",
            "city_name": "Cairo",
            "country_name": "Egypt",
        }
    ]
    light_df = build_map_points_df(sample_points, dark_mode=False)
    dark_df = build_map_points_df(sample_points, dark_mode=True)
    assert light_df.iloc[0]["marker_color"] == COLOR_HIGH_RATING
    assert dark_df.iloc[0]["marker_color"] == COLOR_DARK_HIGH_RATING
    assert "google.com/maps/dir/" in light_df.iloc[0]["directions_url"]
    assert get_rating_color_map(dark_mode=False)["4.0+"] == COLOR_HIGH_RATING
    assert get_rating_color_map(dark_mode=True)["4.0+"] == COLOR_DARK_HIGH_RATING
    assert COLOR_HIGH_RATING != COLOR_DARK_HIGH_RATING


def test_streamlit_config_hides_error_links_and_agent_api() -> None:
    import tomllib

    config_path = REPO_ROOT / "web" / "streamlit" / ".streamlit" / "config.toml"
    parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert parsed["server"]["enableAgentApi"] is False
    assert parsed["client"]["showErrorLinks"] is False
