# IMPLEMENTATION BLUEPRINT & CLOUD DEPLOYMENT ROADMAP (G4)
## Swing Quant Engine — Modular GUI File Architecture, Dependencies & Zero-Install Cloud Hosting

**Document ID:** `G4_UI_BUILD_ROADMAP`  
**Parent Document:** `docs/gui/G0_MASTER_GUI_PRD.md`  
**Version:** `2.0.0`  
**Status:** `APPROVED FOR IMPLEMENTATION`  
**Target Stack:** Python 3.11+ | Streamlit | Plotly | GitHub Web | Streamlit Community Cloud  

---

## 1. Modular File Decomposition & Size Guardrails

To ensure 100% maintainability via the **GitHub Web interface** and **Google AI Studio** without hitting token truncation limits, the Phase 2 GUI is partitioned into four clean, single-responsibility files:

| Build Step | File Path | Max Lines Target | Responsibility & Architectural Scope |
| :--- | :--- | :--- | :--- |
| **Step 1** | `.streamlit/config.toml` & `requirements.txt` | ~40 lines | Institutional Dark-Mode native theme configuration, headless server flags, and locked `streamlit` + `plotly` package versions. |
| **Step 2** | `src/ui_theme.py` | ~320 lines | **Visual & Charting Engine:** Design tokens, custom CSS injection, HTML conviction cards, and all 5 Plotly interactive chart builders (`Portfolio Heat Gauge`, `Dry Powder Donut`, `Triple-Barrier Price Cage`, `Equity Curve`, `R-Distribution`). |
| **Step 3** | `src/dashboard_service.py` | ~350 lines | **Data, Demo & Auth Service Layer:** `StockConvictionCardVM`, `PortfolioDashboardSnapshotVM`, `DashboardDataService` (read-only adapter + deterministic 5-position Sandbox Demo synthesizer), and `GUIAuthController` (`src/security.py` integration). |
| **Step 4** | `app.py` | ~340 lines | **Main Commercial SaaS Cockpit:** Sidebar navigation, 1-click Live/Demo toggle, persistent Top KPI strip, and the 4 core views (`Action Bridge`, `Active Risk Book`, `Track Record Lab`, `Control Room`). |

---

## 2. Dependency & Theme Configuration Specifications (Step 1)

### 2.1 `requirements.txt` Additions
Add the following strictly pinned presentation libraries to the existing `requirements.txt` without altering core engine dependencies:
* `streamlit>=1.39.0,<2.0.0`
* `plotly>=5.24.0,<6.0.0`

### 2.2 `.streamlit/config.toml` Specification
Configures Streamlit to boot natively into the obsidian institutional theme with minimal UI chrome:
```toml
[theme]
base = "dark"
primaryColor = "#06B6D4"
backgroundColor = "#0B0F19"
secondaryBackgroundColor = "#111827"
textColor = "#F9FAFB"
font = "sans serif"

[server]
headless = true
enableCORS = false
enableXsrfProtection = true

[browser]
gatherUsageStats = false

3. Module-by-Module Implementation Contracts (Steps 2–4)
3.1 src/ui_theme.py (Visual & Plotly Factory Module)
Must expose the following exact public functions with zero business-logic side effects:

inject_institutional_css() -> None: Injects custom CSS for glassmorphic KPI cards, monospace financial numerals, risk badges, and clean table styling.

render_top_kpi_strip(snapshot: PortfolioDashboardSnapshotVM) -> None: Renders the 4-column top telemetry row (Total Equity, Free Cash / Dry Powder, Active Slots X/10, Portfolio Heat %).

build_portfolio_heat_gauge(current_heat_pct: float, max_heat_pct: float, open_dollar_risk: float) -> go.Figure: Builds the semicircular Plotly risk dial with Emerald (<3.5%), Amber (3.5%–5.0%), and Crimson (>5.0%) zones.

build_capital_allocation_chart(cash_balance: float, total_equity: float, cards: List[StockConvictionCardVM], max_slots: int) -> go.Figure: Builds the Dry Powder vs. Deployed Capital ring chart.

render_stock_conviction_card(card: StockConvictionCardVM, show_copy_ticket: bool = True) -> None: Renders the per-stock probability card (500d Win Rate %, EV in +R, Primary Score, Conviction Scalar, and Entry / SL / TP order strip).

build_triple_barrier_cage_chart(ohlcv_df: pd.DataFrame, card: StockConvictionCardVM) -> go.Figure: Builds the 60-day candlestick chart overlaid with Entry, Initial Stop, Active Chandelier Stop, 1:3 Take-Profit, and shaded reward/risk zones.

build_performance_charts(closed_trades: List[ClosedTradeAuditSchema], initial_capital: float = 100000.0) -> Tuple[go.Figure, go.Figure]: Returns the Cumulative Equity Curve figure and Realized R-Multiple Distribution bar chart.

3.2 src/dashboard_service.py (Service, Auth & Demo Synthesizer Module)
Must expose the following classes and methods:

StockConvictionCardVM(BaseModel) and PortfolioDashboardSnapshotVM(BaseModel): Strictly typed Pydantic v2 view-models matching G3_UI_DATA_AND_AUTH_CONTRACT.md.

GUIAuthController:

authenticate_session(email: str, password: str, tier_override: Optional[str] = None) -> JWTTokenPayload

get_Quick_Preview_Session(tier: Literal["FREE", "PRO", "ELITE"]) -> JWTTokenPayload: Enables 1-click role/tier switching in the sidebar so the platform owner can test Free vs. Pro vs. Elite subscriber experiences effortlessly.

DashboardDataService:

load_dashboard_snapshot(portfolio_id: UUID, user_claims: JWTTokenPayload, force_demo_mode: bool = False, custom_account_equity: Optional[float] = None) -> PortfolioDashboardSnapshotVM

build_interactive_demo_snapshot(custom_account_equity: float = 100000.0, subscription_tier: str = "ELITE") -> PortfolioDashboardSnapshotVM

load_ticker_cage_ohlcv(ticker: str, card: StockConvictionCardVM, is_demo: bool = False) -> pd.DataFrame

update_tenant_preferences(portfolio_id: UUID, user_claims: JWTTokenPayload, subscribed_indices: List[str], max_heat_pct: float) -> VirtualPortfolioLedgerSchema

3.3 app.py (Main Streamlit Entrypoint)
Must orchestrate the 4-Screen Commercial SaaS Experience:

Page Config & CSS Initialization: st.set_page_config(page_title="Swing Quant Engine | Institutional Terminal", page_icon="🏛️", layout="wide").

Sidebar Control Rail:

Subscriber Tier / Role Switcher (Elite Owner, Pro Subscriber, Free Explorer) + Login gate.

Prominent Portfolio Source Toggle: 🟢 Live Production Ledger vs. 🧪 Interactive Sandbox Demo (5 Positions).

Account Sizing Simulator Input ($10,000 to $1,000,000 real-world broker capital scaler).

4-View Navigation Radio (🎯 Today's Orders, 🛡️ Active Risk Book, 📈 Track Record Lab, ⚙️ Control Room).

Smart Empty-State Handling: If 🟢 Live Production Ledger is selected and len(open_positions) == 0, renders the Active Capital Preservation Banner (100% Cash) with a single-click button to activate 🧪 Interactive Sandbox Demo so the user can inspect populated gauges and charts immediately.

4. Zero-Install Deployment Workflow (GitHub Web -> Streamlit Community Cloud)
Because development operates 100% via the browser without local Python installation, deployment follows this exact 3-minute cloud workflow:

Commit GUI Files in GitHub Web:

Add .streamlit/config.toml, update requirements.txt, and create src/ui_theme.py, src/dashboard_service.py, and app.py.

Verify Integrity via GitHub Actions:

Update scripts/verify_system.py to include AST syntax and symbol verification for src/ui_theme.py, src/dashboard_service.py, and app.py.

Run the GitHub Actions workflow to confirm 100% green checks.

One-Click Cloud Hosting (Streamlit Community Cloud):

Log in to share.streamlit.io using your GitHub account.

Click Create App -> Select your repository (Swing-Quant-Engine), branch main, and Main file path app.py.

In Advanced Settings -> Secrets, paste JWT_SECRET_KEY = "your_32_char_secret".

Click Deploy! — Within 90 seconds, you receive a live, SSL-secured URL accessible from your Chromebook and iPhone 12 Pro, automatically synced whenever GitHub Actions updates data/virtual_portfolio.json.