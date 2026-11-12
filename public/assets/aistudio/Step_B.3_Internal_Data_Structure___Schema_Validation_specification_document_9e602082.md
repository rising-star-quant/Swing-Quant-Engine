# Step B.3: Internal Data Structure & Schema Validation Specification

## 1. Architectural Overview & Multi-Tenant Design Philosophy

This specification defines the strict data contracts, validation rules, and relational storage schemas for the **Swing Quant Engine**. Engineered in alignment with **Dr. Marcos López de Prado** (*Advances in Financial Machine Learning*) and **Jim Simons** (*Renaissance Technologies*), every data structure enforces **Point-in-Time (PiT) integrity**, **Zero-Override mathematical constraints**, and **strict Multi-Tenant Data Isolation**.

### Core Architectural Guarantees:
1. **Shared Compute, Isolated State:** Daily market ingestion, index pipeline calculations, and primary directional signals are computed *once* globally (`Shared Read-Only Layer`), while virtual portfolios, open positions, portfolio heat, and trade histories are strictly partitioned per user (`Isolated Tenant Layer`).
2. **Defense-in-Depth Isolation:** Every tenant-scoped record requires a mandatory `user_id` (`UUID4`) and `portfolio_id` (`UUID4`), validated at runtime via **Pydantic v2** and enforced at the database layer via **PostgreSQL Row-Level Security (RLS)**.
3. **Zero-Friction Storage Evolution:** The Phase 1 `virtual_portfolio.json` file mirrors the normalized Phase 2 PostgreSQL schema 1:1, allowing seamless migration via the Repository Pattern without refactoring core quant logic.

```
+-------------------------------------------------------------------------+
|                   GLOBAL SHARED LAYER (Read-Only)                       |
|  - Dynamic Index Registry (`index_configs`)                             |
|  - Daily Primary & Meta-Labeled Signals (`daily_market_signals`)        |
+-------------------------------------------------------------------------+
                                    |
          +-------------------------+-------------------------+
          | (Filtered by Tenant A Holdings)                   | (Filtered by Tenant B Holdings)
          v                                                   v
+-----------------------------------+       +-----------------------------------+
|      TENANT A ISOLATED STATE      |       |      TENANT B ISOLATED STATE      |
|  - `user_id`: UUID-A              |       |  - `user_id`: UUID-B              |
|  - `portfolio_id`: UUID-PA        |       |  - `portfolio_id`: UUID-PB        |
|  - Open Triple-Barrier Positions  |       |  - Open Triple-Barrier Positions  |
|  - Isolated Portfolio Heat (<=6%) |       |  - Isolated Portfolio Heat (<=6%) |
|  - Closed Trade Audit Log         |       |  - Closed Trade Audit Log         |
+-----------------------------------+       +-----------------------------------+
```

---

## 2. Pydantic v2 Data Contracts & Runtime Validation (`schemas.py`)

All internal engine communication, JSON serialization, and future FastAPI endpoints enforce the following `pydantic` (v2) models:

```python
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Literal, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


# ==========================================
# 1. AUTHENTICATION & MULTI-TENANT IDENTITY
# ==========================================

class UserRole(str, Enum):
    ADMIN = "ADMIN"      # Authorized to trigger headless worker & modify global index registry
    TRADER = "TRADER"    # Owns isolated virtual portfolios & custom index subscriptions
    VIEWER = "VIEWER"    # Read-only access to assigned portfolio telemetry


class UserIdentitySchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID = Field(default_factory=uuid4, description="Immutable primary tenant identifier")
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r"^\S+@\S+\.\S+$")
    password_hash: str = Field(..., description="Argon2id or bcrypt cryptographic hash")
    role: UserRole = Field(default=UserRole.TRADER)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JWTTokenPayload(BaseModel):
    sub: UUID = Field(..., description="Subject user_id")
    role: UserRole
    exp: int = Field(..., description="Expiration UNIX timestamp")
    iat: int = Field(..., description="Issued-at UNIX timestamp")


# ==========================================
# 2. DYNAMIC INDEX REGISTRY & PIPELINE SPECS
# ==========================================

class IndexTier(str, Enum):
    SMALL_CAP = "SMALL_CAP"   # e.g., Russell 2000
    MID_CAP = "MID_CAP"       # e.g., S&P MidCap 400
    LARGE_CAP = "LARGE_CAP"   # e.g., S&P 500, Nasdaq 100


class IndexConfigSchema(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    index_id: str = Field(..., description="Unique index code, e.g., 'RUT_2000', 'SP_400'")
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
    """Output of Step B.1 (Primary Model: Side = +1)"""
    model_config = ConfigDict(frozen=True)

    signal_id: UUID = Field(default_factory=uuid4)
    as_of_date: date = Field(..., description="Strict Point-in-Time EOD market date")
    ticker: str = Field(..., min_length=1, max_length=10)
    index_id: str
    side: Literal[1] = Field(default=1, description="Long-only directional signal (+1)")

    # Stationary & Volatility-Normalized Features (Step B.1)
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

    # Pre-computed Initial Triple-Barrier Levels
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
    UPPER_BARRIER_TP = "UPPER_BARRIER_TP"          # Hit volatility-adjusted Take-Profit
    LOWER_BARRIER_SL = "LOWER_BARRIER_SL"          # Hit dynamic Chandelier Trailing Stop
    VERTICAL_BARRIER_TIME = "VERTICAL_BARRIER_TIME" # Reached 14-day maximum holding horizon
    SYSTEM_CIRCUIT_BREAKER = "SYSTEM_CIRCUIT_BREAKER"


class TripleBarrierPositionSchema(BaseModel):
    """Active position strictly isolated by user_id and portfolio_id"""
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

    # Dynamic Triple-Barrier Cage State
    initial_stop_price: float = Field(..., gt=0.0)
    trailing_stop_price: float = Field(..., gt=0.0)
    take_profit_price: float = Field(..., gt=0.0)
    highest_high_since_entry: float = Field(..., gt=0.0)
    bars_held: int = Field(default=0, ge=0)
    max_holding_bars: int = Field(default=14, ge=3, le=30)
    last_updated_date: date

    def ratchet_trailing_stop(self, current_high: float, current_atr_14: float, k_trail: float, current_date: date) -> None:
        """Enforces strict Ratchet-Only Chandelier Stop (Simons Zero-Override)"""
        if current_date <= self.last_updated_date:
            raise ValueError(f"Point-in-Time violation: {current_date} <= {self.last_updated_date}")

        self.highest_high_since_entry = max(self.highest_high_since_entry, current_high)
        candidate_stop = self.highest_high_since_entry - (k_trail * current_atr_14)

        # Mathematical guarantee: Stop can never move downward
        self.trailing_stop_price = round(max(self.trailing_stop_price, candidate_stop), 4)
        self.bars_held += 1
        self.last_updated_date = current_date

    @property
    def open_dollar_risk(self) -> float:
        """Calculates remaining downside risk to current trailing stop (0 if stop >= entry)"""
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
    """Single tenant's portfolio state enforcing Simons Portfolio Heat & Capacity gates"""
    model_config = ConfigDict(validate_assignment=True)

    portfolio_id: UUID = Field(default_factory=uuid4)
    user_id: UUID = Field(..., description="Owner user_id - strictly isolated")
    portfolio_name: str = Field(default="Primary Swing Shadow Portfolio")
    as_of_date: date

    cash_balance: float = Field(..., ge=0.0)
    total_equity: float = Field(..., gt=0.0)
    max_portfolio_heat_pct: float = Field(default=0.06, gt=0.0, le=0.15)
    max_concurrent_positions: int = Field(default=10, ge=1, le=25)
    subscribed_indices: List[str] = Field(default_factory=lambda: ["RUT_2000", "SP_400"])

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
    """Root schema for Phase 1 `virtual_portfolio.json` supporting multiple isolated users"""
    schema_version: str = Field(default="2.0.0")
    last_updated_utc: datetime = Field(default_factory=datetime.utcnow)
    index_registry: Dict[str, IndexConfigSchema]
    tenant_portfolios: Dict[UUID, VirtualPortfolioLedgerSchema] = Field(
        ..., description="Keyed by portfolio_id with strict tenant isolation validation"
    )
```

---

## 3. Relational Cloud Database Schema & Row-Level Security (PostgreSQL / Supabase)

To guarantee that data from different users can **never intermingle** when scaling to a multi-user mobile/web platform (Phase 2), the database enforces **Foreign Key Cascade Isolation** combined with **PostgreSQL Row-Level Security (RLS)** bound directly to the authenticated JWT session.

```sql
-- Enable cryptographic UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =========================================================================
-- 1. TENANT IDENTITY TABLE
-- =========================================================================
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'TRADER' CHECK (role IN ('ADMIN', 'TRADER', 'VIEWER')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================================================
-- 2. GLOBAL SHARED LAYER (Index Registry & Daily Signals)
-- =========================================================================
CREATE TABLE index_configs (
    index_id VARCHAR(30) PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    benchmark_ticker VARCHAR(10) NOT NULL,
    tier VARCHAR(20) NOT NULL CHECK (tier IN ('SMALL_CAP', 'MID_CAP', 'LARGE_CAP')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    min_price NUMERIC(10, 2) NOT NULL DEFAULT 5.00,
    min_adv_30d BIGINT NOT NULL DEFAULT 500000,
    max_relative_spread NUMERIC(6, 4) NOT NULL DEFAULT 0.0050,
    volume_surge_multiplier NUMERIC(5, 2) NOT NULL DEFAULT 1.50,
    k_stop_atr NUMERIC(5, 2) NOT NULL,
    k_profit_atr NUMERIC(5, 2) NOT NULL,
    max_holding_bars INT NOT NULL DEFAULT 14,
    CHECK (k_profit_atr >= 2.0 * k_stop_atr)
);

CREATE TABLE daily_market_signals (
    signal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    as_of_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    index_id VARCHAR(30) NOT NULL REFERENCES index_configs(index_id),
    close_price NUMERIC(12, 4) NOT NULL CHECK (close_price > 0),
    atr_14 NUMERIC(12, 4) NOT NULL CHECK (atr_14 > 0),
    primary_score NUMERIC(5, 2) NOT NULL CHECK (primary_score BETWEEN 0 AND 100),
    historical_win_rate NUMERIC(5, 4) NOT NULL,
    historical_ev_r_multiple NUMERIC(8, 4) NOT NULL,
    meta_conviction_scalar NUMERIC(4, 2) NOT NULL CHECK (meta_conviction_scalar BETWEEN 0 AND 1.25),
    initial_stop_price NUMERIC(12, 4) NOT NULL,
    take_profit_price NUMERIC(12, 4) NOT NULL,
    is_approved BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (as_of_date, ticker)
);

-- =========================================================================
-- 3. ISOLATED TENANT LAYER (Portfolios, Open Positions, Closed Trades)
-- =========================================================================
CREATE TABLE portfolios (
    portfolio_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    portfolio_name VARCHAR(100) NOT NULL,
    as_of_date DATE NOT NULL,
    cash_balance NUMERIC(14, 2) NOT NULL CHECK (cash_balance >= 0),
    total_equity NUMERIC(14, 2) NOT NULL CHECK (total_equity > 0),
    max_portfolio_heat_pct NUMERIC(5, 4) NOT NULL DEFAULT 0.0600,
    max_concurrent_positions INT NOT NULL DEFAULT 10,
    subscribed_indices TEXT[] NOT NULL DEFAULT ARRAY['RUT_2000', 'SP_400'],
    UNIQUE (portfolio_id, user_id) -- Composite key enables strict composite FK downstream
);

CREATE TABLE open_positions (
    position_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID NOT NULL,
    user_id UUID NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    index_id VARCHAR(30) NOT NULL REFERENCES index_configs(index_id),
    entry_date DATE NOT NULL,
    entry_price NUMERIC(12, 4) NOT NULL CHECK (entry_price > 0),
    shares INT NOT NULL CHECK (shares > 0),
    entry_atr_14 NUMERIC(12, 4) NOT NULL CHECK (entry_atr_14 > 0),
    initial_stop_price NUMERIC(12, 4) NOT NULL,
    trailing_stop_price NUMERIC(12, 4) NOT NULL,
    take_profit_price NUMERIC(12, 4) NOT NULL,
    highest_high_since_entry NUMERIC(12, 4) NOT NULL,
    bars_held INT NOT NULL DEFAULT 0 CHECK (bars_held >= 0),
    max_holding_bars INT NOT NULL DEFAULT 14,
    last_updated_date DATE NOT NULL,
    -- Composite Foreign Key guarantees a position can NEVER be linked to another user's portfolio
    FOREIGN KEY (portfolio_id, user_id) REFERENCES portfolios(portfolio_id, user_id) ON DELETE CASCADE,
    -- Prevents duplicate holdings of the same ticker within a single tenant portfolio
    UNIQUE (portfolio_id, ticker)
);

CREATE TABLE closed_trades_audit (
    trade_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id UUID NOT NULL,
    portfolio_id UUID NOT NULL,
    user_id UUID NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    index_id VARCHAR(30) NOT NULL,
    entry_date DATE NOT NULL,
    exit_date DATE NOT NULL,
    entry_price NUMERIC(12, 4) NOT NULL,
    exit_price NUMERIC(12, 4) NOT NULL,
    shares INT NOT NULL,
    bars_held INT NOT NULL,
    exit_reason VARCHAR(30) NOT NULL,
    realized_pnl_dollars NUMERIC(14, 2) NOT NULL,
    realized_r_multiple NUMERIC(8, 4) NOT NULL,
    FOREIGN KEY (portfolio_id, user_id) REFERENCES portfolios(portfolio_id, user_id) ON DELETE CASCADE
);

-- =========================================================================
-- 4. MANDATORY ROW-LEVEL SECURITY (RLS) POLICIES FOR TENANT ISOLATION
-- =========================================================================
ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE open_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE closed_trades_audit ENABLE ROW LEVEL SECURITY;

-- Enforces that an authenticated session can only SELECT/INSERT/UPDATE/DELETE rows matching its JWT user_id
CREATE POLICY tenant_portfolio_isolation ON portfolios
    FOR ALL
    USING (user_id = current_setting('request.jwt.claim.sub', true)::uuid)
    WITH CHECK (user_id = current_setting('request.jwt.claim.sub', true)::uuid);

CREATE POLICY tenant_open_positions_isolation ON open_positions
    FOR ALL
    USING (user_id = current_setting('request.jwt.claim.sub', true)::uuid)
    WITH CHECK (user_id = current_setting('request.jwt.claim.sub', true)::uuid);

CREATE POLICY tenant_closed_trades_isolation ON closed_trades_audit
    FOR ALL
    USING (user_id = current_setting('request.jwt.claim.sub', true)::uuid)
    WITH CHECK (user_id = current_setting('request.jwt.claim.sub', true)::uuid);
```

---

## 4. Per-Tenant Portfolio Exclusion & Reconciliation Flow

During the daily headless execution run:
1. **Global Market Pass (Executed Once):** The worker fetches OHLCV data for all active indices in `index_configs`, runs the index-specific screening pipelines, performs the 500-day per-asset backtests, and writes validated signals to `daily_market_signals`.
2. **Per-Tenant Reconciliation Loop (Strictly Scoped by `portfolio_id` & `user_id`):**
   * **Step 1 (Triple-Barrier Exit Check):** Evaluates the tenant's `open_positions` against today's High, Low, Close, and `bars_held >= 14`. Executes exits or ratchets `trailing_stop_price` upward.
   * **Step 2 (Tenant-Specific Exclusion Filter):** Filters `daily_market_signals` by removing any ticker present in `open_positions` for *that specific* `portfolio_id` (`ticker NOT IN tenant.open_positions.keys()`) and filtering only indices in `tenant.subscribed_indices`.
   * **Step 3 (Meta-Labeled Sizing & Heat Check):** Allocates shares based on the tenant's isolated `total_equity` and verifies that `current_portfolio_heat_pct <= 0.06` before inserting the new position.