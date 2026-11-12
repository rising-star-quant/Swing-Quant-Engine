# VISUAL DESIGN & INTERACTIVE DASHBOARDS SPECIFICATION (G2)
## Swing Quant Engine — Institutional Dark-Mode UI, Risk Gauges & Plotly Telemetry

**Document ID:** `G2_DESIGN_AND_DASHBOARDS`  
**Parent Document:** `docs/gui/G0_MASTER_GUI_PRD.md`  
**Version:** `2.0.0`  
**Status:** `APPROVED FOR IMPLEMENTATION`  
**Target Stack:** Python 3.11+ | Streamlit | Plotly Graph Objects (`plotly.graph_objects`) | Custom CSS3  

---

## 1. Visual Identity & Institutional Dark-Mode Design Tokens

### 1.1 Design Philosophy
Commercial subscribers judge the credibility of a quantitative platform within milliseconds. The visual language emulates modern institutional trading terminals (Bloomberg Launchpad, Linear, TradingView Dark) using high-contrast semantic colors, tabular monospace numerals (`font-variant-numeric: tabular-nums`), and zero visual clutter.

### 1.2 Color Palette & Semantic Tokens (`src/ui_theme.py`)
All Plotly charts and HTML/CSS cards must import these exact hex constants from `src/ui_theme.py`:

| Token Constant | Hex Code | Semantic Role & Usage |
| :--- | :--- | :--- |
| `BG_PRIMARY` | `#0B0F19` | Deep obsidian main application background (`stApp`). |
| `BG_SURFACE` | `#111827` | Elevated card, KPI container, and chart background. |
| `BG_SIDEBAR` | `#070A12` | Left navigation rail and portfolio context panel. |
| `BORDER_SUBTLE` | `#1F2937` | `1px solid` card borders and table gridlines. |
| `TEXT_PRIMARY` | `#F9FAFB` | High-contrast headings, ticker symbols, and primary KPI figures. |
| `TEXT_MUTED` | `#9CA3AF` | Secondary labels, timestamps, and axis titles. |
| `ACCENT_CYAN` | `#06B6D4` | Primary brand accent, Entry Price level (`Entry`), and active selection. |
| `SEMANTIC_EMERALD` | `#10B981` | Safe Portfolio Heat (`< 3.5%`), Take-Profit Barrier (`TP`), positive EV / P&L. |
| `SEMANTIC_AMBER` | `#F59E0B` | Moderate Portfolio Heat (`3.5% – 5.0%`), Time-Stop approaching (`>= 10d`), raised stop alert. |
| `SEMANTIC_CRIMSON` | `#EF4444` | High Portfolio Heat (`> 5.0%`), Stop-Loss Barrier (`SL`), risk zone shading. |
| `SEMANTIC_VIOLET` | `#8B5CF6` | Meta-Labeling Conviction badge (`phi_meta`) and institutional tier highlights. |

### 1.3 Typography & Card Styling Rules
* **Font Stack:** `'Inter', -apple-system, BlinkMacSystemFont, sans-serif` for UI labels; `'JetBrains Mono', 'Fira Code', monospace` for all prices, percentages, shares, and R-multiples.
* **Glassmorphic Surface Cards:** `background: #111827; border: 1px solid #1F2937; border-radius: 10px; padding: 16px 20px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);`.

---

## 2. Core Dashboard 1 — Portfolio Heat Risk Gauge (`build_portfolio_heat_gauge`)

### 2.1 Functional Purpose
Answers the subscriber's #1 question: **"What is the current risk level in my portfolio?"**
Visualizes `ledger.current_portfolio_heat_pct` against Jim Simons’ hard `ledger.max_portfolio_heat_pct` (`6.00%`) ceiling.

### 2.2 Plotly Specification (`go.Indicator`)
* **Chart Type:** `go.Indicator(mode="gauge+number+delta")`
* **Input Contract:**
  * `current_heat_pct: float` (`ledger.current_portfolio_heat_pct * 100.0`, e.g., `3.45` for `3.45%`)
  * `max_heat_pct: float` (`ledger.max_portfolio_heat_pct * 100.0`, default `6.00`)
  * `open_dollar_risk: float` (`sum(p.open_dollar_risk for p in ledger.open_positions.values())`)
* **Gauge Geometry & Color Zones:**
  * **Axis Range:** `[0.0, max_heat_pct]` (default `[0.0, 6.0]`) with tick suffix `"%"`.
  * **Zone 1 — Safe Zone (`0.0%` to `3.5%`):** Fill `rgba(16, 185, 129, 0.22)` (`SEMANTIC_EMERALD`).
  * **Zone 2 — Elevated Zone (`3.5%` to `5.0%`):** Fill `rgba(245, 158, 11, 0.25)` (`SEMANTIC_AMBER`).
  * **Zone 3 — Maximum Heat Ceiling (`5.0%` to `6.0%`):** Fill `rgba(239, 68, 68, 0.30)` (`SEMANTIC_CRIMSON`).
  * **Dynamic Bar Color:** Bar needle dynamically takes `#10B981` if `< 3.5%`, `#F59E0B` if `<= 5.0%`, or `#EF4444` if `> 5.0%`.
  * **Threshold Line:** Solid crimson marker at `value = max_heat_pct` (`thickness=0.85`).
* **Subtitle / Bottom Annotation:** Displays exact dollar risk exposure: `"Total Open Stop Risk: $X,XXX.XX | Remaining Risk Budget: $X,XXX.XX"`.
* **Layout Dimensions:** `height=260`, `margin=dict(l=24, r=24, t=42, b=18)`, `paper_bgcolor="rgba(0,0,0,0)"`.

---

## 3. Core Dashboard 2 — Available Cash & Capital Allocation Donut (`build_capital_allocation_chart`)

### 3.1 Functional Purpose
Answers the subscriber's #2 question: **"How much free cash do I have ready to invest, and how is my capital deployed?"**

### 3.2 Plotly Specification (`go.Pie` Ring Chart)
* **Chart Type:** `go.Pie(hole=0.68, textinfo="label+percent", hoverinfo="label+value+percent")`
* **Input Contract:**
  * `cash_balance: float` (`ledger.cash_balance`)
  * `total_equity: float` (`ledger.total_equity`)
  * `open_positions: Dict[str, TripleBarrierPositionSchema]`
* **Slice Breakdown:**
  * **Slice 0 (Primary Highlight):** `"Available Cash (Dry Powder)"` = `ledger.cash_balance` colored `#10B981` (`SEMANTIC_EMERALD`) when `> 20%` of equity, or `#06B6D4` (`ACCENT_CYAN`).
  * **Slices 1..N:** Each active holding in `open_positions` (`value = pos.shares * latest_price_or_entry`) colored along a cohesive institutional slate/indigo/cyan gradient (`#3B82F6`, `#6366F1`, `#8B5CF6`, `#0EA5E9`, `#14B8A6`).
* **Center Donut Annotation (HTML / Plotly Annotation):**
  * Top Line (Muted): `"FREE CASH"`
  * Middle Line (Bold Monospace 20px): `"${cash_balance:,.0f}"`
  * Bottom Line (Emerald Pill): `"{cash_pct:.1f}% Liquid | {slots_used}/{max_slots} Slots"`
* **Layout Dimensions:** `height=260`, `showlegend=True` (compact right-hand legend), `paper_bgcolor="rgba(0,0,0,0)"`.

---

## 4. Core Dashboard 3 — Per-Stock Probability & Conviction Card (`render_stock_conviction_card`)

### 4.1 Functional Purpose
Answers the subscriber's #3 question: **"What is the probability of success and statistical edge for each selected stock?"**
Every stock approved by the engine (or held in the portfolio) renders a high-impact **Quant Edge & Probability Card** powered by Dr. Marcos López de Prado’s 500-day Triple-Barrier backtest metrics.

### 4.2 Card Anatomy & Visual Gauges
Each card displays 4 quantitative confidence indicators side-by-side:

1. **500-Day Historical Win Rate (`historical_win_rate`):**
   * Displayed as a bold percentage (`e.g., 64.2% Win Rate`) with a segmented horizontal progress bar (`0% -> 100%`).
   * Color coding: Emerald (`>= 50%`), Cyan (`35% – 49.9%` with asymmetric 1:3 R/R), Amber (`30% – 34.9%`).
2. **Expected Value per Trade (`historical_ev_r_multiple`):**
   * Displayed as `"+0.84 R / Trade"` (`EV > 0` invariant enforced by Meta-Labeling).
   * Tooltip / Micro-caption: *"Average net return in Risk Units (R) across 500-day historical setups."*
3. **Primary Breakout Rank (`primary_score`):**
   * Displayed as `"88.4 / 100"` composite Z-score percentile (`Momentum 45% + Volume Surge 30% + Relative Strength 25%`).
4. **Meta-Labeling Conviction Scalar (`meta_conviction_scalar`):**
   * Displayed as a violet badge: `"1.15x Sizing Conviction"` (`range: 0.50x – 1.25x`), showing how aggressively the Meta-Model scaled the base `1.0%` risk allocation.

### 4.3 Broker Execution Strip (Inside the Card)
Directly below the probability gauges, a horizontal 4-column execution strip displays:
* **BUY QUANTITY:** `{shares:,} Shares` (`${position_cost:,.2f}`)
* **ENTRY PRICE:** `${entry_price:,.2f}` (`ACCENT_CYAN`)
* **STOP-LOSS (`-1R`):** `${initial_stop_price:,.2f}` (`SEMANTIC_CRIMSON`, `Risk: ${open_dollar_risk:,.2f}`)
* **TAKE-PROFIT (`+3R`):** `${take_profit_price:,.2f}` (`SEMANTIC_EMERALD`, `Target: +${expected_profit_dollars:,.2f}`)

---

## 5. Core Dashboard 4 — Interactive Triple-Barrier Price Cage (`build_triple_barrier_cage_chart`)

### 5.1 Functional Purpose
Visualizes the active "protective cage" around any selected stock so the subscriber can see how close the stock is to hitting its **Take-Profit**, its ratcheted **Chandelier Trailing Stop**, or its **14-Day Time Barrier**.

### 5.2 Plotly Specification (`go.Figure` Candlestick + Barrier Overlays)
* **Input Contract:**
  * `ohlcv_df: pd.DataFrame` (trailing 60 trading bars from `ParquetMarketDataRepository`)
  * `position: TripleBarrierPositionSchema`
* **Visual Layers:**
  1. **OHLC Candlesticks:** Increasing candles in `#10B981`, decreasing candles in `#EF4444`, plotted over the trailing 60 trading sessions.
  2. **20-Day SMA Trend Line:** Thin `#6366F1` line (`SMA_20`) showing short-term trend support.
  3. **Upper Barrier Line (Take-Profit Target):** Horizontal dashed `#10B981` line at `y = position.take_profit_price` labeled `"🎯 TAKE PROFIT (+3R): ${take_profit_price:.2f}"`.
  4. **Entry Reference Line:** Horizontal solid `#06B6D4` line at `y = position.entry_price` labeled `"ENTRY: ${entry_price:.2f}"`.
  5. **Active Ratcheted Stop-Loss Line (Lower Barrier):** Horizontal solid `#EF4444` line at `y = position.trailing_stop_price` labeled `"🛡️ ACTIVE STOP (Chandelier): ${trailing_stop_price:.2f}"`.
  6. **Initial Stop Ghost Line (if stop has ratcheted up):** Dotted `#9CA3AF` line at `y = position.initial_stop_price` labeled `"Initial Stop: ${initial_stop_price:.2f} (Locked +{locked_r:.2f}R)"`—visually proving to the subscriber that the algorithm has automatically raised their floor to protect gains.
  7. **Reward vs. Risk Shaded Box:**
     * Translucent green rectangle (`rgba(16, 185, 129, 0.07)`) spanning from `entry_price` to `take_profit_price`.
     * Translucent red rectangle (`rgba(239, 68, 68, 0.08)`) spanning from `trailing_stop_price` to `entry_price`.
  8. **Vertical Barrier Badge (Top-Right Chart Title):** `"⏱️ Time Barrier: Day {position.bars_held} of {position.max_holding_bars} ({remaining_days} Trading Days Left)"`.
* **Layout Dimensions:** `height=440`, `xaxis_rangeslider_visible=False`, dark gridlines (`#1F2937`), `paper_bgcolor="#111827"`, `plot_bgcolor="#0B0F19"`.

---

## 6. Core Dashboard 5 — Track Record & R-Multiple Distribution (`build_performance_charts`)

### 6.1 Cumulative Equity Curve (`build_equity_curve_chart`)
* Plots chronological cumulative equity starting from `$100,000.00` across all `closed_trades_audit` events (`go.Scatter` with `fill="tozeroy"`, line color `#06B6D4`, fill `rgba(6, 182, 212, 0.12)`).
* Overlays high-water mark dotted line (`#10B981`) to visualize drawdown containment.

### 6.2 Realized R-Multiple Distribution (`build_r_distribution_chart`)
* Bar chart (`go.Bar`) of `trade.realized_r_multiple` for each closed trade:
  * Trades with `realized_r_multiple >= 0` colored `#10B981` (`SEMANTIC_EMERALD`).
  * Trades with `realized_r_multiple < 0` colored `#EF4444` (`SEMANTIC_CRIMSON`).
* Visually demonstrates Jim Simons & López de Prado’s asymmetric payoff profile: small, capped `-1.0R` losses vs. large `+2.0R` to `+3.0R` winners.