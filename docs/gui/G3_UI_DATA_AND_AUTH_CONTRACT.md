# UI DATA ADAPTER, SANDBOX SYNTHESIS & AUTHENTICATION CONTRACT (G3)
## Swing Quant Engine — Read-Only Service Layer, Multi-Tenant RBAC & Demo Portfolio Engine

**Document ID:** `G3_UI_DATA_AND_AUTH_CONTRACT`  
**Parent Document:** `docs/gui/G0_MASTER_GUI_PRD.md`  
**Version:** `2.0.0`  
**Status:** `APPROVED FOR IMPLEMENTATION`  
**Target Stack:** Python 3.11+ | Pydantic v2 | Streamlit Session State | Apache Parquet  

---

## 1. Architectural Role of the UI Service Layer (`src/dashboard_service.py`)

### 1.1 Strict Read-Only & Zero-Leakage Mandate
The UI presentation layer (`app.py`) must never manipulate raw JSON files, construct file paths manually, or execute ad-hoc pandas math. All data retrieval, tenant permission checks, probability enrichment, and demo synthesis route exclusively through **`DashboardDataService`** in `src/dashboard_service.py`.

### 1.2 Core Engineering Invariants
1. **Zero Network Calls During UI Load:** `DashboardDataService` interacts strictly with `JsonPortfolioStateRepository` (`data/virtual_portfolio.json`) and `ParquetMarketDataRepository` (`data/market_cache/*.parquet`).
2. **Strict Tenant Isolation:** Every method accepting a `portfolio_id` validates `TenantSecurityGuard.enforce_tenant_access(claims, ledger.user_id)` from `src/security.py` prior to returning data.
3. **Deterministic Probability & Conviction Enrichment:** Because `TripleBarrierPositionSchema` stores active execution barriers (`entry_price`, `trailing_stop_price`, `take_profit_price`), `DashboardDataService` pairs each active position with its corresponding `MetaLabeledSignalSchema` telemetry (or computes deterministic 500-day historical win-rate, Expected Value in `R`, and `primary_score` from the local Parquet cache if not cached in state) so every stock card on the dashboard always displays complete probability metrics.

---

## 2. View-Model Data Contracts (`src/dashboard_service.py`)

To keep `app.py` clean and declarative, `DashboardDataService` returns strongly-typed Pydantic v2 View-Models:

### 2.1 `StockConvictionCardVM` (Per-Stock Probability & Order View-Model)
Represents a single stock's complete execution and statistical edge profile for **View 1 (Action Bridge)** and **View 2 (Active Book)**:
* `ticker: str`
* `index_id: str` (`RUT_2000`, `SP_400`, `SP_500`)
* `action_type: Literal["NEW_ENTRY", "ACTIVE_HOLD", "STOP_RATCHETED", "BARRIER_EXIT"]`
* `shares: int`
* `entry_date: date`
* `entry_price: float`
* `current_price: float` (latest close from Parquet cache or `entry_price` fallback)
* `initial_stop_price: float`
* `trailing_stop_price: float`
* `take_profit_price: float`
* `position_cost_dollars: float` (`shares * entry_price`)
* `open_dollar_risk: float` (`shares * max(0.0, entry_price - trailing_stop_price)`)
* `expected_profit_dollars: float` (`shares * (take_profit_price - entry_price)`)
* `unrealized_pnl_dollars: float` (`shares * (current_price - entry_price)`)
* `unrealized_r_multiple: float` (`(current_price - entry_price) / (entry_price - initial_stop_price)`)
* `r_progress_pct: float` (clamped `[0.0, 100.0]`, mapping `[trailing_stop_price -> take_profit_price]`)
* `bars_held: int`
* `max_holding_bars: int` (`14`)
* `historical_win_rate_pct: float` (`0.0–100.0`, e.g., `64.5%`)
* `historical_ev_r_multiple: float` (e.g., `+0.88 R`)
* `primary_score: float` (`0.0–100.0`, e.g., `89.2`)
* `meta_conviction_scalar: float` (`0.50–1.25`, e.g., `1.15`)
* `broker_order_ticket_text: str` (Ready-to-copy string: `"BUY 140 SHARES EXTR @ $18.40 | SL: $17.10 | TP: $22.30 (GTC)"`)

### 2.2 `PortfolioDashboardSnapshotVM` (Complete Screen State View-Model)
Aggregates the entire tenant dashboard state in a single atomic call:
* `is_demo_mode: bool`
* `subscription_tier: Literal["FREE", "PRO", "ELITE"]`
* `ledger: VirtualPortfolioLedgerSchema`
* `available_indices: Dict[str, IndexConfigSchema]`
* `deployed_capital_dollars: float`
* `cash_allocation_pct: float`
* `remaining_heat_budget_pct: float`
* `remaining_dollar_risk_budget: float`
* `active_conviction_cards: List[StockConvictionCardVM]`
* `todays_new_entries: List[StockConvictionCardVM]`
* `todays_ratcheted_stops: List[StockConvictionCardVM]`
* `todays_closed_exits: List[ClosedTradeAuditSchema]`
* `performance_summary: Dict[str, float]` (`win_rate_pct`, `avg_r_multiple`, `profit_factor`, `total_realized_pnl`, `max_drawdown_pct`)

---

## 3. Deterministic Interactive Sandbox Demo Synthesizer (`build_interactive_demo_snapshot`)

### 3.1 Why This Component is Mission-Critical
When the live production portfolio sits in `100% Cash` (or when a prospective paying subscriber visits the platform for the first time), they must be able to toggle **`🧪 Interactive Sandbox Demo Mode`** to inspect a realistic, mathematically valid multi-position portfolio without touching `data/virtual_portfolio.json`.

### 3.2 Demo Portfolio Specification
`DashboardDataService.build_interactive_demo_snapshot()` deterministically constructs an in-memory `PortfolioDashboardSnapshotVM` with:
1. **Equity & Risk State:**
   * `total_equity = $104,850.00` (reflecting `+$4,850.00` realized gains)
   * `cash_balance = $46,420.00` (`44.3%` Dry Powder ready to invest)
   * `Active Capacity = 5 / 10 Slots`
   * `current_portfolio_heat_pct = 0.0365` (`3.65% / 6.00% Max` — illustrating elevated/healthy risk management)
2. **5 Realistic Active Triple-Barrier Positions (`open_positions`):**
   * Diversified across `RUT_2000` and `SP_400` (e.g., `EXTR`, `ONTO`, `MEDP`, `POWL`, `MOD`), including:
     * **2 Newly Entered Today (`bars_held = 0`):** Showing fresh `BUY` broker order tickets on **View 1**.
     * **2 Positions with Ratcheted Chandelier Stops (`trailing_stop_price > initial_stop_price`):** Demonstrating how the algorithm automatically raises the stop-loss floor to lock in profit.
     * **1 Position Approaching Time Barrier (`bars_held = 11 / 14`):** Demonstrating the vertical time barrier countdown.
3. **60-Day Synthetic OHLCV Candle Series per Demo Ticker:**
   * If a demo ticker is not present in the local `data/market_cache/`, `DashboardDataService` generates a deterministic 60-day OHLCV `pd.DataFrame` (seeded via `np.random.default_rng(42)`) whose final close, ATR, and breakout trajectory match the exact `entry_price`, `trailing_stop_price`, and `take_profit_price` of the demo position—guaranteeing the **Triple-Barrier Price Cage Chart** works out-of-the-box in every environment.
4. **14 Historical Closed Audit Trades (`closed_trades_audit`):**
   * Realistic mix of `UPPER_BARRIER_TP` (`+3.0R`), ratcheted `LOWER_BARRIER_SL` (`-1.0R` to `+1.2R`), and `VERTICAL_BARRIER_TIME` (`+0.6R`), yielding a `64.3%` win rate and `+1.18R` expectancy on **View 3**.

---

## 4. Authentication, Session Management & Tier Gating (`GUIAuthController`)

### 4.1 Integration with `src/security.py`
The GUI leverages the existing `PasswordManager`, `JWTManager`, and `TenantSecurityGuard` classes from `src/security.py` with zero duplication:

1. **Default Credentials & Multi-Tier Preview Accounts:**
   * In `sandbox` / `development` or initial single-owner deployment, `GUIAuthController` pre-provisions three switchable test/owner identities (or reads credentials from environment secrets `ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH`):
     * **Admin / Elite Owner:** maps to primary shadow portfolio `00000000-0000-4000-8000-000000000001` (`UserRole.ADMIN`, `ELITE` tier).
     * **Pro Subscriber Preview:** (`UserRole.TRADER`, `PRO` tier).
     * **Free Explorer Preview:** (`UserRole.VIEWER`, `FREE` tier).
2. **JWT Session Lifecycle in `st.session_state`:**
   * On login, `JWTManager.create_access_token(user)` stores the signed JWT in `st.session_state["jwt_token"]`.
   * On every page rerun, `GUIAuthController.get_verified_session()` decodes and validates the token via `JWTManager.verify_token()`. Expired or tampered tokens automatically clear session state and redirect to the login screen.

### 4.2 Controlled Self-Service Settings Persistence
In **View 4 (Control Room)**, when an authenticated `PRO` or `ELITE` user updates their portfolio settings:
* `DashboardDataService.update_tenant_preferences()` validates:
  * `0.02 <= max_portfolio_heat_pct <= 0.06` (Simons hard cap).
  * `subscribed_indices` contains only valid registered index IDs (`RUT_2000`, `SP_400`, `SP_500`).
  * If `is_demo_mode == True`, updates apply only to the in-memory session snapshot; if `is_demo_mode == False`, updates persist atomically via `JsonPortfolioStateRepository.upsert_tenant_portfolio()`.