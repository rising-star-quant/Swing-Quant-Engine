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
    email: str = Field(..., pattern=r"^\S+@\S+\.\S+$")
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
    """Output of Step B.1 (Primary Directional Model: Side = +1)"""
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
    """Output of Step B.2 (Secondary Meta-Model & 500d Per-Asset Backtest Harness)"""
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
    """Active position strictly isolated by user_id and portfolio_id with Ratchet-Only validator."""
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
        """Guarantees that trailing_stop_price can never fall below initial_stop_price."""
        if self.trailing_stop_price + 1e-6 < self.initial_stop_price:
            raise ValueError(
                f"RATCHET VIOLATION: trailing_stop_price ({self.trailing_stop_price}) "
                f"cannot be lower than initial_stop_price ({self.initial_stop_price})."
            )
        return self

    def update_trailing_stop(self, proposed_stop: float) -> None:
        """Strict setter that rejects any downward stop adjustment (Stop_t >= Stop_{t-1})."""
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
        """Enforces strict Ratchet-Only Chandelier Stop (Simons Zero-Override)."""
        if current_date <= self.last_updated_date:
            raise ValueError(f"Point-in-Time violation: {current_date} <= {self.last_updated_date}")

        self.highest_high_since_entry = max(self.highest_high_since_entry, current_high)
        candidate_stop = self.highest_high_since_entry - (k_trail * current_atr_14)

        self.trailing_stop_price = round(max(self.trailing_stop_price, candidate_stop), 4)
        self.bars_held += 1
        self.last_updated_date = current_date

    @property
    def open_dollar_risk(self) -> float:
        """Calculates remaining downside risk to current trailing stop (0 if stop >= entry)."""
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
    """Single tenant's portfolio state enforcing Simons Portfolio Heat & Capacity gates."""
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
    """Root container supporting multiple isolated tenant portfolios and dynamic index registry."""
    schema_version: str = Field(default="2.0.0")
    last_updated_utc: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    index_registry: Dict[str, IndexConfigSchema]
    tenant_portfolios: Dict[UUID, VirtualPortfolioLedgerSchema] = Field(
        ..., description="Keyed by portfolio_id with strict tenant isolation validation"
    )
