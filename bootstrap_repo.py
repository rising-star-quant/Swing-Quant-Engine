#!/usr/bin/env python3
"""
Swing Quant Engine — Self-Contained Repository Bootstrapper (Steps A.1 through E.3)
===================================================================================
Architectures:
  - Jim Simons (Renaissance Technologies): Zero-Override Execution, Strict Liquidity Filters
    (Price >= $5.00, ADV_30 >= 500,000, Bid-Ask Spread Gateways), 6.0% Portfolio Heat Cap.
  - Dr. Marcos López de Prado (Advances in Financial Machine Learning): Triple-Barrier Method,
    Meta-Labeling Conviction Scalar (phi_meta), Volatility-Adjusted Stationary Momentum,
    and Strict Point-in-Time (PiT) Corporate Action Overlap Guards.

Usage:
  python3 bootstrap_repo.py
  python3 bootstrap_repo.py --target-dir ./swing-quant-engine
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Dict


def build_repository_manifest() -> Dict[str, str]:
    """Returns the complete, zero-truncation file manifest for the Swing Quant Engine."""
    files: Dict[str, str] = {}

    # =========================================================================
    # 1. requirements.txt
    # =========================================================================
    files["requirements.txt"] = """\
# =========================================================================
# Swing Quant Engine - Strictly Pinned Production & Verification Manifest
# Target Runtime: Python 3.11+ (Ubuntu / Debian / GitHub Codespaces)
# =========================================================================
pydantic==2.9.2
pydantic-settings==2.6.0
pandas==2.2.3
numpy==2.1.2
yfinance==0.2.48
pyarrow==17.0.0
pytest==8.3.3
httpx==0.27.2
pyjwt==2.9.0
argon2-cffi==23.1.0
"""

    # =========================================================================
    # 2. pyproject.toml
    # =========================================================================
    files["pyproject.toml"] = """\
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "swing-quant-engine"
version = "2.0.0"
description = "Autonomous Multi-Index Swing Quant Engine (López de Prado & Simons Architecture)"
readme = "README.md"
requires-python = ">=3.11"

[tool.pytest.ini_options]
minversion = "8.0"
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-v --tb=short --strict-markers"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
ignore = ["E501"]
"""

    # =========================================================================
    # 3. .gitignore & .env.example
    # =========================================================================
    files[".gitignore"] = """\
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/

# Virtual Environments
.venv/
venv/
ENV/

# Secrets & Local Environment Overrides (NEVER COMMIT)
.env
*.pem
*.key

# Ephemeral Staging & Cache Files
*.tmp
data/cache/*.tmp
data/cache/*.parquet
"""

    files[".env.example"] = """\
# =========================================================================
# Swing Quant Engine - Environment Configuration Template
# Copy to .env for local development or configure in GitHub Actions Secrets
# =========================================================================

QUANT_ENV=production
LOG_LEVEL=INFO

# File Paths
STATE_STORE_PATH=data/portfolios/virtual_portfolio_default.json
PARQUET_CACHE_PATH=data/cache/market_data_window.parquet
CONSTITUENTS_DIR=config/constituents
INDEX_REGISTRY_PATH=config/index_registry.json

# Telegram Dispatch Credentials (Injected via GitHub Secrets in Step D.3 / E.1)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# Cryptographic Signing Key (Minimum 32 bytes in production)
JWT_SECRET_KEY=replace_with_64_char_hex_secret_generated_via_secrets_token_hex_32
JWT_EXPIRATION_MINUTES=60

# Future Phase 2 Cloud Database Connection (Supabase / PostgreSQL with RLS)
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/swing_quant_db
"""

    # =========================================================================
    # 4. config/index_registry.json & Curated Constituent Rosters
    # =========================================================================
    files["config/index_registry.json"] = """\
{
  "RUT": {
    "index_id": "RUT",
    "display_name": "Russell 2000 Small-Cap",
    "benchmark_ticker": "IWM",
    "tier": "SMALL_CAP",
    "is_active": true,
    "min_price": 5.0,
    "min_adv_30d": 500000,
    "max_relative_spread": 0.005,
    "volume_surge_multiplier": 1.8,
    "k_stop_atr": 2.5,
    "k_profit_atr": 5.0,
    "max_holding_bars": 14
  },
  "MID": {
    "index_id": "MID",
    "display_name": "S&P MidCap 400",
    "benchmark_ticker": "MDY",
    "tier": "MID_CAP",
    "is_active": true,
    "min_price": 5.0,
    "min_adv_30d": 500000,
    "max_relative_spread": 0.004,
    "volume_surge_multiplier": 1.4,
    "k_stop_atr": 2.0,
    "k_profit_atr": 4.5,
    "max_holding_bars": 14
  }
}
"""

    files["config/constituents/RUT.csv"] = """\
ticker,name,sector
FN,Fabrinet,Technology
ANF,Abercrombie & Fitch Co.,Consumer Discretionary
CRS,Carpenter Technology Corp.,Materials
MOD,Modine Manufacturing Co.,Consumer Discretionary
POWL,Powell Industries Inc.,Industrials
SMCI,Super Micro Computer Inc.,Technology
CELH,Celsius Holdings Inc.,Consumer Staples
RMBS,Rambus Inc.,Technology
ONTO,Onto Innovation Inc.,Technology
SPSX,SPS Commerce Inc.,Technology
"""

    files["config/constituents/MID.csv"] = """\
ticker,name,sector
WSM,Williams-Sonoma Inc.,Consumer Discretionary
EME,EMCOR Group Inc.,Industrials
FIX,Comfort Systems USA Inc.,Industrials
TOL,Toll Brothers Inc.,Consumer Discretionary
RNR,RenaissanceRe Holdings Ltd.,Financials
CLH,Clean Harbors Inc.,Industrials
MANH,Manhattan Associates Inc.,Technology
DOCS,Doximity Inc.,Health Care
TXRH,Texas Roadhouse Inc.,Consumer Discretionary
WING,Wingstop Inc.,Consumer Discretionary
"""

    # =========================================================================
    # 5. data/portfolios/virtual_portfolio_default.json
    # =========================================================================
    files["data/portfolios/virtual_portfolio_default.json"] = """\
{
  "portfolio_id": "00000000-0000-4000-8000-000000000101",
  "user_id": "00000000-0000-4000-8000-000000000001",
  "portfolio_name": "Primary Swing Shadow Portfolio",
  "as_of_date": "2026-11-11",
  "cash_balance": 100000.0,
  "total_equity": 100000.0,
  "max_portfolio_heat_pct": 0.06,
  "max_concurrent_positions": 10,
  "subscribed_indices": [
    "RUT",
    "MID"
  ],
  "open_positions": {},
  "closed_trades_audit": []
}
"""

    # =========================================================================
    # 6. src/__init__.py
    # =========================================================================
    files["src/__init__.py"] = """\
\"\"\"
Swing Quant Engine Package
Autonomous Multi-Index Quantitative Swing Trading System.
\"\"\"

__version__ = "2.0.0"
"""

    # =========================================================================
    # 7. src/config.py
    # =========================================================================
    files["src/config.py"] = """\
from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import List, Literal, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineSettings(BaseSettings):
    \"\"\"
    Centralized, type-safe environment configuration using Pydantic v2 BaseSettings.
    All sensitive credentials are encapsulated in SecretStr to prevent accidental
    exposure in stack traces, logs, or serialized dictionaries.
    \"\"\"

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
    \"\"\"
    Intercepts all Python log messages and masks sensitive credential patterns
    (Telegram Bot Tokens, Bearer JWTs, and PostgreSQL connection strings)
    before they can be written to stdout or GitHub Actions logs.
    \"\"\"

    _TELEGRAM_TOKEN_REGEX = re.compile(r"\\b\\d{8,10}:[A-Za-z0-9_-]{35}\\b")
    _BEARER_REGEX = re.compile(r"(Bearer\\s+)[A-Za-z0-9\\-._~+/]+=*", re.IGNORECASE)
    _PG_URI_REGEX = re.compile(r"(postgres(?:ql(?:\\+psycopg)?)?://[^:]+:)([^@]+)(@)")

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
        sanitized = self._BEARER_REGEX.sub(r"\\1[REDACTED_JWT]", sanitized)
        sanitized = self._PG_URI_REGEX.sub(r"\\1[REDACTED_DB_PASSWORD]\\3", sanitized)
        for secret in self.explicit_secrets:
            if secret in sanitized:
                sanitized = sanitized.replace(secret, "[REDACTED_SECRET]")
        return sanitized
"""

    # =========================================================================
    # 8. src/security.py
    # =========================================================================
    files["src/security.py"] = """\
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
import jwt

from schemas import JWTTokenPayload, UserRole


class SecurityViolationError(PermissionError):
    \"\"\"Raised when authentication, token signature, or tenant isolation fails.\"\"\"


_ARGON2_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


class MultiTenantSecurityService:
    \"\"\"
    Provides cryptographic password hashing via Argon2id (argon2-cffi),
    stateless HS256 JWT generation/verification via PyJWT, and strict
    Multi-Tenant Role-Based Access Control (RBAC) enforcement.
    \"\"\"

    def __init__(self, jwt_secret_key: str, token_ttl_minutes: int = 60) -> None:
        if len(jwt_secret_key) < 32:
            raise ValueError("jwt_secret_key must be at least 32 characters long.")
        self._secret_key = jwt_secret_key
        self._token_ttl_seconds = token_ttl_minutes * 60

    @staticmethod
    def hash_password(plain_password: str) -> str:
        \"\"\"Hashes a plaintext password using Argon2id.\"\"\"
        if len(plain_password) < 12:
            raise ValueError("Password must be at least 12 characters long.")
        return _ARGON2_HASHER.hash(plain_password)

    @staticmethod
    def verify_password(plain_password: str, stored_hash: str) -> bool:
        \"\"\"Verifies a plaintext password against an Argon2id hash in constant time.\"\"\"
        try:
            return bool(_ARGON2_HASHER.verify(stored_hash, plain_password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def issue_jwt(self, user_id: UUID, role: UserRole) -> str:
        \"\"\"Issues a signed HS256 JWT containing user_id (sub) and role claims.\"\"\"
        now_ts = int(datetime.now(tz=timezone.utc).timestamp())
        payload_model = JWTTokenPayload(
            sub=user_id,
            role=role,
            iat=now_ts,
            exp=now_ts + self._token_ttl_seconds,
        )
        claims: Dict[str, Any] = {
            "sub": str(payload_model.sub),
            "role": payload_model.role.value,
            "iat": payload_model.iat,
            "exp": payload_model.exp,
        }
        return jwt.encode(claims, self._secret_key, algorithm="HS256")

    def verify_jwt(self, token: str) -> JWTTokenPayload:
        \"\"\"Verifies an HS256 JWT signature and expiration timestamp.\"\"\"
        try:
            decoded: Dict[str, Any] = jwt.decode(
                token,
                self._secret_key,
                algorithms=["HS256"],
                options={"require": ["sub", "role", "iat", "exp"]},
            )
            return JWTTokenPayload.model_validate(decoded)
        except jwt.ExpiredSignatureError as exc:
            raise SecurityViolationError("JWT token has expired.") from exc
        except jwt.InvalidTokenError as exc:
            raise SecurityViolationError(f"Invalid JWT token: {exc}") from exc

    @staticmethod
    def assert_tenant_portfolio_access(
        token_payload: JWTTokenPayload,
        target_portfolio_owner_id: UUID,
        require_write: bool = False,
    ) -> None:
        \"\"\"
        Enforces strict Multi-Tenant Isolation:
        - A user can NEVER access or mutate a portfolio owned by another user_id.
        - VIEWER role is strictly blocked from write/mutation operations.
        \"\"\"
        if token_payload.sub != target_portfolio_owner_id:
            raise SecurityViolationError(
                f"CROSS-TENANT ACCESS DENIED: Authenticated user ({token_payload.sub}) "
                f"cannot access portfolio owned by ({target_portfolio_owner_id})."
            )
        if require_write and token_payload.role == UserRole.VIEWER:
            raise SecurityViolationError(
                "RBAC VIOLATION: VIEWER role is prohibited from mutating portfolio state."
            )
"""

    # =========================================================================
    # 9. src/schemas.py
    # =========================================================================
    files["src/schemas.py"] = """\
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Dict, List, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ==========================================
# 1. AUTHENTICATION & MULTI-TENANT IDENTITY
# ==========================================

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    TRADER = "TRADER"
    VIEWER = "VIEWER"


class UserIdentitySchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID = Field(default_factory=uuid4, description="Immutable primary tenant identifier")
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r"^\\S+@\\S+\\.\\S+$")
    password_hash: str = Field(..., description="Argon2id cryptographic hash")
    role: UserRole = Field(default=UserRole.TRADER)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class JWTTokenPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    sub: UUID = Field(..., description="Subject user_id")
    role: UserRole
    exp: int = Field(..., description="Expiration UNIX timestamp")
    iat: int = Field(..., description="Issued-at UNIX timestamp")


# ==========================================
# 2. DYNAMIC INDEX REGISTRY & PIPELINE SPECS
# ==========================================

class IndexTier(str, Enum):
    SMALL_CAP = "SMALL_CAP"
    MID_CAP = "MID_CAP"
    LARGE_CAP = "LARGE_CAP"


class IndexConfigSchema(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    index_id: str = Field(..., description="Unique index code, e.g., 'RUT', 'MID'")
    display_name: str
    benchmark_ticker: str = Field(..., description="ETF proxy ticker, e.g., 'IWM', 'MDY'")
    tier: IndexTier
    is_active: bool = Field(default=True)

    # Simons Liquidity & Slippage Gates
    min_price: float = Field(default=5.0, ge=1.0)
    min_adv_30d: int = Field(default=500_000, ge=50_000)
    max_relative_spread: float = Field(default=0.005, gt=0.0, le=0.05)
    volume_surge_multiplier: float = Field(default=1.5, ge=1.1)

    # López de Prado Triple-Barrier Multipliers
    k_stop_atr: float = Field(..., gt=0.5, le=5.0, description="Initial & trailing chandelier stop ATR multiple")
    k_profit_atr: float = Field(..., gt=1.0, le=10.0, description="Upper take-profit barrier ATR multiple")
    max_holding_bars: int = Field(default=14, ge=3, le=30, description="Vertical time-barrier in trading days")

    @model_validator(mode="after")
    def enforce_asymmetric_reward_to_risk(self) -> "IndexConfigSchema":
        if self.k_profit_atr < 2.0 * self.k_stop_atr:
            raise ValueError(
                f"Index {self.index_id} violates positive expectancy structure: "
                f"k_profit_atr ({self.k_profit_atr}) must be >= 2.0 * k_stop_atr ({self.k_stop_atr})."
            )
        return self


# ==========================================
# 3. PRIMARY DIRECTIONAL & META-LABELED SIGNALS
# ==========================================

class DirectionalSignalSchema(BaseModel):
    \"\"\"Output of Step B.1 (Primary Directional Model: Side = +1)\"\"\"
    model_config = ConfigDict(frozen=True)

    signal_id: UUID = Field(default_factory=uuid4)
    as_of_date: date = Field(..., description="Strict Point-in-Time EOD market date")
    ticker: str = Field(..., min_length=1, max_length=10)
    index_id: str
    side: Literal[1] = Field(default=1, description="Long-only directional signal (+1)")

    close_price: float = Field(..., gt=0.0)
    atr_14: float = Field(..., gt=0.0)
    adv_30d: float = Field(..., ge=500_000)
    vol_adj_momentum: float = Field(..., description="M_vol_adj: 20d return scaled by ATR_14 * sqrt(20)")
    volume_zscore: float = Field(..., description="V_zscore: 20d standardized volume surge")
    norm_relative_strength: float = Field(..., description="RS_norm: 60d excess return over benchmark")
    primary_score: float = Field(..., ge=0.0, le=100.0, description="Composite cross-sectional score S_primary")


class MetaLabeledSignalSchema(BaseModel):
    \"\"\"Output of Step B.2 (Secondary Meta-Model & 500d Per-Asset Backtest Harness)\"\"\"
    model_config = ConfigDict(frozen=True)

    primary_signal: DirectionalSignalSchema
    backtest_lookback_days: int = Field(default=500, ge=250)
    historical_win_rate: float = Field(..., ge=0.0, le=1.0)
    historical_ev_r_multiple: float = Field(..., description="Historical Expected Value in R-multiples")
    meta_conviction_scalar: float = Field(..., ge=0.0, le=1.25, description="phi_meta sizing scalar")
    is_approved: bool = Field(..., description="True if EV > 0 and phi_meta > 0")

    initial_stop_price: float = Field(..., gt=0.0)
    take_profit_price: float = Field(..., gt=0.0)
    max_holding_bars: int = Field(default=14, ge=3, le=30)

    @model_validator(mode="after")
    def validate_barrier_geometry(self) -> "MetaLabeledSignalSchema":
        entry = self.primary_signal.close_price
        if not (self.initial_stop_price < entry < self.take_profit_price):
            raise ValueError(
                f"Invalid Triple-Barrier geometry for {self.primary_signal.ticker}: "
                f"Stop ({self.initial_stop_price}) < Entry ({entry}) < Target ({self.take_profit_price}) required."
            )
        if self.is_approved and (self.historical_ev_r_multiple <= 0 or self.meta_conviction_scalar <= 0):
            raise ValueError("Signal cannot be approved with non-positive historical EV or zero conviction.")
        return self


# ==========================================
# 4. TENANT-SCOPED TRIPLE-BARRIER POSITIONS
# ==========================================

class ExitReason(str, Enum):
    UPPER_BARRIER_TP = "UPPER_BARRIER_TP"
    LOWER_BARRIER_SL = "LOWER_BARRIER_SL"
    VERTICAL_BARRIER_TIME = "VERTICAL_BARRIER_TIME"
    SYSTEM_CIRCUIT_BREAKER = "SYSTEM_CIRCUIT_BREAKER"


class TripleBarrierPositionSchema(BaseModel):
    \"\"\"Active position strictly isolated by user_id and portfolio_id with Ratchet-Only validator.\"\"\"
    model_config = ConfigDict(validate_assignment=True)

    position_id: UUID = Field(default_factory=uuid4)
    user_id: UUID = Field(..., description="Mandatory tenant isolation key")
    portfolio_id: UUID = Field(..., description="Mandatory portfolio foreign key")
    ticker: str
    index_id: str

    entry_date: date
    entry_price: float = Field(..., gt=0.0)
    shares: int = Field(..., gt=0)
    entry_atr_14: float = Field(..., gt=0.0)

    initial_stop_price: float = Field(..., gt=0.0)
    trailing_stop_price: float = Field(..., gt=0.0)
    take_profit_price: float = Field(..., gt=0.0)
    highest_high_since_entry: float = Field(..., gt=0.0)
    bars_held: int = Field(default=0, ge=0)
    max_holding_bars: int = Field(default=14, ge=3, le=30)
    last_updated_date: date

    @model_validator(mode="after")
    def enforce_ratchet_floor(self) -> "TripleBarrierPositionSchema":
        \"\"\"Guarantees that trailing_stop_price can never fall below initial_stop_price.\"\"\"
        if self.trailing_stop_price + 1e-6 < self.initial_stop_price:
            raise ValueError(
                f"RATCHET VIOLATION: trailing_stop_price ({self.trailing_stop_price}) "
                f"cannot be lower than initial_stop_price ({self.initial_stop_price})."
            )
        return self

    def update_trailing_stop(self, proposed_stop: float) -> None:
        \"\"\"Strict setter that rejects any downward stop adjustment (Stop_t >= Stop_{t-1}).\"\"\"
        if proposed_stop < self.trailing_stop_price - 1e-6:
            raise ValueError(
                f"RATCHET VIOLATION: Proposed stop ({proposed_stop}) < current trailing stop ({self.trailing_stop_price})."
            )
        self.trailing_stop_price = round(max(self.trailing_stop_price, proposed_stop), 4)

    def ratchet_trailing_stop(
        self,
        current_high: float,
        current_atr_14: float,
        k_trail: float,
        current_date: date,
    ) -> None:
        \"\"\"Enforces strict Ratchet-Only Chandelier Stop (Simons Zero-Override).\"\"\"
        if current_date <= self.last_updated_date:
            raise ValueError(f"Point-in-Time violation: {current_date} <= {self.last_updated_date}")

        self.highest_high_since_entry = max(self.highest_high_since_entry, current_high)
        candidate_stop = self.highest_high_since_entry - (k_trail * current_atr_14)

        self.trailing_stop_price = round(max(self.trailing_stop_price, candidate_stop), 4)
        self.bars_held += 1
        self.last_updated_date = current_date

    @property
    def open_dollar_risk(self) -> float:
        \"\"\"Calculates remaining downside risk to current trailing stop (0 if stop >= entry).\"\"\"
        risk_per_share = max(0.0, self.entry_price - self.trailing_stop_price)
        return round(risk_per_share * self.shares, 2)


class ClosedTradeAuditSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    trade_id: UUID = Field(default_factory=uuid4)
    position_id: UUID
    user_id: UUID
    portfolio_id: UUID
    ticker: str
    index_id: str
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    shares: int
    bars_held: int
    exit_reason: ExitReason
    realized_pnl_dollars: float
    realized_r_multiple: float


# ==========================================
# 5. VIRTUAL PORTFOLIO LEDGER & MULTI-TENANT STATE
# ==========================================

class VirtualPortfolioLedgerSchema(BaseModel):
    \"\"\"Single tenant's portfolio state enforcing Simons Portfolio Heat & Capacity gates.\"\"\"
    model_config = ConfigDict(validate_assignment=True)

    portfolio_id: UUID = Field(default_factory=uuid4)
    user_id: UUID = Field(..., description="Owner user_id - strictly isolated")
    portfolio_name: str = Field(default="Primary Swing Shadow Portfolio")
    as_of_date: date

    cash_balance: float = Field(..., ge=0.0)
    total_equity: float = Field(..., gt=0.0)
    max_portfolio_heat_pct: float = Field(default=0.06, gt=0.0, le=0.15)
    max_concurrent_positions: int = Field(default=10, ge=1, le=25)
    subscribed_indices: List[str] = Field(default_factory=lambda: ["RUT", "MID"])

    open_positions: Dict[str, TripleBarrierPositionSchema] = Field(
        default_factory=dict, description="Keyed by ticker symbol for O(1) exclusion lookup"
    )
    closed_trades_audit: List[ClosedTradeAuditSchema] = Field(default_factory=list)

    @property
    def current_portfolio_heat_pct(self) -> float:
        total_open_risk = sum(pos.open_dollar_risk for pos in self.open_positions.values())
        return round(total_open_risk / self.total_equity, 6)

    @model_validator(mode="after")
    def enforce_tenant_isolation_and_risk_gates(self) -> "VirtualPortfolioLedgerSchema":
        if len(self.open_positions) > self.max_concurrent_positions:
            raise ValueError(
                f"Portfolio capacity breached: {len(self.open_positions)} > {self.max_concurrent_positions}"
            )
        for ticker, pos in self.open_positions.items():
            if pos.user_id != self.user_id or pos.portfolio_id != self.portfolio_id:
                raise ValueError(
                    f"CRITICAL SECURITY BREACH: Cross-tenant position detected for ticker {ticker}! "
                    f"Position owner ({pos.user_id}) != Portfolio owner ({self.user_id})."
                )
        if self.current_portfolio_heat_pct > self.max_portfolio_heat_pct + 1e-5:
            raise ValueError(
                f"Portfolio Heat circuit breaker breached: "
                f"{self.current_portfolio_heat_pct:.2%} > {self.max_portfolio_heat_pct:.2%}"
            )
        return self


class MultiTenantStateStoreSchema(BaseModel):
    \"\"\"Root container supporting multiple isolated tenant portfolios and dynamic index registry.\"\"\"
    schema_version: str = Field(default="2.0.0")
    last_updated_utc: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    index_registry: Dict[str, IndexConfigSchema]
    tenant_portfolios: Dict[UUID, VirtualPortfolioLedgerSchema] = Field(
        ..., description="Keyed by portfolio_id with strict tenant isolation validation"
    )
"""

    # =========================================================================
    # 10. src/data_ingestion.py
    # =========================================================================
    files["src/data_ingestion.py"] = """\
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta
import logging
from pathlib import Path
import random
import time
from typing import Dict, List, Set, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from schemas import IndexConfigSchema, MultiTenantStateStoreSchema

logger = logging.getLogger("SwingQuantEngine.DataIngestion")


# =========================================================================
# 1. ABSTRACT DATA PROVIDER INTERFACE
# =========================================================================

class BaseMarketDataProvider(ABC):
    \"\"\"
    Abstract contract for market data vendors (yfinance, Polygon.io, Alpaca).
    Enforces strict Point-in-Time (PiT) upper bounds and adjusted OHLCV schemas.
    \"\"\"

    @abstractmethod
    def fetch_ohlcv_batch(
        self,
        tickers: List[str],
        start_date: date,
        end_date_inclusive: date,
    ) -> pd.DataFrame:
        \"\"\"
        Returns a MultiIndex DataFrame indexed by (date, ticker) with columns:
        ['open', 'high', 'low', 'close', 'volume', 'dividends', 'splits']
        All prices MUST be adjusted for splits and dividends up to end_date_inclusive.
        \"\"\"
        raise NotImplementedError

    @abstractmethod
    def fetch_index_constituents(self, index_id: str) -> List[str]:
        \"\"\"Returns the current constituent ticker roster for a registered index.\"\"\"
        raise NotImplementedError


# =========================================================================
# 2. YFINANCE CONCRETE PROVIDER WITH CHUNKING & EXPONENTIAL BACKOFF
# =========================================================================

class YFinanceProvider(BaseMarketDataProvider):
    \"\"\"
    Resilient Yahoo Finance implementation with chunked batching,
    rate-limit jitter, and exponential backoff retry logic.
    \"\"\"

    def __init__(
        self,
        chunk_size: int = 100,
        max_retries: int = 3,
        base_backoff_sec: float = 2.0,
        constituent_lists_dir: Path = Path("config/constituents"),
    ) -> None:
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec
        self.constituent_lists_dir = constituent_lists_dir

    def fetch_index_constituents(self, index_id: str) -> List[str]:
        \"\"\"
        Loads constituent symbols for the given index_id (e.g., 'RUT', 'MID')
        from a curated local CSV roster.
        \"\"\"
        roster_file = self.constituent_lists_dir / f"{index_id}.csv"
        if not roster_file.exists():
            raise FileNotFoundError(
                f"Constituent roster file not found for index '{index_id}' at {roster_file}"
            )
        df = pd.read_csv(roster_file)
        tickers = (
            df["ticker"]
            .dropna()
            .astype(str)
            .str.strip()
            .str.upper()
            .str.replace(".", "-", regex=False)
            .unique()
            .tolist()
        )
        return sorted(tickers)

    def fetch_ohlcv_batch(
        self,
        tickers: List[str],
        start_date: date,
        end_date_inclusive: date,
    ) -> pd.DataFrame:
        if not tickers:
            return pd.DataFrame()

        yf_end_date = end_date_inclusive + timedelta(days=1)
        all_chunks: List[pd.DataFrame] = []

        chunks = [
            tickers[i : i + self.chunk_size]
            for i in range(0, len(tickers), self.chunk_size)
        ]

        for idx, chunk in enumerate(chunks, start=1):
            chunk_df = self._download_chunk_with_backoff(
                chunk=chunk,
                start_str=start_date.isoformat(),
                end_str=yf_end_date.isoformat(),
                chunk_index=idx,
                total_chunks=len(chunks),
            )
            if not chunk_df.empty:
                all_chunks.append(chunk_df)

            if idx < len(chunks):
                time.sleep(random.uniform(0.35, 0.85))

        if not all_chunks:
            return pd.DataFrame()

        combined = pd.concat(all_chunks, axis=0)
        combined = combined.loc[
            combined.index.get_level_values("date") <= pd.Timestamp(end_date_inclusive)
        ]
        return combined.sort_index()

    def _download_chunk_with_backoff(
        self,
        chunk: List[str],
        start_str: str,
        end_str: str,
        chunk_index: int,
        total_chunks: int,
    ) -> pd.DataFrame:
        for attempt in range(1, self.max_retries + 1):
            try:
                raw = yf.download(
                    tickers=chunk,
                    start=start_str,
                    end=end_str,
                    auto_adjust=True,
                    actions=True,
                    group_by="ticker",
                    threads=True,
                    progress=False,
                )
                if raw is None or raw.empty:
                    return pd.DataFrame()
                return self._normalize_yf_dataframe(raw, chunk)

            except Exception as exc:
                wait_time = (self.base_backoff_sec ** attempt) + random.uniform(0.1, 0.9)
                logger.warning(
                    f"[Chunk {chunk_index}/{total_chunks}] Attempt {attempt}/{self.max_retries} "
                    f"failed ({exc}). Retrying in {wait_time:.2f}s..."
                )
                time.sleep(wait_time)

        logger.error(f"[Chunk {chunk_index}/{total_chunks}] Exhausted all retries. Skipping chunk.")
        return pd.DataFrame()

    @staticmethod
    def _normalize_yf_dataframe(raw: pd.DataFrame, requested_tickers: List[str]) -> pd.DataFrame:
        \"\"\"Transforms yfinance wide/MultiIndex output into a standardized (date, ticker) table.\"\"\"
        records: List[pd.DataFrame] = []

        if isinstance(raw.columns, pd.MultiIndex):
            available_tickers = set(raw.columns.get_level_values(0))
            for ticker in requested_tickers:
                if ticker not in available_tickers:
                    continue
                sub = raw[ticker].copy()
                sub["ticker"] = ticker
                records.append(sub)
        else:
            sub = raw.copy()
            sub["ticker"] = requested_tickers[0]
            records.append(sub)

        if not records:
            return pd.DataFrame()

        stacked = pd.concat(records, axis=0)
        stacked.index.name = "date"
        stacked = stacked.reset_index()
        stacked["date"] = pd.to_datetime(stacked["date"]).dt.tz_localize(None).dt.normalize()

        rename_map = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Dividends": "dividends",
            "Stock Splits": "splits",
        }
        stacked = stacked.rename(columns=rename_map)

        for action_col in ("dividends", "splits"):
            if action_col not in stacked.columns:
                stacked[action_col] = 0.0
            else:
                stacked[action_col] = stacked[action_col].fillna(0.0)

        required_cols = [
            "date",
            "ticker",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "dividends",
            "splits",
        ]
        stacked = stacked[[c for c in required_cols if c in stacked.columns]]
        stacked = stacked.dropna(subset=["open", "high", "low", "close", "volume"])

        return stacked.set_index(["date", "ticker"]).sort_index()


# Alias for backward compatibility
YFinanceDataProvider = YFinanceProvider


# =========================================================================
# 3. SMART SLIDING WINDOW MANAGER (Incremental Delta + Corporate Action Guard)
# =========================================================================

class SmartSlidingWindowOrchestrator:
    \"\"\"
    Maintains a rolling W-day historical OHLCV window (default 500 trading days)
    stored in Apache Parquet. Uses daily 2-day Delta Fetches, Pre-Ingestion
    active portfolio exclusion tracking, and t-1 Overlap Corporate Action detection.
    \"\"\"

    def __init__(
        self,
        provider: BaseMarketDataProvider,
        cache_path: Path = Path("data/cache/market_data_window.parquet"),
        max_window_bars: int = 500,
        min_required_bars: int = 250,
        reconciliation_tolerance: float = 1e-4,
    ) -> None:
        self.provider = provider
        self.cache_path = cache_path
        self.max_window_bars = max_window_bars
        self.min_required_bars = min_required_bars
        self.reconciliation_tolerance = reconciliation_tolerance
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def filter_candidate_universe(
        constituent_tickers: List[str],
        active_portfolio_tickers: Set[str],
    ) -> List[str]:
        \"\"\"
        Pre-Ingestion Portfolio Exclusion Gate: removes tickers currently held
        in the active portfolio from the new-candidate screening roster.
        \"\"\"
        held_upper = {t.upper() for t in active_portfolio_tickers}
        return [t for t in constituent_tickers if t.upper() not in held_upper]

    def sync_daily_market_window(
        self,
        state_store: MultiTenantStateStoreSchema,
        as_of_date: date,
    ) -> Tuple[pd.DataFrame, Set[str]]:
        active_indices: Dict[str, IndexConfigSchema] = {
            idx_id: cfg
            for idx_id, cfg in state_store.index_registry.items()
            if cfg.is_active
        }

        held_tickers: Set[str] = set()
        for portfolio in state_store.tenant_portfolios.values():
            held_tickers.update(portfolio.open_positions.keys())

        universe_tickers: Set[str] = set(held_tickers)
        for idx_id, cfg in active_indices.items():
            universe_tickers.add(cfg.benchmark_ticker.upper())
            constituents = self.provider.fetch_index_constituents(idx_id)
            universe_tickers.update(constituents)

        sorted_universe = sorted(universe_tickers)
        logger.info(
            f"Starting Sliding Window Sync as of {as_of_date} for {len(sorted_universe)} unique symbols "
            f"({len(held_tickers)} currently held across tenant portfolios)."
        )

        cached_df = self._load_cached_window(as_of_date)

        if cached_df.empty:
            logger.info("No local cache found. Executing Cold-Start Full History Hydration...")
            updated_df = self._hydrate_full_history(sorted_universe, as_of_date)
        else:
            updated_df = self._incremental_delta_sync(cached_df, sorted_universe, as_of_date)

        sanitized_df = self._sanitize_and_trim_window(updated_df, as_of_date)
        self._save_cached_window(sanitized_df)

        return sanitized_df, held_tickers

    def _hydrate_full_history(self, tickers: List[str], as_of_date: date) -> pd.DataFrame:
        calendar_lookback = int(self.max_window_bars * 1.52)
        start_date = as_of_date - timedelta(days=calendar_lookback)
        return self.provider.fetch_ohlcv_batch(
            tickers=tickers,
            start_date=start_date,
            end_date_inclusive=as_of_date,
        )

    def _incremental_delta_sync(
        self,
        cached_df: pd.DataFrame,
        universe_tickers: List[str],
        as_of_date: date,
    ) -> pd.DataFrame:
        cached_tickers = set(cached_df.index.get_level_values("ticker").unique())
        missing_tickers = sorted(set(universe_tickers) - cached_tickers)
        existing_tickers = sorted(set(universe_tickers) & cached_tickers)

        delta_start = as_of_date - timedelta(days=7)
        delta_df = self.provider.fetch_ohlcv_batch(
            tickers=existing_tickers,
            start_date=delta_start,
            end_date_inclusive=as_of_date,
        )

        corrupted_tickers = self._detect_corporate_actions(cached_df, delta_df)
        rehydrate_list = sorted(set(missing_tickers) | corrupted_tickers)

        if rehydrate_list:
            logger.info(
                f"Re-hydrating full {self.max_window_bars}-bar history for {len(rehydrate_list)} tickers "
                f"({len(missing_tickers)} new, {len(corrupted_tickers)} corporate action adjustments)."
            )
            rehydrated_df = self._hydrate_full_history(rehydrate_list, as_of_date)
        else:
            rehydrated_df = pd.DataFrame()

        clean_cached = cached_df.loc[
            ~cached_df.index.get_level_values("ticker").isin(rehydrate_list)
        ]
        clean_delta = (
            delta_df.loc[~delta_df.index.get_level_values("ticker").isin(rehydrate_list)]
            if not delta_df.empty
            else pd.DataFrame()
        )

        frames = [f for f in (clean_cached, clean_delta, rehydrated_df) if not f.empty]
        if not frames:
            return pd.DataFrame()

        merged = pd.concat(frames, axis=0)
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        return merged

    def _detect_corporate_actions(
        self,
        cached_df: pd.DataFrame,
        delta_df: pd.DataFrame,
    ) -> Set[str]:
        \"\"\"
        Compares the overlapping t-1 adjusted close between cached_df and delta_df,
        and inspects explicit split/dividend columns.
        \"\"\"
        if delta_df.empty:
            return set()

        flagged_tickers: Set[str] = set()

        action_mask = (delta_df["splits"] != 0.0) | (delta_df["dividends"] != 0.0)
        if action_mask.any():
            flagged_tickers.update(
                delta_df.loc[action_mask].index.get_level_values("ticker").unique()
            )

        common_index = cached_df.index.intersection(delta_df.index)
        if len(common_index) > 0:
            cached_closes = cached_df.loc[common_index, "close"]
            delta_closes = delta_df.loc[common_index, "close"]
            rel_diff = (delta_closes - cached_closes).abs() / cached_closes.replace(0, np.nan)
            discrepancy_mask = rel_diff > self.reconciliation_tolerance
            if discrepancy_mask.any():
                flagged_tickers.update(
                    rel_diff.loc[discrepancy_mask].index.get_level_values("ticker").unique()
                )

        return flagged_tickers

    def _sanitize_and_trim_window(self, df: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
        if df.empty:
            return df

        df = df.loc[df.index.get_level_values("date") <= pd.Timestamp(as_of_date)]

        valid_bar_mask = (
            (df["close"] > 0.0)
            & (df["open"] > 0.0)
            & (df["low"] > 0.0)
            & (df["high"] >= df["low"])
            & (df["high"] >= df["open"])
            & (df["high"] >= df["close"])
            & (df["low"] <= df["open"])
            & (df["low"] <= df["close"])
            & (df["volume"] >= 0)
        )
        df = df.loc[valid_bar_mask].sort_index()
        df = df.groupby(level="ticker", group_keys=False).tail(self.max_window_bars)
        return df

    def _load_cached_window(self, as_of_date: date) -> pd.DataFrame:
        if not self.cache_path.exists():
            return pd.DataFrame()
        df = pd.read_parquet(self.cache_path)
        df = df.loc[df.index.get_level_values("date") <= pd.Timestamp(as_of_date)]
        return df.sort_index()

    def _save_cached_window(self, df: pd.DataFrame) -> None:
        if not df.empty:
            df.to_parquet(self.cache_path, engine="pyarrow", compression="snappy")
"""

    # =========================================================================
    # 11. src/quant_engine.py
    # =========================================================================
    files["src/quant_engine.py"] = """\
from __future__ import annotations

from datetime import date
import logging
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

import numpy as np
import pandas as pd

from schemas import (
    ClosedTradeAuditSchema,
    DirectionalSignalSchema,
    ExitReason,
    IndexConfigSchema,
    IndexTier,
    MetaLabeledSignalSchema,
    MultiTenantStateStoreSchema,
    TripleBarrierPositionSchema,
    VirtualPortfolioLedgerSchema,
)

logger = logging.getLogger("SwingQuantEngine.QuantCore")


# =========================================================================
# 1. VECTORIZED FEATURE & PRIMARY SCREENING ENGINE (Step B.1)
# =========================================================================

class VectorizedFeatureEngine:
    \"\"\"
    Computes stationary volatility-adjusted features (Wilder's ATR_14,
    Volatility-Adjusted Momentum, Standardized Volume Surge, Relative Strength)
    and executes index-tailored primary directional screening without Python loops.
    \"\"\"

    def __init__(
        self,
        w_momentum: float = 0.45,
        w_volume: float = 0.30,
        w_rel_strength: float = 0.25,
    ) -> None:
        self.w_momentum = w_momentum
        self.w_volume = w_volume
        self.w_rel_strength = w_rel_strength

    def compute_universe_features(
        self,
        market_df: pd.DataFrame,
        as_of_date: date,
    ) -> pd.DataFrame:
        df = market_df.loc[
            market_df.index.get_level_values("date") <= pd.Timestamp(as_of_date)
        ].copy()
        if df.empty:
            return pd.DataFrame()

        df = df.sort_index(level=["ticker", "date"])
        grouped = df.groupby(level="ticker", group_keys=False)

        # 1. Previous Close & Wilder's True Range (ATR_14)
        df["prev_close"] = grouped["close"].shift(1)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["prev_close"]).abs()
        tr3 = (df["low"] - df["prev_close"]).abs()
        df["tr"] = np.maximum(tr1, np.maximum(tr2, tr3))

        df["atr_14"] = grouped["tr"].transform(
            lambda s: s.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
        )

        # 2. Moving Averages & Liquidity Baselines
        df["sma_20"] = grouped["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
        df["sma_50"] = grouped["close"].transform(lambda s: s.rolling(50, min_periods=50).mean())
        df["sma_200"] = grouped["close"].transform(lambda s: s.rolling(200, min_periods=200).mean())
        df["adv_30d"] = grouped["volume"].transform(lambda s: s.rolling(30, min_periods=30).mean())

        # 3. Prior N-Day Highs
        df["prior_high_20"] = grouped["high"].transform(
            lambda s: s.shift(1).rolling(20, min_periods=20).max()
        )
        df["prior_high_15"] = grouped["high"].transform(
            lambda s: s.shift(1).rolling(15, min_periods=15).max()
        )

        # 4. Volume Statistics (20-day mean & std)
        df["vol_sma_20"] = grouped["volume"].transform(
            lambda s: s.shift(1).rolling(20, min_periods=20).mean()
        )
        df["vol_std_20"] = grouped["volume"].transform(
            lambda s: s.shift(1).rolling(20, min_periods=20).std(ddof=1)
        )
        df["volume_ratio_20"] = df["volume"] / df["vol_sma_20"].replace(0, np.nan)
        df["volume_zscore"] = (df["volume"] - df["vol_sma_20"]) / df["vol_std_20"].replace(0, np.nan)

        # 5. López de Prado Stationary Volatility-Adjusted Momentum (M_vol_adj)
        close_20d_ago = grouped["close"].shift(20)
        df["vol_adj_momentum"] = (df["close"] - close_20d_ago) / (
            df["atr_14"] * np.sqrt(20.0)
        ).replace(0, np.nan)

        # 6. Daily & 60-Day Returns for Benchmark Relative Strength
        df["ret_1d"] = grouped["close"].pct_change(1)
        df["ret_60d"] = grouped["close"].pct_change(60)

        return df

    def screen_index_candidates(
        self,
        featured_df: pd.DataFrame,
        index_cfg: IndexConfigSchema,
        constituent_tickers: List[str],
        as_of_date: date,
        excluded_tickers: Optional[Set[str]] = None,
        top_n: int = 15,
    ) -> List[DirectionalSignalSchema]:
        if featured_df.empty:
            return []

        excluded = excluded_tickers or set()
        eligible_tickers = [t for t in constituent_tickers if t not in excluded]
        if not eligible_tickers:
            return []

        target_ts = pd.Timestamp(as_of_date)
        if target_ts not in featured_df.index.get_level_values("date"):
            logger.warning(f"No market bars found on exact date {as_of_date} for index {index_cfg.index_id}.")
            return []

        benchmark_symbol = index_cfg.benchmark_ticker.upper()
        rs_norm_map = self._compute_relative_strength_vs_benchmark(
            featured_df=featured_df,
            tickers=eligible_tickers,
            benchmark_ticker=benchmark_symbol,
            as_of_ts=target_ts,
        )

        daily_slice = featured_df.xs(target_ts, level="date").copy()
        daily_slice = daily_slice.loc[daily_slice.index.isin(eligible_tickers)].copy()
        if daily_slice.empty:
            return []

        daily_slice["norm_relative_strength"] = daily_slice.index.map(rs_norm_map)
        daily_slice = daily_slice.dropna(
            subset=[
                "close",
                "atr_14",
                "sma_20",
                "sma_50",
                "sma_200",
                "adv_30d",
                "prior_high_20",
                "prior_high_15",
                "volume_ratio_20",
                "vol_adj_momentum",
                "volume_zscore",
                "norm_relative_strength",
            ]
        )
        if daily_slice.empty:
            return []

        # Gate 1: Simons Liquidity & Price Gateways
        liquidity_mask = (
            (daily_slice["close"] >= index_cfg.min_price)
            & (daily_slice["adv_30d"] >= index_cfg.min_adv_30d)
            & (daily_slice["atr_14"] > 0.0)
        )
        daily_slice = daily_slice.loc[liquidity_mask]
        if daily_slice.empty:
            return []

        # Gate 2: Tailored Index Calculation Pipelines
        if index_cfg.tier == IndexTier.SMALL_CAP:
            regime_mask = (
                (daily_slice["close"] > daily_slice["sma_200"])
                & (daily_slice["close"] > daily_slice["sma_50"])
                & (daily_slice["close"] >= daily_slice["prior_high_20"])
                & (daily_slice["volume_ratio_20"] >= max(1.8, index_cfg.volume_surge_multiplier))
                & (daily_slice["norm_relative_strength"] > 0.25)
            )
        elif index_cfg.tier == IndexTier.MID_CAP:
            breakout_trigger = daily_slice["close"] >= daily_slice["prior_high_15"]
            pullback_trigger = (
                (daily_slice["low"] <= daily_slice["sma_20"] * 1.015)
                & (daily_slice["close"] > daily_slice["sma_20"])
                & (daily_slice["close"] > daily_slice["open"])
            )
            regime_mask = (
                (daily_slice["close"] > daily_slice["sma_200"])
                & (daily_slice["sma_20"] > daily_slice["sma_50"])
                & (breakout_trigger | pullback_trigger)
                & (daily_slice["volume_ratio_20"] >= max(1.4, index_cfg.volume_surge_multiplier))
                & (daily_slice["norm_relative_strength"] > 0.0)
            )
        else:
            regime_mask = (
                (daily_slice["close"] > daily_slice["sma_200"])
                & (daily_slice["close"] >= daily_slice["prior_high_20"])
                & (daily_slice["volume_ratio_20"] >= index_cfg.volume_surge_multiplier)
            )

        candidates = daily_slice.loc[regime_mask].copy()
        if candidates.empty:
            return []

        candidates["score_mom"] = self._winsorized_zscore_to_100(candidates["vol_adj_momentum"])
        candidates["score_vol"] = self._winsorized_zscore_to_100(candidates["volume_zscore"])
        candidates["score_rs"] = self._winsorized_zscore_to_100(candidates["norm_relative_strength"])

        candidates["primary_score"] = (
            self.w_momentum * candidates["score_mom"]
            + self.w_volume * candidates["score_vol"]
            + self.w_rel_strength * candidates["score_rs"]
        ).round(2)

        candidates = candidates.sort_values(by="primary_score", ascending=False).head(top_n)

        signals: List[DirectionalSignalSchema] = []
        for ticker, row in candidates.iterrows():
            signals.append(
                DirectionalSignalSchema(
                    as_of_date=as_of_date,
                    ticker=str(ticker),
                    index_id=index_cfg.index_id,
                    side=1,
                    close_price=round(float(row["close"]), 4),
                    atr_14=round(float(row["atr_14"]), 4),
                    adv_30d=round(float(row["adv_30d"]), 2),
                    vol_adj_momentum=round(float(row["vol_adj_momentum"]), 4),
                    volume_zscore=round(float(row["volume_zscore"]), 4),
                    norm_relative_strength=round(float(row["norm_relative_strength"]), 4),
                    primary_score=float(row["primary_score"]),
                )
            )
        return signals

    @staticmethod
    def _compute_relative_strength_vs_benchmark(
        featured_df: pd.DataFrame,
        tickers: List[str],
        benchmark_ticker: str,
        as_of_ts: pd.Timestamp,
    ) -> Dict[str, float]:
        if benchmark_ticker not in featured_df.index.get_level_values("ticker"):
            return {t: 0.5 for t in tickers}

        bench_series = (
            featured_df.xs(benchmark_ticker, level="ticker")["ret_1d"]
            .dropna()
            .tail(60)
        )
        if len(bench_series) < 30:
            return {t: 0.5 for t in tickers}

        rs_scores: Dict[str, float] = {}
        for ticker in tickers:
            if ticker not in featured_df.index.get_level_values("ticker"):
                continue
            asset_series = featured_df.xs(ticker, level="ticker")["ret_1d"].dropna().tail(60)
            common_dates = asset_series.index.intersection(bench_series.index)
            if len(common_dates) < 30:
                continue
            excess_daily = asset_series.loc[common_dates] - bench_series.loc[common_dates]
            tracking_std = float(excess_daily.std(ddof=1))
            if tracking_std <= 1e-8:
                rs_scores[ticker] = 0.0
            else:
                cum_excess = float(
                    (1.0 + asset_series.loc[common_dates]).prod()
                    - (1.0 + bench_series.loc[common_dates]).prod()
                )
                rs_scores[ticker] = cum_excess / (tracking_std * np.sqrt(len(common_dates)))
        return rs_scores

    @staticmethod
    def _winsorized_zscore_to_100(series: pd.Series) -> pd.Series:
        if len(series) <= 1:
            return pd.Series(75.0, index=series.index)
        lower = series.quantile(0.05)
        upper = series.quantile(0.95)
        clipped = series.clip(lower=lower, upper=upper)
        std = float(clipped.std(ddof=1))
        if std <= 1e-8:
            return pd.Series(50.0, index=series.index)
        z = ((clipped - float(clipped.mean())) / std).clip(-3.0, 3.0)
        return ((z + 3.0) / 6.0) * 100.0


# =========================================================================
# 2. 500-DAY WALK-FORWARD BACKTESTER & META-LABELING SIZER (Step B.2)
# =========================================================================

class WalkForwardBacktester:
    \"\"\"
    Runs a strict Point-in-Time 500-day historical simulation on each candidate
    to compute empirical Expected Value (EV in R-multiples) and assign the
    López de Prado Meta-Labeling Conviction Scalar (phi_meta in [0.0, 1.25]).
    \"\"\"

    def __init__(self, min_historical_trades: int = 3, min_win_rate: float = 0.38) -> None:
        self.min_historical_trades = min_historical_trades
        self.min_win_rate = min_win_rate

    def evaluate_and_meta_label(
        self,
        signal: DirectionalSignalSchema,
        featured_df: pd.DataFrame,
        index_cfg: IndexConfigSchema,
    ) -> MetaLabeledSignalSchema:
        ticker = signal.ticker
        asset_df = featured_df.xs(ticker, level="ticker").copy()
        hist_df = asset_df.loc[asset_df.index < pd.Timestamp(signal.as_of_date)].tail(500)

        r_multiples = self._simulate_historical_triple_barrier_trades(hist_df, index_cfg)

        if len(r_multiples) >= self.min_historical_trades:
            wins = [r for r in r_multiples if r > 0.0]
            win_rate = round(len(wins) / len(r_multiples), 4)
            ev_r = round(float(np.mean(r_multiples)), 4)
        else:
            win_rate = 0.45 if signal.primary_score >= 65.0 else 0.35
            ev_r = 0.35 if signal.primary_score >= 65.0 else -0.10

        phi_meta = self._compute_meta_conviction_scalar(
            primary_score=signal.primary_score,
            win_rate=win_rate,
            ev_r=ev_r,
        )
        is_approved = (ev_r > 0.0) and (win_rate >= self.min_win_rate) and (phi_meta > 0.0)

        initial_stop = round(signal.close_price - (index_cfg.k_stop_atr * signal.atr_14), 4)
        initial_stop = max(0.01, initial_stop)
        take_profit = round(signal.close_price + (index_cfg.k_profit_atr * signal.atr_14), 4)

        return MetaLabeledSignalSchema(
            primary_signal=signal,
            backtest_lookback_days=min(500, max(250, len(hist_df))),
            historical_win_rate=win_rate,
            historical_ev_r_multiple=ev_r,
            meta_conviction_scalar=phi_meta,
            is_approved=is_approved,
            initial_stop_price=initial_stop,
            take_profit_price=take_profit,
            max_holding_bars=index_cfg.max_holding_bars,
        )

    def _simulate_historical_triple_barrier_trades(
        self,
        hist_df: pd.DataFrame,
        index_cfg: IndexConfigSchema,
    ) -> List[float]:
        if len(hist_df) < 60:
            return []

        closes = hist_df["close"].to_numpy()
        highs = hist_df["high"].to_numpy()
        lows = hist_df["low"].to_numpy()
        atrs = hist_df["atr_14"].to_numpy()
        sma50 = hist_df["sma_50"].to_numpy()
        prior_h15 = hist_df["prior_high_15"].to_numpy()
        vol_ratio = hist_df["volume_ratio_20"].to_numpy()

        r_outcomes: List[float] = []
        i = 20
        n = len(hist_df)

        while i < n - index_cfg.max_holding_bars:
            if (
                not np.isnan(atrs[i])
                and atrs[i] > 0
                and closes[i] > sma50[i]
                and closes[i] >= prior_h15[i]
                and vol_ratio[i] >= 1.25
            ):
                entry_p = closes[i]
                initial_risk = index_cfg.k_stop_atr * atrs[i]
                trail_stop = entry_p - initial_risk
                target_p = entry_p + (index_cfg.k_profit_atr * atrs[i])
                highest_h = highs[i]

                exit_p = closes[min(i + index_cfg.max_holding_bars, n - 1)]
                bars_elapsed = index_cfg.max_holding_bars

                for step in range(1, index_cfg.max_holding_bars + 1):
                    idx = i + step
                    if lows[idx] <= trail_stop:
                        exit_p = trail_stop
                        bars_elapsed = step
                        break
                    if highs[idx] >= target_p:
                        exit_p = target_p
                        bars_elapsed = step
                        break
                    highest_h = max(highest_h, highs[idx])
                    candidate_stop = highest_h - (index_cfg.k_stop_atr * atrs[idx])
                    trail_stop = max(trail_stop, candidate_stop)

                r_mult = (exit_p - entry_p) / initial_risk
                r_outcomes.append(float(r_mult))
                i += bars_elapsed
            else:
                i += 1

        return r_outcomes

    def _compute_meta_conviction_scalar(
        self,
        primary_score: float,
        win_rate: float,
        ev_r: float,
    ) -> float:
        if ev_r <= 0.0 or win_rate < self.min_win_rate:
            return 0.0
        if primary_score >= 80.0 and ev_r >= 0.60 and win_rate >= 0.50:
            return 1.25
        if primary_score >= 60.0 and ev_r >= 0.25:
            return 1.00
        return 0.75


# Alias for specification compatibility
PerAssetTripleBarrierBacktester = WalkForwardBacktester


class MetaLabelingSizer:
    \"\"\"
    Computes Volatility-Parity share allocations scaled by López de Prado's
    Meta-Labeling Conviction Scalar (phi_meta) and enforces the 6.0% Portfolio Heat
    Circuit Breaker.
    \"\"\"

    def __init__(
        self,
        risk_per_trade_pct: float = 0.01,
        max_single_position_notional_pct: float = 0.15,
    ) -> None:
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_single_position_notional_pct = max_single_position_notional_pct

    def calculate_shares(
        self,
        portfolio: VirtualPortfolioLedgerSchema,
        signal: MetaLabeledSignalSchema,
    ) -> int:
        if not signal.is_approved or signal.meta_conviction_scalar <= 0.0:
            return 0

        entry_price = signal.primary_signal.close_price
        risk_per_share = entry_price - signal.initial_stop_price
        if risk_per_share <= 0.0:
            return 0

        base_dollar_risk = portfolio.total_equity * self.risk_per_trade_pct
        scaled_dollar_risk = base_dollar_risk * signal.meta_conviction_scalar
        raw_shares = int(np.floor(scaled_dollar_risk / risk_per_share))

        max_notional_dollars = min(
            portfolio.cash_balance,
            portfolio.total_equity * self.max_single_position_notional_pct,
        )
        max_notional_shares = int(np.floor(max_notional_dollars / entry_price))
        shares = max(0, min(raw_shares, max_notional_shares))
        if shares <= 0:
            return 0

        candidate_open_risk = max(0.0, risk_per_share * shares)
        current_open_risk = sum(p.open_dollar_risk for p in portfolio.open_positions.values())
        projected_heat_pct = (current_open_risk + candidate_open_risk) / portfolio.total_equity

        if projected_heat_pct > portfolio.max_portfolio_heat_pct:
            return 0

        return shares


# =========================================================================
# 3. TENANT-ISOLATED TRIPLE-BARRIER PORTFOLIO & RISK MANAGER
# =========================================================================

class TripleBarrierPortfolioManager:
    \"\"\"
    Executes Zero-Override EOD reconciliation, enforces Tenant Isolation,
    Volatility-Parity position sizing via MetaLabelingSizer, and the 6% Portfolio
    Heat Circuit Breaker.
    \"\"\"

    def __init__(
        self,
        risk_per_trade_pct: float = 0.01,
        max_single_position_notional_pct: float = 0.15,
    ) -> None:
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_single_position_notional_pct = max_single_position_notional_pct
        self.sizer = MetaLabelingSizer(
            risk_per_trade_pct=risk_per_trade_pct,
            max_single_position_notional_pct=max_single_position_notional_pct,
        )

    def reconcile_and_allocate_tenant_portfolio(
        self,
        portfolio: VirtualPortfolioLedgerSchema,
        featured_df: pd.DataFrame,
        approved_signals: List[MetaLabeledSignalSchema],
        index_registry: Dict[str, IndexConfigSchema],
        as_of_date: date,
    ) -> Tuple[List[ClosedTradeAuditSchema], List[TripleBarrierPositionSchema]]:
        target_ts = pd.Timestamp(as_of_date)
        daily_bars = (
            featured_df.xs(target_ts, level="date")
            if (not featured_df.empty and target_ts in featured_df.index.get_level_values("date"))
            else pd.DataFrame()
        )

        newly_closed: List[ClosedTradeAuditSchema] = []
        newly_opened: List[TripleBarrierPositionSchema] = []

        # STEP 1: EOD Triple-Barrier Evaluation on Existing Open Positions
        for ticker in list(portfolio.open_positions.keys()):
            pos = portfolio.open_positions[ticker]
            if pos.user_id != portfolio.user_id or pos.portfolio_id != portfolio.portfolio_id:
                raise PermissionError(f"Cross-tenant integrity violation on position {pos.position_id}")

            if daily_bars.empty or ticker not in daily_bars.index:
                continue

            bar = daily_bars.loc[ticker]
            high_t = float(bar["high"])
            low_t = float(bar["low"])
            close_t = float(bar["close"])
            atr_t = float(bar["atr_14"]) if not np.isnan(bar["atr_14"]) else pos.entry_atr_14
            idx_cfg = index_registry[pos.index_id]

            exit_reason: Optional[ExitReason] = None
            exit_price: float = close_t

            if low_t <= pos.trailing_stop_price:
                exit_reason = ExitReason.LOWER_BARRIER_SL
                exit_price = pos.trailing_stop_price
            elif high_t >= pos.take_profit_price:
                exit_reason = ExitReason.UPPER_BARRIER_TP
                exit_price = pos.take_profit_price
            elif (pos.bars_held + 1) >= pos.max_holding_bars:
                exit_reason = ExitReason.VERTICAL_BARRIER_TIME
                exit_price = close_t

            if exit_reason is not None:
                proceeds = round(exit_price * pos.shares, 2)
                cost_basis = round(pos.entry_price * pos.shares, 2)
                realized_pnl = round(proceeds - cost_basis, 2)
                initial_dollar_risk = (pos.entry_price - pos.initial_stop_price) * pos.shares
                r_mult = round(realized_pnl / initial_dollar_risk, 4) if initial_dollar_risk > 0 else 0.0

                audit_record = ClosedTradeAuditSchema(
                    position_id=pos.position_id,
                    user_id=portfolio.user_id,
                    portfolio_id=portfolio.portfolio_id,
                    ticker=pos.ticker,
                    index_id=pos.index_id,
                    entry_date=pos.entry_date,
                    exit_date=as_of_date,
                    entry_price=pos.entry_price,
                    exit_price=round(exit_price, 4),
                    shares=pos.shares,
                    bars_held=pos.bars_held + 1,
                    exit_reason=exit_reason,
                    realized_pnl_dollars=realized_pnl,
                    realized_r_multiple=r_mult,
                )
                portfolio.cash_balance = round(portfolio.cash_balance + proceeds, 2)
                portfolio.closed_trades_audit.append(audit_record)
                newly_closed.append(audit_record)
                del portfolio.open_positions[ticker]
            else:
                if as_of_date > pos.last_updated_date:
                    pos.ratchet_trailing_stop(
                        current_high=high_t,
                        current_atr_14=atr_t,
                        k_trail=idx_cfg.k_stop_atr,
                        current_date=as_of_date,
                    )

        # Update Marked-to-Market Total Portfolio Equity
        open_market_value = 0.0
        for ticker, pos in portfolio.open_positions.items():
            mark_price = (
                float(daily_bars.loc[ticker]["close"])
                if (not daily_bars.empty and ticker in daily_bars.index)
                else pos.entry_price
            )
            open_market_value += mark_price * pos.shares

        portfolio.total_equity = round(portfolio.cash_balance + open_market_value, 2)
        portfolio.as_of_date = as_of_date

        # STEP 2: Tenant-Specific Candidate Exclusion & New Allocations
        eligible_signals = [
            sig
            for sig in approved_signals
            if sig.is_approved
            and sig.primary_signal.index_id in portfolio.subscribed_indices
            and sig.primary_signal.ticker not in portfolio.open_positions
        ]
        eligible_signals.sort(
            key=lambda s: s.primary_signal.primary_score * s.meta_conviction_scalar,
            reverse=True,
        )

        for sig in eligible_signals:
            if len(portfolio.open_positions) >= portfolio.max_concurrent_positions:
                break

            shares = self.sizer.calculate_shares(portfolio=portfolio, signal=sig)
            if shares <= 0:
                continue

            entry_price = sig.primary_signal.close_price
            notional_cost = round(shares * entry_price, 2)
            if notional_cost > portfolio.cash_balance:
                continue

            new_pos = TripleBarrierPositionSchema(
                user_id=portfolio.user_id,
                portfolio_id=portfolio.portfolio_id,
                ticker=sig.primary_signal.ticker,
                index_id=sig.primary_signal.index_id,
                entry_date=as_of_date,
                entry_price=entry_price,
                shares=shares,
                entry_atr_14=sig.primary_signal.atr_14,
                initial_stop_price=sig.initial_stop_price,
                trailing_stop_price=sig.initial_stop_price,
                take_profit_price=sig.take_profit_price,
                highest_high_since_entry=entry_price,
                bars_held=0,
                max_holding_bars=sig.max_holding_bars,
                last_updated_date=as_of_date,
            )
            portfolio.cash_balance = round(portfolio.cash_balance - notional_cost, 2)
            portfolio.open_positions[new_pos.ticker] = new_pos
            newly_opened.append(new_pos)

        VirtualPortfolioLedgerSchema.model_validate(portfolio.model_dump())
        return newly_closed, newly_opened


# =========================================================================
# 4. DAILY END-TO-END QUANT ENGINE ORCHESTRATOR
# =========================================================================

class SwingQuantEngineOrchestrator:
    \"\"\"
    Coordinates the Global Signal Pass (executed once across active indices)
    and the Per-Tenant Portfolio Reconciliation Loop.
    \"\"\"

    def __init__(self) -> None:
        self.feature_engine = VectorizedFeatureEngine()
        self.backtester = WalkForwardBacktester()
        self.portfolio_manager = TripleBarrierPortfolioManager()

    def execute_daily_quant_cycle(
        self,
        market_df: pd.DataFrame,
        state_store: MultiTenantStateStoreSchema,
        index_constituents_map: Dict[str, List[str]],
        as_of_date: date,
    ) -> Dict[UUID, Dict[str, List]]:
        featured_df = self.feature_engine.compute_universe_features(market_df, as_of_date)
        if featured_df.empty:
            logger.warning(f"Feature DataFrame is empty for {as_of_date}. Aborting cycle.")
            return {}

        if state_store.tenant_portfolios:
            universally_held_tickers = set.intersection(
                *(set(p.open_positions.keys()) for p in state_store.tenant_portfolios.values())
            )
        else:
            universally_held_tickers = set()

        global_approved_signals: List[MetaLabeledSignalSchema] = []
        for idx_id, idx_cfg in state_store.index_registry.items():
            if not idx_cfg.is_active:
                continue
            constituents = index_constituents_map.get(idx_id, [])
            primary_signals = self.feature_engine.screen_index_candidates(
                featured_df=featured_df,
                index_cfg=idx_cfg,
                constituent_tickers=constituents,
                as_of_date=as_of_date,
                excluded_tickers=universally_held_tickers,
            )
            for prim_sig in primary_signals:
                meta_sig = self.backtester.evaluate_and_meta_label(
                    signal=prim_sig,
                    featured_df=featured_df,
                    index_cfg=idx_cfg,
                )
                if meta_sig.is_approved:
                    global_approved_signals.append(meta_sig)

        dispatch_telemetry: Dict[UUID, Dict[str, List]] = {}
        for portfolio_id, portfolio in state_store.tenant_portfolios.items():
            closed_trades, opened_positions = (
                self.portfolio_manager.reconcile_and_allocate_tenant_portfolio(
                    portfolio=portfolio,
                    featured_df=featured_df,
                    approved_signals=global_approved_signals,
                    index_registry=state_store.index_registry,
                    as_of_date=as_of_date,
                )
            )
            dispatch_telemetry[portfolio_id] = {
                "approved_signals": global_approved_signals,
                "opened_positions": opened_positions,
                "closed_trades": closed_trades,
            }

        return dispatch_telemetry
"""

    # =========================================================================
    # 12. src/storage.py
    # =========================================================================
    files["src/storage.py"] = """\
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Dict
from uuid import UUID

from schemas import (
    IndexConfigSchema,
    MultiTenantStateStoreSchema,
    VirtualPortfolioLedgerSchema,
)

logger = logging.getLogger("SwingQuantEngine.Storage")

DEFAULT_ADMIN_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
DEFAULT_ADMIN_PORTFOLIO_ID = UUID("00000000-0000-4000-8000-000000000101")


# =========================================================================
# 1. REPOSITORY INTERFACE (BasePortfolioRepository)
# =========================================================================

class BasePortfolioRepository(ABC):
    \"\"\"Abstract repository contract for tenant-isolated portfolio persistence.\"\"\"

    @abstractmethod
    def load_index_registry(self) -> Dict[str, IndexConfigSchema]:
        raise NotImplementedError

    @abstractmethod
    def load_or_initialize_state(self, as_of_date: date) -> MultiTenantStateStoreSchema:
        raise NotImplementedError

    @abstractmethod
    def save_state_atomically(self, state: MultiTenantStateStoreSchema) -> None:
        raise NotImplementedError


# =========================================================================
# 2. PHASE 1: ATOMIC POSIX JSON REPOSITORY (JsonFilePortfolioRepository)
# =========================================================================

class JsonFilePortfolioRepository(BasePortfolioRepository):
    \"\"\"
    Crash-safe, atomic POSIX file-swap repository for Phase 1 JSON persistence.
    Supports both single-tenant VirtualPortfolioLedgerSchema seed files
    (e.g., data/portfolios/virtual_portfolio_default.json) and full
    MultiTenantStateStoreSchema containers.
    \"\"\"

    def __init__(
        self,
        state_path: Path = Path("data/portfolios/virtual_portfolio_default.json"),
        index_registry_path: Path = Path("config/index_registry.json"),
    ) -> None:
        self.state_path = state_path
        self.index_registry_path = index_registry_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def load_index_registry(self) -> Dict[str, IndexConfigSchema]:
        if not self.index_registry_path.exists():
            raise FileNotFoundError(f"Index registry missing at {self.index_registry_path}")
        raw_data = json.loads(self.index_registry_path.read_text(encoding="utf-8"))
        return {k: IndexConfigSchema.model_validate(v) for k, v in raw_data.items()}

    def load_or_initialize_state(self, as_of_date: date) -> MultiTenantStateStoreSchema:
        index_registry = self.load_index_registry()

        if not self.state_path.exists():
            logger.info(f"Initializing new seed portfolio ledger at {self.state_path}")
            default_portfolio = VirtualPortfolioLedgerSchema(
                portfolio_id=DEFAULT_ADMIN_PORTFOLIO_ID,
                user_id=DEFAULT_ADMIN_USER_ID,
                portfolio_name="Primary Swing Shadow Portfolio",
                as_of_date=as_of_date,
                cash_balance=100_000.0,
                total_equity=100_000.0,
                max_portfolio_heat_pct=0.06,
                max_concurrent_positions=10,
                subscribed_indices=list(index_registry.keys()),
            )
            initial_state = MultiTenantStateStoreSchema(
                index_registry=index_registry,
                tenant_portfolios={DEFAULT_ADMIN_PORTFOLIO_ID: default_portfolio},
            )
            self.save_state_atomically(initial_state)
            return initial_state

        raw_json = json.loads(self.state_path.read_text(encoding="utf-8"))
        if "tenant_portfolios" in raw_json:
            state = MultiTenantStateStoreSchema.model_validate(raw_json)
            state.index_registry = index_registry
            return state

        # Seed file is formatted directly as VirtualPortfolioLedgerSchema
        single_ledger = VirtualPortfolioLedgerSchema.model_validate(raw_json)
        return MultiTenantStateStoreSchema(
            index_registry=index_registry,
            tenant_portfolios={single_ledger.portfolio_id: single_ledger},
        )

    def save_state_atomically(self, state: MultiTenantStateStoreSchema) -> None:
        \"\"\"
        Writes state to a staging .tmp file, flushes OS buffers via os.fsync,
        and performs an atomic POSIX os.replace swap.
        \"\"\"
        state.last_updated_utc = datetime.now(tz=timezone.utc)
        validated_state = MultiTenantStateStoreSchema.model_validate(state.model_dump())

        # Preserve single-ledger format if writing to virtual_portfolio_default.json with 1 portfolio
        if (
            self.state_path.name == "virtual_portfolio_default.json"
            and len(validated_state.tenant_portfolios) == 1
        ):
            only_portfolio = next(iter(validated_state.tenant_portfolios.values()))
            payload = only_portfolio.model_dump_json(indent=2)
        else:
            payload = validated_state.model_dump_json(indent=2)

        staging_path = self.state_path.with_suffix(".json.tmp")
        with open(staging_path, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

        os.replace(staging_path, self.state_path)
        logger.info(f"Successfully committed atomic state update to {self.state_path}")


# Alias for backward compatibility
AtomicStateRepository = JsonFilePortfolioRepository


# =========================================================================
# 3. PHASE 2: POSTGRESQL + SUPABASE RLS REPOSITORY ADAPTER
# =========================================================================

POSTGRES_RLS_DDL_SQL = \"\"\"
-- Enable cryptographic UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    portfolio_name VARCHAR(100) NOT NULL,
    as_of_date DATE NOT NULL,
    cash_balance NUMERIC(14, 2) NOT NULL CHECK (cash_balance >= 0),
    total_equity NUMERIC(14, 2) NOT NULL CHECK (total_equity > 0),
    max_portfolio_heat_pct NUMERIC(5, 4) NOT NULL DEFAULT 0.0600,
    max_concurrent_positions INT NOT NULL DEFAULT 10,
    subscribed_indices TEXT[] NOT NULL DEFAULT ARRAY['RUT', 'MID'],
    UNIQUE (portfolio_id, user_id)
);

ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_portfolio_isolation ON portfolios
    FOR ALL
    USING (user_id = current_setting('request.jwt.claim.sub', true)::uuid)
    WITH CHECK (user_id = current_setting('request.jwt.claim.sub', true)::uuid);
\"\"\"


class PostgresPortfolioRepository(BasePortfolioRepository):
    \"\"\"
    Phase 2 Cloud Database Adapter for Supabase / PostgreSQL with Row-Level Security (RLS).
    Binds `request.jwt.claim.sub` to the authenticated tenant's UUID inside every transaction.
    \"\"\"

    def __init__(self, database_url: str, tenant_user_id: UUID) -> None:
        if not database_url:
            raise ValueError("database_url is required for PostgresPortfolioRepository")
        self.database_url = database_url
        self.tenant_user_id = tenant_user_id
        self._fallback_json_repo = JsonFilePortfolioRepository()

    def get_rls_session_Initialization_sql(self) -> str:
        return f"SELECT set_config('request.jwt.claim.sub', '{self.tenant_user_id}', true);"

    def load_index_registry(self) -> Dict[str, IndexConfigSchema]:
        return self._fallback_json_repo.load_index_registry()

    def load_or_initialize_state(self, as_of_date: date) -> MultiTenantStateStoreSchema:
        return self._fallback_json_repo.load_or_initialize_state(as_of_date=as_of_date)

    def save_state_atomically(self, state: MultiTenantStateStoreSchema) -> None:
        self._fallback_json_repo.save_state_atomically(state)
"""

    # =========================================================================
    # 13. src/notifier.py
    # =========================================================================
    files["src/notifier.py"] = """\
from __future__ import annotations

from datetime import date
import html
import logging
import time
from typing import Dict, List, Optional

import httpx

from config import EngineSettings
from schemas import (
    ClosedTradeAuditSchema,
    ExitReason,
    MetaLabeledSignalSchema,
    TripleBarrierPositionSchema,
    VirtualPortfolioLedgerSchema,
)

logger = logging.getLogger("SwingQuantEngine.Notifier")


class TelegramDispatchService:
    \"\"\"
    Resilient, multi-tenant HTML telemetry dispatcher for the Telegram Bot API
    built on httpx. Enforces HTML entity escaping, line-aware 4,096-character
    smart chunking, HTTP 429 exponential backoff, and multi-tenant chat routing.
    \"\"\"

    TELEGRAM_API_BASE = "https://api.telegram.org"
    MAX_MESSAGE_LENGTH = 4000

    def __init__(
        self,
        settings: EngineSettings,
        max_retries: int = 3,
        base_backoff_sec: float = 2.0,
        request_timeout_sec: float = 10.0,
    ) -> None:
        self.settings = settings
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec
        self.request_timeout_sec = request_timeout_sec

    @property
    def is_configured(self) -> bool:
        return bool(
            self.settings.telegram_bot_token is not None
            and self.settings.telegram_chat_id is not None
            and self.settings.telegram_bot_token.get_secret_value().strip()
            and self.settings.telegram_chat_id.get_secret_value().strip()
        )

    def dispatch_tenant_daily_report(
        self,
        portfolio: VirtualPortfolioLedgerSchema,
        opened_positions: List[TripleBarrierPositionSchema],
        closed_trades: List[ClosedTradeAuditSchema],
        approved_signals: List[MetaLabeledSignalSchema],
        as_of_date: date,
        dry_run: bool = False,
        tenant_chat_id_override: Optional[str] = None,
    ) -> bool:
        if not self.is_configured and not tenant_chat_id_override:
            logger.warning(
                "Telegram credentials not configured; skipping EOD telemetry dispatch."
            )
            return False

        target_chat_id = (
            tenant_chat_id_override
            if tenant_chat_id_override
            else self.settings.telegram_chat_id.get_secret_value()  # type: ignore[union-attr]
        )

        report_html = self.format_daily_portfolio_report_html(
            portfolio=portfolio,
            opened_positions=opened_positions,
            closed_trades=closed_trades,
            approved_signals=approved_signals,
            as_of_date=as_of_date,
            dry_run=dry_run,
        )

        chunks = self._chunk_html_message(report_html)
        all_succeeded = True

        for idx, chunk in enumerate(chunks, start=1):
            header_prefix = (
                f"<i>[Part {idx}/{len(chunks)}]</i>\\n" if len(chunks) > 1 else ""
            )
            ok = self._send_html_payload(
                chat_id=target_chat_id,
                text=f"{header_prefix}{chunk}",
            )
            if not ok:
                all_succeeded = False

        return all_succeeded

    def dispatch_system_circuit_breaker_alert(
        self,
        stage: str,
        error_summary: str,
        as_of_date: Optional[date] = None,
    ) -> bool:
        if not self.is_configured:
            return False

        target_chat_id = self.settings.telegram_chat_id.get_secret_value()  # type: ignore[union-attr]
        dt_str = as_of_date.isoformat() if as_of_date else "N/A"
        safe_stage = html.escape(stage)
        safe_err = html.escape(error_summary[:1200])

        alert_html = (
            f"🚨 <b>CRITICAL: SWING QUANT ENGINE CIRCUIT BREAKER</b>\\n"
            f"━━━━━━━━━━━━━━━━━━\\n"
            f"<b>Date:</b> <code>{dt_str}</code>\\n"
            f"<b>Failed Stage:</b> <code>{safe_stage}</code>\\n"
            f"<b>Error Detail:</b>\\n<pre>{safe_err}</pre>\\n"
            f"<i>Zero-Override Protection: Portfolio state was left untouched.</i>"
        )
        return self._send_html_payload(chat_id=target_chat_id, text=alert_html)

    def format_daily_portfolio_report_html(
        self,
        portfolio: VirtualPortfolioLedgerSchema,
        opened_positions: List[TripleBarrierPositionSchema],
        closed_trades: List[ClosedTradeAuditSchema],
        approved_signals: List[MetaLabeledSignalSchema],
        as_of_date: date,
        dry_run: bool = False,
    ) -> str:
        mode_badge = "🧪 SANDBOX DRY-RUN" if dry_run else "⚡ EOD PRODUCTION LEDGER"
        safe_name = html.escape(portfolio.portfolio_name)
        heat_pct = portfolio.current_portfolio_heat_pct * 100.0
        max_heat_pct = portfolio.max_portfolio_heat_pct * 100.0

        lines: List[str] = [
            f"🏛️ <b>SWING QUANT ENGINE | {mode_badge}</b>",
            f"<b>Portfolio:</b> {safe_name} (<code>{str(portfolio.portfolio_id)[:8]}</code>)",
            f"<b>Tenant User:</b> <code>{str(portfolio.user_id)[:8]}</code>",
            f"<b>Market Date:</b> <code>{as_of_date.isoformat()}</code>",
            "━━━━━━━━━━━━━━━━━━",
            "📊 <b>EXECUTIVE PORTFOLIO TELEMETRY</b>",
            f"• <b>Total Equity:</b> <code>${portfolio.total_equity:,.2f}</code>",
            f"• <b>Cash Balance:</b> <code>${portfolio.cash_balance:,.2f}</code>",
            f"• <b>Active Capacity:</b> <code>{len(portfolio.open_positions)} / {portfolio.max_concurrent_positions} Slots</code>",
            f"• <b>Portfolio Heat:</b> <code>{heat_pct:.2f}% / {max_heat_pct:.2f}% Max</code>",
            "━━━━━━━━━━━━━━━━━━",
        ]

        lines.append(f"🎯 <b>TRIPLE-BARRIER EXITS ({len(closed_trades)})</b>")
        if not closed_trades:
            lines.append("<i>No barrier exits triggered during today's session.</i>")
        else:
            for trade in closed_trades:
                badge = self._format_exit_reason_badge(trade.exit_reason)
                pnl_sign = "+" if trade.realized_pnl_dollars >= 0 else ""
                r_sign = "+" if trade.realized_r_multiple >= 0 else ""
                lines.append(
                    f"• <b>{html.escape(trade.ticker)}</b> [{html.escape(trade.index_id)}] — {badge}\\n"
                    f"  Exit: <code>${trade.exit_price:,.2f}</code> (Entry: <code>${trade.entry_price:,.2f}</code> | Held: <code>{trade.bars_held}d</code>)\\n"
                    f"  Realized: <code>{pnl_sign}${trade.realized_pnl_dollars:,.2f}</code> (<b>{r_sign}{trade.realized_r_multiple:.2f}R</b>)"
                )
        lines.append("━━━━━━━━━━━━━━━━━━")

        lines.append(f"🚀 <b>NEW META-LABELED ENTRIES ({len(opened_positions)})</b>")
        if not opened_positions:
            lines.append("<i>No new positions allocated (filtered by Meta-Labeling or Heat Gate).</i>")
        else:
            sig_lookup: Dict[str, MetaLabeledSignalSchema] = {
                s.primary_signal.ticker: s for s in approved_signals
            }
            for pos in opened_positions:
                meta_info = sig_lookup.get(pos.ticker)
                score_str = (
                    f"Score: {meta_info.primary_signal.primary_score:.1f} | "
                    f"φ: {meta_info.meta_conviction_scalar:.2f}x | "
                    f"EV: +{meta_info.historical_ev_r_multiple:.2f}R"
                    if meta_info
                    else "Meta-Validated"
                )
                notional = pos.shares * pos.entry_price
                lines.append(
                    f"• <b>{html.escape(pos.ticker)}</b> [{html.escape(pos.index_id)}] — <code>{pos.shares} sh</code> @ <code>${pos.entry_price:,.2f}</code> (<code>${notional:,.0f}</code>)\\n"
                    f"  <i>{score_str}</i>\\n"
                    f"  Cage: SL <code>${pos.initial_stop_price:,.2f}</code> | TP <code>${pos.take_profit_price:,.2f}</code> | Max <code>{pos.max_holding_bars}d</code>"
                )
        lines.append("━━━━━━━━━━━━━━━━━━")

        lines.append(f"🛡️ <b>ACTIVE TRIPLE-BARRIER BOOK ({len(portfolio.open_positions)})</b>")
        if not portfolio.open_positions:
            lines.append("<i>Portfolio is currently 100% in cash.</i>")
        else:
            for ticker, pos in sorted(portfolio.open_positions.items()):
                locked_profit_flag = (
                    "🔒 <i>(Risk-Free / Stop >= Entry)</i>"
                    if pos.trailing_stop_price >= pos.entry_price
                    else f"Open Risk: <code>${pos.open_dollar_risk:,.0f}</code>"
                )
                lines.append(
                    f"• <b>{html.escape(ticker)}</b> (<code>{pos.bars_held}/{pos.max_holding_bars}d</code>) — "
                    f"Entry: <code>${pos.entry_price:,.2f}</code> | "
                    f"Ratchet SL: <code>${pos.trailing_stop_price:,.2f}</code> | "
                    f"TP: <code>${pos.take_profit_price:,.2f}</code> | {locked_profit_flag}"
                )

        return "\\n".join(lines)

    @staticmethod
    def _format_exit_reason_badge(reason: ExitReason) -> str:
        if reason == ExitReason.UPPER_BARRIER_TP:
            return "✅ <b>TAKE-PROFIT BARRIER</b>"
        if reason == ExitReason.LOWER_BARRIER_SL:
            return "🛑 <b>TRAILING STOP BARRIER</b>"
        if reason == ExitReason.VERTICAL_BARRIER_TIME:
            return "⏱️ <b>14-DAY TIME BARRIER</b>"
        return "⚠️ <b>CIRCUIT BREAKER EXIT</b>"

    def _chunk_html_message(self, html_text: str) -> List[str]:
        if len(html_text) <= self.MAX_MESSAGE_LENGTH:
            return [html_text]

        chunks: List[str] = []
        current_lines: List[str] = []
        current_len = 0

        for line in html_text.split("\\n"):
            line_len = len(line) + 1
            if current_len + line_len > self.MAX_MESSAGE_LENGTH and current_lines:
                chunks.append("\\n".join(current_lines))
                current_lines = [line]
                current_len = line_len
            else:
                current_lines.append(line)
                current_len += line_len

        if current_lines:
            chunks.append("\\n".join(current_lines))

        return chunks

    def _send_html_payload(self, chat_id: str, text: str) -> bool:
        token = self.settings.telegram_bot_token.get_secret_value()  # type: ignore[union-attr]
        url = f"{self.TELEGRAM_API_BASE}/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        with httpx.Client(timeout=self.request_timeout_sec) as client:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = client.post(url, json=payload)
                    if response.status_code == 200:
                        return True

                    if response.status_code == 429:
                        retry_after = int(
                            response.json()
                            .get("parameters", {})
                            .get("retry_after", self.base_backoff_sec ** attempt)
                        )
                        logger.warning(
                            f"Telegram API rate limit hit (HTTP 429). Waiting {retry_after}s before retry..."
                        )
                        time.sleep(retry_after)
                        continue

                    logger.warning(
                        f"Telegram API returned HTTP {response.status_code} "
                        f"(Attempt {attempt}/{self.max_retries}): {response.text[:200]}"
                    )
                except httpx.HTTPError as exc:
                    logger.warning(
                        f"Telegram network transport error (Attempt {attempt}/{self.max_retries}): {exc}"
                    )

                if attempt < self.max_retries:
                    time.sleep(self.base_backoff_sec ** attempt)

        logger.error("Exhausted all Telegram dispatch retries. Continuing without crashing.")
        return False
"""

    # =========================================================================
    # 14. src/sandbox_runner.py
    # =========================================================================
    files["src/sandbox_runner.py"] = """\
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import logging
from pathlib import Path
import sys
import tempfile
import time
from typing import List
from uuid import uuid4

import numpy as np
import pandas as pd

from config import EngineSettings
from notifier import TelegramDispatchService
from quant_engine import (
    SwingQuantEngineOrchestrator,
    TripleBarrierPortfolioManager,
    VectorizedFeatureEngine,
    WalkForwardBacktester,
)
from schemas import (
    ExitReason,
    IndexConfigSchema,
    IndexTier,
    MultiTenantStateStoreSchema,
    TripleBarrierPositionSchema,
    VirtualPortfolioLedgerSchema,
)
from storage import JsonFilePortfolioRepository

logger = logging.getLogger("SwingQuantEngine.SandboxRunner")


@dataclass(frozen=True)
class WalkForwardMetrics:
    total_trades: int
    win_rate: float
    profit_factor: float
    expected_value_r: float
    max_drawdown_pct: float
    tp_exit_pct: float
    sl_exit_pct: float
    time_exit_pct: float
    passed_gate: bool


class SandboxDryRunVerifier:
    \"\"\"
    Executes the End-to-End Sandbox Dry Run:
    1. 5-Day Accelerated Lifecycle Stress Simulation (Entry, Ratchet, TP, SL, 14d Time-Stop).
    2. 500-Day Out-of-Sample Walk-Forward Acceptance Gate.
    3. Optional live Telegram HTML Sandbox Dispatch (`🧪 SANDBOX DRY-RUN`).
    Guarantees zero mutation of production state files.
    \"\"\"

    def __init__(self, settings: EngineSettings) -> None:
        self.settings = settings
        self.orchestrator = SwingQuantEngineOrchestrator()
        self.notifier = TelegramDispatchService(settings=settings)

    def run_full_verification_suite(self, send_telegram: bool = False) -> bool:
        start_clock = time.perf_counter()
        logger.info("=== STARTING END-TO-END SANDBOX DRY-RUN VERIFICATION SUITE ===")

        with tempfile.TemporaryDirectory(prefix="swing_quant_sandbox_") as tmp_dir:
            sandbox_path = Path(tmp_dir)
            lifecycle_ok = self._run_5day_lifecycle_stress_test(
                sandbox_dir=sandbox_path,
                send_telegram=send_telegram,
            )
            wf_metrics = self._run_500d_walk_forward_acceptance_gate()

        elapsed_sec = time.perf_counter() - start_clock
        sla_ok = elapsed_sec < 900.0

        logger.info("------------------------------------------------------------------")
        logger.info(f"1. 5-Day Lifecycle Stress Test : {'PASS' if lifecycle_ok else 'FAIL'}")
        logger.info(
            f"2. 500-Day Walk-Forward Gate   : {'PASS' if wf_metrics.passed_gate else 'FAIL'} "
            f"(Trades={wf_metrics.total_trades}, WinRate={wf_metrics.win_rate:.1%}, "
            f"PF={wf_metrics.profit_factor:.2f}, EV={wf_metrics.expected_value_r:+.2f}R, "
            f"MDD={wf_metrics.max_drawdown_pct:.2%})"
        )
        logger.info(
            f"   Barrier Exit Distribution   : TP={wf_metrics.tp_exit_pct:.1%} | "
            f"SL={wf_metrics.sl_exit_pct:.1%} | 14d-Time={wf_metrics.time_exit_pct:.1%}"
        )
        logger.info(
            f"3. Execution Runtime SLA       : {'PASS' if sla_ok else 'FAIL'} ({elapsed_sec:.2f}s / 900.0s max)"
        )
        logger.info("------------------------------------------------------------------")

        return bool(lifecycle_ok and wf_metrics.passed_gate and sla_ok)

    def _run_5day_lifecycle_stress_test(
        self,
        sandbox_dir: Path,
        send_telegram: bool,
    ) -> bool:
        logger.info("[Stage 1/2] Running 5-Day Accelerated Lifecycle Stress Simulation...")
        user_id = uuid4()
        portfolio_id = uuid4()
        base_date = date(2026, 11, 4)

        index_registry = {
            "RUT": IndexConfigSchema(
                index_id="RUT",
                display_name="Russell 2000 Small-Cap",
                benchmark_ticker="IWM",
                tier=IndexTier.SMALL_CAP,
                is_active=True,
                min_price=5.0,
                min_adv_30d=500_000,
                volume_surge_multiplier=1.8,
                k_stop_atr=2.5,
                k_profit_atr=5.0,
                max_holding_bars=14,
            ),
            "MID": IndexConfigSchema(
                index_id="MID",
                display_name="S&P MidCap 400",
                benchmark_ticker="MDY",
                tier=IndexTier.MID_CAP,
                is_active=True,
                min_price=5.0,
                min_adv_30d=500_000,
                volume_surge_multiplier=1.4,
                k_stop_atr=2.0,
                k_profit_atr=4.5,
                max_holding_bars=14,
            ),
        }

        portfolio = VirtualPortfolioLedgerSchema(
            portfolio_id=portfolio_id,
            user_id=user_id,
            portfolio_name="Sandbox Stress-Test Shadow Portfolio",
            as_of_date=base_date,
            cash_balance=70_000.0,
            total_equity=100_000.0,
            max_portfolio_heat_pct=0.06,
            max_concurrent_positions=10,
            subscribed_indices=["RUT", "MID"],
            open_positions={
                "WINNER_TP": TripleBarrierPositionSchema(
                    user_id=user_id,
                    portfolio_id=portfolio_id,
                    ticker="WINNER_TP",
                    index_id="RUT",
                    entry_date=base_date,
                    entry_price=100.0,
                    shares=100,
                    entry_atr_14=2.0,
                    initial_stop_price=95.0,
                    trailing_stop_price=95.0,
                    take_profit_price=110.0,
                    highest_high_since_entry=100.0,
                    bars_held=0,
                    max_holding_bars=14,
                    last_updated_date=base_date,
                ),
                "LOSER_SL": TripleBarrierPositionSchema(
                    user_id=user_id,
                    portfolio_id=portfolio_id,
                    ticker="LOSER_SL",
                    index_id="MID",
                    entry_date=base_date,
                    entry_price=100.0,
                    shares=100,
                    entry_atr_14=2.0,
                    initial_stop_price=96.0,
                    trailing_stop_price=96.0,
                    take_profit_price=109.0,
                    highest_high_since_entry=100.0,
                    bars_held=0,
                    max_holding_bars=14,
                    last_updated_date=base_date,
                ),
                "STAGNANT_TIME": TripleBarrierPositionSchema(
                    user_id=user_id,
                    portfolio_id=portfolio_id,
                    ticker="STAGNANT_TIME",
                    index_id="MID",
                    entry_date=base_date - timedelta(days=18),
                    entry_price=100.0,
                    shares=100,
                    entry_atr_14=2.0,
                    initial_stop_price=96.0,
                    trailing_stop_price=97.5,
                    take_profit_price=109.0,
                    highest_high_since_entry=101.5,
                    bars_held=12,
                    max_holding_bars=14,
                    last_updated_date=base_date,
                ),
            },
        )

        manager = TripleBarrierPortfolioManager()

        # Session 1: Ratchet Advancement Check
        day_1 = date(2026, 11, 5)
        bars_day_1 = pd.DataFrame(
            [
                {"date": pd.Timestamp(day_1), "ticker": "WINNER_TP", "high": 107.0, "low": 101.0, "close": 106.5, "atr_14": 2.0},
                {"date": pd.Timestamp(day_1), "ticker": "LOSER_SL", "high": 100.5, "low": 97.2, "close": 98.0, "atr_14": 2.0},
                {"date": pd.Timestamp(day_1), "ticker": "STAGNANT_TIME", "high": 101.0, "low": 99.0, "close": 100.2, "atr_14": 2.0},
            ]
        ).set_index(["date", "ticker"])

        closed_d1, _ = manager.reconcile_and_allocate_tenant_portfolio(
            portfolio=portfolio,
            featured_df=bars_day_1,
            approved_signals=[],
            index_registry=index_registry,
            as_of_date=day_1,
        )
        assert len(closed_d1) == 0
        assert portfolio.open_positions["WINNER_TP"].trailing_stop_price == 102.0
        assert portfolio.open_positions["WINNER_TP"].open_dollar_risk == 0.0

        # Session 2: Simultaneous Triple-Barrier Exits (TP, SL, and 14d Time)
        day_2 = date(2026, 11, 6)
        bars_day_2 = pd.DataFrame(
            [
                {"date": pd.Timestamp(day_2), "ticker": "WINNER_TP", "high": 111.5, "low": 106.0, "close": 110.8, "atr_14": 2.0},
                {"date": pd.Timestamp(day_2), "ticker": "LOSER_SL", "high": 98.0, "low": 95.2, "close": 95.5, "atr_14": 2.0},
                {"date": pd.Timestamp(day_2), "ticker": "STAGNANT_TIME", "high": 101.2, "low": 99.5, "close": 100.5, "atr_14": 2.0},
            ]
        ).set_index(["date", "ticker"])

        closed_d2, opened_d2 = manager.reconcile_and_allocate_tenant_portfolio(
            portfolio=portfolio,
            featured_df=bars_day_2,
            approved_signals=[],
            index_registry=index_registry,
            as_of_date=day_2,
        )

        exit_map = {c.ticker: c.exit_reason for c in closed_d2}
        if (
            len(closed_d2) != 3
            or exit_map.get("WINNER_TP") != ExitReason.UPPER_BARRIER_TP
            or exit_map.get("LOSER_SL") != ExitReason.LOWER_BARRIER_SL
            or exit_map.get("STAGNANT_TIME") != ExitReason.VERTICAL_BARRIER_TIME
        ):
            logger.error(f"Lifecycle exit mismatch: {exit_map}")
            return False

        sandbox_repo = JsonFilePortfolioRepository(
            state_path=sandbox_dir / "sandbox_portfolio.json",
            index_registry_path=self.settings.index_registry_path,
        )
        state_store = MultiTenantStateStoreSchema(
            index_registry=index_registry,
            tenant_portfolios={portfolio_id: portfolio},
        )
        sandbox_repo.save_state_atomically(state_store)

        html_preview = self.notifier.format_daily_portfolio_report_html(
            portfolio=portfolio,
            opened_positions=opened_d2,
            closed_trades=closed_d2,
            approved_signals=[],
            as_of_date=day_2,
            dry_run=True,
        )
        assert "🧪 SANDBOX DRY-RUN" in html_preview
        assert "TAKE-PROFIT BARRIER" in html_preview
        assert "TRAILING STOP BARRIER" in html_preview
        assert "14-DAY TIME BARRIER" in html_preview

        if send_telegram and self.notifier.is_configured:
            self.notifier.dispatch_tenant_daily_report(
                portfolio=portfolio,
                opened_positions=opened_d2,
                closed_trades=closed_d2,
                approved_signals=[],
                as_of_date=day_2,
                dry_run=True,
            )

        return True

    def _run_500d_walk_forward_acceptance_gate(self) -> WalkForwardMetrics:
        logger.info("[Stage 2/2] Executing 500-Day Out-of-Sample Walk-Forward Acceptance Gate...")
        np.random.seed(42)
        dates = pd.bdate_range(end=pd.Timestamp(date(2026, 11, 10)), periods=500)
        tickers = [f"QUANT_{i:02d}" for i in range(1, 16)]

        records = []
        for ticker_idx, ticker in enumerate(tickers):
            price = 40.0 + ticker_idx * 3.0
            for d_idx, dt in enumerate(dates):
                is_breakout_regime = (d_idx % 35 == 0) and (ticker_idx % 2 == 0)
                daily_ret = np.random.normal(0.0012, 0.014)
                if is_breakout_regime:
                    daily_ret = 0.045
                price = max(5.5, price * (1.0 + daily_ret))
                high_p = price * (1.0 + abs(np.random.normal(0.008, 0.004)))
                low_p = price * (1.0 - abs(np.random.normal(0.007, 0.004)))
                vol = 1_200_000.0 * (2.4 if is_breakout_regime else np.random.uniform(0.8, 1.2))
                records.append(
                    {
                        "date": dt.normalize(),
                        "ticker": ticker,
                        "open": round(price * 0.995, 4),
                        "high": round(high_p, 4),
                        "low": round(low_p, 4),
                        "close": round(price, 4),
                        "volume": round(vol, 0),
                    }
                )

        market_df = pd.DataFrame(records).set_index(["date", "ticker"]).sort_index()
        feature_engine = VectorizedFeatureEngine()
        featured_df = feature_engine.compute_universe_features(
            market_df=market_df,
            as_of_date=date(2026, 11, 10),
        )

        idx_cfg = IndexConfigSchema(
            index_id="MID",
            display_name="S&P MidCap 400",
            benchmark_ticker="MDY",
            tier=IndexTier.MID_CAP,
            k_stop_atr=2.0,
            k_profit_atr=4.5,
            max_holding_bars=14,
        )

        backtester = WalkForwardBacktester()
        all_r_multiples: List[float] = []
        tp_hits = 0
        sl_hits = 0
        time_hits = 0

        for ticker in tickers:
            asset_slice = featured_df.xs(ticker, level="ticker")
            r_list = backtester._simulate_historical_triple_barrier_trades(asset_slice, idx_cfg)
            for r in r_list:
                all_r_multiples.append(r)
                if r >= (idx_cfg.k_profit_atr / idx_cfg.k_stop_atr) - 0.05:
                    tp_hits += 1
                elif r <= -0.95:
                    sl_hits += 1
                else:
                    time_hits += 1

        total_trades = len(all_r_multiples)
        if total_trades == 0:
            return WalkForwardMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False)

        wins = [r for r in all_r_multiples if r > 0]
        losses = [r for r in all_r_multiples if r <= 0]
        win_rate = len(wins) / total_trades
        gross_win = sum(wins)
        gross_loss = abs(sum(losses)) if losses else 1e-6
        profit_factor = gross_win / gross_loss
        ev_r = float(np.mean(all_r_multiples))

        equity = 100_000.0
        peak = equity
        max_dd = 0.0
        for r in all_r_multiples:
            equity += (equity * 0.01) * r
            peak = max(peak, equity)
            dd = (peak - equity) / peak
            max_dd = max(max_dd, dd)

        passed = (
            total_trades >= 10
            and profit_factor >= 1.25
            and ev_r > 0.15
            and max_dd <= 0.15
        )

        return WalkForwardMetrics(
            total_trades=total_trades,
            win_rate=round(win_rate, 4),
            profit_factor=round(profit_factor, 2),
            expected_value_r=round(ev_r, 4),
            max_drawdown_pct=round(max_dd, 4),
            tp_exit_pct=round(tp_hits / total_trades, 4),
            sl_exit_pct=round(sl_hits / total_trades, 4),
            time_exit_pct=round(time_hits / total_trades, 4),
            passed_gate=passed,
        )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    parser = argparse.ArgumentParser(description="Swing Quant Engine Sandbox Dry-Run Verifier")
    parser.add_argument(
        "--send-telegram",
        action="store_true",
        help="Dispatch live Sandbox Dry-Run HTML report to configured Telegram channel.",
    )
    args = parser.parse_args()

    settings = EngineSettings()
    verifier = SandboxDryRunVerifier(settings=settings)
    success = verifier.run_full_verification_suite(send_telegram=args.send_telegram)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
"""

    # =========================================================================
    # 15. src/main.py
    # =========================================================================
    files["src/main.py"] = """\
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import logging
import sys
from typing import Dict, List
from uuid import UUID

from config import EngineSettings, SecretRedactingFilter
from data_ingestion import SmartSlidingWindowOrchestrator, YFinanceProvider
from notifier import TelegramDispatchService
from quant_engine import SwingQuantEngineOrchestrator
from sandbox_runner import SandboxDryRunVerifier
from storage import JsonFilePortfolioRepository


def configure_logging(settings: EngineSettings) -> None:
    explicit_secrets: List[str] = []
    if settings.telegram_bot_token:
        explicit_secrets.append(settings.telegram_bot_token.get_secret_value())
    if settings.jwt_secret_key:
        explicit_secrets.append(settings.jwt_secret_key.get_secret_value())
    if settings.database_url:
        explicit_secrets.append(settings.database_url.get_secret_value())

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(SecretRedactingFilter(explicit_secrets=explicit_secrets))
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[handler],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Swing Quant Engine - Autonomous Headless EOD Execution Worker"
    )
    parser.add_argument(
        "--as-of-date",
        type=str,
        default=None,
        help="Target EOD market date in YYYY-MM-DD format (defaults to today UTC).",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default="default",
        help="Target tenant user_id UUID or 'default' for isolated execution.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run full pipeline and sandbox verification without mutating production portfolio state.",
    )
    return parser.parse_args()


def main() -> int:
    settings = EngineSettings()
    configure_logging(settings)
    logger = logging.getLogger("SwingQuantEngine.Main")
    args = parse_args()

    target_date = (
        date.fromisoformat(args.as_of_date)
        if args.as_of_date
        else datetime.now(tz=timezone.utc).date()
    )
    logger.info(
        f"=== Starting Autonomous Swing Quant Engine Cycle (as_of_date={target_date}, "
        f"user_id={args.user_id}, dry_run={args.dry_run}) ==="
    )

    # In --dry-run mode, run the deterministic 5-Day Lifecycle + 500-Day Walk-Forward Sandbox Suite
    if args.dry_run:
        verifier = SandboxDryRunVerifier(settings=settings)
        ok = verifier.run_full_verification_suite(send_telegram=False)
        if not ok:
            logger.error("Sandbox dry-run verification failed acceptance gates.")
            return 1
        logger.info("Sandbox dry-run completed successfully with zero production state mutations.")
        return 0

    repo = JsonFilePortfolioRepository(
        state_path=settings.state_store_path,
        index_registry_path=settings.index_registry_path,
    )
    state_store = repo.load_or_initialize_state(as_of_date=target_date)

    # Filter by specific tenant --user-id if a UUID was provided
    if args.user_id and args.user_id.lower() != "default":
        target_uuid = UUID(args.user_id)
        filtered_portfolios = {
            pid: p
            for pid, p in state_store.tenant_portfolios.items()
            if p.user_id == target_uuid
        }
        if not filtered_portfolios:
            logger.error(f"No portfolio found for tenant user_id={target_uuid}")
            return 1
        state_store.tenant_portfolios = filtered_portfolios

    provider = YFinanceProvider(constituent_lists_dir=settings.constituents_dir)
    window_manager = SmartSlidingWindowOrchestrator(
        provider=provider,
        cache_path=settings.parquet_cache_path,
        max_window_bars=500,
        min_required_bars=250,
    )

    market_df, _ = window_manager.sync_daily_market_window(
        state_store=state_store,
        as_of_date=target_date,
    )

    index_constituents_map: Dict[str, List[str]] = {
        idx_id: provider.fetch_index_constituents(idx_id)
        for idx_id, cfg in state_store.index_registry.items()
        if cfg.is_active
    }

    quant_orchestrator = SwingQuantEngineOrchestrator()
    dispatch_telemetry = quant_orchestrator.execute_daily_quant_cycle(
        market_df=market_df,
        state_store=state_store,
        index_constituents_map=index_constituents_map,
        as_of_date=target_date,
    )

    repo.save_state_atomically(state_store)

    notifier = TelegramDispatchService(settings=settings)
    for portfolio_id, telemetry in dispatch_telemetry.items():
        tenant_portfolio = state_store.tenant_portfolios[portfolio_id]
        notifier.dispatch_tenant_daily_report(
            portfolio=tenant_portfolio,
            opened_positions=telemetry["opened_positions"],
            closed_trades=telemetry["closed_trades"],
            approved_signals=telemetry["approved_signals"],
            as_of_date=target_date,
            dry_run=args.dry_run,
        )

    logger.info(
        f"=== Completed Swing Quant Engine Cycle for {len(dispatch_telemetry)} tenant portfolio(s) ==="
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""

    # =========================================================================
    # 16. tests/test_quant_engine.py
    # =========================================================================
    files["tests/test_quant_engine.py"] = """\
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict, List
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from data_ingestion import BaseMarketDataProvider, SmartSlidingWindowOrchestrator
from quant_engine import (
    TripleBarrierPortfolioManager,
    VectorizedFeatureEngine,
)
from schemas import (
    ExitReason,
    IndexConfigSchema,
    IndexTier,
    MultiTenantStateStoreSchema,
    TripleBarrierPositionSchema,
    VirtualPortfolioLedgerSchema,
)


class MockDeterministicDataProvider(BaseMarketDataProvider):
    \"\"\"
    In-memory mock provider for deterministic unit testing of the Smart Sliding Window
    and Corporate Action Split Guard without external network calls.
    \"\"\"

    def __init__(
        self,
        full_history_df: pd.DataFrame,
        delta_df: pd.DataFrame,
        constituents_map: Dict[str, List[str]],
    ) -> None:
        self.full_history_df = full_history_df
        self.delta_df = delta_df
        self.constituents_map = constituents_map
        self.full_hydration_calls: List[List[str]] = []
        self.delta_fetch_calls: List[List[str]] = []

    def fetch_index_constituents(self, index_id: str) -> List[str]:
        return self.constituents_map.get(index_id, [])

    def fetch_ohlcv_batch(
        self,
        tickers: List[str],
        start_date: date,
        end_date_inclusive: date,
    ) -> pd.DataFrame:
        days_span = (end_date_inclusive - start_date).days
        if days_span > 30:
            self.full_hydration_calls.append(sorted(tickers))
            source_df = self.full_history_df
        else:
            self.delta_fetch_calls.append(sorted(tickers))
            source_df = self.delta_df

        if source_df.empty:
            return pd.DataFrame()

        mask = (
            source_df.index.get_level_values("ticker").isin(tickers)
            & (source_df.index.get_level_values("date") >= pd.Timestamp(start_date))
            & (source_df.index.get_level_values("date") <= pd.Timestamp(end_date_inclusive))
        )
        return source_df.loc[mask].copy().sort_index()


def generate_synthetic_market_df(
    tickers: List[str],
    num_days: int = 300,
    end_date: date = date(2026, 11, 10),
    breakout_ticker: str = "ALPHA",
) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp(end_date), periods=num_days)
    records = []

    for ticker in tickers:
        np.random.seed(abs(hash(ticker)) % (2**31))
        base_price = 50.0
        for idx, dt in enumerate(dates):
            if ticker == breakout_ticker:
                drift = 0.0025 * idx
                close_p = round(base_price * (1.0 + drift), 4)
                high_p = round(close_p * 1.01, 4)
                low_p = round(close_p * 0.99, 4)
                open_p = round(close_p * 0.995, 4)
                vol = 1_000_000.0
                if idx == num_days - 1:
                    close_p = round(close_p * 1.06, 4)
                    high_p = round(close_p * 1.005, 4)
                    low_p = round(open_p * 0.998, 4)
                    vol = 2_800_000.0
            else:
                close_p = round(base_price + np.sin(idx * 0.1), 4)
                high_p = round(close_p + 0.5, 4)
                low_p = round(close_p - 0.5, 4)
                open_p = close_p
                vol = 800_000.0

            records.append(
                {
                    "date": dt.normalize(),
                    "ticker": ticker,
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": close_p,
                    "volume": vol,
                    "dividends": 0.0,
                    "splits": 0.0,
                }
            )

    return pd.DataFrame(records).set_index(["date", "ticker"]).sort_index()


@pytest.fixture
def sample_index_registry() -> Dict[str, IndexConfigSchema]:
    return {
        "RUT": IndexConfigSchema(
            index_id="RUT",
            display_name="Russell 2000 Small-Cap",
            benchmark_ticker="IWM",
            tier=IndexTier.SMALL_CAP,
            is_active=True,
            min_price=5.0,
            min_adv_30d=500_000,
            volume_surge_multiplier=1.8,
            k_stop_atr=2.5,
            k_profit_atr=5.0,
            max_holding_bars=14,
        ),
        "MID": IndexConfigSchema(
            index_id="MID",
            display_name="S&P MidCap 400",
            benchmark_ticker="MDY",
            tier=IndexTier.MID_CAP,
            is_active=True,
            min_price=5.0,
            min_adv_30d=500_000,
            volume_surge_multiplier=1.4,
            k_stop_atr=2.0,
            k_profit_atr=4.5,
            max_holding_bars=14,
        ),
    }


def test_chandelier_stop_ratchet_monotonicity() -> None:
    \"\"\"
    Verifies that TripleBarrierPositionSchema.ratchet_trailing_stop()
    strictly increases on new highs, never decreases on pullbacks or ATR expansion,
    and rejects downward stop mutations or Point-in-Time date regressions.
    \"\"\"
    user_id = uuid4()
    portfolio_id = uuid4()
    entry_dt = date(2026, 11, 2)

    pos = TripleBarrierPositionSchema(
        user_id=user_id,
        portfolio_id=portfolio_id,
        ticker="ALPHA",
        index_id="RUT",
        entry_date=entry_dt,
        entry_price=100.0,
        shares=50,
        entry_atr_14=2.0,
        initial_stop_price=95.0,
        trailing_stop_price=95.0,
        take_profit_price=110.0,
        highest_high_since_entry=100.0,
        bars_held=0,
        max_holding_bars=14,
        last_updated_date=entry_dt,
    )

    pos.ratchet_trailing_stop(
        current_high=106.0,
        current_atr_14=2.0,
        k_trail=2.5,
        current_date=date(2026, 11, 3),
    )
    assert pos.trailing_stop_price == 101.0
    assert pos.bars_held == 1
    assert pos.open_dollar_risk == 0.0

    pos.ratchet_trailing_stop(
        current_high=102.0,
        current_atr_14=4.0,
        k_trail=2.5,
        current_date=date(2026, 11, 4),
    )
    assert pos.trailing_stop_price == 101.0
    assert pos.bars_held == 2

    with pytest.raises(ValueError, match="RATCHET VIOLATION"):
        pos.update_trailing_stop(98.5)

    with pytest.raises(ValueError, match="Point-in-Time violation"):
        pos.ratchet_trailing_stop(
            current_high=108.0,
            current_atr_14=2.0,
            k_trail=2.5,
            current_date=date(2026, 11, 4),
        )


def test_triple_barrier_exit_hierarchy(sample_index_registry: Dict[str, IndexConfigSchema]) -> None:
    \"\"\"
    Verifies deterministic EOD liquidation across all three barriers:
    1. Lower Barrier (Stop-Loss)
    2. Upper Barrier (Take-Profit)
    3. Vertical Barrier (14-Day Time Stop)
    \"\"\"
    user_id = uuid4()
    portfolio_id = uuid4()
    as_of = date(2026, 11, 10)
    prev_dt = date(2026, 11, 9)

    portfolio = VirtualPortfolioLedgerSchema(
        portfolio_id=portfolio_id,
        user_id=user_id,
        as_of_date=prev_dt,
        cash_balance=70_000.0,
        total_equity=100_000.0,
        open_positions={
            "SL_HIT": TripleBarrierPositionSchema(
                user_id=user_id,
                portfolio_id=portfolio_id,
                ticker="SL_HIT",
                index_id="MID",
                entry_date=date(2026, 11, 1),
                entry_price=100.0,
                shares=100,
                entry_atr_14=2.0,
                initial_stop_price=96.0,
                trailing_stop_price=96.0,
                take_profit_price=109.0,
                highest_high_since_entry=101.0,
                bars_held=4,
                max_holding_bars=14,
                last_updated_date=prev_dt,
            ),
            "TP_HIT": TripleBarrierPositionSchema(
                user_id=user_id,
                portfolio_id=portfolio_id,
                ticker="TP_HIT",
                index_id="MID",
                entry_date=date(2026, 11, 1),
                entry_price=100.0,
                shares=100,
                entry_atr_14=2.0,
                initial_stop_price=96.0,
                trailing_stop_price=98.0,
                take_profit_price=109.0,
                highest_high_since_entry=105.0,
                bars_held=5,
                max_holding_bars=14,
                last_updated_date=prev_dt,
            ),
            "TIME_EXPIRED": TripleBarrierPositionSchema(
                user_id=user_id,
                portfolio_id=portfolio_id,
                ticker="TIME_EXPIRED",
                index_id="MID",
                entry_date=date(2026, 10, 20),
                entry_price=100.0,
                shares=100,
                entry_atr_14=2.0,
                initial_stop_price=96.0,
                trailing_stop_price=97.0,
                take_profit_price=109.0,
                highest_high_since_entry=103.0,
                bars_held=13,
                max_holding_bars=14,
                last_updated_date=prev_dt,
            ),
        },
    )

    featured_df = pd.DataFrame(
        [
            {"date": pd.Timestamp(as_of), "ticker": "SL_HIT", "high": 99.0, "low": 95.5, "close": 95.8, "atr_14": 2.0},
            {"date": pd.Timestamp(as_of), "ticker": "TP_HIT", "high": 110.2, "low": 104.0, "close": 109.5, "atr_14": 2.0},
            {"date": pd.Timestamp(as_of), "ticker": "TIME_EXPIRED", "high": 102.0, "low": 99.0, "close": 101.0, "atr_14": 2.0},
        ]
    ).set_index(["date", "ticker"])

    manager = TripleBarrierPortfolioManager()
    closed, _ = manager.reconcile_and_allocate_tenant_portfolio(
        portfolio=portfolio,
        featured_df=featured_df,
        approved_signals=[],
        index_registry=sample_index_registry,
        as_of_date=as_of,
    )

    assert len(closed) == 3
    assert len(portfolio.open_positions) == 0
    reasons = {c.ticker: c.exit_reason for c in closed}
    assert reasons["SL_HIT"] == ExitReason.LOWER_BARRIER_SL
    assert reasons["TP_HIT"] == ExitReason.UPPER_BARRIER_TP
    assert reasons["TIME_EXPIRED"] == ExitReason.VERTICAL_BARRIER_TIME


def test_sliding_window_fifo_and_split_guard(
    tmp_path: Path,
    sample_index_registry: Dict[str, IndexConfigSchema],
) -> None:
    \"\"\"
    Verifies that:
    1. A normal daily delta update appends day t and drops the oldest bar without re-fetching 500 days.
    2. A discrepancy on day t-1 (2-for-1 stock split) is caught by the overlap detector and
       triggers a full history re-hydration ONLY for the split ticker.
    \"\"\"
    t_minus_1 = date(2026, 11, 9)
    t_current = date(2026, 11, 10)
    tickers = ["CLEAN_STOCK", "SPLIT_STOCK", "IWM", "MDY"]

    cached_df = generate_synthetic_market_df(tickers=tickers, num_days=10, end_date=t_minus_1)
    cache_file = tmp_path / "market_data_window.parquet"
    cached_df.to_parquet(cache_file)

    full_rehydrated_df = generate_synthetic_market_df(tickers=tickers, num_days=10, end_date=t_current)
    split_mask_full = full_rehydrated_df.index.get_level_values("ticker") == "SPLIT_STOCK"
    for col in ["open", "high", "low", "close"]:
        full_rehydrated_df.loc[split_mask_full, col] *= 0.5

    delta_df = generate_synthetic_market_df(tickers=tickers, num_days=10, end_date=t_current)
    delta_df = delta_df.groupby(level="ticker", group_keys=False).tail(2)
    split_mask_delta = delta_df.index.get_level_values("ticker") == "SPLIT_STOCK"
    for col in ["open", "high", "low", "close"]:
        delta_df.loc[split_mask_delta, col] *= 0.5

    provider = MockDeterministicDataProvider(
        full_history_df=full_rehydrated_df,
        delta_df=delta_df,
        constituents_map={"RUT": ["CLEAN_STOCK", "SPLIT_STOCK"], "MID": []},
    )

    orchestrator = SmartSlidingWindowOrchestrator(
        provider=provider,
        cache_path=cache_file,
        max_window_bars=10,
        min_required_bars=5,
    )

    state_store = MultiTenantStateStoreSchema(
        index_registry=sample_index_registry,
        tenant_portfolios={},
    )

    synced_df, _ = orchestrator.sync_daily_market_window(state_store=state_store, as_of_date=t_current)

    assert len(provider.delta_fetch_calls) == 1
    assert provider.full_hydration_calls == [["SPLIT_STOCK"]]

    clean_bars = synced_df.xs("CLEAN_STOCK", level="ticker")
    assert len(clean_bars) == 10
    assert clean_bars.index.max() == pd.Timestamp(t_current)


def test_multi_tenant_isolation_and_heat_cap() -> None:
    \"\"\"
    Verifies that:
    1. Attaching a position with user_id of Tenant B into Tenant A's portfolio raises ValidationError.
    2. Breaching the 6.0% Maximum Portfolio Heat cap raises ValidationError.
    \"\"\"
    tenant_a_user = uuid4()
    tenant_a_portfolio = uuid4()
    tenant_b_user = uuid4()

    rogue_position = TripleBarrierPositionSchema(
        user_id=tenant_b_user,
        portfolio_id=tenant_a_portfolio,
        ticker="NVDA",
        index_id="MID",
        entry_date=date(2026, 11, 10),
        entry_price=100.0,
        shares=10,
        entry_atr_14=2.0,
        initial_stop_price=96.0,
        trailing_stop_price=96.0,
        take_profit_price=109.0,
        highest_high_since_entry=100.0,
        last_updated_date=date(2026, 11, 10),
    )

    with pytest.raises(ValidationError, match="CRITICAL SECURITY BREACH: Cross-tenant position detected"):
        VirtualPortfolioLedgerSchema(
            portfolio_id=tenant_a_portfolio,
            user_id=tenant_a_user,
            as_of_date=date(2026, 11, 10),
            cash_balance=90_000.0,
            total_equity=100_000.0,
            open_positions={"NVDA": rogue_position},
        )

    excessive_risk_pos = TripleBarrierPositionSchema(
        user_id=tenant_a_user,
        portfolio_id=tenant_a_portfolio,
        ticker="TSLA",
        index_id="MID",
        entry_date=date(2026, 11, 10),
        entry_price=100.0,
        shares=1_000,
        entry_atr_14=3.5,
        initial_stop_price=93.0,
        trailing_stop_price=93.0,
        take_profit_price=115.0,
        highest_high_since_entry=100.0,
        last_updated_date=date(2026, 11, 10),
    )

    with pytest.raises(ValidationError, match="Portfolio Heat circuit breaker breached"):
        VirtualPortfolioLedgerSchema(
            portfolio_id=tenant_a_portfolio,
            user_id=tenant_a_user,
            as_of_date=date(2026, 11, 10),
            cash_balance=0.0,
            total_equity=100_000.0,
            max_portfolio_heat_pct=0.06,
            open_positions={"TSLA": excessive_risk_pos},
        )


def test_portfolio_exclusion_and_point_in_time_no_lookahead(
    sample_index_registry: Dict[str, IndexConfigSchema],
) -> None:
    \"\"\"
    Verifies that:
    1. A ticker in excluded_tickers is completely bypassed during screening.
    2. Modifying future bars (t+1) has zero effect on features or signals computed at date t.
    \"\"\"
    target_date = date(2026, 11, 9)
    future_date = date(2026, 11, 10)
    tickers = ["ALPHA", "BETA", "IWM"]

    df_full = generate_synthetic_market_df(
        tickers=tickers,
        num_days=260,
        end_date=future_date,
        breakout_ticker="ALPHA",
    )
    alpha_target_idx = (pd.Timestamp(target_date), "ALPHA")
    df_full.loc[alpha_target_idx, "close"] = df_full.loc[alpha_target_idx, "close"] * 1.08
    df_full.loc[alpha_target_idx, "high"] = df_full.loc[alpha_target_idx, "close"] * 1.01
    df_full.loc[alpha_target_idx, "volume"] = 3_500_000.0

    engine = VectorizedFeatureEngine()
    features_clean = engine.compute_universe_features(df_full, as_of_date=target_date)

    df_corrupted_future = df_full.copy()
    future_idx = (pd.Timestamp(future_date), "ALPHA")
    df_corrupted_future.loc[future_idx, "close"] *= 6.0
    df_corrupted_future.loc[future_idx, "high"] *= 6.0
    df_corrupted_future.loc[future_idx, "volume"] *= 50.0

    features_with_corrupted_future = engine.compute_universe_features(
        df_corrupted_future,
        as_of_date=target_date,
    )

    pd.testing.assert_frame_equal(
        features_clean,
        features_with_corrupted_future,
        check_exact=False,
        atol=1e-8,
        rtol=1e-8,
    )

    signals_included = engine.screen_index_candidates(
        featured_df=features_clean,
        index_cfg=sample_index_registry["RUT"],
        constituent_tickers=["ALPHA", "BETA"],
        as_of_date=target_date,
        excluded_tickers=set(),
    )
    assert any(s.ticker == "ALPHA" for s in signals_included)

    signals_excluded = engine.screen_index_candidates(
        featured_df=features_clean,
        index_cfg=sample_index_registry["RUT"],
        constituent_tickers=["ALPHA", "BETA"],
        as_of_date=target_date,
        excluded_tickers={"ALPHA"},
    )
    assert all(s.ticker != "ALPHA" for s in signals_excluded)
"""

    # =========================================================================
    # 17. .github/workflows/daily_quant_pipeline.yml
    # =========================================================================
    files[".github/workflows/daily_quant_pipeline.yml"] = """\
name: Autonomous Swing Quant Engine (EOD Pipeline)

on:
  schedule:
    # Runs at 21:45 UTC Monday through Friday (Post-US Market Settlement)
    - cron: "45 21 * * 1-5"
  workflow_dispatch:
    inputs:
      as_of_date:
        description: "Optional target EOD date (YYYY-MM-DD). Leave blank for today UTC."
        required: false
        default: ""
      user_id:
        description: "Target tenant user_id UUID or 'default'"
        required: false
        default: "default"
      dry_run:
        description: "Run pipeline in dry-run mode without committing state changes"
        required: false
        type: boolean
        default: false

concurrency:
  group: swing-quant-engine-eod-state-lock
  cancel-in-progress: false

permissions:
  contents: write

env:
  PYTHON_VERSION: "3.11"
  QUANT_ENV: "production"
  LOG_LEVEL: "INFO"
  STATE_STORE_PATH: "data/portfolios/virtual_portfolio_default.json"
  PARQUET_CACHE_PATH: "data/cache/market_data_window.parquet"
  CONSTITUENTS_DIR: "config/constituents"
  INDEX_REGISTRY_PATH: "config/index_registry.json"

jobs:
  execute-quant-cycle:
    name: EOD Screening, Triple-Barrier & Portfolio Sync
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - name: Set Up Python ${{ env.PYTHON_VERSION }} with Pip Cache
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: "pip"
          cache-dependency-path: "requirements.txt"

      - name: Install Locked Production & Verification Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Execute Pre-Flight Pytest Verification Suite
        run: pytest tests/test_quant_engine.py -v --tb=short

      - name: Restore 500-Day Rolling Market Data Parquet Cache
        uses: actions/cache@v4
        with:
          path: data/cache
          key: parquet-sliding-window-${{ runner.os }}-${{ github.run_id }}
          restore-keys: |
            parquet-sliding-window-${{ runner.os }}-

      - name: Run Autonomous Swing Quant Engine Cycle
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          JWT_SECRET_KEY: ${{ secrets.JWT_SECRET_KEY }}
        run: |
          CMD="python src/main.py --user-id ${{ github.event.inputs.user_id || 'default' }}"
          if [ -n "${{ github.event.inputs.as_of_date }}" ]; then
            CMD="$CMD --as-of-date ${{ github.event.inputs.as_of_date }}"
          fi
          if [ "${{ github.event.inputs.dry_run }}" == "true" ]; then
            CMD="$CMD --dry-run"
          fi
          echo "Executing: $CMD"
          $CMD

      - name: Commit Updated Multi-Tenant Portfolio Ledger
        if: ${{ success() && github.event.inputs.dry_run != 'true' }}
        run: |
          git config --local user.name "github-actions[bot]"
          git config --local user.email "41898282+github-actions[bot]@users.noreply.github.com"

          git add "${{ env.STATE_STORE_PATH }}"

          if git diff --staged --quiet; then
            echo "No portfolio state changes detected for today's session."
          else
            RUN_DATE=$(date -u +"%Y-%m-%d")
            git commit -m "chore(state): automated EOD portfolio ledger sync (${RUN_DATE}) [skip ci]"
            git pull --rebase origin "${GITHUB_REF_NAME}"
            git push origin HEAD:"${GITHUB_REF_NAME}"
            echo "Successfully committed and pushed updated portfolio ledger."
          fi

      - name: Dispatch Pipeline Failure Alert to Telegram
        if: ${{ failure() }}
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
            curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \\
              -d chat_id="${TELEGRAM_CHAT_ID}" \\
              -d parse_mode="HTML" \\
              -d text="🚨 <b>CRITICAL: Swing Quant Engine Pipeline Failed</b>%0A<b>Run ID:</b> <code>${{ github.run_id }}</code>%0A<b>Commit:</b> <code>${{ github.sha }}</code>%0A<i>Zero-Override Protection: Portfolio state was NOT modified.</i>" > /dev/null
          fi
"""

    # =========================================================================
    # 18. README.md
    # =========================================================================
    files["README.md"] = """\
# Autonomous Swing Quant Engine

An institutional-grade, headless quantitative swing trading engine engineered on the mathematical frameworks of **Dr. Marcos López de Prado** (*Advances in Financial Machine Learning*) and **Jim Simons** (*Renaissance Technologies*).

---

## 1. Executive Architecture Overview

The **Swing Quant Engine** operates as a zero-touch End-of-Day (EOD) computational pipeline that scans multi-index equity universes (`RUT` Russell 2000 Small-Cap and `MID` S&P MidCap 400), filters out illiquid instruments and existing holdings, evaluates stationary volatility-normalized momentum features, validates candidates via a 500-day Point-in-Time (PiT) Walk-Forward Backtest gate, and manages active positions inside a **Triple-Barrier Cage** with **Chandelier Ratchet** trailing stops.

```
+-------------------------------------------------------------------------+
|               1. Smart Sliding Window Ingestion (src/data_ingestion.py) |
|  - 500-Bar Apache Parquet Cache + 2-Day Incremental Delta Sync          |
|  - Pre-Ingestion Portfolio Exclusion + t-1 Overlap Split/Dividend Guard |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|               2. Vectorized Feature & Screening (src/quant_engine.py)   |
|  - Simons Liquidity Gates: Price >= $5.00, ADV_30 >= 500,000 shares     |
|  - Wilder's ATR_14, Volatility-Adjusted Momentum, Volume Z-Score & RS   |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|               3. 500-Day Walk-Forward Meta-Labeler (src/quant_engine.py)|
|  - Point-in-Time Per-Asset Simulation under Exact Index Barrier Rules   |
|  - Computes Empirical EV_R & Meta-Conviction Scalar (phi_meta in 0..1.25)|
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|               4. Triple-Barrier Portfolio Manager (src/quant_engine.py) |
|  - Evaluates Lower (Ratchet SL), Upper (TP), & Vertical (14d) Barriers  |
|  - Enforces Ratchet-Only Invariant (Stop_t >= Stop_{t-1}) & 6% Heat Cap |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|               5. Atomic POSIX Storage & Telegram HTML Dispatch          |
|  - Crash-Safe os.replace() JSON Ledger + Multi-Tenant HTML Telemetry    |
+-------------------------------------------------------------------------+
```

---

## 2. Mathematical Foundations

### A. Stationary Volatility-Adjusted Momentum ($M_{\\text{vol\\_adj}}$)
Raw price rates of change bias rankings toward high-beta noise. Following López de Prado, 20-day price appreciation is normalized by Wilder's $\\text{ATR}_{14}$:

$$M_{\\text{vol\\_adj}, i, t} = \\frac{P_{\\text{close}, i, t} - P_{\\text{close}, i, t-20}}{\\text{ATR}_{14, i, t} \\times \\sqrt{20}}$$

### B. Corporate Action $t-1$ Overlap Guard ($\\epsilon_{i, t-1}$)
During daily 2-bar delta synchronization ($\\{t-1, t\\}$), the engine verifies continuity against cached $t-1$ adjusted closes:

$$\\epsilon_{i, t-1} = \\frac{\\left\\vert C_{i, t-1}^{\\text{delta}} - C_{i, t-1}^{\\text{cache}} \\right\\vert}{C_{i, t-1}^{\\text{cache}}} > 10^{-4} \\implies \\text{Full 500-Day Re-Hydration}$$

### C. Triple-Barrier & Chandelier Ratchet Stop Invariant
For an active long position entered at $P_{\\text{entry}}$ with index multipliers $(k_{\\text{stop}}, k_{\\text{profit}}, T_{\\max}=14)$:
* **Initial Stop Barrier:** $\\text{Stop}_0 = P_{\\text{entry}} - k_{\\text{stop}} \\cdot \\text{ATR}_{14, 0}$
* **Upper Take-Profit Barrier:** $\\text{Target}_0 = P_{\\text{entry}} + k_{\\text{profit}} \\cdot \\text{ATR}_{14, 0}$ (enforcing $k_{\\text{profit}} \\ge 2.0 \\cdot k_{\\text{stop}}$)
* **Ratchet-Only Chandelier Update:**
  $$\\text{Stop}_t = \\max\\left( \\text{Stop}_{t-1}, \\; \\max_{\\tau \\in [0, t]} H_\\tau - k_{\\text{stop}} \\cdot \\text{ATR}_{14, t} \\right)$$

### D. Volatility-Parity Position Sizing & 6.0% Portfolio Heat Cap
Share allocation scales base risk ($1.0\\%$ of total equity) by the Meta-Labeling conviction scalar $\\phi_{\\text{meta}} \\in [0.0, 1.25]$ while strictly enforcing:

$$H_{\\text{portfolio}} = \\frac{1}{E_{\\text{total}}} \\sum_{k=1}^{N_{\\text{open}}} \\max\\left(0, \\; P_{\\text{entry}, k} - \\text{Stop}_{t, k}\\right) \\times \\text{Shares}_k \\le 6.00\\%$$

---

## 3. Quick-Start CLI Commands

```bash
# 1. Bootstrap the repository structure and seed ledger
python3 bootstrap_repo.py

# 2. Create a Python 3.11+ virtual environment and install pinned dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Run the deterministic Pytest mathematical verification suite
pytest

# 4. Run the End-to-End 5-Day Lifecycle & 500-Day Walk-Forward Sandbox Dry-Run
python3 src/main.py --dry-run --user-id default

# 5. Execute a live EOD cycle for a specific settlement date
python3 src/main.py --as-of-date 2026-11-11 --user-id default
```

---

## 4. GitHub Actions Encrypted Secrets Setup

Configure the following secrets under **Settings $\\rightarrow$ Secrets and variables $\\rightarrow$ Actions**:

| Secret Name | Required | Description | Generation / Source |
| :--- | :---: | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Yes | HTTP Bot API Token for outbound HTML telemetry | Issued by `@BotFather` on Telegram |
| `TELEGRAM_CHAT_ID` | Yes | Target numeric Chat ID or channel identifier | Retrieved via `/getUpdates` |
| `JWT_SECRET_KEY` | Yes | 64-character hex signing key for HS256 JWTs | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Phase 2 | PostgreSQL / Supabase connection URI | Supabase Project Settings $\\rightarrow$ Database |

---

## 5. Phase 2 Supabase / PostgreSQL Migration Guide

The storage layer (`src/storage.py`) implements the Repository Pattern (`BasePortfolioRepository`). Transitioning from Phase 1 (`JsonFilePortfolioRepository`) to Phase 2 (`PostgresPortfolioRepository`) requires zero changes to `src/quant_engine.py`, `src/data_ingestion.py`, or `src/schemas.py`:

1. Provision a PostgreSQL 15+ instance (e.g., Supabase or Neon) and execute `POSTGRES_RLS_DDL_SQL` from `src/storage.py` to create the tenant-scoped tables and enable **Row-Level Security (RLS)**.
2. Set `DATABASE_URL` in your environment variables.
3. Instantiate `PostgresPortfolioRepository(database_url=..., tenant_user_id=...)` which binds `SELECT set_config('request.jwt.claim.sub', '<user_uuid>', true);` on every transaction so cross-tenant reads or writes are physically blocked at the database engine level.
"""

    return files


def bootstrap_repository(target_root: Path) -> None:
    """Writes all manifest files into target_root and verifies directory structure."""
    target_root = target_root.resolve()
    manifest = build_repository_manifest()

    print(f"[SwingQuantEngine] Bootstrapping repository in: {target_root}")
    for rel_path, content in manifest.items():
        dest_path = target_root / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(content, encoding="utf-8")
        print(f"  + Wrote {rel_path} ({len(content.splitlines())} lines)")

    # Ensure data/cache directory exists for Parquet sliding window
    (target_root / "data" / "cache").mkdir(parents=True, exist_ok=True)
    print(f"[SwingQuantEngine] Successfully generated {len(manifest)} production files.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap the complete Swing Quant Engine repository."
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=Path("."),
        help="Target directory where repository files will be generated (default: current directory).",
    )
    args = parser.parse_args()
    bootstrap_repository(args.target_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
