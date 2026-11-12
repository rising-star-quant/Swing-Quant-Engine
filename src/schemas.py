from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Dict, List, Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# =============================================================================
# 1. AUTHENTICATION & MULTI-TENANT IDENTITY CONTRACTS
# =============================================================================

class UserRole(str, Enum):
    """Multi-tenant role-based access control tiers."""
    ADMIN = "ADMIN"
    TRADER = "TRADER"
    VIEWER = "VIEWER"


class UserIdentitySchema(BaseModel):
    """Immutable user entity contract aligned 1:1 with PostgreSQL tenant accounts."""
    model_config = ConfigDict(frozen=True)

    user_id: UUID = Field(
        default_factory=uuid4,
        description="Immutable primary tenant identifier (UUIDv4).",
    )
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Unique alphanumeric username with underscores and hyphens allowed.",
    )
    email: str = Field(
        ...,
        pattern=r"^\S+@\S+\.\S+$",
        description="Standard RFC-compliant email address.",
    )
    password_hash: str = Field(
        ...,
        min_length=20,
        description="Cryptographic password hash (Argon2id or bcrypt string).",
    )
    role: UserRole = Field(
        default=UserRole.TRADER,
        description="RBAC permission tier.",
    )
    is_active: bool = Field(
        default=True,
        description="Global active flag for tenant account authorization.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Point-in-Time account creation timestamp in UTC.",
    )


class JWTTokenPayload(BaseModel):
    """Stateless HS256/RS256 JWT claims contract with expiration integrity."""
    model_config = ConfigDict(frozen=True)

    sub: UUID = Field(
        ...,
        description="Subject claim holding the authenticated tenant user_id.",
    )
    role: UserRole = Field(
        ...,
        description="Role claim embedded for zero-lookup authorization.",
    )
    exp: int = Field(
        ...,
        gt=0,
        description="Expiration epoch timestamp in seconds (must exceed iat).",
    )
    iat: int = Field(
        ...,
        gt=0,
        description="Issued-at epoch timestamp in seconds.",
    )

    @model_validator(mode="after")
    def validate_token_chronology(self) -> JWTTokenPayload:
        """Enforces strictly positive token lifespan (exp > iat)."""
        if self.exp <= self.iat:
            raise ValueError(
                f"Invalid JWT chronological bounds: exp ({self.exp}) must be strictly greater than iat ({self.iat})."
            )
        return self


# =============================================================================
# 2. DYNAMIC INDEX REGISTRY & PIPELINE CONFIGURATION CONTRACTS
# =============================================================================

class IndexTier(str, Enum):
    """Market capitalization tier categorization."""
    SMALL_CAP = "SMALL_CAP"
    MID_CAP = "MID_CAP"
    LARGE_CAP = "LARGE_CAP"


class IndexConfigSchema(BaseModel):
    """
    Index-level parameter configuration schema encapsulating Jim Simons liquidity
    gates and Dr. Marcos López de Prado Triple-Barrier multipliers.
    """
    model_config = ConfigDict(validate_assignment=True)

    index_id: str = Field(
        ...,
        min_length=2,
        max_length=30,
        description="Unique index code identifier (e.g., 'RUT', 'MID').",
    )
    display_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Human-readable index designation.",
    )
    benchmark_ticker: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Benchmark ETF ticker used for relative strength calculation (e.g., 'IWM', 'MDY').",
    )
    tier: IndexTier = Field(
        ...,
        description="Index market capitalization tier.",
    )
    is_active: bool = Field(
        default=True,
        description="Flag indicating if the index is currently ingested and screened.",
    )

    # Simons Liquidity & Slippage Gateways
    min_price: float = Field(
        default=5.0,
        ge=1.0,
        description="Minimum absolute close price required to eliminate low-float penny stock noise.",
    )
    min_adv_30d: int = Field(
        default=500_000,
        ge=50_000,
        description="Minimum 30-day Average Daily Volume required for institutional liquidity.",
    )
    max_relative_spread: float = Field(
        default=0.005,
        gt=0.0,
        le=0.05,
        description="Maximum estimated relative bid-ask spread permitted (0.50% default).",
    )
    volume_surge_multiplier: float = Field(
        default=1.5,
        ge=1.1,
        description="Volume threshold multiple against 20-day moving average.",
    )

    # Scoring Weights (w1, w2, w3 summing to 1.0)
    weight_momentum: float = Field(
        default=0.45,
        gt=0.0,
        lt=1.0,
        description="Score weighting for stationary Volatility-Adjusted Momentum.",
    )
    weight_volume: float = Field(
        default=0.30,
        gt=0.0,
        lt=1.0,
        description="Score weighting for 20-day Standardized Volume Surge Z-Score.",
    )
    weight_rs: float = Field(
        default=0.25,
        gt=0.0,
        lt=1.0,
        description="Score weighting for Normalized Relative Strength against benchmark ETF.",
    )

    # López de Prado Triple-Barrier Multipliers
    k_stop_atr: float = Field(
        ...,
        gt=0.5,
        le=5.0,
        description="Multiplier for initial and trailing chandelier stop: Stop = Entry - (k_stop * ATR_14).",
    )
    k_profit_atr: float = Field(
        ...,
        gt=1.0,
        le=10.0,
        description="Multiplier for take-profit target barrier: Target = Entry + (k_profit * ATR_14).",
    )
    max_holding_bars: int = Field(
        default=14,
        ge=3,
        le=30,
        description="Vertical time-barrier horizon in daily trading bars.",
    )

    @field_validator("index_id", "benchmark_ticker")
    @classmethod
    def normalize_identifiers(cls, value: str) -> str:
        """Normalizes symbol codes to clean uppercase strings."""
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_invariants(self) -> IndexConfigSchema:
        """
        Validates:
        1. Positive mathematical expectancy: k_profit_atr >= 2.0 * k_stop_atr.
        2. Convex weights normalization: w_mom + w_vol + w_rs == 1.0 within epsilon.
        """
        if self.k_profit_atr < 2.0 * self.k_stop_atr:
            raise ValueError(
                f"EXPECTANCY VIOLATION in Index '{self.index_id}': k_profit_atr ({self.k_profit_atr}) "
                f"must be >= 2.0 * k_stop_atr ({self.k_stop_atr}) to ensure minimum 2:1 Reward-to-Risk ratio."
            )

        weight_sum = self.weight_momentum + self.weight_volume + self.weight_rs
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError(
                f"WEIGHT NORMALIZATION VIOLATION in Index '{self.index_id}': Component weights sum to "
                f"{weight_sum:.6f}, but must equal 1.000000 exactly."
            )

        return self


# =============================================================================
# 3. PRIMARY DIRECTIONAL & META-LABELED SIGNAL CONTRACTS
# =============================================================================

class DirectionalSignalSchema(BaseModel):
    """
    Output contract of Step B.1 Primary Directional Model (Side = +1 long-only).
    Represents Point-in-Time features and cross-sectional scoring results.
    """
    model_config = ConfigDict(frozen=True)

    signal_id: UUID = Field(
        default_factory=uuid4,
        description="Immutable identifier for the directional signal event.",
    )
    as_of_date: date = Field(
        ...,
        description="Strict Point-in-Time EOD settlement date.",
    )
    ticker: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Normalized equity symbol.",
    )
    index_id: str = Field(
        ...,
        description="Originating index identifier.",
    )
    side: Literal[1] = Field(
        default=1,
        description="Directional conviction: Long-only (+1).",
    )

    close_price: float = Field(
        ...,
        gt=0.0,
        description="Point-in-Time unadjusted/adjusted closing price on as_of_date.",
    )
    atr_14: float = Field(
        ...,
        gt=0.0,
        description="Wilder's 14-period Average True Range in price units.",
    )
    adv_30d: float = Field(
        ...,
        ge=500_000.0,
        description="30-day Average Daily Volume verified against Simons minimum liquidity.",
    )
    vol_adj_momentum: float = Field(
        ...,
        description="Stationary momentum: (Close_t - Close_{t-20}) / (ATR_14 * sqrt(20)).",
    )
    volume_zscore: float = Field(
        ...,
        description="Standardized volume surge: (Volume_t - Mean_20) / Std_20.",
    )
    norm_relative_strength: float = Field(
        ...,
        description="Normalized 60-day excess return over benchmark divided by tracking error.",
    )
    primary_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Weighted composite score S_primary in [0, 100].",
    )

    @field_validator("ticker")
    @classmethod
    def sanitize_ticker(cls, v: str) -> str:
        """Normalizes symbol to uppercase and strips whitespace."""
        return v.strip().upper()


class MetaLabeledSignalSchema(BaseModel):
    """
    Output contract of Step B.2 Meta-Labeling Secondary Model & 500-day Walk-Forward Gate.
    Calculates empirical Expected Value (EV) and sizes the conviction scalar (phi_meta).
    """
    model_config = ConfigDict(frozen=True)

    primary_signal: DirectionalSignalSchema = Field(
        ...,
        description="Underlying primary directional signal.",
    )
    backtest_lookback_days: int = Field(
        default=500,
        ge=250,
        description="Historical out-of-sample simulation window in trading days.",
    )
    historical_win_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Empirical win rate across historical Triple-Barrier exits.",
    )
    historical_ev_r_multiple: float = Field(
        ...,
        description="Empirical Expected Value expressed in R-multiples.",
    )
    meta_conviction_scalar: float = Field(
        ...,
        ge=0.0,
        le=1.25,
        description="López de Prado Meta-Labeling sizing conviction multiplier phi_meta in [0.0, 1.25].",
    )
    is_approved: bool = Field(
        ...,
        description="Binary approval flag: True if EV > 0 and phi_meta > 0.",
    )

    initial_stop_price: float = Field(
        ...,
        gt=0.0,
        description="Lower stop-loss barrier price level.",
    )
    take_profit_price: float = Field(
        ...,
        gt=0.0,
        description="Upper take-profit barrier price level.",
    )
    max_holding_bars: int = Field(
        default=14,
        ge=3,
        le=30,
        description="Vertical time-barrier duration in trading bars.",
    )

    @model_validator(mode="after")
    def validate_meta_barrier_geometry(self) -> MetaLabeledSignalSchema:
        """
        Validates:
        1. Geometric ordering: Stop < Entry < Target.
        2. Meta-Labeling approval consistency:
           - Approved -> EV > 0 and phi_meta > 0.
           - Rejected -> phi_meta == 0.0.
        """
        entry_price = self.primary_signal.close_price
        if not (self.initial_stop_price < entry_price < self.take_profit_price):
            raise ValueError(
                f"TRIPLE-BARRIER GEOMETRY VIOLATION for {self.primary_signal.ticker}: "
                f"Stop ({self.initial_stop_price}) < Entry ({entry_price}) < Target ({self.take_profit_price}) required."
            )

        if self.is_approved:
            if self.historical_ev_r_multiple <= 0.0:
                raise ValueError(
                    f"APPROVAL GATE BREACH for {self.primary_signal.ticker}: Approved signals must have "
                    f"positive historical EV (got {self.historical_ev_r_multiple:.4f}R)."
                )
            if self.meta_conviction_scalar <= 0.0:
                raise ValueError(
                    f"CONVICTION SIZING BREACH for {self.primary_signal.ticker}: Approved signals must have "
                    f"strictly positive meta_conviction_scalar (got {self.meta_conviction_scalar})."
                )
        else:
            if self.meta_conviction_scalar != 0.0:
                raise ValueError(
                    f"INACTIVE CONVICTION BREACH for {self.primary_signal.ticker}: Rejected signal must have "
                    f"meta_conviction_scalar == 0.0 (got {self.meta_conviction_scalar})."
                )

        return self


# =============================================================================
# 4. TENANT-SCOPED TRIPLE-BARRIER POSITION & AUDIT CONTRACTS
# =============================================================================

class ExitReason(str, Enum):
    """Categorical trigger for position liquidation."""
    UPPER_BARRIER_TP = "UPPER_BARRIER_TP"
    LOWER_BARRIER_SL = "LOWER_BARRIER_SL"
    VERTICAL_BARRIER_TIME = "VERTICAL_BARRIER_TIME"
    SYSTEM_CIRCUIT_BREAKER = "SYSTEM_CIRCUIT_BREAKER"


class TripleBarrierPositionSchema(BaseModel):
    """
    Active position contract with tenant scoping and strict Chandelier Ratchet
    monotonicity validation (Stop_t >= Stop_{t-1} and Stop >= InitialStop).
    """
    model_config = ConfigDict(validate_assignment=True)

    position_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for the open position.",
    )
    user_id: UUID = Field(
        ...,
        description="Mandatory tenant isolation foreign key.",
    )
    portfolio_id: UUID = Field(
        ...,
        description="Mandatory portfolio ledger foreign key.",
    )
    ticker: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Equity ticker symbol.",
    )
    index_id: str = Field(
        ...,
        description="Index registry identifier associated with trade rules.",
    )

    entry_date: date = Field(
        ...,
        description="Settlement date when position was opened.",
    )
    entry_price: float = Field(
        ...,
        gt=0.0,
        description="Execution price at entry.",
    )
    shares: int = Field(
        ...,
        gt=0,
        description="Positive integer share allocation.",
    )
    entry_atr_14: float = Field(
        ...,
        gt=0.0,
        description="ATR_14 value captured at time of entry.",
    )

    initial_stop_price: float = Field(
        ...,
        gt=0.0,
        description="Initial protective stop floor established at entry.",
    )
    trailing_stop_price: float = Field(
        ...,
        gt=0.0,
        description="Active trailing chandelier stop level (monotonically non-decreasing).",
    )
    take_profit_price: float = Field(
        ...,
        gt=0.0,
        description="Upper take-profit ceiling.",
    )
    highest_high_since_entry: float = Field(
        ...,
        gt=0.0,
        description="Peak price High reached during active holding period.",
    )
    bars_held: int = Field(
        default=0,
        ge=0,
        description="Number of trading sessions the position has remained open.",
    )
    max_holding_bars: int = Field(
        default=14,
        ge=3,
        le=30,
        description="Vertical barrier maximum holding limit.",
    )
    last_updated_date: date = Field(
        ...,
        description="Point-in-Time date of most recent ratchet evaluation.",
    )

    @field_validator("ticker")
    @classmethod
    def sanitize_ticker(cls, v: str) -> str:
        """Normalizes symbol to uppercase and strips whitespace."""
        return v.strip().upper()

    @model_validator(mode="after")
    def enforce_ratchet_floor(self) -> TripleBarrierPositionSchema:
        """
        Enforces Jim Simons zero-override trailing stop rule:
        Trailing stop must never degrade below the initial stop floor.
        """
        if self.trailing_stop_price + 1e-6 < self.initial_stop_price:
            raise ValueError(
                f"RATCHET INVARIANT VIOLATION for {self.ticker}: trailing_stop_price ({self.trailing_stop_price:.4f}) "
                f"cannot fall below initial_stop_price ({self.initial_stop_price:.4f})."
            )
        return self

    def update_trailing_stop(self, proposed_stop: float) -> None:
        """
        Explicit setter enforcing monotonic stop escalation:
        Rejects any attempt to lower the active trailing stop (Stop_t >= Stop_{t-1}).
        """
        if proposed_stop < self.trailing_stop_price - 1e-6:
            raise ValueError(
                f"DOWNWARD STOP MODIFICATION REJECTED for {self.ticker}: Proposed stop ({proposed_stop:.4f}) "
                f"is strictly below active trailing stop ({self.trailing_stop_price:.4f})."
            )
        self.trailing_stop_price = round(max(self.trailing_stop_price, proposed_stop), 4)

    def ratchet_trailing_stop(
        self,
        current_high: float,
        current_atr_14: float,
        k_trail: float,
        current_date: date,
    ) -> None:
        """
        Evaluates and advances the Chandelier Ratchet Stop:
        Stop_t = max(Stop_{t-1}, PeakHigh_t - k_trail * ATR_t).
        Enforces Point-in-Time date progression and increments bar count.
        """
        if current_date <= self.last_updated_date:
            raise ValueError(
                f"POINT-IN-TIME DATE VIOLATION for {self.ticker}: current_date ({current_date}) "
                f"must be strictly greater than last_updated_date ({self.last_updated_date})."
            )

        self.highest_high_since_entry = max(self.highest_high_since_entry, current_high)
        candidate_stop = self.highest_high_since_entry - (k_trail * current_atr_14)

        if candidate_stop > self.trailing_stop_price:
            self.trailing_stop_price = round(candidate_stop, 4)

        self.bars_held += 1
        self.last_updated_date = current_date

    @property
    def open_dollar_risk(self) -> float:
        """
        Calculates remaining downside open dollar risk to the current trailing stop:
        Risk = max(0.0, EntryPrice - TrailingStop) * Shares.
        Returns 0.0 once trailing stop has advanced to or beyond entry (Risk-Free).
        """
        per_share_downside = max(0.0, self.entry_price - self.trailing_stop_price)
        return round(per_share_downside * self.shares, 2)


class ClosedTradeAuditSchema(BaseModel):
    """
    Immutable audit ledger record representing a fully liquidated position.
    Guarantees non-repudiation and performance attribution across tenants.
    """
    model_config = ConfigDict(frozen=True)

    trade_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for the closed trade audit event.",
    )
    position_id: UUID = Field(
        ...,
        description="Reference identifier to the originating position.",
    )
    user_id: UUID = Field(
        ...,
        description="Tenant identifier for multi-tenant isolation.",
    )
    portfolio_id: UUID = Field(
        ...,
        description="Portfolio ledger foreign key.",
    )
    ticker: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Normalized equity symbol.",
    )
    index_id: str = Field(
        ...,
        description="Index registry identifier.",
    )
    entry_date: date = Field(
        ...,
        description="Position entry date.",
    )
    exit_date: date = Field(
        ...,
        description="Position exit liquidation date.",
    )
    entry_price: float = Field(
        ...,
        gt=0.0,
        description="Execution price at entry.",
    )
    exit_price: float = Field(
        ...,
        gt=0.0,
        description="Execution price at exit.",
    )
    shares: int = Field(
        ...,
        gt=0,
        description="Quantity of shares liquidated.",
    )
    bars_held: int = Field(
        ...,
        ge=1,
        description="Total sessions position was maintained.",
    )
    exit_reason: ExitReason = Field(
        ...,
        description="Categorical barrier trigger that terminated the trade.",
    )
    realized_pnl_dollars: float = Field(
        ...,
        description="Net realized profit or loss in portfolio currency units: (Exit - Entry) * Shares.",
    )
    realized_r_multiple: float = Field(
        ...,
        description="Realized outcome normalized by initial unit risk R.",
    )

    @field_validator("ticker")
    @classmethod
    def sanitize_ticker(cls, v: str) -> str:
        """Normalizes symbol to uppercase and strips whitespace."""
        return v.strip().upper()

    @model_validator(mode="after")
    def validate_audit_chronology(self) -> ClosedTradeAuditSchema:
        """Enforces that exit date cannot precede entry date."""
        if self.exit_date < self.entry_date:
            raise ValueError(
                f"CHRONOLOGY ERROR in trade audit {self.trade_id}: exit_date ({self.exit_date}) "
                f"cannot precede entry_date ({self.entry_date})."
            )
        return self


# =============================================================================
# 5. VIRTUAL PORTFOLIO LEDGER & MULTI-TENANT STATE STORE CONTRACTS
# =============================================================================

class VirtualPortfolioLedgerSchema(BaseModel):
    """
    Tenant-scoped shadow portfolio state enforcing Jim Simons risk constraints:
    - Maximum Portfolio Heat circuit breaker (sum(open_dollar_risk) / total_equity <= 6.0%).
    - Maximum concurrent position capacity (<= 10 positions default).
    - Strict cross-tenant position isolation (Position.user_id == Portfolio.user_id).
    """
    model_config = ConfigDict(validate_assignment=True)

    portfolio_id: UUID = Field(
        default_factory=uuid4,
        description="Primary portfolio identifier (UUIDv4).",
    )
    user_id: UUID = Field(
        ...,
        description="Tenant owner identifier strictly enforced for RBAC and RLS isolation.",
    )
    portfolio_name: str = Field(
        default="Primary Swing Shadow Portfolio",
        min_length=1,
        max_length=100,
        description="Descriptive portfolio name.",
    )
    as_of_date: date = Field(
        ...,
        description="Current Point-in-Time market state evaluation date.",
    )

    cash_balance: float = Field(
        ...,
        ge=0.0,
        description="Available unallocated cash balance (strictly non-negative).",
    )
    total_equity: float = Field(
        ...,
        gt=0.0,
        description="Total marked-to-market portfolio equity (cash + open positions market value).",
    )
    max_portfolio_heat_pct: float = Field(
        default=0.06,
        gt=0.0,
        le=0.15,
        description="Maximum permissible portfolio open risk percentage (6.0% default cap).",
    )
    max_concurrent_positions: int = Field(
        default=10,
        ge=1,
        le=25,
        description="Maximum concurrent active position slots.",
    )
    subscribed_indices: List[str] = Field(
        default_factory=lambda: ["RUT", "MID"],
        description="List of active index IDs this portfolio accepts signals from.",
    )

    open_positions: Dict[str, TripleBarrierPositionSchema] = Field(
        default_factory=dict,
        description="Active positions dictionary keyed by ticker symbol for O(1) exclusion lookups.",
    )
    closed_trades_audit: List[ClosedTradeAuditSchema] = Field(
        default_factory=list,
        description="Append-only historical audit trail of liquidated positions.",
    )

    @property
    def current_portfolio_heat_pct(self) -> float:
        """
        Calculates active Portfolio Heat:
        Heat = sum(open_dollar_risk for all open positions) / total_equity.
        """
        total_open_risk = sum(pos.open_dollar_risk for pos in self.open_positions.values())
        return round(total_open_risk / self.total_equity, 6)

    @model_validator(mode="after")
    def enforce_tenant_isolation_and_circuit_breakers(self) -> VirtualPortfolioLedgerSchema:
        """
        Validates:
        1. Capacity gate: len(open_positions) <= max_concurrent_positions.
        2. Strict tenant isolation: pos.user_id == self.user_id and pos.portfolio_id == self.portfolio_id.
        3. Key consistency: open_positions key must match pos.ticker.
        4. Simons Portfolio Heat circuit breaker: current_portfolio_heat_pct <= max_portfolio_heat_pct.
        """
        # Capacity Gate
        if len(self.open_positions) > self.max_concurrent_positions:
            raise ValueError(
                f"PORTFOLIO CAPACITY BREACH: Number of open positions ({len(self.open_positions)}) "
                f"exceeds maximum allowed capacity ({self.max_concurrent_positions})."
            )

        # Cross-Tenant Isolation & Key Verification Gate
        for ticker_key, pos in self.open_positions.items():
            if pos.ticker != ticker_key:
                raise ValueError(
                    f"POSITION KEY MISMATCH: Position dictionary key '{ticker_key}' does not match "
                    f"underlying position ticker '{pos.ticker}'."
                )
            if pos.user_id != self.user_id:
                raise ValueError(
                    f"CRITICAL SECURITY BREACH: Cross-tenant position detected for ticker {ticker_key}! "
                    f"Position owner ({pos.user_id}) does not match portfolio owner ({self.user_id})."
                )
            if pos.portfolio_id != self.portfolio_id:
                raise ValueError(
                    f"CROSS-PORTFOLIO INTEGRITY BREACH for ticker {ticker_key}: Position portfolio_id "
                    f"({pos.portfolio_id}) does not match parent portfolio_id ({self.portfolio_id})."
                )

        # Simons Portfolio Heat Circuit Breaker Gate
        if self.current_portfolio_heat_pct > self.max_portfolio_heat_pct + 1e-5:
            raise ValueError(
                f"PORTFOLIO HEAT CIRCUIT BREAKER BREACHED: Current heat ({self.current_portfolio_heat_pct:.2%}) "
                f"exceeds maximum authorized threshold ({self.max_portfolio_heat_pct:.2%})."
            )

        return self


class MultiTenantStateStoreSchema(BaseModel):
    """
    Root state container for atomic persistence, containing the active index registry
    and all isolated tenant portfolio ledgers.
    """
    schema_version: str = Field(
        default="2.0.0",
        description="State persistence format schema version.",
    )
    last_updated_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the latest atomic state serialization.",
    )
    index_registry: Dict[str, IndexConfigSchema] = Field(
        ...,
        description="Index registry configuration keyed by index_id.",
    )
    tenant_portfolios: Dict[UUID, VirtualPortfolioLedgerSchema] = Field(
        ...,
        description="Tenant portfolio ledgers keyed by portfolio_id.",
    )

    @model_validator(mode="after")
    def validate_portfolio_keys(self) -> MultiTenantStateStoreSchema:
        """Enforces that the dictionary key matches portfolio.portfolio_id."""
        for pid, ledger in self.tenant_portfolios.items():
            if pid != ledger.portfolio_id:
                raise ValueError(
                    f"STATE STORE KEY MISMATCH: Dictionary key ({pid}) does not match "
                    f"portfolio_id ({ledger.portfolio_id})."
                )
        return self
