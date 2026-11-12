# MASTER PRODUCT & ARCHITECTURE REQUIREMENTS DOCUMENT (G0)
## Swing Quant Engine — Commercial SaaS Subscriber GUI (Phase 2)

**Document ID:** `G0_MASTER_GUI_PRD`  
**Version:** `2.0.0`  
**Status:** `APPROVED FOR IMPLEMENTATION`  
**Target Stack:** Python 3.11+ | Streamlit | Plotly | Pydantic v2 | Apache Parquet  

---

## 1. Executive Product Vision & Commercial Transformation

### 1.1 Strategic Objective
Phase 2 transforms the **Swing Quant Engine** from a zero-UI, autonomous post-market execution worker into a commercial, subscription-ready SaaS platform. Paying retail and semi-institutional subscribers do not purchase raw Python code—they purchase **instant capital clarity, quantified statistical edge, and disciplined risk protection**.

The GUI operates as a **60-Second Daily Execution Cockpit**, translating Dr. Marcos López de Prado’s Meta-Labeling and Triple-Barrier mathematics alongside Jim Simons’ strict portfolio heat controls into an intuitive, institutional dark-mode dashboard.

### 1.2 The Three Core Subscriber Value Pillars ("The 3-Second Rule")
Every screen and visual component is engineered to answer three mission-critical questions within **3 seconds of login**:

1. **Instant Portfolio Risk Clarity (Capital Protection Gauge):**
   * Real-time visual dial displaying **Current Portfolio Heat** (`0.00%` up to the hard `6.00%` Simons ceiling) so the subscriber knows immediately how much capital is at risk if every active stop-loss were hit simultaneously.
2. **Available Dry Powder & Slot Capacity (Capital Deployment Meter):**
   * Visual breakdown of **Available Cash (`cash_balance`) vs. Deployed Capital**, paired with active position slot capacity (`X / 10 Slots`), showing exact buying power ready for the next market setup.
3. **Quantified Probability & Conviction per Stock (Meta-Labeling Edge Cards):**
   * Every candidate or active position displays its **500-Day Historical Win Rate (%)**, **Expected Value (`EV` in R-Multiples)**, **Primary Breakout Score (`0–100`)**, and **Meta-Conviction Scalar (`phi_meta`)**, alongside an interactive **Triple-Barrier Price Cage** (`Entry`, ratcheting `Chandelier Stop`, `1:3 Take-Profit`, and `14-Bar Time-Stop`).

---

## 2. End-to-End System Topology (Headless Engine <-> Commercial GUI)

### 2.1 Strict Producer-Consumer Architectural Decoupling
The Headless Quantitative Engine and the Commercial GUI operate as strictly decoupled processes communicating exclusively through validated persistence contracts (`src/schemas.py` and `src/storage.py`):

```text
====================================================================================
  PRODUCER LOOP: NIGHTLY POST-MARKET WORKER (GitHub Actions - 21:30 UTC Mon-Fri)
====================================================================================
  [YFinance API] ---> [Parquet Market Cache] ---> [PrimaryScreeningEngine]
                             (data/market_cache/)              |
                                                               v
  [Telegram Bot] <--- [TenantPortfolioReconciler] <--- [MetaLabelingBacktestEngine]
                             |                         (500d Triple-Barrier Gate)
                             v
                 +-----------------------+
                 |  PERSISTENCE LAYER    |
                 | - virtual_portfolio   |
                 |   .json (Phase 2A)    |
                 | - Supabase PostgreSQL |
                 |   (Phase 2B Upgrade)  |
                 +-----------------------+
                             |
                             | (Read-Only State & Parquet Consumption)
                             v
====================================================================================
  CONSUMER LOOP: 24/7 COMMERCIAL SUBSCRIBER GUI (Streamlit Community Cloud)
====================================================================================
  [Subscriber Browser] ---> [app.py (Dark-Mode Institutional Cockpit)]
                                   |
           +-----------------------+-----------------------+
           v                                               v
  [src/security.py]                               [src/dashboard_service.py]
  - Argon2id Authentication                       - Read-Only Ledger Adapter
  - JWT Session Verification                      - Triple-Barrier Chart Builder
  - Tenant UUID Isolation                         - Interactive Sandbox Previewer


2.2 Operational & Maintainability Invariants
Zero Live Market Scraping in UI: The GUI never invokes yfinance during page loads. It reads pre-synced Parquet files (data/market_cache/{TICKER}.parquet) and validated state (data/virtual_portfolio.json), guaranteeing < 1.5s render latency and zero external API rate-limiting.

Zero Risk-Gate Override: Subscribers can customize preferences within hard mathematical bounds (e.g., max_portfolio_heat_pct clamped to [0.02, 0.06]), but cannot override stop-loss ratchets, force vetoed EV <= 0 trades, or bypass tenant isolation.

Zero-Friction Cloud Maintenance: 100% Python implementation maintainable directly via GitHub Web and auto-deployed to Streamlit Community Cloud on every commit to main.

3. Modular Sub-PRD Registry & Governance Map
The GUI engineering blueprint is partitioned into four modular child specifications under docs/gui/:

Sub-PRD ID	File Path	Engineering Scope & Deliverables	Core Schema / Module Bindings
G1	docs/gui/G1_UI_PRODUCT_SPEC.md	Commercial subscription tiers (Free, Pro, Elite), 3-second onboarding UX, 4-view navigation architecture, and 100%-cash Empty-State / Demo Preview workflows.	UserRole, IndexTier (src/schemas.py)
G2	docs/gui/G2_DESIGN_AND_DASHBOARDS.md	Institutional Dark-Mode CSS tokens and exact Plotly specifications for the Portfolio Heat Gauge, Dry Powder Donut, Meta-Labeling Conviction Cards, and Triple-Barrier Price Cage Chart.	VirtualPortfolioLedgerSchema, TripleBarrierPositionSchema, MetaLabeledSignalSchema
G3	docs/gui/G3_UI_DATA_AND_AUTH_CONTRACT.md	DashboardDataService read-only adapter contract, deterministic Sandbox Demo portfolio synthesizer, and Argon2id + JWT authentication & multi-tenant RBAC flow.	src/security.py, src/storage.py, src/sandbox_runner.py
G4	docs/gui/G4_UI_BUILD_ROADMAP.md	File-by-file implementation specs (src/ui_theme.py, src/dashboard_service.py, app.py, .streamlit/config.toml), requirements.txt updates, and Streamlit Cloud deployment steps.	requirements.txt, scripts/verify_system.py

4. Strict Cross-Layer Data & Schema Contract Matrix
Every visual element in the GUI binds strictly to validated Pydantic v2 attributes in src/schemas.py:

Visual Widget / Dashboard Element	Target Screen	Source Pydantic Schema	Exact Field Mapping & Formula
Portfolio Heat Dial Gauge	Global KPI Header & Active Book	VirtualPortfolioLedgerSchema	current_portfolio_heat_pct vs. max_portfolio_heat_pct (6.00% hard cap)
Dry Powder & Capital Allocation Donut	Global KPI Header & Active Book	VirtualPortfolioLedgerSchema	cash_balance, total_equity, invested_capital = total_equity - cash_balance
Slot Capacity Bar	Global KPI Header & Active Book	VirtualPortfolioLedgerSchema	len(open_positions) / max_concurrent_positions (10)
Meta-Labeling Probability Card	Daily Action Bridge & Active Book	MetaLabeledSignalSchema	historical_win_rate (%), historical_ev_r_multiple (+X.XX R), primary_score (0–100), meta_conviction_scalar (0.50x–1.25x)
Broker Execution Order Ticket	Daily Action Bridge	TripleBarrierPositionSchema	ticker, index_id, shares, entry_price, initial_stop_price, take_profit_price, open_dollar_risk
Triple-Barrier Interactive Chart	Active Book	ParquetMarketDataRepository + TripleBarrierPositionSchema	60-day OHLCV candles + horizontal lines for entry_price, trailing_stop_price, and take_profit_price
Time-Barrier Countdown Pill	Active Book	TripleBarrierPositionSchema	bars_held vs. max_holding_bars (14 trading days)
Closed Trade Audit Ledger	Track Record Lab	ClosedTradeAuditSchema	ticker, entry_date, exit_date, exit_reason, realized_pnl_dollars, realized_r_multiple
Index Subscription Controls	Control Room	VirtualPortfolioLedgerSchema	subscribed_indices (RUT_2000, SP_400, SP_500)

5. Security, Multi-Tenant Isolation & Commercial Tier Gating
5.1 Authentication & Tenant Isolation
Argon2id + JWT Session Flow: User credentials are verified via PasswordManager.verify_password() (src/security.py). Authenticated sessions store a signed JWTTokenPayload in st.session_state["jwt_token"].

Hard Tenant Boundary: Every service call executes TenantSecurityGuard.enforce_tenant_access(claims, ledger.user_id) prior to returning portfolio data. Cross-tenant reads or writes raise AuthorizationError immediately.

Zero-Touch Interactive Demo Mode: Prospective users or subscribers viewing a 100%-cash live portfolio can toggle Interactive Sandbox Demo Mode, rendering an isolated, realistic multi-position portfolio in memory without mutating data/virtual_portfolio.json.

5.2 Commercial Tier Entitlements
Explorer (Free): Interactive Sandbox Demo Mode, delayed (T+1) single signal preview, educational Triple-Barrier chart.

Quant Trader (Pro): Live post-market EOD Action Bridge (RUT_2000, SP_400), full 500d Meta-Labeling Win-Rate & Expected Value (R) cards, dynamic share calculator, and Telegram alert integration.

Institutional (Elite): Full multi-index access including SP_500, custom Portfolio Heat ceiling (2.0%–6.0%), multi-portfolio management, and full CSV/JSON audit export.

6. Phase 2 Definition of Done (DoD) & Acceptance Gates
Performance SLA: Dashboard initial render and tab transitions complete in < 1.5 seconds using cached Parquet/JSON state.

Strict Decoupling: Static AST audit (scripts/verify_system.py) confirms zero yfinance network calls inside UI modules.

100%-Cash UX Resilience: When open_positions is empty, the dashboard displays an active Capital Preservation status card and offers a one-click switch to the populated Sandbox Demo book.

Accurate Visual Telemetry: Plotly gauges and cards match underlying Pydantic computed fields (current_portfolio_heat_pct, open_dollar_risk, realized_r_multiple) to 4 decimal places.

Responsive Dark-Mode Layout: Clean rendering across desktop widescreen and mobile browsers (iPhone Safari / Chrome).


---
