# SIRIX — Bottom Navigation, Algorithmic Search, Audit Log & User Preferences Specification

**Document ID:** `02_SEARCH_AUDIT_AND_PREFERENCES`
**Target Branch:** `feat/adaptive-client`
**Parent Hub:** `00_SIRIX_MASTER_ARCHITECTURE.md`

---

## 1. Fixed 3-Icon Bottom Navigation Bar

Across mobile and compact viewports (`< 1024px`), **SIRIX** maintains a fixed bottom navigation bar (`56px` height + `env(safe-area-inset-bottom)`, `--bg-surface`, `1px solid var(--border-subtle)` top border) with **strictly three icons**:

| Slot (Start $\rightarrow$ End) | Icon | Canonical / Localized Label | Target Destination |
| :--- | :--- | :--- | :--- |
| **1 (Primary)** | `Briefcase` / `PieChart` | Portfolio Status (*מצב התיק*) | Main 3-tier Portfolio Home screen (`01_PORTFOLIO_HOME_AND_INSPECTOR.md`). |
| **2 (Center)** | `Search` | Stock Search (*חיפוש מניה*) | Algorithmic Universe & Telemetry Search screen. |
| **3 (End)** | `Sliders` / `UserCog` | User Preferences (*העדפות משתמש*) | Theme palettes, 4-language selector, account tier status, and engine risk parameters. |

*(On Desktop `>= 1024px`, these three destinations are accessible via a compact vertical icon rail on the far start edge of the viewport).*

---

## 2. Screen 2: Algorithmic Stock Search (`חיפוש מניה`)

Because **SIRIX** enforces **Zero-Override** (no manual buy/sell buttons), the Search screen serves as an **Explainable AI & Universe Telemetry Lookup** across the `RUT` (Russell 2000) and `MID` (S&P MidCap 400) universes.

### 2.1 Search Input & Quick Filters
* Auto-focused search bar accepting ticker symbols or company names (`dir="ltr"` input formatting for tickers).
* Quick filter chips: `All Universe`, `Held in Portfolio`, `Near Signal`, `Blackout Restricted`.

### 2.2 Dual-State Search Result Behavior
1. **Case A — Ticker is Currently Held in Portfolio:**
   * Displays an `ACTIVE POSITION` badge (`--status-profit-bg`).
   * Tapping the result opens the exact same **Deep-Dive Position Inspector** (`01_PORTFOLIO_HOME_AND_INSPECTOR.md`) with its 7-day candlestick chart and live `Triple-Barrier` levels.
2. **Case B — Ticker is NOT Held in Portfolio (Algorithmic Transparency Card):**
   * Displays an `UNHELD • ZERO-OVERRIDE` badge and explains **why the quantitative engine did not enter a position** during the latest EOD scan:
     * **Primary Rejection / Status Reason Badge:**
       * `BELOW_CONVICTION_THRESHOLD` (e.g., `Conviction: 0.52 < 0.70 required`)
       * `EARNINGS_BLACKOUT_ACTIVE` (e.g., Earnings report within 5 trading days)
       * `MAX_PORTFOLIO_HEAT_REACHED` (Signal valid, but portfolio risk ceiling `6.0%` was full)
       * `TREND_FILTER_INACTIVE` (Price below 50-day SMA regime filter)
     * **Diagnostic Snapshot:** Last EOD Close price, `ATR (14d)`, Index membership (`RUT` / `MID`), and `Conviction` score so the user gains full transparency into the engine's discipline.

---

## 3. Closed-Trade `Audit Log` View

Triggered from the dedicated **`Audit Log`** boundary bar on the Portfolio Home screen (Zone 2). Renders as a full-screen slide-over view on mobile or modal/drawer on desktop.

### 3.1 Summary Performance Strip
* Displays rolling historical metrics: **Total Closed Trades**, **Win Rate %**, **Average R-Multiple**, and **Profit Factor** (all isolated `dir="ltr"` tabular numerals).

### 3.2 Closed Trade Ledger Rows
Each historical trade row displays:
* **Ticker & Index Tag:** e.g., `ANF` • `RUT`
* **Exit Date & Holding Duration:** e.g., `2026-11-10` • `9d / 14d`
* **Realized Return:** Signed percentage and dollar P&L (`+14.20%` / `+$1,840.00`).
* **Canonical Exit Reason Pill (Color-Coded):**
  * `TAKE_PROFIT` (`--status-profit` / `--status-profit-bg`)
  * `CHANDELIER_STOP` (`--status-risk` if net loss, `--status-fresh` if locked-in trailing profit)
  * `TIME_BARRIER` (`--status-warn` / `--status-warn-bg`)
  * `EARNINGS_BLACKOUT` (`--status-warn` / `--status-warn-bg`)
* **Entry `Conviction` Score:** e.g., `Conviction: 0.86` (visible to `EXPERT` tier).

---

## 4. Screen 3: User Preferences & Engine Guardrails (`העדפות משתמש`)

Consolidates visual ergonomics, localization, account tier status, and engine risk parameters into a clean, grouped settings interface.

### 4.1 Appearance & Color Palette Selector
Interactive visual swatch cards allowing instant switching (`data-theme` attribute update + `localStorage` persistence):
1. **`Obsidian Dark`** — Swatch preview (`#090D16` / `#111827` / `#06B6D4`) — *Default Institutional Dark.*
2. **`Sirius Ice Light`** — Swatch preview (`#F0F7FF` / `#FFFFFF` / `#0284C7`) — *Daylight Sky & Ice Blue.*
3. **`Midnight Sapphire`** — Swatch preview (`#0B192C` / `#132743` / `#38BDF8`) — *Royal Banking Navy.*

### 4.2 Interface Language (`i18n` & `RTL`/`LTR`)
Segmented selector for the four supported locales:
* **`EN`** (English — `LTR`)
* **`עב`** (Hebrew — `RTL`)
* **`عر`** (Arabic — `RTL`)
* **`RU`** (Russian — `LTR`)
* Includes an explanatory helper note confirming that core financial terms (`Triple-Barrier`, `Chandelier Stop`, `Portfolio Heat`, etc.) remain in English for precision.

### 4.3 Engine Risk Guardrails (`index_registry.json` Sync)
Displays and (for authorized tiers) allows adjusting the risk parameters governing the user's isolated portfolio:
* **`Max Portfolio Heat %`:** Slider/stepper (`2.0%` to `10.0%`, default `6.0%`) with `ⓘ` tooltip. Updates the Portfolio Home gauge ceiling immediately upon save.
* **`Risk Per Trade %`:** Fixed fractional risk unit (`0.5%` to `2.0%`, default `1.0%`).
* **`Time Barrier` Horizon:** Read-only or configurable max holding days (`14 Trading Days`).
* **`Earnings Blackout` Window:** Pre-earnings exit buffer (`5 Trading Days`).
* **Autonomous `Zero-Override` & `Kill-Switch` Status:** Displays active engine state (`ACTIVE — AUTONOMOUS EOD`) and emergency portfolio halt toggle (`EXPERT` tier only, protected by a two-step confirmation dialog).

### 4.4 Account Profile & Session Footer
* Displays authenticated `user_id`, active subscription badge (`FREE`, `PRO`, or `EXPERT`), last EOD pipeline sync timestamp, and a clean **`Sign Out`** action button.