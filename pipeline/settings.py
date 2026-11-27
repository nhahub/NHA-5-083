"""Configuration loader for the ETL pipeline and Airflow DAGs.

This module is the single settings reader inside ``pipeline/`` permitted to access
OS environment variables and ``config/settings.toml`` (enforced by
``tests/test_architecture.py``).
"""

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipeline.constants import (
    MAX_ABS_LATITUDE,
    MAX_ABS_LONGITUDE,
    MAX_PRICE_RANGE,
    MAX_QUARANTINE_RATE,
    MAX_RATING,
    MIN_PRICE_RANGE,
    MIN_RATING,
    QUERY_LOG_MAX_CHARS,
    STORAGE_BACKEND_LOCAL,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "settings.toml"
DEFAULT_CUISINE_MAP_PATH = REPO_ROOT / "config" / "cuisine_map.csv"
DEFAULT_GOLD_VIEWS_SQL_PATH = REPO_ROOT / "sql" / "002_create_gold_views.sql"
DEFAULT_MYSQL_PORT = 3306
DEFAULT_CONNECT_TIMEOUT_SECONDS = 15
DEFAULT_GOLD_MAX_AGE_DAYS = 7


def _resolve_config_path(config_path: Path | None = None) -> Path:
    if config_path is not None:
        return config_path
    env_override = os.getenv("APP_CONFIG_PATH")
    if env_override:
        return Path(env_override)
    return DEFAULT_CONFIG_PATH


def _load_toml_flat(config_path: Path | None = None) -> dict[str, object]:
    """Read TOML sections needed by the pipeline into flattened field keys."""
    resolved = _resolve_config_path(config_path)
    if not resolved.is_file():
        return {}
    with resolved.open("rb") as handle:
        raw_toml = tomllib.load(handle)

    flat: dict[str, object] = {}
    section_names = ("logging", "quality", "freshness", "pipeline", "database")
    for section in section_names:
        section_data = raw_toml.get(section)
        if isinstance(section_data, dict):
            for key, value in section_data.items():
                flat[f"{section}_{key}"] = value

    sources_data = raw_toml.get("sources")
    if isinstance(sources_data, dict):
        zomato_data = sources_data.get("zomato")
        if isinstance(zomato_data, dict):
            for key, value in zomato_data.items():
                flat[f"sources_zomato_{key}"] = value

    return flat


class PipelineRuntimeConfig(BaseModel):
    """Non-secret runtime settings loaded from ``config/settings.toml``."""

    logging_level: str = "INFO"
    logging_format: str = "json"
    logging_query_max_chars: int = QUERY_LOG_MAX_CHARS

    quality_max_quarantine_rate: float = MAX_QUARANTINE_RATE
    quality_rating_min: float = MIN_RATING
    quality_rating_max: float = MAX_RATING
    quality_price_range_min: int = MIN_PRICE_RANGE
    quality_price_range_max: int = MAX_PRICE_RANGE
    quality_latitude_abs_max: float = MAX_ABS_LATITUDE
    quality_longitude_abs_max: float = MAX_ABS_LONGITUDE

    freshness_gold_max_age_days: int = DEFAULT_GOLD_MAX_AGE_DAYS

    pipeline_bronze_local_path: str = "data/bronze"
    pipeline_quarantine_path: str = "data/quarantine"
    pipeline_reports_path: str = "data/reports"
    pipeline_logs_path: str = "logs"
    pipeline_bronze_container: str = "bronze"

    database_connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS

    sources_zomato_kaggle_dataset: str = "shrutimehta/zomato-restaurants-data"
    sources_zomato_schedule: str = "@weekly"
    sources_zomato_skip_if_unchanged: bool = True
    sources_zomato_file_name: str = "zomato.csv"
    sources_zomato_file_encoding: str = "latin-1"

    def resolve_path(self, raw_path: str) -> Path:
        """Resolve a configured relative path against the repository root.

        Args:
            raw_path: Relative or absolute path string from settings.

        Returns:
            Resolved ``Path`` object.
        """
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return REPO_ROOT / candidate


class PipelineSettings(BaseSettings):
    """Full pipeline settings combining ``config/settings.toml`` and secrets."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Environment & secrets (required secrets use SecretStr with no default)
    app_env: str = "local"
    mysql_host: str = "localhost"
    mysql_port: int = DEFAULT_MYSQL_PORT
    mysql_database: str = "global_restaurant_explorer"
    mysql_tls_enabled: bool = False
    mysql_pipeline_user: str = Field(...)
    mysql_pipeline_password: SecretStr = Field(...)

    kaggle_username: str = Field(...)
    kaggle_key: SecretStr = Field(...)

    storage_backend: str = STORAGE_BACKEND_LOCAL
    azure_storage_account_url: str | None = None
    azure_storage_connection_string: SecretStr | None = None
    fx_rate_api_key: SecretStr | None = None

    # Non-secret TOML tunables
    logging_level: str = "INFO"
    logging_format: str = "json"
    logging_query_max_chars: int = QUERY_LOG_MAX_CHARS

    quality_max_quarantine_rate: float = MAX_QUARANTINE_RATE
    quality_rating_min: float = MIN_RATING
    quality_rating_max: float = MAX_RATING
    quality_price_range_min: int = MIN_PRICE_RANGE
    quality_price_range_max: int = MAX_PRICE_RANGE
    quality_latitude_abs_max: float = MAX_ABS_LATITUDE
    quality_longitude_abs_max: float = MAX_ABS_LONGITUDE

    freshness_gold_max_age_days: int = DEFAULT_GOLD_MAX_AGE_DAYS

    pipeline_bronze_local_path: str = "data/bronze"
    pipeline_quarantine_path: str = "data/quarantine"
    pipeline_reports_path: str = "data/reports"
    pipeline_logs_path: str = "logs"
    pipeline_bronze_container: str = "bronze"

    database_connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS

    sources_zomato_kaggle_dataset: str = "shrutimehta/zomato-restaurants-data"
    sources_zomato_schedule: str = "@weekly"
    sources_zomato_skip_if_unchanged: bool = True
    sources_zomato_file_name: str = "zomato.csv"
    sources_zomato_file_encoding: str = "latin-1"

    def to_runtime_config(self) -> PipelineRuntimeConfig:
        """Extract the non-secret runtime configuration subset.

        Returns:
            ``PipelineRuntimeConfig`` populated from this settings object.
        """
        return PipelineRuntimeConfig(
            logging_level=self.logging_level,
            logging_format=self.logging_format,
            logging_query_max_chars=self.logging_query_max_chars,
            quality_max_quarantine_rate=self.quality_max_quarantine_rate,
            quality_rating_min=self.quality_rating_min,
            quality_rating_max=self.quality_rating_max,
            quality_price_range_min=self.quality_price_range_min,
            quality_price_range_max=self.quality_price_range_max,
            quality_latitude_abs_max=self.quality_latitude_abs_max,
            quality_longitude_abs_max=self.quality_longitude_abs_max,
            freshness_gold_max_age_days=self.freshness_gold_max_age_days,
            pipeline_bronze_local_path=self.pipeline_bronze_local_path,
            pipeline_quarantine_path=self.pipeline_quarantine_path,
            pipeline_reports_path=self.pipeline_reports_path,
            pipeline_logs_path=self.pipeline_logs_path,
            pipeline_bronze_container=self.pipeline_bronze_container,
            database_connect_timeout_seconds=self.database_connect_timeout_seconds,
            sources_zomato_kaggle_dataset=self.sources_zomato_kaggle_dataset,
            sources_zomato_schedule=self.sources_zomato_schedule,
            sources_zomato_skip_if_unchanged=self.sources_zomato_skip_if_unchanged,
            sources_zomato_file_name=self.sources_zomato_file_name,
            sources_zomato_file_encoding=self.sources_zomato_file_encoding,
        )

    def resolve_path(self, raw_path: str) -> Path:
        """Resolve a configured relative path against the repository root.

        Args:
            raw_path: Relative or absolute path string from settings.

        Returns:
            Resolved ``Path`` object.
        """
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return REPO_ROOT / candidate


def load_pipeline_runtime_config(
    config_path: Path | None = None,
) -> PipelineRuntimeConfig:
    """Load non-secret pipeline settings from ``config/settings.toml``.

    Environment overrides following the ``SECTION_KEY`` convention (for
    example ``SOURCES_ZOMATO_SCHEDULE``) take precedence over TOML values.

    Args:
        config_path: Optional path to an alternate TOML configuration file.

    Returns:
        Validated ``PipelineRuntimeConfig`` instance.
    """
    flat_toml = _load_toml_flat(config_path)
    merged: dict[str, object] = dict(flat_toml)
    for field_name in PipelineRuntimeConfig.model_fields:
        env_val = os.getenv(field_name.upper())
        if env_val is not None:
            merged[field_name] = env_val
    return PipelineRuntimeConfig.model_validate(merged)


def load_pipeline_settings(
    config_path: Path | None = None,
    overrides: dict[str, object] | None = None,
) -> PipelineSettings:
    """Load full pipeline settings with TOML defaults and env precedence.

    Args:
        config_path: Optional path to an alternate TOML file.
        overrides: Optional explicit field overrides (useful in tests).

    Returns:
        Validated ``PipelineSettings`` instance.
    """
    flat_toml = _load_toml_flat(config_path)
    merged_kwargs: dict[str, object] = {}
    for key, value in flat_toml.items():
        if key in PipelineSettings.model_fields and os.getenv(key.upper()) is None:
            merged_kwargs[key] = value
    if overrides:
        merged_kwargs.update(overrides)
    return PipelineSettings(**merged_kwargs)  # type: ignore[arg-type]


def export_kaggle_credentials(settings: PipelineSettings) -> None:
    """Populate Kaggle SDK environment variables from settings secrets.

    Args:
        settings: Pipeline settings holding Kaggle username and API key.
    """
    os.environ["KAGGLE_USERNAME"] = settings.kaggle_username
    os.environ["KAGGLE_KEY"] = settings.kaggle_key.get_secret_value()
