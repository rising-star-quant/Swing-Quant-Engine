# Autonomous Swing Quant Engine

An institutional-grade, headless quantitative swing trading engine engineered on the mathematical frameworks of **Dr. Marcos López de Prado** (*Advances in Financial Machine Learning*) and **Jim Simons** (*Renaissance Technologies*).

---

## 1. Executive Architecture Overview

The **Swing Quant Engine** operates as a zero-touch End-of-Day (EOD) computational pipeline that scans multi-index equity universes (`RUT` Russell 2000 Small-Cap and `MID` S&P MidCap 400), filters out illiquid instruments and existing holdings, evaluates stationary volatility-normalized momentum features, validates candidates via a 500-day Point-in-Time (PiT) Walk-Forward Backtest gate, and manages active positions inside a **Triple-Barrier Cage** with **Chandelier Ratchet** trailing stops.

```
+-------------------------------------------------------------------------+
|               1. Smart Sliding Window Ingestion (src/data_ingestion.py) |
|  - 500-Bar Apache Parquet Cache + 2-Day Incremental Delta Sync          |
|  - Pre-Ingestion Portfolio Exclusion + t-1 Overlap Split/Dividend Guard |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|               2. Vectorized Feature & Screening (src/quant_engine.py)   |
|  - Simons Liquidity Gates: Price >= $5.00, ADV_30 >= 500,000 shares     |
|  - Wilder's ATR_14, Volatility-Adjusted Momentum, Volume Z-Score & RS   |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|               3. 500-Day Walk-Forward Meta-Labeler (src/quant_engine.py)|
|  - Point-in-Time Per-Asset Simulation under Exact Index Barrier Rules   |
|  - Computes Empirical EV_R & Meta-Conviction Scalar (phi_meta in 0..1.25)|
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|               4. Triple-Barrier Portfolio Manager (src/quant_engine.py) |
|  - Evaluates Lower (Ratchet SL), Upper (TP), & Vertical (14d) Barriers  |
|  - Enforces Ratchet-Only Invariant (Stop_t >= Stop_{t-1}) & 6% Heat Cap |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|               5. Atomic POSIX Storage & Telegram HTML Dispatch          |
|  - Crash-Safe os.replace() JSON Ledger + Multi-Tenant HTML Telemetry    |
+-------------------------------------------------------------------------+
```

---

## 2. Mathematical Foundations

### A. Stationary Volatility-Adjusted Momentum ($M_{\text{vol\_adj}}$)
Raw price rates of change bias rankings toward high-beta noise. Following López de Prado, 20-day price appreciation is normalized by Wilder's $\text{ATR}_{14}$:

$$M_{\text{vol\_adj}, i, t} = \frac{P_{\text{close}, i, t} - P_{\text{close}, i, t-20}}{\text{ATR}_{14, i, t} \times \sqrt{20}}$$

### B. Corporate Action $t-1$ Overlap Guard ($\epsilon_{i, t-1}$)
During daily 2-bar delta synchronization ($\{t-1, t\}$), the engine verifies continuity against cached $t-1$ adjusted closes:

$$\epsilon_{i, t-1} = \frac{\left\vert C_{i, t-1}^{\text{delta}} - C_{i, t-1}^{\text{cache}} \right\vert}{C_{i, t-1}^{\text{cache}}} > 10^{-4} \implies \text{Full 500-Day Re-Hydration}$$

### C. Triple-Barrier & Chandelier Ratchet Stop Invariant
For an active long position entered at $P_{\text{entry}}$ with index multipliers $(k_{\text{stop}}, k_{\text{profit}}, T_{\max}=14)$:
* **Initial Stop Barrier:** $\text{Stop}_0 = P_{\text{entry}} - k_{\text{stop}} \cdot \text{ATR}_{14, 0}$
* **Upper Take-Profit Barrier:** $\text{Target}_0 = P_{\text{entry}} + k_{\text{profit}} \cdot \text{ATR}_{14, 0}$ (enforcing $k_{\text{profit}} \ge 2.0 \cdot k_{\text{stop}}$)
* **Ratchet-Only Chandelier Update:**
  $$\text{Stop}_t = \max\left( \text{Stop}_{t-1}, \; \max_{\tau \in [0, t]} H_\tau - k_{\text{stop}} \cdot \text{ATR}_{14, t} \right)$$

### D. Volatility-Parity Position Sizing & 6.0% Portfolio Heat Cap
Share allocation scales base risk ($1.0\%$ of total equity) by the Meta-Labeling conviction scalar $\phi_{\text{meta}} \in [0.0, 1.25]$ while strictly enforcing:

$$H_{\text{portfolio}} = \frac{1}{E_{\text{total}}} \sum_{k=1}^{N_{\text{open}}} \max\left(0, \; P_{\text{entry}, k} - \text{Stop}_{t, k}\right) \times \text{Shares}_k \le 6.00\%$$

---

## 3. Quick-Start CLI Commands

```bash
# 1. Bootstrap the repository structure and seed ledger
python3 bootstrap_repo.py

# 2. Create a Python 3.11+ virtual environment and install pinned dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Run the deterministic Pytest mathematical verification suite
pytest

# 4. Run the End-to-End 5-Day Lifecycle & 500-Day Walk-Forward Sandbox Dry-Run
python3 src/main.py --dry-run --user-id default

# 5. Execute a live EOD cycle for a specific settlement date
python3 src/main.py --as-of-date 2026-11-11 --user-id default
```

---

## 4. GitHub Actions Encrypted Secrets Setup

Configure the following secrets under **Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**:

| Secret Name | Required | Description | Generation / Source |
| :--- | :---: | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Yes | HTTP Bot API Token for outbound HTML telemetry | Issued by `@BotFather` on Telegram |
| `TELEGRAM_CHAT_ID` | Yes | Target numeric Chat ID or channel identifier | Retrieved via `/getUpdates` |
| `JWT_SECRET_KEY` | Yes | 64-character hex signing key for HS256 JWTs | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Phase 2 | PostgreSQL / Supabase connection URI | Supabase Project Settings $\rightarrow$ Database |

---

## 5. Phase 2 Supabase / PostgreSQL Migration Guide

The storage layer (`src/storage.py`) implements the Repository Pattern (`BasePortfolioRepository`). Transitioning from Phase 1 (`JsonFilePortfolioRepository`) to Phase 2 (`PostgresPortfolioRepository`) requires zero changes to `src/quant_engine.py`, `src/data_ingestion.py`, or `src/schemas.py`:

1. Provision a PostgreSQL 15+ instance (e.g., Supabase or Neon) and execute `POSTGRES_RLS_DDL_SQL` from `src/storage.py` to create the tenant-scoped tables and enable **Row-Level Security (RLS)**.
2. Set `DATABASE_URL` in your environment variables.
3. Instantiate `PostgresPortfolioRepository(database_url=..., tenant_user_id=...)` which binds `SELECT set_config('request.jwt.claim.sub', '<user_uuid>', true);` on every transaction so cross-tenant reads or writes are physically blocked at the database engine level.
