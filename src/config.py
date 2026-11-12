from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Dict, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.schemas import IndexConfigSchema


class SystemSettings(BaseSettings):
    """
    Centralized, type-safe environment and algorithmic engine settings
    using Pydantic v2 BaseSettings.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment & Execution Mode
    environment: str = Field(
        default="sandbox",
        pattern=r"^(sandbox|production|test)$",
        description="Runtime tier: 'sandbox', 'production', or 'test'.",
    )
    log_level: str = Field(
        default="INFO",
        pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Logging level threshold.",
    )
    dry_run: bool = Field(
        default=True,
        description="If True, executes pipeline and sandbox gates without persisting state mutations.",
    )

    # Paths & Persistence (Phase 1 Local Parquet & JSON Store)
    base_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent,
        description="Repository root directory.",
    )
    index_registry_path: Path = Field(
        default=Path("config/index_registry.json"),
        description="Relative or absolute path to index registry JSON.",
    )
    parquet_data_dir: Path = Field(
        default=Path("data/ohlcv_parquet"),
        description="Directory storing rolling historical OHLCV Parquet files.",
    )
    virtual_portfolio_path: Path = Field(
        default=Path("data/virtual_portfolio.json"),
        description="Path to local single-tenant or default portfolio ledger JSON.",
    )

    # Quantitative Lookback & Risk Constants (Simons & López de Prado Invariants)
    screening_lookback_days: int = Field(
        default=250,
        ge=200,
        le=500,
        description="Rolling lookback window for feature calculation and screening.",
    )
    backtest_lookback_days: int = Field(
        default=500,
        ge=250,
        le=1000,
        description="Rolling window for Walk-Forward out-of-sample Meta-Labeling simulation.",
    )
    split_detection_tolerance: float = Field(
        default=0.15,
        gt=0.05,
        le=0.50,
        description="Maximum relative t-1 price difference before flagging a corporate action split.",
    )
    top_n_candidates_per_index: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum candidates passed to Meta-Labeling per index.",
    )
    default_max_portfolio_heat_pct: float = Field(
        default=0.06,
        gt=0.0,
        le=0.15,
        description="Jim Simons maximum portfolio heat ceiling (sum open risk / equity <= 6.0%).",
    )
    base_risk_per_trade_pct: float = Field(
        default=0.01,
        gt=0.001,
        le=0.05,
        description="Base risk per trade before conviction scaling (1.0% default).",
    )

    # Data Ingestion Resilience
    yfinance_batch_size: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum symbols requested in a single yfinance download chunk.",
    )
    yfinance_max_retries: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Maximum retry attempts on network or HTTP 429 errors.",
    )
    yfinance_base_backoff_sec: float = Field(
        default=1.5,
        ge=0.5,
        le=10.0,
        description="Exponential backoff base sleep duration in seconds.",
    )

    # Telegram Notification Secrets
    telegram_bot_token: Optional[str] = Field(
        default=None,
        description="Telegram Bot API token for outbound HTML dispatch.",
    )
    telegram_chat_id: Optional[str] = Field(
        default=None,
        description="Telegram target chat identifier.",
    )

    # Multi-Tenant Security & Future Cloud Migration (Argon2id / JWT / Supabase)
    jwt_secret_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_MIN_32_CHARS_LONG!",
        min_length=32,
        description="Cryptographic secret key for HS256 JWT validation.",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="Cryptographic algorithm for JWT generation.",
    )
    jwt_access_token_expire_minutes: int = Field(
        default=60,
        ge=5,
        le=1440,
        description="Access token lifespan in minutes.",
    )
    supabase_url: Optional[str] = Field(
        default=None,
        description="Supabase / PostgreSQL cloud endpoint URL.",
    )
    supabase_service_key: Optional[str] = Field(
        default=None,
        description="Supabase service role secret key.",
    )

    @model_validator(mode="after")
    def resolve_paths_and_create_directories(self) -> SystemSettings:
        """
        Resolves relative paths against base_dir and ensures target directories exist.
        """
        # Resolve index_registry_path
        if not self.index_registry_path.is_absolute():
            object.__setattr__(
                self,
                "index_registry_path",
                (self.base_dir / self.index_registry_path).resolve(),
            )

        # Resolve parquet_data_dir
        if not self.parquet_data_dir.is_absolute():
            object.__setattr__(
                self,
                "parquet_data_dir",
                (self.base_dir / self.parquet_data_dir).resolve(),
            )

        # Resolve virtual_portfolio_path
        if not self.virtual_portfolio_path.is_absolute():
            object.__setattr__(
                self,
                "virtual_portfolio_path",
                (self.base_dir / self.virtual_portfolio_path).resolve(),
            )

        # Ensure local persistence directories exist
        self.parquet_data_dir.mkdir(parents=True, exist_ok=True)
        self.virtual_portfolio_path.parent.mkdir(parents=True, exist_ok=True)

        return self


def load_index_registry(registry_path: Path) -> Dict[str, IndexConfigSchema]:
    """
    Reads, parses, and validates the index registry JSON file.
    Validates each entry against IndexConfigSchema and ensures key consistency.
    """
    if not registry_path.exists():
        raise FileNotFoundError(
            f"Index registry configuration file not found at: {registry_path.resolve()}"
        )

    try:
        raw_text = registry_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except Exception as exc:
        raise ValueError(f"Failed to parse index registry JSON at {registry_path}: {exc}") from exc

    if not isinstance(data, dict) or not data:
        raise ValueError(
            f"Index registry at {registry_path} must be a non-empty JSON object mapping index IDs to configurations."
        )

    validated_registry: Dict[str, IndexConfigSchema] = {}
    for index_key, raw_cfg in data.items():
        if not isinstance(raw_cfg, dict):
            raise ValueError(f"Registry entry '{index_key}' must be a dictionary configuration.")

        cfg_schema = IndexConfigSchema.model_validate(raw_cfg)

        if cfg_schema.index_id != index_key:
            raise ValueError(
                f"Index registry key mismatch: Dictionary key '{index_key}' does not match schema index_id '{cfg_schema.index_id}'."
            )

        validated_registry[index_key] = cfg_schema

    if not validated_registry:
        raise ValueError(f"No valid index configurations found in registry at {registry_path}.")

    return validated_registry


@lru_cache(maxsize=1)
def get_settings() -> SystemSettings:
    """Returns a cached singleton instance of SystemSettings."""
    return SystemSettings()


def get_active_indices(settings: Optional[SystemSettings] = None) -> Dict[str, IndexConfigSchema]:
    """
    Loads the index registry and returns only indices configured with is_active=True.
    """
    cfg = settings or get_settings()
    registry = load_index_registry(cfg.index_registry_path)
    return {idx_id: index_cfg for idx_id, index_cfg in registry.items() if index_cfg.is_active}
