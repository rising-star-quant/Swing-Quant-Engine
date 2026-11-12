# Step B.1: Screening & Momentum Algorithm Design (v2 - Quant Gate Compliant)

## 1. Overview & Quantitative Architecture

The Screening & Momentum Engine acts as the **Primary Directional Model** ($Side = +1$) of the Swing Quant Engine, engineered in strict compliance with the frameworks of **Dr. Marcos López de Prado** (*Advances in Financial Machine Learning*) and **Jim Simons** (*Renaissance Technologies*).

Operating as an autonomous, multi-tiered quantitative filter, this module ingests constituent rosters from dynamically registered benchmark indices, eliminates redundant holdings and illiquid instruments, evaluates stationary volatility-normalized momentum features through index-tailored pipelines, and outputs primary directional signals into the **Meta-Labeling & Triple-Barrier Risk Engine (Step B.2)**.

```
+-----------------------------------------------------------------------+
|                         Dynamic Index Registry                        |
|             (Russell 2000, S&P MidCap 400, S&P 500, etc.)             |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                   Portfolio Exclusion Gate (Pre-Filter)               |
|            Excludes tickers currently held in Virtual Portfolio       |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|              Liquidity & Slippage Control Gateways (Simons)           |
|             (Price >= $5, ADV_30 >= 500k, Spread Tolerance)           |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                 Tailored Index Calculation Pipelines                  |
|          (Index-specific SMA Regimes, Volume & Momentum Rules)        |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|          Volatility-Adjusted Scoring & Stationary Ranking Model       |
|       Normalized Score = w1(Vol-Adj Momentum) + w2(Vol) + w3(RS)      |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|      Primary Directional Output (Side = +1) -> Meta-Labeling (B.2)    |
+-----------------------------------------------------------------------+
```

---

## 2. Pre-Filtering & Portfolio Exclusion Gate

To maximize computational efficiency, conserve API quotas, and prevent duplicate exposure to assets already held in the portfolio, the engine executes a deterministic pre-filtering check prior to time-series feature engineering:

1. **Portfolio State Ingestion:** Reads active open positions from the virtual ledger (`virtual_portfolio.json` or cloud relational DB).
2. **Dynamic Symbol Exclusion:** Any constituent ticker currently held in the active portfolio ($\text{Symbol} \in \text{ActivePortfolio}$) is immediately excluded from the daily screening universe.
3. **Zero Redundant Processing:** Bypasses historical OHLCV fetching, indicator calculation, and scoring for existing holdings (which are evaluated separately by the Step B.2 Triple-Barrier EOD reconciliation loop).

---

## 3. Liquidity & Slippage Control Gateways (Simons / Renaissance Standard)

To ensure theoretical signals are executable in live market conditions without adverse market impact or excessive transaction friction, every candidate must pass three hard liquidity gates:

* **Minimum Asset Price ($P_{\text{close}}$):**
  $$P_{\text{close}} \ge \$5.00$$
  *Eliminates micro-cap and penny stocks prone to extreme microstructure noise and wide spreads.*

* **Average Daily Volume ($\text{ADV}_{30}$):**
  $$\text{ADV}_{30} = \frac{1}{30} \sum_{i=1}^{30} \text{Volume}_i \ge 500,000 \text{ shares/day}$$
  *Guarantees sufficient institutional market depth for frictionless swing entries and exits.*

* **Relative Bid-Ask Spread Cap:**
  $$\text{Spread}_{\text{rel}} = \frac{P_{\text{Ask}} - P_{\text{Bid}}}{P_{\text{Mid}}} \le \theta_{\text{spread, Index}}$$
  *Enforces an index-specific maximum slippage threshold.*

---

## 4. Tailored Index Calculation Pipelines (Strategy Registry Pattern)

Acknowledging that benchmark indices exhibit distinct volatility structures, institutional flows, and noise profiles, the engine dynamically routes each ticker through its index-specific calculation strategy:

### A. Small-Cap Pipeline (e.g., Russell 2000)
* **Structural Profile:** High idiosyncratic volatility, wider intraday ranges, higher false-breakout frequency.
* **Macro Trend Filter:** $P_{\text{close}} > \text{SMA}_{200}$ and $P_{\text{close}} > \text{SMA}_{50}$.
* **Primary Directional Trigger:** 20-day high price breakout ($\text{Close}_t \ge \max(\text{High}_{t-1 \dots t-20})$) accompanied by strict institutional volume confirmation ($\text{Volume}_t \ge 1.8 \times \text{SMA}_{20}(\text{Volume})$).
* **Relative Strength Gate:** Must outperform the Russell 2000 benchmark over a 60-day lookback ($RS_{60} > 1.05$).

### B. Mid-Cap Pipeline (e.g., S&P MidCap 400)
* **Structural Profile:** Balanced growth and institutional stability, moderate ATR volatility.
* **Macro Trend Filter:** $P_{\text{close}} > \text{SMA}_{200}$ and $\text{SMA}_{20} > \text{SMA}_{50}$ (confirmed trend alignment).
* **Primary Directional Trigger:** Either a 15-day high breakout or a low-volatility pullback toward $\text{SMA}_{20}$ followed by a bullish expansion bar with volume confirmation ($\text{Volume}_t \ge 1.4 \times \text{SMA}_{20}(\text{Volume})$).

### C. Large-Cap Pipeline (e.g., S&P 500 / Nasdaq 100)
* **Structural Profile:** High liquidity, lower ATR percentage, strong institutional mean-reversion and trend persistence.
* **Macro Trend Filter:** $P_{\text{close}} > \text{SMA}_{200}$.
* **Primary Directional Trigger:** Momentum continuation or volatility-contraction breakout with moderate volume expansion ($\text{Volume}_t \ge 1.2 \times \text{SMA}_{20}(\text{Volume})$).

---

## 5. Volatility-Adjusted Momentum & Stationary Ranking Model (López de Prado Standard)

Raw price rates of change (ROC) are non-stationary and inherently bias rankings toward dangerously volatile assets. Following López de Prado's feature engineering principles, all momentum and volume metrics are **volatility-normalized** (expressed in units of standard deviation or $\text{ATR}_{14}$) to achieve cross-sectional stationarity across indices.

### A. Volatility-Normalized Momentum ($M_{\text{vol\_adj}}$)
Measures the 20-day price appreciation normalized by the asset's daily volatility ($\text{ATR}_{14}$), acting as a short-term Information Ratio / Sharpe proxy:

$$M_{\text{vol\_adj}} = \frac{P_{\text{close}, t} - P_{\text{close}, t-20}}{\text{ATR}_{14, t} \times \sqrt{20}}$$

### B. Standardized Volume Surge ($V_{\text{zscore}}$)
Measures the statistical significance of the breakout volume relative to its 20-day distribution:

$$V_{\text{zscore}} = \frac{\text{Volume}_t - \mu_{\text{Volume}, 20}}{\sigma_{\text{Volume}, 20}}$$

### C. Volatility-Adjusted Relative Strength ($RS_{\text{norm}}$)
Measures the excess return of the asset over its parent benchmark index over 60 trading days, scaled by tracking volatility:

$$RS_{\text{norm}} = \frac{R_{\text{asset}, 60} - R_{\text{index}, 60}}{\sigma_{(R_{\text{asset}} - R_{\text{index}}), 60}}$$

### D. Composite Cross-Sectional Conviction Score ($S_{\text{primary}}$)
Each metric is winsorized and cross-sectionally standardized (Z-score mapped to $[0, 100]$) before computing the weighted composite score:

$$S_{\text{primary}} = w_1 \cdot Z\left(M_{\text{vol\_adj}}\right) + w_2 \cdot Z\left(V_{\text{zscore}}\right) + w_3 \cdot Z\left(RS_{\text{norm}}\right)$$

*(Default Index Registry weights: $w_1 = 0.45$, $w_2 = 0.30$, $w_3 = 0.25$).*

---

## 6. Architectural Bridge to Meta-Labeling (Hand-off to Step B.2)

In strict adherence to López de Prado's **Meta-Labeling** paradigm, Step B.1 and Step B.2 maintain a clear separation of concerns:

1. **Primary Model Role (Step B.1):** Identifies the directional opportunity ($Side = +1$, Long Only) and computes the stationary conviction score $S_{\text{primary}}$ for the Top $N$ candidates (e.g., $N = 10$).
2. **Secondary Meta-Model Role (Step B.2 & Per-Asset Backtest Harness):** 
   * Receives the `CandidateSignal` payload containing $S_{\text{primary}}$ and $\text{ATR}_{14}$.
   * Runs a 500-day historical Triple-Barrier backtest on the specific asset to evaluate historical Expected Value ($\text{EV}$) and Win Rate under identical barrier parameters.
   * Combines $S_{\text{primary}}$ and historical $\text{EV}$ to produce the **Meta-Labeling Conviction Scalar** ($\phi_{\text{meta}} \in [0.0, 1.25]$), which either vetoes false positives ($\phi_{\text{meta}} = 0.0$) or scales the exact share allocation in the Virtual Ledger.