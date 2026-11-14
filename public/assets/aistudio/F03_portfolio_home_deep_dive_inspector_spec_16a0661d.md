# SIRIX — Portfolio Home Screen & Deep-Dive Inspector Specification

**Document ID:** `01_PORTFOLIO_HOME_AND_INSPECTOR`
**Target Branch:** `feat/adaptive-client`
**Parent Hub:** `00_SIRIX_MASTER_ARCHITECTURE.md`

---

## 1. Screen Architecture Overview

The **Portfolio Home** view is the primary entry screen of **SIRIX**. It implements strict **Progressive Disclosure** so the user can assess total account health and macro position performance within two seconds, while isolating complex quantitative telemetry (`Triple-Barrier` levels, `ATR`, `Conviction`, and 7-day candlesticks) inside an on-demand **Deep-Dive Inspector**.

---

## 2. Three-Tier Vertical Hierarchy (Mobile & Master Pane)

The vertical viewport is divided into three clean, non-overlapping zones above the fixed 3-icon bottom navigation bar:

### 2.1 Zone 1: Hero Portfolio Summary Header
Located at the top of the viewport (`--bg-canvas`), providing an immediate macro snapshot:
1. **Top Brand & Telemetry Strip:**
   * Left/Start: Minimalist **SIRIX** wordmark + `Zero-Override` status pill (`AUTONOMOUS`).
   * Right/End: Persistent **Portfolio Heat Gauge** compact arc/dial widget showing `current_heat_pct` vs. `max_heat_pct` (e.g., `5.4% / 6.0%`) paired with a localized `ⓘ` tooltip trigger.
2. **Hero Total Equity Display:**
   * Large tabular figure (`32px` mobile / `40px` desktop, `--text-primary`, `dir="ltr"`): e.g., **`$104,820.50`**.
3. **Two-Row Performance Breakdown (Directly Below Equity):**
   * **Row 1 — Daily Change (Last EOD Session):** Localized label + isolated LTR figure, e.g., `+$1,140.20 (+1.10%)` in `--status-profit` (or `--status-risk` if negative).
   * **Row 2 — Inception Return (Since Account Opening):** Localized label + isolated LTR figure, e.g., `+$4,820.50 (+4.82%)`.

### 2.2 Zone 2: Boundary Action Bar (`Audit Log` Trigger)
Positioned directly on the seam between the Hero Portfolio Summary (Zone 1) and the Scrollable Equity List (Zone 3):
* **Visual Structure:** Full-width interactive surface bar (`--bg-surface`, `1px solid var(--border-subtle)`, `rounded-xl`, `44px` height).
* **Left/Start Content:** Dedicated history/scroll icon (`History` / `ScrollText`) + canonical English label **`Audit Log`** + localized `ⓘ` tooltip trigger.
* **Right/End Content:** Pill badge showing closed trade count or rolling win-rate (e.g., `18 Closed • 66.7% Win`) + directional chevron (`rtl:rotate-180`).
* **Interaction:** Tapping this bar opens the closed-trade **`Audit Log`** view/drawer (detailed in `02_SEARCH_AUDIT_AND_PREFERENCES.md`) without displacing the 3-icon bottom navigation bar.

### 2.3 Zone 3: Scrollable Minimalist Equity List
Displays all currently held active positions in a clean, scannable vertical stack (`gap-2.5`).

#### Equity Row / Banner Anatomy (Zero Clutter Rule)
Each position card (`--bg-surface`, `rounded-xl`, overflow hidden) displays **strictly four core data points** plus the bottom **Timeline Bar**:
1. **Top-Start:** Ticker Symbol (`15px` bold, e.g., `SMCI`) + compact index badge (`RUT` or `MID` in `--accent-brand`).
2. **Bottom-Start:** Current Share Price (`13px` mono, `--text-secondary`, e.g., `$53.90`).
3. **Top-End:** Total Position Market Value (`15px` bold mono, `--text-primary`, e.g., `$13,475.00`).
4. **Bottom-End:** Unrealized P&L Percentage (`13px` bold mono, `--status-profit` or `--status-risk`, e.g., `+11.83%`).

#### Flush Bottom 14-Day `Timeline Bar` (`3px` Height)
Integrated flush along the bottom edge of every position banner, visualizing holding duration against the 14-trading-day `Time Barrier` ($\text{Progress} = \min(100\%, \frac{\text{days\_held}}{14} \times 100\%)$):
* **Days 1–7 (`7% – 50%` width):** `--status-fresh` (Cyan / Cerulean) — *Fresh momentum phase.*
* **Days 8–11 (`57% – 78%` width):** `--status-warn` (Amber / Ochre) — *Maturing position; trailing stop tightening.*
* **Days 12–14 (`85% – 100%` width):** `--status-risk` (Crimson / Red) — *Imminent `Time Barrier` auto-liquidation alert.*
* *(Note: Bar progression always fills Left-to-Right `dir="ltr"` even in RTL locales to maintain universal time-series consistency).*

---

## 3. Deep-Dive Position Inspector (On-Demand Detail View)

Tapping or clicking any position banner opens the **Deep-Dive Inspector** without losing the user's vertical scroll position in the list.

### 3.1 Adaptive Presentation Mode
* **Mobile (`< 1024px`):** Renders as a slide-up **Bottom Sheet** (`max-height: 85dvh`, rounded top corners `20px`, drag handle bar at top, backdrop blur `--bg-overlay`). Includes swipe-down dismissal and Prev/Next ticker chevrons in the header to cycle through positions seamlessly.
* **Desktop (`>= 1024px`):** Renders permanently in the right-hand **Detail Pane** of the Master-Detail Split View (`flex-1`), immediately updating whenever a row is clicked in the left-hand Master Pane.

### 3.2 Inspector Content Modules
1. **Inspector Header:**
   * Ticker (`SMCI`), Index Tag (`RUT`), Current Price (`$53.90`), Unrealized P&L (`+$1,425.00 / +11.83%`), and Share Count (`250 Shares`).
2. **7-Day Candlestick Chart (OHLC Mini-Chart):**
   * Crisp HTML5 Canvas or SVG candlestick visualization covering the last 7 trading sessions (`dir="ltr"`).
   * Bullish candles rendered in `--status-profit`; bearish candles in `--status-risk`.
   * **Three Horizontal Barrier Overlays:**
     * Upper dashed line (`--status-profit`): **`Take-Profit`** target price (e.g., `$57.80`).
     * Middle dotted line (`--text-muted`): **`Entry Price`** (e.g., `$48.20`).
     * Lower solid line (`--status-risk`): **`Chandelier Stop`** ratchet-only floor (e.g., `$49.50`).
3. **Interactive `Triple-Barrier` Price Gauge:**
   * Normalized horizontal range bar plotting current price $P_t$ between `Chandelier Stop` ($S_t$, $0\%$) and `Take-Profit` ($T_p$, $100\%$):
     $$\text{Barrier Progress} = \frac{P_t - S_t}{T_p - S_t} \times 100\%$$
   * Displays exact dollar and percentage cushion remaining above `Chandelier Stop` and distance to `Take-Profit`.
4. **Quantitative Telemetry Matrix (2x2 Grid with `ⓘ` Tooltips):**
   * **Cell 1 — `ATR (14d)` & Buffer:** e.g., `$2.15 (3.98%)` • `2.05x ATR above Stop`.
   * **Cell 2 — `Time Barrier` Status:** e.g., `Day 6 / 14` (color-coded to match the banner's `Timeline Bar`).
   * **Cell 3 — `Conviction` Score:** Meta-Labeling probability score, e.g., `0.84` (`High Confidence`).
   * **Cell 4 — `Earnings Blackout`:** Next scheduled earnings date (e.g., `2026-12-04 • Safe (22d)`), warning in `--status-warn` if within 5 trading days of mandatory blackout exit.