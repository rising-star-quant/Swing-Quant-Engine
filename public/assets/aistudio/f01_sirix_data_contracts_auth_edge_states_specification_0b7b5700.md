# F01: SIRIX Data Contracts, Authentication & Edge States Specification

## 1. Purpose & API Boundary Principles

This specification defines the strict **Pydantic v2** data contracts, **Single-Origin Cookie Authentication** flows, internal scheduler hooks, and graceful degradation **Edge States** governing communication between the **Google Cloud Run FastAPI Backend** (`/api/*`) and the **SIRIX PWA Frontend** (`/*`).

### Core Contract Rules
* **Strict Read-Only Portfolio Boundary:** No API endpoint permits manual order creation, stop-loss modification, or signal override (`Zero-Override Mandate`).
* **Single-Origin Relative Routing:** All client requests target relative paths (`/api/...`) on the same origin (`https://<cloud-run-service>.a.run.app`), eliminating CORS preflight overhead and external `VITE_API_BASE_URL` dependencies.
* **Atomic State Hydration:** The backend reads `virtual_portfolio.json`, `equity_curve.json`, and `eod_telemetry.json` from `GCS_BUCKET_NAME` (falling back to local `data/state/` when running offline) via a 60-second in-memory TTL cache.

---

## 2. Core Data Contracts (Pydantic v2 Schemas)

### A. EOD System Telemetry Contract (`GET /api/system/status`)

Exposes real-time operational health from the nightly EOD batch worker (`eod_telemetry.json`) so the UI accurately reflects market-calendar skips, active batch runs, or upstream settlement delays.

```python
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

EODExecutionStatus = Literal[
    "IDLE",
    "RUNNING_EOD",
    "SKIPPED_MARKET_CLOSED",
    "FAILED_DATA_DELAY",
    "CRITICAL_ERROR",
]

class SystemHealthTelemetry(BaseModel):
    eod_status: EODExecutionStatus = Field(
        ..., description="Current or most recent nightly EOD pipeline execution state"
    )
    last_successful_eod_timestamp: Optional[datetime] = Field(
        None, description="ISO-8601 UTC timestamp of the last completed EOD state persistence"
    )
    last_trading_date_processed: Optional[str] = Field(
        None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Most recent NYSE trading date settled (YYYY-MM-DD)"
    )
    next_scheduled_run_utc: datetime = Field(
        ..., description="Next scheduled weekday EOD run (21:45 UTC)"
    )
    storage_backend: Literal["GCS", "LOCAL_FALLBACK"] = Field(
        ..., description="Active state storage source"
    )
    failure_reason: Optional[str] = Field(
        None, description="Sanitized diagnostic message when eod_status is FAILED_DATA_DELAY or CRITICAL_ERROR"
    )
```

### B. Executive Portfolio Ledger Contract (`GET /api/portfolio/summary`)

Hydrated from `virtual_portfolio.json` produced at Stage 5 of the EOD state machine.

```python
from datetime import datetime
from typing import List, Literal
from pydantic import BaseModel, Field

class ActivePositionDTO(BaseModel):
    ticker: str
    index_source: Literal["RUT_2000", "SP_400", "SP_500"]
    entry_date: str
    entry_price: float = Field(..., gt=0)
    current_price: float = Field(..., gt=0)
    shares: int = Field(..., gt=0)
    initial_stop_price: float = Field(..., gt=0)
    ratchet_stop_price: float = Field(..., gt=0)
    take_profit_price: float = Field(..., gt=0)
    atr_14: float = Field(..., gt=0)
    meta_confidence_phi: float = Field(..., ge=0.5, le=1.25)
    days_held: int = Field(..., ge=0, le=14)
    max_holding_days: int = Field(default=14)
    unrealized_pnl_usd: float
    unrealized_pnl_pct: float
    unrealized_r_multiple: float
    open_risk_usd: float = Field(..., ge=0, description="Zero once ratchet_stop_price >= entry_price")

class PortfolioSummaryResponse(BaseModel):
    as_of_utc: datetime
    total_equity_usd: float = Field(..., gt=0)
    cash_balance_usd: float = Field(..., ge=0)
    invested_capital_usd: float = Field(..., ge=0)
    portfolio_heat_pct: float = Field(..., ge=0.0, le=6.0)
    max_heat_cap_pct: float = Field(default=6.0)
    open_positions_count: int = Field(..., ge=0, le=10)
    max_positions_cap: int = Field(default=10)
    cumulative_return_pct: float
    win_rate_pct: float = Field(..., ge=0.0, le=100.0)
    expectancy_r: float
    positions: List[ActivePositionDTO]
```

### C. Equity Curve & Closed Trade Audit Contracts

* **`GET /api/portfolio/equity-curve`:** Returns an ordered array of `{ date: "YYYY-MM-DD", portfolio_nav: float, benchmark_iwm_norm: float, benchmark_mdy_norm: float, heat_pct: float }`.
* **`GET /api/portfolio/audit-ledger`:** Returns paginated closed trades `{ trade_id, ticker, index_source, entry_date, exit_date, entry_price, exit_price, shares, realized_pnl_usd, realized_r_multiple, exit_reason: Literal["TAKE_PROFIT", "RATCHET_STOP", "TIME_BARRIER_14D", "SPLIT_ADJUSTED_EXIT"], corporate_action_note: Optional[str] }`.

---

## 3. Single-Origin Authentication & Internal Scheduler Endpoints

### A. Hardened Cookie Session Flow

1. **`POST /api/auth/login`**
   * **Request Body:** `{ "username": str, "password": str }`
   * **Verification:** Validates password against **Argon2id** hash (`ADMIN_PASSWORD_HASH` env var). Enforces sliding-window rate limit (**max 5 failed attempts per 15 minutes per IP**, returning `429 Too Many Requests`).
   * **Success (`200 OK`):** Sets an **`HttpOnly; Secure; SameSite=Strict`** cookie (`sirix_session`) containing an HS256 JWT (`exp` = 24 hours) and returns `{ "authenticated": true, "expires_at_utc": "..." }`. No raw token is exposed to `localStorage`.
2. **`POST /api/auth/logout`**
   * **Action:** Clears the `sirix_session` cookie (`Max-Age=0`) and returns `200 OK`.
3. **`GET /api/auth/me`**
   * **Action:** Validates the `sirix_session` cookie; returns `200 OK` if valid or `401 Unauthorized` to trigger the Login view.

### B. Internal Cloud Scheduler & Cache-Invalidation Hook

* **`POST /api/internal/trigger-eod`**
  * **Security:** Validates cryptographic header `X-Sirix-Scheduler-Token` against `INTERNAL_SCHEDULER_TOKEN` (returns `403 Forbidden` on mismatch).
  * **Behavior:** Immediately invalidates the 60-second GCS in-memory cache so the next GUI request reflects fresh EOD state, and optionally dispatches a GitHub `workflow_dispatch` event if triggered by Google Cloud Scheduler failover. Returns `202 Accepted`.

---

## 4. UI Edge States & Graceful Degradation Matrix

The PWA must handle all non-nominal operational states cleanly without crashing or displaying blank screens:

| Edge State Trigger | API / Status Condition | Required PWA User Experience |
| :--- | :--- | :--- |
| **Active Nightly Batch** | `eod_status == "RUNNING_EOD"` | Display a non-blocking top status pill: *"EOD Pipeline Active — Ledger updates automatically upon settlement."* Continue rendering prior settled portfolio state. |
| **US Market Holiday / Weekend** | `eod_status == "SKIPPED_MARKET_CLOSED"` | Display neutral market-closed badge alongside `last_trading_date_processed`. No warning colors or error banners. |
| **Upstream Settlement Delay** | `eod_status == "FAILED_DATA_DELAY"` | Display an amber advisory banner noting upstream close-data delay and showing the exact timestamp of the last valid ledger snapshot. |
| **Critical Engine Failure** | `eod_status == "CRITICAL_ERROR"` | Display a high-visibility red alert banner with `failure_reason` while preserving read-only access to the last known good portfolio state. |
| **Zero Open Positions (100% Cash)** | `positions == []` and `portfolio_heat_pct == 0.0` | Render dedicated *"100% Cash — No Active Momentum Breakouts"* empty state card inside the Active Positions table; Heat gauge displays `0.00% / 6.00%`. |
| **Cold Start / Container Wake-Up** | Initial Cloud Run spin-up latency (`~1–2s`) | Display institutional skeleton loaders (shimmer placeholders) for KPI cards and charts until `/api/portfolio/summary` resolves. |
| **Session Expiry** | Any protected `/api/*` returns `401 Unauthorized` | Intercept globally, clear stale client state, and route cleanly to the Login screen without uncaught promise errors. |

---

## 5. Acceptance Criteria (for AI Studio Implementation)

1. **Schema Strictness:** All API endpoints validate inputs and outputs via Pydantic v2 models; malformed state files return `503 Service Unavailable` with structured JSON error details rather than unhandled `500` tracebacks.
2. **Cookie-Only Session Security:** Login sets `HttpOnly; Secure; SameSite=Strict` cookie; zero JWT tokens are stored in `localStorage` or `sessionStorage`.
3. **Rate-Limit Enforcement:** Six consecutive invalid login attempts from the same client return `429 Too Many Requests`.
4. **Edge-State Rendering:** Mocking `eod_status = "SKIPPED_MARKET_CLOSED"` or `positions = []` renders the exact UX states specified in Section 4 without layout shifts or console errors.
5. **Cache Invalidation:** Calling `POST /api/internal/trigger-eod` with a valid token immediately flushes the FastAPI GCS memory cache.