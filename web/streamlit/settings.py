"""Configuration and structured JSON logging for the Streamlit presentation layer."""

from __future__ import annotations

import json
import logging
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from web.streamlit.constants import (
    DEFAULT_API_TIMEOUT_SECONDS,
    DEFAULT_CACHE_TTL_SECONDS,
    GOLD_MAX_AGE_DAYS,
    QUERY_LOG_MAX_CHARS,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_TOML_PATH = _REPO_ROOT / "config" / "settings.toml"
_CONFIG_SECTIONS: tuple[str, ...] = ("logging", "freshness", "streamlit")


def _resolve_toml_path() -> Path:
    override = os.getenv("APP_CONFIG_PATH")
    if override:
        return Path(override)
    return _DEFAULT_TOML_PATH


def _load_toml_values() -> dict[str, str | int | float | bool]:
    toml_path = _resolve_toml_path()
    if not toml_path.is_file():
        return {}
    with toml_path.open("rb") as handle:
        raw_data = tomllib.load(handle)

    flattened: dict[str, str | int | float | bool] = {}
    for section in _CONFIG_SECTIONS:
        section_map = raw_data.get(section)
        if not isinstance(section_map, dict):
            continue
        for key, value in section_map.items():
            if isinstance(value, (str, int, float, bool)):
                flattened[f"{section}_{key}"] = value
    return flattened


class StreamlitSettings(BaseSettings):
    """Typed settings loaded from OS env, `.env`, and `config/settings.toml`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    streamlit_backend_url: str = Field(default="http://127.0.0.1:8000")
    streamlit_api_timeout_seconds: int = Field(
        default=DEFAULT_API_TIMEOUT_SECONDS, ge=1
    )
    streamlit_cache_ttl_seconds: int = Field(default=DEFAULT_CACHE_TTL_SECONDS, ge=0)
    freshness_gold_max_age_days: int = Field(default=GOLD_MAX_AGE_DAYS, ge=1)
    logging_level: str = Field(default="INFO")
    logging_format: str = Field(default="json")
    logging_query_max_chars: int = Field(default=QUERY_LOG_MAX_CHARS, ge=1)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Prioritize OS env and `.env` above TOML init values and field defaults."""
        return (
            env_settings,
            dotenv_settings,
            init_settings,
            file_secret_settings,
        )


class _JsonLogFormatter(logging.Formatter):
    """Format log records as single-line UTC JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level_name: str) -> None:
    """Configure root JSON-line logging once for the Streamlit app."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonLogFormatter())
    root_logger.addHandler(handler)
    level = getattr(logging, level_name.upper(), logging.INFO)
    root_logger.setLevel(level)


def truncate_query_for_log(query: str) -> str:
    """Truncate user NLP query strings before writing structured logs."""
    limit = settings.logging_query_max_chars
    if len(query) <= limit:
        return query
    return f"{query[:limit]}..."


settings = StreamlitSettings.model_validate(_load_toml_values())
configure_logging(settings.logging_level)
