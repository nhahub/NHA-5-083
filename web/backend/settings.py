"""Backend configuration loaded from OS environment, .env, and settings.toml."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from web.backend.constants import (
    DEFAULT_CACHE_MAX_ENTRIES,
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_NLP_RATE_LIMIT_PER_MINUTE,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_SEMANTIC_CUISINE_THRESHOLD,
    DEFAULT_SEMANTIC_MODEL_ID,
    DEFAULT_SEMANTIC_PRICE_THRESHOLD,
    GOLD_MAX_AGE_DAYS,
    MAX_NLP_INPUT_CHARS,
    MAX_NLP_OUTPUT_TOKENS,
    MAX_PAGE_LIMIT,
    NLP_TIMEOUT_SECONDS,
    PLACEHOLDER_PREFIX,
    QUERY_LOG_MAX_CHARS,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "settings.toml"
TOML_SECTIONS: tuple[str, ...] = (
    "logging",
    "freshness",
    "database",
    "nlp",
    "backend",
)


def _load_toml_flattened() -> dict[str, object]:
    """Load flattened tunable settings from config/settings.toml."""
    raw_path = os.getenv("APP_CONFIG_PATH")
    config_path = Path(raw_path) if raw_path else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        return {}
    parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    flattened: dict[str, object] = {}
    for section in TOML_SECTIONS:
        section_data = parsed.get(section)
        if isinstance(section_data, dict):
            for key, value in section_data.items():
                flattened[f"{section}_{key}"] = value
    return flattened


class TomlConfigSettingsSource(PydanticBaseSettingsSource):
    """Pydantic settings source reading config/settings.toml."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        """Initialize the TOML settings source."""
        super().__init__(settings_cls)
        self._data = _load_toml_flattened()

    def get_field_value(
        self,
        field: FieldInfo,
        field_name: str,
    ) -> tuple[object, str, bool]:
        """Return a single field value from the parsed TOML dictionary."""
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        """Return all non-None fields loaded from the TOML file."""
        return {
            field_name: self._data[field_name]
            for field_name in self.settings_cls.model_fields
            if field_name in self._data
        }


class BackendSettings(BaseSettings):
    """Validated runtime configuration and secrets for the FastAPI backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "ci", "production"] = "local"

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "global_restaurant_explorer"
    mysql_tls_enabled: bool = False
    mysql_app_user: str
    mysql_app_password: SecretStr

    hf_api_key: SecretStr

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    backend_cors_origins: str = "http://localhost:8501"

    logging_level: str = "INFO"
    logging_format: str = "json"
    logging_query_max_chars: int = QUERY_LOG_MAX_CHARS

    freshness_gold_max_age_days: int = GOLD_MAX_AGE_DAYS
    database_connect_timeout_seconds: int = 15

    nlp_model_id: str = "Qwen/Qwen3-32B"
    nlp_provider: str = "auto"
    nlp_semantic_model_id: str = DEFAULT_SEMANTIC_MODEL_ID
    nlp_semantic_enabled: bool = True
    nlp_semantic_cuisine_threshold: float = DEFAULT_SEMANTIC_CUISINE_THRESHOLD
    nlp_semantic_price_threshold: float = DEFAULT_SEMANTIC_PRICE_THRESHOLD
    nlp_timeout_seconds: int = NLP_TIMEOUT_SECONDS
    nlp_max_input_chars: int = MAX_NLP_INPUT_CHARS
    nlp_max_output_tokens: int = MAX_NLP_OUTPUT_TOKENS
    nlp_temperature: float = 0.0
    nlp_cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES
    nlp_cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS

    backend_nlp_rate_limit_per_minute: int = DEFAULT_NLP_RATE_LIMIT_PER_MINUTE
    backend_page_default_limit: int = DEFAULT_PAGE_LIMIT
    backend_page_max_limit: int = MAX_PAGE_LIMIT
    backend_allow_csv_fallback_in_local: bool = True
    backend_local_fallback_csv_path: str = "data/zomato.csv"

    cuisine_map_path: Path = Field(
        default_factory=lambda: ROOT_DIR / "config" / "cuisine_map.csv"
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse comma-separated CORS origins into a clean list."""
        return [
            origin.strip()
            for origin in self.backend_cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def resolved_fallback_csv_path(self) -> Path:
        """Resolve fallback CSV path relative to repository root if needed."""
        candidate = Path(self.backend_local_fallback_csv_path)
        return candidate if candidate.is_absolute() else ROOT_DIR / candidate

    @model_validator(mode="after")
    def validate_production_secrets(self) -> BackendSettings:
        """Reject placeholder secret values when running in production."""
        if self.app_env == "production":
            for label, secret in (
                ("MYSQL_APP_USER", self.mysql_app_user),
                ("MYSQL_APP_PASSWORD", self.mysql_app_password.get_secret_value()),
                ("HF_API_KEY", self.hf_api_key.get_secret_value()),
            ):
                if not secret.strip() or secret.startswith(PLACEHOLDER_PREFIX):
                    raise ValueError(
                        f"{label} must not be empty or a placeholder in production"
                    )
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Configure precedence: init > env > .env > settings.toml > file secrets."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


def get_settings() -> BackendSettings:
    """Create and validate a BackendSettings instance."""
    return BackendSettings()  # type: ignore[call-arg]


settings = get_settings()
