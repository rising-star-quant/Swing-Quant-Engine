from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import List, Literal, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineSettings(BaseSettings):
    """
    Centralized, type-safe environment configuration using Pydantic v2 BaseSettings.
    All sensitive credentials are encapsulated in SecretStr to prevent accidental
    exposure in stack traces, logs, or serialized dictionaries.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    quant_env: Literal["development", "staging", "production", "test"] = Field(
        default="production", validation_alias="QUANT_ENV"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )

    state_store_path: Path = Field(
        default=Path("data/portfolios/virtual_portfolio_default.json"),
        validation_alias="STATE_STORE_PATH",
    )
    parquet_cache_path: Path = Field(
        default=Path("data/cache/market_data_window.parquet"),
        validation_alias="PARQUET_CACHE_PATH",
    )
    constituents_dir: Path = Field(
        default=Path("config/constituents"),
        validation_alias="CONSTITUENTS_DIR",
    )
    index_registry_path: Path = Field(
        default=Path("config/index_registry.json"),
        validation_alias="INDEX_REGISTRY_PATH",
    )

    telegram_bot_token: Optional[SecretStr] = Field(
        default=None, validation_alias="TELEGRAM_BOT_TOKEN"
    )
    telegram_chat_id: Optional[SecretStr] = Field(
        default=None, validation_alias="TELEGRAM_CHAT_ID"
    )

    database_url: Optional[SecretStr] = Field(
        default=None, validation_alias="DATABASE_URL"
    )
    jwt_secret_key: SecretStr = Field(
        default=SecretStr("change-me-in-production-min-32-bytes-cryptographic-key"),
        validation_alias="JWT_SECRET_KEY",
    )
    jwt_expiration_minutes: int = Field(
        default=60, ge=5, le=1440, validation_alias="JWT_EXPIRATION_MINUTES"
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def enforce_strong_jwt_secret_in_prod(cls, v: SecretStr, info) -> SecretStr:
        env = info.data.get("quant_env", "production")
        raw_secret = v.get_secret_value()
        if env == "production" and len(raw_secret) < 32:
            raise ValueError(
                "SECURITY VIOLATION: JWT_SECRET_KEY must be at least 32 characters in production."
            )
        return v


class SecretRedactingFilter(logging.Filter):
    """
    Intercepts all Python log messages and masks sensitive credential patterns
    (Telegram Bot Tokens, Bearer JWTs, and PostgreSQL connection strings)
    before they can be written to stdout or GitHub Actions logs.
    """

    _TELEGRAM_TOKEN_REGEX = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")
    _BEARER_REGEX = re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
    _PG_URI_REGEX = re.compile(r"(postgres(?:ql(?:\+psycopg)?)?://[^:]+:)([^@]+)(@)")

    def __init__(self, explicit_secrets: Optional[List[str]] = None) -> None:
        super().__init__()
        self.explicit_secrets = [
            s for s in (explicit_secrets or []) if s and len(s) >= 6
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = self._redact_text(msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True

    def _redact_text(self, text: str) -> str:
        sanitized = self._TELEGRAM_TOKEN_REGEX.sub("[REDACTED_TELEGRAM_TOKEN]", text)
        sanitized = self._BEARER_REGEX.sub(r"\1[REDACTED_JWT]", sanitized)
        sanitized = self._PG_URI_REGEX.sub(r"\1[REDACTED_DB_PASSWORD]\3", sanitized)
        for secret in self.explicit_secrets:
            if secret in sanitized:
                sanitized = sanitized.replace(secret, "[REDACTED_SECRET]")
        return sanitized
