# PRODUCT & UX SPECIFICATION DOCUMENT (G1)
## Swing Quant Engine — Commercial SaaS Subscriber Experience, Tier Gating & Screen Architecture

**Document ID:** `G1_UI_PRODUCT_SPEC`  
**Parent Document:** `docs/gui/G0_MASTER_GUI_PRD.md`  
**Version:** `2.0.0`  
**Status:** `APPROVED FOR IMPLEMENTATION`  
**Target Stack:** Python 3.11+ | Streamlit | Plotly | Pydantic v2  

---

## 1. Product Vision & Commercial Value Proposition (Why Users Pay)

### 1.1 The Core Commercial Premise
Retail and semi-institutional swing traders fail primarily due to emotional execution errors: chasing extended breakouts, sizing positions inconsistently, moving stop-losses downward during drawdowns, or forcing low-probability trades in choppy markets. 

The **Swing Quant Engine GUI** monetizes institutional discipline. Subscribers pay for a **60-Second Daily Post-Market Execution Ritual** that translates Dr. Marcos López de Prado’s **Meta-Labeling** and **Triple-Barrier Method** alongside Jim Simons’ **Portfolio Heat Controls** into actionable, unambiguous broker instructions.

### 1.2 The "3-Second First Impression" Rule
Upon authenticating into the platform, the subscriber must never face raw data dumps or ambiguous charts. Within **3 seconds** of page load—without scrolling—the persistent Global Telemetry Header answers three questions:

1. **Capital Safety (Portfolio Heat Gauge):** *"How much of my total equity is currently at risk if every open stop-loss is hit today?"* (`current_portfolio_heat_pct` vs. `6.00%` maximum hard cap).
2. **Buying Power & Dry Powder (Capital Allocation Meter):** *"How much free cash and slot capacity do I have available for tonight's setups?"* (`cash_balance`, `deployed_equity_pct`, and `Active Slots X / 10`).
3. **Quantified Edge per Signal (Meta-Labeling Conviction):** *"Which exact orders do I place tonight, and what is their proven 500-day statistical expectancy?"* (`historical_win_rate`, `historical_ev_r_multiple`, and `meta_conviction_scalar`).

---

## 2. Commercial Subscription Tiers & Feature Gating (`Free` vs. `Pro` vs. `Elite`)

Subscription entitlements are enforced strictly at the service layer (`src/dashboard_service.py`) bound to `UserIdentitySchema` and `UserRole` (`src/schemas.py`).

| Capability / Feature | Explorer (`Free`) | Quant Trader (`Pro` - Core Paid) | Institutional (`Elite`) |
| :--- | :--- | :--- | :--- |
| **Interactive Sandbox Demo Portfolio** | Full Access (5-position simulated book) | Full Access | Full Access |
| **Post-Market EOD Signal Feed** | Delayed (`T+1`) Top-1 Signal Preview | Real-Time EOD (`T+0`) Full Feed | Real-Time EOD (`T+0`) Full Feed |
| **Covered Market Indices** | Preview Only | `RUT_2000` (Small-Cap) + `SP_400` (Mid-Cap) | `RUT_2000` + `SP_400` + `SP_500` (Large-Cap) |
| **Meta-Labeling Probability Cards** | Blurred / Sample Only | Full 500d `Win Rate %`, `EV (+R)`, `phi_meta` | Full + Historical Signal Breakdown |
| **Dynamic Position Sizing Calculator** | Fixed `$100k` Demo Equity | Custom Account Equity Input | Multi-Portfolio Custom Equity |
| **Interactive Triple-Barrier Cage Chart** | Demo Tickers Only | All Active & Candidate Tickers | All Active & Candidate Tickers |
| **Portfolio Heat Ceiling Customization** | Locked (`6.00%`) | Locked (`6.00%` Simons Standard) | Configurable (`2.00%` – `6.00%` Hard Cap) |
| **Automated Telegram Execution Alerts** | Disabled | Personal Chat ID Pairing | Multi-Channel / Webhook Pairing |
| **Closed Trade Audit Ledger Export** | View Only (Last 10 Trades) | Full View | Full CSV / JSON Audit Export |

---

## 3. Information Architecture & 4-Screen Navigation Map

### 3.1 Global Persistent Layout
* **Left Sidebar Navigation Rail:**
  * **Brand Header:** `SWING QUANT ENGINE` + Environment Badge (`LIVE PRODUCTION` or `INTERACTIVE DEMO`).
  * **Portfolio Context Selector:** Active Tenant Portfolio Name (`portfolio_name`), Tenant UUID badge, and **Live Book <-> Sandbox Demo Toggle**.
  * **Primary View Switcher (Radio / Segmented Tabs):**
    1. `🎯 Today's Orders (Action Bridge)`
    2. `🛡️ Active Risk Book (Live Positions)`
    3. `📈 Track Record & Audit Lab`
    4. `⚙️ Control Room & Settings`
  * **System Telemetry Footer:** `Last EOD Sync: YYYY-MM-DD HH:MM UTC`, Active Indices pills (`RUT_2000`, `SP_400`), and `Logout` button.

* **Global Top KPI Strip (Persistent Across Views 1 & 2):**
  * **Card 1 — Total Portfolio Equity:** `$XXX,XXX.XX` (`total_equity`) with net realized P&L delta.
  * **Card 2 — Available Dry Powder:** `$XXX,XXX.XX` (`cash_balance`) + percentage in cash (`cash_balance / total_equity`).
  * **Card 3 — Active Slot Capacity:** `X / 10 Positions` (`len(open_positions) / max_concurrent_positions`).
  * **Card 4 — Portfolio Heat Status:** `X.XX% / 6.00% Max` (`current_portfolio_heat_pct`) with color-coded safety badge (`SAFE`, `MODERATE`, `MAX HEAT`).

---

### 3.2 View 1: Daily Action Bridge (`🎯 Today's Orders`)
**Objective:** Give the subscriber exact, copy-pasteable broker execution tickets generated by today's post-market run.

1. **Section A — Urgent Barrier Exits & Ratcheted Stop Updates (Top Priority):**
   * **Closed Positions Today (`SELL AT MARKET / EOD`):** Lists any holdings that triggered `UPPER_BARRIER_TP`, `LOWER_BARRIER_SL`, or `VERTICAL_BARRIER_TIME` (`14d`), displaying realized `$ P&L` and `R-Multiple`.
   * **Trailing Stop Ratchets (`RAISE BROKER STOP-LOSS`):** Highlights open positions where today's high ratcheted `trailing_stop_price` upward (`Chandelier Exit`), showing `Previous Stop -> New Ratcheted Stop` so the user updates their broker GTC stop order.
2. **Section B — Approved Meta-Labeled Buy Entries (`NEW BUY ORDERS`):**
   * Rendered as high-contrast **Execution Order Cards** (1 card per approved entry):
     * **Header:** `Ticker` (`index_id` badge, e.g., `RUT_2000`) | Action Badge: `BUY LIMIT / MARKET`.
     * **Order Sizing Block:** Exact `Shares to Buy`, `Entry Price ($)`, `Total Position Cost ($)`, and `Dollar Risk at Stop ($)` (`open_dollar_risk`).
     * **Triple-Barrier Cage Parameters:**
       * 🔴 **Initial Stop-Loss (`SL`):** `$XX.XX` (`-k_stop * ATR_14`)
       * 🟢 **Take-Profit Target (`TP`):** `$XX.XX` (`+k_profit * ATR_14`, minimum `1:3` R/R)
       * ⏱️ **Time Barrier:** `14 Trading Days Max`
     * **Meta-Labeling Probability & Edge Strip (Why This Stock Was Chosen):**
       * **500d Win Rate:** `XX.X%` (`historical_win_rate`)
       * **Expected Value (EV):** `+X.XX R` (`historical_ev_r_multiple`)
       * **Breakout Rank Score:** `XX.X / 100` (`primary_score`)
       * **Conviction Multiplier:** `X.XXx` (`meta_conviction_scalar`)
     * **One-Click Copy Ticket Block:** Pre-formatted code block (`BUY {shares} {ticker} @ {entry} | SL: {stop} | TP: {target}`) with native one-click copy icon.

---

### 3.3 View 2: Live Risk & Portfolio Command (`🛡️ Active Risk Book`)
**Objective:** Visual monitoring of portfolio risk, capital allocation, and real-time distance to barriers for all active holdings.

1. **Visual Risk & Capital Dashboards Row (2-Column Split):**
   * **Left Panel — Portfolio Heat Dial Gauge:** Interactive Plotly semicircular gauge (`0.0%` to `6.0%`) with green/amber/crimson risk zones and current heat needle.
   * **Right Panel —