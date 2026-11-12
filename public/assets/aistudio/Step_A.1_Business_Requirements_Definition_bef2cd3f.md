# Step A.1: Business Requirements Document (BRD)

## 1. Scope & Asset Universe
* **Dynamic Multi-Index Support:** The engine must support scanning broad indices such as **Russell 2000** and **Mid-Cap 400**, with architectural flexibility to extend to additional index universes (e.g., S&P 500) via configuration.
* **Strict Liquidity & Spread Filtering:** Automatic exclusion of assets failing minimum Average Daily Volume (ADV) thresholds or presenting wide bid-ask spreads, mitigating slippage risks during live execution.

## 2. Time Horizon & Execution Cadence
* **Holding Horizon:** Targeted for **Swing Trading** with an average holding period of 3 to 14 trading days per position.
* **Execution Cadence:** Fully automated daily execution cycle scheduled immediately post-market close (US session).

## 3. Core Deliverables & Signal Generation
* **Buy Signals:** Daily filtered candidate list featuring:
  * Exact Entry/Trigger Price.
  * Dynamic Volatility-Based Stop-Loss (derived from Average True Range - ATR).
  * Pre-calculated Take-Profit target enforcing a minimum **1:3 Risk/Reward Ratio**.
* **Portfolio Maintenance & Exit Engine:**
  * Continuous tracking and evaluation of active holdings.
  * Generation of Sell/Trim signals for stagnant positions, time-stop breaches, or key structural breakdown levels.
* **Per-Asset Historical Validation (Automated Backtest Gate):**
  * Automated historical backtest execution (12–24 months window) for every candidate passing initial momentum filters.
  * Signals are finalized **only if** the asset demonstrates a positive expected value ($\text{EV} > 0$) and acceptable risk metrics historically.

## 4. Shadow Portfolio & Forward Testing (Virtual Ledger)
* **Mirror State Engine:** The system maintains a **Virtual Ledger** tracking all open and closed positions, operating as a 1:1 mirror of the targeted real-world portfolio.
* **Autonomous Virtual Execution:** All position management events (buy, sell, scale-in, scale-out) are executed automatically within the Virtual Ledger upon signal trigger.
* **Human Execution Bridge:** The user acts as the execution bridge for the live account based on Virtual Ledger actions, enabling real-time **Forward Testing in Production** without unvalidated capital exposure.

## 5. Operational Constraints & Safety Protocols
* **Zero-Touch Automation:** Ingestion, calculation, backtesting, ledger reconciliation, and output generation run end-to-end without human intervention.
* **Risk-First Architecture:** Hard-coded rejection of any signal or position modification that violates predefined volatility parameters or risk limits.