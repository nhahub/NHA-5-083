"""Shared pytest fixtures for backend unit and FastAPI route tests."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_DATABASE", "global_restaurant_explorer")
os.environ.setdefault("MYSQL_TLS_ENABLED", "false")
os.environ.setdefault("MYSQL_APP_USER", "test_app_user")
os.environ.setdefault("MYSQL_APP_PASSWORD", "test_app_password")
os.environ.setdefault("HF_API_KEY", "replace_with_test_key")

from web.backend.main import create_app
from web.backend.repositories.csv_fallback import clear_csv_snapshot_cache
from web.backend.repositories.db import get_db_connection
from web.backend.repositories.meta_repository import VocabularySnapshot
from web.backend.settings import BackendSettings

SAMPLE_ZOMATO_CSV = "\n".join(
    [
        (
            "Restaurant ID,Restaurant Name,Country Code,City,Address,Locality,"
            "Locality Verbose,Longitude,Latitude,Cuisines,Average Cost for two,"
            "Currency,Has Table booking,Has Online delivery,Is delivering now,"
            "Switch to order menu,Price range,Aggregate rating,Rating color,"
            "Rating text,Votes"
        ),
        (
            '1001,"Pasta Palace",1,"New Delhi","12 Connaught Place","Connaught Place",'
            '"Connaught Place, New Delhi",77.216721,28.631451,"Italian, Pizza",1200,'
            '"Indian Rupees(Rs.)",Yes,Yes,No,No,2,4.5,Dark Green,Excellent,320'
        ),
        (
            '1002,"Döner & Kebab House",208,"ï¿½ï¿½stanbul","10 Istiklal St",'
            '"Beyoglu","Beyoglu, Istanbul",28.978359,41.008238,'
            '"Kebab, Dï¿½_ner, Turkish Pizza",180,'
            '"Turkish Lira(TL)",No,No,No,No,2,4.7,Dark Green,Excellent,450'
        ),
        (
            '1003,"Unrated Corner Cafe",1,"New Delhi","44 Karol Bagh","Karol Bagh",'
            '"Karol Bagh, New Delhi",0,0,"Tea, Bakery",0,'
            '"Indian Rupees(Rs.)",No,Yes,No,No,1,0,White,Not rated,0'
        ),
        (
            '1004,"Spice Route",1,"New Delhi","18 Khan Market","Khan Market",'
            '"Khan Market, New Delhi",77.227000,28.600100,'
            '"North Indian, Mughlai",1800,'
            '"Indian Rupees(Rs.)",Yes,No,No,No,3,4.2,Green,Very Good,210'
        ),
        (
            '1005,"Roma Trattoria",1,"New Delhi","22 Connaught Circus",'
            '"Connaught Place","Connaught Place, New Delhi",77.219000,28.633000,'
            '"Italian, Mediterranean",1400,'
            '"Indian Rupees(Rs.)",No,Yes,No,No,2,4.1,Green,Very Good,145'
        ),
        (
            '1006,"Soho Bites",215,"London","5 Dean St","Soho",'
            '"Soho, London",-0.132400,51.514100,"British, Cafe",55,'
            '"Pounds(ï¿½ï¿½)",Yes,No,No,No,3,4.6,Dark Green,Excellent,580'
        ),
        (
            '1007,"Manila Grill",162,"Makati City","99 Ayala Ave","Legaspi Village",'
            '"Legaspi Village, Makati City",121.019000,14.554700,"Malay, Seafood",1500,'
            '"Botswana Pula(P)",No,No,No,No,3,4.3,Green,Very Good,190'
        ),
    ]
)

SAMPLE_CUISINE_MAP_CSV = "\n".join(
    [
        "source_label,canonical_cuisine,cuisine_group",
        "Italian,Italian,European",
        "Pizza,Pizza,Dish and Format",
        "Mediterranean,Mediterranean,European",
        "Kebab,Kebab,Middle Eastern and Turkish",
        "Döner,Turkish,Middle Eastern and Turkish",
        "Turkish Pizza,Turkish,Middle Eastern and Turkish",
        "Tea,Coffee & Tea,Cafe and Beverages",
        "Bakery,Bakery,Bakery and Desserts",
        "North Indian,North Indian,Indian",
        "Mughlai,Mughlai,Indian",
        "British,British,European",
        "Cafe,Cafe,Cafe and Beverages",
        "Malay,Malaysian,Southeast Asian",
        "Seafood,Seafood,Dish and Format",
    ]
)


@pytest.fixture()
def sample_csv_files(tmp_path: Path) -> tuple[Path, Path]:
    """Create temporary Zomato CSV and cuisine map CSV files."""
    csv_path = tmp_path / "zomato.csv"
    csv_path.write_bytes(SAMPLE_ZOMATO_CSV.encode("latin-1"))
    cuisine_map_path = tmp_path / "cuisine_map.csv"
    cuisine_map_path.write_text(SAMPLE_CUISINE_MAP_CSV, encoding="utf-8")
    clear_csv_snapshot_cache()
    return csv_path, cuisine_map_path


@pytest.fixture()
def test_settings(sample_csv_files: tuple[Path, Path]) -> BackendSettings:
    """Return isolated BackendSettings pointing at temporary CSV fixtures."""
    csv_path, cuisine_map_path = sample_csv_files
    return BackendSettings(
        app_env="local",
        mysql_app_user="test_user",
        mysql_app_password=SecretStr("test_fixture_val"),
        hf_api_key=SecretStr("replace_with_test_key"),
        nlp_semantic_enabled=False,
        backend_allow_csv_fallback_in_local=True,
        backend_local_fallback_csv_path=str(csv_path),
        cuisine_map_path=cuisine_map_path,
        backend_nlp_rate_limit_per_minute=30,
    )


@pytest.fixture()
def api_client(
    test_settings: BackendSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """Return a FastAPI TestClient wired to the local CSV fallback."""
    import web.backend.dependencies as deps_mod
    import web.backend.repositories.restaurant_repository as repo_mod

    monkeypatch.setattr(deps_mod, "settings", test_settings)
    monkeypatch.setattr(repo_mod, "settings", test_settings)

    app = create_app(test_settings)

    def _override_db() -> Generator[None, None, None]:
        yield None

    app.dependency_overrides[get_db_connection] = _override_db
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def sample_vocabulary() -> VocabularySnapshot:
    """Return a deterministic VocabularySnapshot for NLP unit tests."""
    return VocabularySnapshot(
        countries=("India", "Turkey", "United Kingdom", "Philippines"),
        cities=("New Delhi", "İstanbul", "London", "Makati City"),
        localities=(
            "Connaught Place",
            "Karol Bagh",
            "Khan Market",
            "Beyoglu",
            "Soho",
            "Legaspi Village",
        ),
        cuisines=(
            "Italian",
            "Pizza",
            "Mediterranean",
            "Turkish",
            "Kebab",
            "North Indian",
            "Mughlai",
            "Coffee & Tea",
            "Bakery",
            "British",
            "Cafe",
            "Malaysian",
            "Seafood",
        ),
        cuisine_groups=(
            "European",
            "Dish and Format",
            "Middle Eastern and Turkish",
            "Indian",
            "Cafe and Beverages",
            "Bakery and Desserts",
            "Southeast Asian",
        ),
        cuisine_synonyms={},
    )
