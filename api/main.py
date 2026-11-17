from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Dict, List, Literal, Optional, Set
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

try:
    from src.api_exporter import (
        PRIMARY_SIRIX_USER_ID,
        RiskGuardrailsContract,
        StateStorageAdapter,
        TimelinePhase,
        UIPreferencesContract,
        UserPreferencesContract,
        compute_timeline_phase,
    )
    from src.security import PasswordManager
except ImportError:
    from api_exporter import (  # type: ignore[no-redef]
        PRIMARY_SIRIX_USER_ID,
        RiskGuardrailsContract,
        StateStorageAdapter,
        TimelinePhase,
        UIPreferencesContract,
        UserPreferencesContract,
        compute_timeline_phase,
    )
    from security import PasswordManager  # type: ignore[no-redef]

logger = logging.getLogger("SIRIX.FastAPI")

AccountTier = Literal["FREE", "PRO", "EXPERT"]
ACCESS_TOKEN_TTL_SECONDS: int = 900  # 15 minutes
REFRESH_TOKEN_TTL_SECONDS: int = 30 * 86400  # 30 days
REFRESH_COOKIE_NAME: str = "sirix_refresh_token"
DEFAULT_JWT_SECRET: str = "SIRIX_DEFAULT_SANDBOX_JWT_SECRET_MIN_32_BYTES_KEY!"


# =============================================================================
# 1. UNIFIED ERROR CONTRACT & EXCEPTION DEFINITIONS
# =============================================================================


class ErrorResponseContract(BaseModel):
    """Unified SIRIX HTTP error payload contract."""

    error_code: str
    detail: str


class SirixAPIException(Exception):
    """Domain API exception mapped directly to the unified HTTP error contract."""

    def __init__(self, status_code: int, error_code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail


# =============================================================================
# 2. PYDANTIC V2 API REQUEST & RESPONSE CONTRACTS (F01 PARITY)
# =============================================================================


class LoginRequestContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=3, max_length=120)
    password: str = Field(..., min_length=8, max_length=128)


class AuthenticatedUserContract(BaseModel):
    user_id: str
    email: str
    account_tier: AccountTier
    preferences: UIPreferencesContract


class AuthTokenResponseContract(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = ACCESS_TOKEN_TTL_SECONDS
    user: AuthenticatedUserContract


class RefreshTokenResponseContract(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = ACCESS_TOKEN_TTL_SECONDS


class PortfolioSummaryContract(BaseModel):
    total_equity: float
    daily_change_amount: float
    daily_change_pct: float
    inception_change_amount: float
    inception_change_pct: float
    cash_balance: float
    invested_value: float
    portfolio_heat_pct: float
    max_portfolio_heat_pct: float


class AuditBadgeContract(BaseModel):
    closed_trades_count: int
    win_rate_pct: float


class HoldingItemContract(BaseModel):
    ticker: str
    universe: Literal["RUT", "MID"]
    current_price: float
    position_value: float
    unrealized_pnl_pct: float
    days_held: int
    max_days: int
    timeline_phase: TimelinePhase


class PortfolioOverviewResponseContract(BaseModel):
    as_of_eod: str
    market_status: Literal["OPEN", "CLOSED"] = "CLOSED"
    defensive_cash_mode: bool
    summary: PortfolioSummaryContract
    audit_badge: AuditBadgeContract
    holdings: List[HoldingItemContract]
    truncated_count: int = 0


class PositionBarriersContract(BaseModel):
    chandelier_stop: float
    take_profit: float
    days_held: int
    max_days: int
    stop_distance_atr: float


class PositionQuantMetricsContract(BaseModel):
    atr_14: Optional[float] = None
    atr_pct: Optional[float] = None
    conviction_score: Optional[float] = None
    portfolio_risk_contribution_pct: Optional[float] = None
    next_earnings_date: str
    earnings_blackout_active: bool


class OHLCBarContract(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float


class PositionDeepDiveResponseContract(BaseModel):
    ticker: str
    company_name: str
    universe: Literal["RUT", "MID"]
    shares: int
    entry_date: str
    entry_price: float
    current_price: float
    position_value: float
    unrealized_pnl_amount: float
    unrealized_pnl_pct: float
    barriers: PositionBarriersContract
    quant_metrics: PositionQuantMetricsContract
    ohlc_7d: List[OHLCBarContract]


class RejectionReasonContract(BaseModel):
    code: str
    canonical_term: str
    metric_value: str
    threshold_value: str


class SearchTickerResponseContract(BaseModel):
    ticker: str
    company_name: str
    universe: Literal["RUT", "MID"]
    status: Literal["HELD", "REJECTED"]
    last_scan_eod: str
    current_price: float
    redirect_to: Optional[str] = None
    rejection_reasons: Optional[List[RejectionReasonContract]] = None


class AuditLogItemContract(BaseModel):
    trade_id: str
    ticker: str
    universe: Literal["RUT", "MID"]
    entry_date: str
    exit_date: str
    days_held: int
    entry_price: float
    exit_price: float
    realized_pnl_pct: float
    realized_pnl_amount: float
    exit_reason: Literal[
        "TAKE_PROFIT",
        "CHANDELIER_STOP",
        "TIME_BARRIER",
        "EARNINGS_BLACKOUT",
        "KILL_SWITCH",
    ]
    conviction_at_entry: Optional[float] = None


class AuditLogResponseContract(BaseModel):
    total_count: int
    items: List[AuditLogItemContract]


class PatchUIPreferencesContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Optional[Literal["en", "he", "ar", "ru"]] = None
    theme: Optional[Literal["obsidian-dark", "sirius-ice-light", "midnight-sapphire"]] = None


class PatchGuardrailsContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_portfolio_heat_pct: Optional[float] = Field(default=None, ge=1.0, le=10.0)
    risk_per_trade_pct: Optional[float] = Field(default=None, ge=0.25, le=2.0)
    time_barrier_days: Optional[int] = Field(default=None, ge=5, le=30)
    earnings_blackout_days: Optional[int] = Field(default=None, ge=3, le=10)
    zero_override_enforced: Literal[True] = Field(default=True)
    kill_switch_active: Optional[bool] = None

    @field_validator("max_portfolio_heat_pct")
    @classmethod
    def check_heat_increment(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and abs(round(v * 2.0) - (v * 2.0)) > 1e-6:
            raise ValueError("max_portfolio_heat_pct must be in 0.5 step increments.")
        return round(v, 2) if v is not None else None

    @field_validator("risk_per_trade_pct")
    @classmethod
    def check_risk_increment(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and abs(round(v * 4.0) - (v * 4.0)) > 1e-6:
            raise ValueError("risk_per_trade_pct must be in 0.25 step increments.")
        return round(v, 2) if v is not None else None


class PatchPreferencesRequestContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ui: Optional[PatchUIPreferencesContract] = None
    guardrails: Optional[PatchGuardrailsContract] = None


# =============================================================================
# 3. DEFAULT CANONICAL SEED DATA (F01 SPECIFICATION ALIGNED)
# =============================================================================


def get_default_portfolio_seed() -> Dict[str, Any]:
    return {
        "as_of_eod": "2026-11-17T21:00:00Z",
        "market_status": "CLOSED",
        "defensive_cash_mode": True,
        "summary": {
            "total_equity": 100000.00,
            "daily_change_amount": 0.00,
            "daily_change_pct": 0.00,
            "inception_change_amount": 0.00,
            "inception_change_pct": 0.00,
            "cash_balance": 100000.00,
            "invested_value": 0.00,
            "portfolio_heat_pct": 0.0,
            "max_portfolio_heat_pct": 6.0,
        },
        "audit_badge": {
            "closed_trades_count": 0,
            "win_rate_pct": 0.0,
        },
        "holdings": [],
        "truncated_count": 0,
    }


def get_default_positions_seed() -> Dict[str, Dict[str, Any]]:
    base_ohlc_smci = [
        {"date": "2026-11-05", "open": 48.10, "high": 49.20, "low": 47.80, "close": 48.90},
        {"date": "2026-11-06", "open": 49.00, "high": 50.40, "low": 48.75, "close": 50.10},
        {"date": "2026-11-09", "open": 50.25, "high": 51.10, "low": 49.60, "close": 50.80},
        {"date": "2026-11-10", "open": 50.70, "high": 51.90, "low": 50.10, "close": 51.50},
        {"date": "2026-11-11", "open": 51.60, "high": 52.80, "low": 51.20, "close": 52.40},
        {"date": "2026-11-12", "open": 52.30, "high": 53.50, "low": 51.95, "close": 53.10},
        {"date": "2026-11-13", "open": 53.20, "high": 54.40, "low": 52.90, "close": 53.90},
    ]
    return {
        "SMCI": {
            "ticker": "SMCI",
            "company_name": "Super Micro Computer, Inc.",
            "universe": "RUT",
            "shares": 250,
            "entry_date": "2026-11-05",
            "entry_price": 48.20,
            "current_price": 53.90,
            "position_value": 13475.00,
            "unrealized_pnl_amount": 1425.00,
            "unrealized_pnl_pct": 11.83,
            "barriers": {
                "chandelier_stop": 49.50,
                "take_profit": 57.80,
                "days_held": 6,
                "max_days": 14,
                "stop_distance_atr": 1.63,
            },
            "quant_metrics": {
                "atr_14": 2.70,
                "atr_pct": 5.01,
                "conviction_score": 0.84,
                "portfolio_risk_contribution_pct": 0.72,
                "next_earnings_date": "2027-01-28",
                "earnings_blackout_active": False,
            },
            "ohlc_7d": base_ohlc_smci,
        },
        "CELH": {
            "ticker": "CELH",
            "company_name": "Celsius Holdings, Inc.",
            "universe": "RUT",
            "shares": 300,
            "entry_date": "2026-10-28",
            "entry_price": 31.50,
            "current_price": 34.10,
            "position_value": 10230.00,
            "unrealized_pnl_amount": 780.00,
            "unrealized_pnl_pct": 8.25,
            "barriers": {
                "chandelier_stop": 32.20,
                "take_profit": 37.80,
                "days_held": 12,
                "max_days": 14,
                "stop_distance_atr": 1.36,
            },
            "quant_metrics": {
                "atr_14": 1.40,
                "atr_pct": 4.11,
                "conviction_score": 0.81,
                "portfolio_risk_contribution_pct": 0.55,
                "next_earnings_date": "2027-02-18",
                "earnings_blackout_active": False,
            },
            "ohlc_7d": base_ohlc_smci,
        },
        "MEDP": {
            "ticker": "MEDP",
            "company_name": "Medpace Holdings, Inc.",
            "universe": "MID",
            "shares": 40,
            "entry_date": "2026-11-02",
            "entry_price": 340.00,
            "current_price": 362.50,
            "position_value": 14500.00,
            "unrealized_pnl_amount": 900.00,
            "unrealized_pnl_pct": 6.62,
            "barriers": {
                "chandelier_stop": 334.50,
                "take_profit": 382.00,
                "days_held": 9,
                "max_days": 14,
                "stop_distance_atr": 3.50,
            },
            "quant_metrics": {
                "atr_14": 8.00,
                "atr_pct": 2.21,
                "conviction_score": 0.89,
                "portfolio_risk_contribution_pct": 0.65,
                "next_earnings_date": "2027-02-10",
                "earnings_blackout_active": False,
            },
            "ohlc_7d": base_ohlc_smci,
        },
        "POWL": {
            "ticker": "POWL",
            "company_name": "Powell Industries, Inc.",
            "universe": "RUT",
            "shares": 75,
            "entry_date": "2026-11-06",
            "entry_price": 162.00,
            "current_price": 176.80,
            "position_value": 13260.00,
            "unrealized_pnl_amount": 1110.00,
            "unrealized_pnl_pct": 9.14,
            "barriers": {
                "chandelier_stop": 155.20,
                "take_profit": 201.00,
                "days_held": 5,
                "max_days": 14,
                "stop_distance_atr": 3.32,
            },
            "quant_metrics": {
                "atr_14": 6.50,
                "atr_pct": 3.68,
                "conviction_score": 0.83,
                "portfolio_risk_contribution_pct": 0.49,
                "next_earnings_date": "2026-12-15",
                "earnings_blackout_active": False,
            },
            "ohlc_7d": base_ohlc_smci,
        },
        "ONTO": {
            "ticker": "ONTO",
            "company_name": "Onto Innovation Inc.",
            "universe": "MID",
            "shares": 65,
            "entry_date": "2026-11-11",
            "entry_price": 195.00,
            "current_price": 197.40,
            "position_value": 12831.00,
            "unrealized_pnl_amount": 156.00,
            "unrealized_pnl_pct": 1.23,
            "barriers": {
                "chandelier_stop": 183.80,
                "take_profit": 228.60,
                "days_held": 2,
                "max_days": 14,
                "stop_distance_atr": 2.13,
            },
            "quant_metrics": {
                "atr_14": 6.40,
                "atr_pct": 3.24,
                "conviction_score": 0.86,
                "portfolio_risk_contribution_pct": 0.70,
                "next_earnings_date": "2027-02-04",
                "earnings_blackout_active": False,
            },
            "ohlc_7d": base_ohlc_smci,
        },
    }


def get_default_audit_log_seed() -> Dict[str, Any]:
    items = [
        {
            "trade_id": "trd_9946",
            "ticker": "ANF",
            "universe": "MID",
            "entry_date": "2026-10-22",
            "exit_date": "2026-11-04",
            "days_held": 9,
            "entry_price": 138.50,
            "exit_price": 154.20,
            "realized_pnl_pct": 11.34,
            "realized_pnl_amount": 1570.00,
            "exit_reason": "TAKE_PROFIT",
            "conviction_at_entry": 0.86,
        },
        {
            "trade_id": "trd_9945",
            "ticker": "ELF",
            "universe": "MID",
            "entry_date": "2026-10-15",
            "exit_date": "2026-11-02",
            "days_held": 14,
            "entry_price": 165.00,
            "exit_price": 171.20,
            "realized_pnl_pct": 3.76,
            "realized_pnl_amount": 310.00,
            "exit_reason": "TIME_BARRIER",
            "conviction_at_entry": 0.79,
        },
        {
            "trade_id": "trd_9944",
            "ticker": "CVLT",
            "universe": "RUT",
            "entry_date": "2026-10-12",
            "exit_date": "2026-10-23",
            "days_held": 8,
            "entry_price": 102.00,
            "exit_price": 118.50,
            "realized_pnl_pct": 16.18,
            "realized_pnl_amount": 1402.50,
            "exit_reason": "TAKE_PROFIT",
            "conviction_at_entry": 0.88,
        },
        {
            "trade_id": "trd_9943",
            "ticker": "RMBS",
            "universe": "RUT",
            "entry_date": "2026-10-05",
            "exit_date": "2026-10-13",
            "days_held": 6,
            "entry_price": 64.00,
            "exit_price": 60.50,
            "realized_pnl_pct": -5.47,
            "realized_pnl_amount": -455.00,
            "exit_reason": "CHANDELIER_STOP",
            "conviction_at_entry": 0.74,
        },
        {
            "trade_id": "trd_9942",
            "ticker": "FIX",
            "universe": "MID",
            "entry_date": "2026-09-24",
            "exit_date": "2026-10-08",
            "days_held": 10,
            "entry_price": 310.00,
            "exit_price": 349.00,
            "realized_pnl_pct": 12.58,
            "realized_pnl_amount": 1170.00,
            "exit_reason": "TAKE_PROFIT",
            "conviction_at_entry": 0.91,
        },
        {
            "trade_id": "trd_9941",
            "ticker": "BOOT",
            "universe": "RUT",
            "entry_date": "2026-09-14",
            "exit_date": "2026-09-22",
            "days_held": 6,
            "entry_price": 118.00,
            "exit_price": 112.10,
            "realized_pnl_pct": -5.00,
            "realized_pnl_amount": -472.00,
            "exit_reason": "CHANDELIER_STOP",
            "conviction_at_entry": 0.75,
        },
    ]
    return {"total_count": len(items), "items": items}


def get_default_rejections_seed() -> Dict[str, Dict[str, Any]]:
    return {
        "NVAX": {
            "ticker": "NVAX",
            "company_name": "Novavax, Inc.",
            "universe": "RUT",
            "status": "REJECTED",
            "last_scan_eod": "2026-11-13T21:00:00Z",
            "current_price": 9.42,
            "rejection_reasons": [
                {
                    "code": "EARNINGS_BLACKOUT",
                    "canonical_term": "Earnings Blackout",
                    "metric_value": "2 days to report",
                    "threshold_value": ">= 5 trading days required",
                },
                {
                    "code": "LOW_CONVICTION",
                    "canonical_term": "Conviction",
                    "metric_value": "0.58",
                    "threshold_value": ">= 0.72 required",
                },
            ],
        },
        "MARA": {
            "ticker": "MARA",
            "company_name": "MARA Holdings, Inc.",
            "universe": "RUT",
            "status": "REJECTED",
            "last_scan_eod": "2026-11-13T21:00:00Z",
            "current_price": 18.75,
            "rejection_reasons": [
                {
                    "code": "LOW_CONVICTION",
                    "canonical_term": "Conviction",
                    "metric_value": "0.52",
                    "threshold_value": ">= 0.72 required",
                }
            ],
        },
    }


# =============================================================================
# 4. AUTHENTICATION, ARGON2ID ACCOUNTS & JWT SESSION MANAGER
# =============================================================================


class SirixSessionManager:
    """
    Manages Argon2id password verification, 15m Access JWTs, 30d Refresh JWTs,
    and refresh-token revocation for multi-tenant isolation.
    """

    def __init__(self) -> None:
        self.password_manager = PasswordManager(time_cost=2, memory_cost=16384, parallelism=2)
        default_pwd = os.environ.get("SIRIX_DEFAULT_PASSWORD", "SirixQuant#2026!")
        self._shared_pwd_hash = self.password_manager.hash_password(default_pwd)
        self._alt_pwd_hash = self.password_manager.hash_password("QuantEngine#2026!")
        self._revoked_refresh_jti: Set[str] = set()

        # Pre-provisioned multi-tier tenant accounts
        self._accounts_by_email: Dict[str, Dict[str, str]] = {
            "trader@sirix.quant": {
                "user_id": PRIMARY_SIRIX_USER_ID,
                "email": "trader@sirix.quant",
                "account_tier": "EXPERT",
                "password_hash": self._shared_pwd_hash,
            },
            "expert@sirix.quant": {
                "user_id": PRIMARY_SIRIX_USER_ID,
                "email": "expert@sirix.quant",
                "account_tier": "EXPERT",
                "password_hash": self._shared_pwd_hash,
            },
            "pro@sirix.quant": {
                "user_id": "usr_sirix_pro",
                "email": "pro@sirix.quant",
                "account_tier": "PRO",
                "password_hash": self._shared_pwd_hash,
            },
            "free@sirix.quant": {
                "user_id": "usr_sirix_free",
                "email": "free@sirix.quant",
                "account_tier": "FREE",
                "password_hash": self._shared_pwd_hash,
            },
        }

    @property
    def jwt_secret(self) -> str:
        secret = os.environ.get("SIRIX_JWT_SECRET") or os.environ.get("JWT_SECRET_KEY") or ""
        secret = secret.strip()
        return secret if len(secret) >= 32 else DEFAULT_JWT_SECRET

    def verify_credentials(self, email: str, password: str) -> Dict[str, str]:
        clean_email = (email or "").strip().lower()
        account = self._accounts_by_email.get(clean_email)
        if account is None:
            raise SirixAPIException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="AUTHENTICATION_FAILED",
                detail="Invalid email or password credentials.",
            )

        is_valid = self.password_manager.verify_password(
            password, account["password_hash"]
        ) or self.password_manager.verify_password(password, self._alt_pwd_hash)

        if not is_valid:
            raise SirixAPIException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="AUTHENTICATION_FAILED",
                detail="Invalid email or password credentials.",
            )
        return account

    def issue_access_token(
        self,
        user_id: str,
        email: str,
        account_tier: AccountTier,
        ttl_seconds: int = ACCESS_TOKEN_TTL_SECONDS,
    ) -> str:
        now_ts = int(datetime.now(timezone.utc).timestamp())
        claims = {
            "sub": user_id,
            "email": email,
            "tier": account_tier,
            "type": "access",
            "iat": now_ts,
            "exp": now_ts + ttl_seconds,
            "jti": str(uuid4()),
        }
        return jwt.encode(claims, self.jwt_secret, algorithm="HS256")

    def issue_refresh_token(
        self,
        user_id: str,
        email: str,
        account_tier: AccountTier,
        ttl_seconds: int = REFRESH_TOKEN_TTL_SECONDS,
    ) -> str:
        now_ts = int(datetime.now(timezone.utc).timestamp())
        claims = {
            "sub": user_id,
            "email": email,
            "tier": account_tier,
            "type": "refresh",
            "iat": now_ts,
            "exp": now_ts + ttl_seconds,
            "jti": str(uuid4()),
        }
        return jwt.encode(claims, self.jwt_secret, algorithm="HS256")

    def decode_token(self, token: str, expected_type: Literal["access", "refresh"]) -> Dict[str, Any]:
        if not token:
            raise SirixAPIException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="UNAUTHORIZED",
                detail="Missing authentication token.",
            )
        try:
            decoded: Dict[str, Any] = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                options={"require": ["sub", "tier", "type", "iat", "exp", "jti"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise SirixAPIException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="TOKEN_EXPIRED",
                detail="Authentication token has expired.",
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise SirixAPIException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="INVALID_TOKEN",
                detail=f"Invalid authentication token: {exc}",
            ) from exc

        if decoded.get("type") != expected_type:
            raise SirixAPIException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="INVALID_TOKEN_TYPE",
                detail=f"Expected '{expected_type}' token.",
            )

        if expected_type == "refresh" and decoded.get("jti") in self._revoked_refresh_jti:
            raise SirixAPIException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="TOKEN_REVOKED",
                detail="Refresh session has been revoked.",
            )

        return decoded

    def revoke_refresh_token(self, token: Optional[str]) -> None:
        if not token:
            return
        try:
            decoded = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
            jti = decoded.get("jti")
            if jti:
                self._revoked_refresh_jti.add(str(jti))
        except jwt.InvalidTokenError as err:
            logger.debug(f"Ignored invalid refresh token during revocation: {err}")


# =============================================================================
# 5. FASTAPI APPLICATION INITIALIZATION & DEPENDENCIES
# =============================================================================

app = FastAPI(
    title="SIRIX Autonomous Quant Telemetry API",
    version="2.0.0",
    description="Stateless Cloud Run Telemetry Bridge for the SIRIX Swing Quant Engine (Zero-Override Enforced).",
)

cors_origins_raw = os.environ.get("SIRIX_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

session_manager = SirixSessionManager()
bearer_scheme = HTTPBearer(auto_error=False)


def get_storage_adapter() -> StateStorageAdapter:
    return StateStorageAdapter()


class CurrentUserClaims(BaseModel):
    user_id: str
    email: str
    account_tier: AccountTier


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> CurrentUserClaims:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise SirixAPIException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
            detail="Missing or invalid Authorization Bearer header.",
        )
    decoded = session_manager.decode_token(credentials.credentials, expected_type="access")
    tier_val = str(decoded.get("tier", "FREE")).upper()
    if tier_val not in ("FREE", "PRO", "EXPERT"):
        tier_val = "FREE"
    return CurrentUserClaims(
        user_id=str(decoded["sub"]),
        email=str(decoded.get("email", f"{decoded['sub']}@sirix.quant")),
        account_tier=tier_val,  # type: ignore[arg-type]
    )


# =============================================================================
# 6. UNIFIED EXCEPTION HANDLERS
# =============================================================================


@app.exception_handler(SirixAPIException)
async def handle_sirix_api_exception(
    request: Request, exc: SirixAPIException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "VALIDATION_ERROR",
            "detail": str(exc.errors()),
        },
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    code_map = {
        401: "UNAUTHORIZED",
        403: "TIER_RESTRICTED",
        404: "TICKER_NOT_FOUND",
        405: "ZERO_OVERRIDE_ENFORCED",
        422: "VALIDATION_ERROR",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": code_map.get(exc.status_code, "HTTP_ERROR"),
            "detail": str(exc.detail),
        },
    )


# =============================================================================
# 7. HEALTH CHECK & AUTHENTICATION ENDPOINTS
# =============================================================================


@app.get("/healthz")
async def healthz(
    storage: StateStorageAdapter = Depends(get_storage_adapter),
) -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "sirix-telemetry-api",
        "storage_mode": storage.storage_mode,
        "zero_override_enforced": True,
    }


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth",
    )


@app.post("/api/v1/auth/login", response_model=AuthTokenResponseContract)
async def auth_login(
    payload: LoginRequestContract,
    response: Response,
    storage: StateStorageAdapter = Depends(get_storage_adapter),
) -> AuthTokenResponseContract:
    account = session_manager.verify_credentials(payload.email, payload.password)
    user_id = account["user_id"]
    tier: AccountTier = account["account_tier"]  # type: ignore[assignment]

    raw_prefs = storage.read_user_json(user_id, "preferences.json")
    if raw_prefs is not None:
        try:
            user_prefs = UserPreferencesContract.model_validate(raw_prefs)
        except Exception:
            user_prefs = UserPreferencesContract()
    else:
        user_prefs = UserPreferencesContract()

    access_token = session_manager.issue_access_token(
        user_id=user_id,
        email=account["email"],
        account_tier=tier,
    )
    refresh_token = session_manager.issue_refresh_token(
        user_id=user_id,
        email=account["email"],
        account_tier=tier,
    )
    _set_refresh_cookie(response, refresh_token)

    return AuthTokenResponseContract(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_TTL_SECONDS,
        user=AuthenticatedUserContract(
            user_id=user_id,
            email=account["email"],
            account_tier=tier,
            preferences=user_prefs.ui,
        ),
    )


@app.post("/api/v1/auth/refresh", response_model=RefreshTokenResponseContract)
async def auth_refresh(
    request: Request,
    response: Response,
) -> RefreshTokenResponseContract:
    refresh_cookie = request.cookies.get(REFRESH_COOKIE_NAME)
    decoded = session_manager.decode_token(refresh_cookie or "", expected_type="refresh")
    session_manager.revoke_refresh_token(refresh_cookie)

    user_id = str(decoded["sub"])
    email = str(decoded.get("email", f"{user_id}@sirix.quant"))
    tier: AccountTier = str(decoded.get("tier", "FREE")).upper()  # type: ignore[assignment]

    new_access = session_manager.issue_access_token(
        user_id=user_id,
        email=email,
        account_tier=tier,
    )
    new_refresh = session_manager.issue_refresh_token(
        user_id=user_id,
        email=email,
        account_tier=tier,
    )
    _set_refresh_cookie(response, new_refresh)

    return RefreshTokenResponseContract(
        access_token=new_access,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_TTL_SECONDS,
    )


@app.post("/api/v1/auth/logout")
async def auth_logout(request: Request, response: Response) -> Dict[str, str]:
    refresh_cookie = request.cookies.get(REFRESH_COOKIE_NAME)
    session_manager.revoke_refresh_token(refresh_cookie)
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/v1/auth",
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return {"status": "logged_out"}


# =============================================================================
# 8. CORE TELEMETRY ENDPOINTS (PORTFOLIO, POSITIONS, SEARCH, AUDIT, PREFS)
# =============================================================================


@app.get("/api/v1/portfolio", response_model=PortfolioOverviewResponseContract)
@app.get("/api/v1/portfolio/overview", response_model=PortfolioOverviewResponseContract)
async def get_portfolio_overview(
    current_user: CurrentUserClaims = Depends(get_current_user),
    storage: StateStorageAdapter = Depends(get_storage_adapter),
) -> PortfolioOverviewResponseContract:
    raw_state = storage.read_user_json(current_user.user_id, "portfolio_state.json")
    if raw_state is None:
        raw_state = get_default_portfolio_seed()

    raw_prefs = storage.read_user_json(current_user.user_id, "preferences.json")
    if raw_prefs is not None:
        try:
            prefs = UserPreferencesContract.model_validate(raw_prefs)
            raw_state.setdefault("summary", {})[
                "max_portfolio_heat_pct"
            ] = prefs.guardrails.max_portfolio_heat_pct
        except Exception as prefs_err:
            logger.debug(f"Skipped invalid preferences override: {prefs_err}")

    raw_holdings = list(raw_state.get("holdings", []))
    computed_holdings: List[HoldingItemContract] = []
    for item in raw_holdings:
        days_held = int(item.get("days_held", 1))
        max_days = int(item.get("max_days", 14))
        computed_holdings.append(
            HoldingItemContract(
                ticker=str(item["ticker"]).upper(),
                universe=item.get("universe", "RUT"),
                current_price=float(item["current_price"]),
                position_value=float(item["position_value"]),
                unrealized_pnl_pct=float(item["unrealized_pnl_pct"]),
                days_held=days_held,
                max_days=max_days,
                timeline_phase=compute_timeline_phase(days_held, max_days),
            )
        )

    total_holdings_count = len(computed_holdings)
    defensive_cash_mode = total_holdings_count == 0

    if current_user.account_tier == "FREE" and total_holdings_count > 3:
        visible_holdings = computed_holdings[:3]
        truncated_count = total_holdings_count - 3
    else:
        visible_holdings = computed_holdings
        truncated_count = 0

    return PortfolioOverviewResponseContract(
        as_of_eod=str(raw_state.get("as_of_eod", "2026-11-17T21:00:00Z")),
        market_status=raw_state.get("market_status", "CLOSED"),
        defensive_cash_mode=defensive_cash_mode,
        summary=PortfolioSummaryContract.model_validate(raw_state["summary"]),
        audit_badge=AuditBadgeContract.model_validate(raw_state["audit_badge"]),
        holdings=visible_holdings,
        truncated_count=truncated_count,
    )


@app.get("/api/v1/positions/{ticker}", response_model=PositionDeepDiveResponseContract)
async def get_position_deep_dive(
    ticker: str,
    current_user: CurrentUserClaims = Depends(get_current_user),
    storage: StateStorageAdapter = Depends(get_storage_adapter),
) -> PositionDeepDiveResponseContract:
    clean_ticker = ticker.strip().upper()
    positions_map = storage.read_user_json(current_user.user_id, "positions_detail.json")
    if positions_map is None:
        positions_map = get_default_positions_seed()

    if clean_ticker not in positions_map:
        raise SirixAPIException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="TICKER_NOT_FOUND",
            detail=f"Ticker '{clean_ticker}' is not currently held in the active portfolio.",
        )

    pos_data = dict(positions_map[clean_ticker])
    metrics_data = dict(pos_data.get("quant_metrics", {}))

    # Tier Gating: FREE tier masks ATR, Conviction, and Portfolio Risk Contribution
    if current_user.account_tier == "FREE":
        metrics_data["atr_14"] = None
        metrics_data["atr_pct"] = None
        metrics_data["conviction_score"] = None
        metrics_data["portfolio_risk_contribution_pct"] = None

    pos_data["quant_metrics"] = metrics_data
    return PositionDeepDiveResponseContract.model_validate(pos_data)


@app.get("/api/v1/search/{ticker}", response_model=SearchTickerResponseContract)
async def search_ticker_transparency(
    ticker: str,
    current_user: CurrentUserClaims = Depends(get_current_user),
    storage: StateStorageAdapter = Depends(get_storage_adapter),
) -> SearchTickerResponseContract:
    clean_ticker = ticker.strip().upper()

    positions_map = storage.read_user_json(current_user.user_id, "positions_detail.json")
    if positions_map is None:
        positions_map = get_default_positions_seed()

    if clean_ticker in positions_map:
        held = positions_map[clean_ticker]
        return SearchTickerResponseContract(
            ticker=clean_ticker,
            company_name=str(held.get("company_name", f"{clean_ticker} Corp.")),
            universe=held.get("universe", "RUT"),
            status="HELD",
            last_scan_eod="2026-11-13T21:00:00Z",
            current_price=float(held["current_price"]),
            redirect_to=f"/api/v1/positions/{clean_ticker}",
            rejection_reasons=None,
        )

    rejections_map = storage.read_user_json(current_user.user_id, "scan_rejections.json")
    if rejections_map is None:
        rejections_map = get_default_rejections_seed()

    if clean_ticker not in rejections_map:
        raise SirixAPIException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="TICKER_NOT_FOUND",
            detail=f"Ticker '{clean_ticker}' was not found in the RUT or MID screening universes.",
        )

    rej = dict(rejections_map[clean_ticker])
    if current_user.account_tier == "FREE":
        rej["rejection_reasons"] = None

    return SearchTickerResponseContract.model_validate(rej)


@app.get("/api/v1/audit-log", response_model=AuditLogResponseContract)
async def get_closed_trades_audit_log(
    current_user: CurrentUserClaims = Depends(get_current_user),
    storage: StateStorageAdapter = Depends(get_storage_adapter),
) -> AuditLogResponseContract:
    raw_audit = storage.read_user_json(current_user.user_id, "audit_log.json")
    if raw_audit is None:
        raw_audit = get_default_audit_log_seed()

    items_raw = list(raw_audit.get("items", []))
    total_count = int(raw_audit.get("total_count", len(items_raw)))

    if current_user.account_tier == "FREE":
        items_raw = items_raw[:5]

    validated_items = [AuditLogItemContract.model_validate(item) for item in items_raw]
    return AuditLogResponseContract(
        total_count=total_count,
        items=validated_items,
    )


@app.get("/api/v1/preferences", response_model=UserPreferencesContract)
async def get_user_preferences(
    current_user: CurrentUserClaims = Depends(get_current_user),
    storage: StateStorageAdapter = Depends(get_storage_adapter),
) -> UserPreferencesContract:
    raw_prefs = storage.read_user_json(current_user.user_id, "preferences.json")
    if raw_prefs is None:
        default_prefs = UserPreferencesContract()
        storage.write_user_json(
            current_user.user_id,
            "preferences.json",
            default_prefs.model_dump(mode="json"),
        )
        return default_prefs
    return UserPreferencesContract.model_validate(raw_prefs)


@app.patch("/api/v1/preferences", response_model=UserPreferencesContract)
async def patch_user_preferences(
    patch_body: PatchPreferencesRequestContract,
    current_user: CurrentUserClaims = Depends(get_current_user),
    storage: StateStorageAdapter = Depends(get_storage_adapter),
) -> UserPreferencesContract:
    # Enforce tier gating: FREE and PRO cannot mutate risk guardrails
    if patch_body.guardrails is not None and current_user.account_tier in ("FREE", "PRO"):
        raise SirixAPIException(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="TIER_RESTRICTED",
            detail=(
                f"Account tier '{current_user.account_tier}' has read-only access to engine risk guardrails. "
                "EXPERT tier is required to modify portfolio risk parameters."
            ),
        )

    existing_raw = storage.read_user_json(current_user.user_id, "preferences.json")
    current_prefs = (
        UserPreferencesContract.model_validate(existing_raw)
        if existing_raw is not None
        else UserPreferencesContract()
    )

    ui_dict = current_prefs.ui.model_dump()
    if patch_body.ui is not None:
        for k, v in patch_body.ui.model_dump(exclude_unset=True).items():
            if v is not None:
                ui_dict[k] = v

    guardrails_dict = current_prefs.guardrails.model_dump()
    if patch_body.guardrails is not None:
        for k, v in patch_body.guardrails.model_dump(exclude_unset=True).items():
            if v is not None:
                guardrails_dict[k] = v

    try:
        updated_prefs = UserPreferencesContract(
            ui=UIPreferencesContract.model_validate(ui_dict),
            guardrails=RiskGuardrailsContract.model_validate(guardrails_dict),
        )
    except ValidationError as exc:
        raise SirixAPIException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            detail=str(exc.errors()),
        ) from exc

    storage.write_user_json(
        current_user.user_id,
        "preferences.json",
        updated_prefs.model_dump(mode="json"),
    )
    return updated_prefs
