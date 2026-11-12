# Step B.1: Screening & Momentum Algorithm Design

## 1. Overview & Operational Pipeline

The Screening & Momentum Engine acts as the primary signal discovery module of the Swing Quant Engine. It operates as an automated, multi-tiered quantitative filter that ingests full constituent rosters from dynamically registered benchmark indices, filters out ineligible or redundant assets, evaluates trend and momentum indicators through index-tailored pipelines, and scores candidates to identify high-probability swing trading opportunities.

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
|                    Liquidity & Volatility Gateways                    |
|             (Price > $5, ADV > 500k, Bid-Ask Spread Cap)              |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                 Tailored Index Calculation Pipelines                  |
|          (Index-specific SMA, ATR Multiples & Momentum Rules)         |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                   Multi-Factor Scoring & Ranking Model                |
|           Composite Score = w1(Momentum) + w2(Volume) + w3(RS)        |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                     Top N Candidates to Backtest                      |
+-----------------------------------------------------------------------+
```

---

## 2. Pre-Filtering & Portfolio Exclusion Gate

To maximize computational efficiency and avoid processing assets to which the strategy is already exposed, the engine executes a strict pre-filtering mechanism prior to indicator calculation:

1. **Portfolio State Ingestion:** Reads the current active positions from the virtual ledger (`virtual_portfolio.json` or relational DB).
2. **Dynamic Symbol Exclusion:** Any asset symbol ($Symbol \in \text{Portfolio}$) is instantly skipped during the ingestion phase.
3. **Resource Optimization:** Bypasses external API data requests, feature engineering, and scoring computations for existing holdings, preserving bandwidth and processing quotas.

---

## 3. Liquidity & Volatility Gateways

Before technical indicators are calculated, all remaining candidate assets must pass hard liquidity and volatility constraints to ensure execution quality and mitigate slippage:

* **Minimum Asset Price ($P_{\text{close}}$):**
  $$P_{\text{close}} \ge \$5.00$$
  *Filters out micro-cap / penny stocks subject to extreme manipulation and illiquidity.*

* **Average Daily Volume ($\text{ADV}_{30}$):**
  $$\text{ADV}_{30} = \frac{1}{30} \sum_{i=1}^{30} \text{Volume}_i \ge 500,000 \text{ shares/day}$$
  *Ensures institutional depth and order execution without significant market impact.*

* **Bid-Ask Spread Gateway:**
  $$\text{Spread}_{\text{relative}} = \frac{P_{\text{Ask}} - P_{\text{Bid}}}{P_{\text{Mid}}} \le \text{Threshold}_{\text{Index}}$$
  *Applies dynamic bid-ask tolerance depending on the index tier.*

---

## 4. Tailored Index Calculation Pipelines (Strategy Registry Pattern)

Acknowledging that different market indices represent distinct market capitalization profiles, volatility dynamics, and liquidity regimes, the engine applies index-tailored parameter configurations rather than a one-size-fits-all model:

### A. Small-Cap Pipeline (e.g., Russell 2000)
* **Volatility Regime:** Higher inherent ATR volatility.
* **Trend Filter:** $P_{\text{close}} > \text{SMA}_{200}$ and $P_{\text{close}} > \text{SMA}_{50}$.
* **Momentum Trigger:** 20-day high breakout with strong volume confirmation ($\text{Volume}_{\text{today}} \ge 1.8 \times \text{Volume}_{\text{SMA20}}$).
* **Relative Strength Threshold:** Requires higher relative strength vs. index benchmark to filter out speculative noise.

### B. Mid-Cap Pipeline (e.g., S&P MidCap 400)
* **Volatility Regime:** Moderate ATR volatility.
* **Trend Filter:** $P_{\text{close}} > \text{SMA}_{200}$ and $\text{SMA}_{20} > \text{SMA}_{50}$.
* **Momentum Trigger:** Pullback consolidation within an established uptrend or 15-day high breakout with moderate volume confirmation ($\text{Volume}_{\text{today}} \ge 1.4 \times \text{Volume}_{\text{SMA20}}$).

### C. Large-Cap Pipeline (e.g., S&P 500 / Nasdaq 100)
* **Volatility Regime:** Lower ATR volatility, higher institutional sponsorship.
* **Trend Filter:** $P_{\text{close}} > \text{SMA}_{200}$.
* **Momentum Trigger:** Mean-reversion or momentum continuation setup with lower volume expansion requirements ($\text{Volume}_{\text{today}} \ge 1.2 \times \text{Volume}_{\text{SMA20}}$).

---

## 5. Quantitative Scoring & Ranking Model

Shortlisted assets passing all gatekeeping rules are evaluated via a composite scoring function to rank candidates deterministically.

### Scoring Formula:
$$\text{Score} = w_1 \cdot M_{\text{rank}} + w_2 \cdot V_{\text{surge}} + w_3 \cdot RS_{\text{index}}$$

Where:
* **$M_{\text{rank}}$ (Momentum Metric):** Normalized rate of change (ROC) over 10-day and 20-day lookback windows.
  $$M_{\text{rank}} = \frac{P_{\text{close}} - P_{\text{close, -20}}}{P_{\text{close, -20}}}$$
* **$V_{\text{surge}}$ (Volume Confirmation Ratio):**
  $$V_{\text{surge}} = \frac{\text{Volume}_{\text{today}}}{\text{SMA}_{20}(\text{Volume})}$$
* **$RS_{\text{index}}$ (Relative Strength vs. Benchmark):** Ratio of asset performance relative to its respective benchmark index over a 60-day window.
* **Weights ($w_1, w_2, w_3$):** Configurable weighting vectors defined per index configuration in the strategy registry (default: $w_1 = 0.4, w_2 = 0.35, w_3 = 0.25$).

---

## 6. Output & Hand-off to Backtest Engine

The top-ranked candidates (e.g., Top $N = 10$) are outputted as structured `CandidateSignal` objects via Pydantic schemas and forwarded directly to the **Per-Asset Backtest Harness (Step B.2 & B.3)** for trade expectancy verification ($\text{EV} > 0$) prior to order creation.