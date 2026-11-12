# Step A.3: Technical Stack Selection Document (TSSD)

## 1. Core Runtime & Environment
* **Language & Execution Environment:** **Python 3.11+**
  * Selected for optimal asynchronous runtime performance, enhanced type hinting capabilities, and low-overhead execution within CI/CD pipelines.
* **Environment & Package Management:** `pip` with `requirements.txt` / `pyproject.toml`
  * Strict dependency pinning to ensure deterministic builds within GitHub Actions runners and cloud container environments.

## 2. Data Processing & Data Abstraction Layer
* **Vectorized Calculations & Time-Series Processing:** `pandas` (v2.x) & `numpy`
  * High-performance processing of daily OHLCV datasets, moving averages, trend metrics, and dynamic ATR volatility windows.
* **Market Data Ingestion:** `yfinance` (encapsulated under an abstract interface)
  * Implemented behind a repository pattern (`DataFetcher` interface) to decouple external market data API calls from the quant engine core, facilitating frictionless switching to enterprise providers (FMP, Polygon.io, IBKR) in future iterations.

## 3. Data Validation & Schema Enforcement
* **Strict Type Safety & Contracts:** `pydantic` (v2.x)
  * Enforces strongly typed data structures across the system pipeline:
    * Signal Candidate Schemas (Trigger price, Stop-Loss, Take-Profit).
    * Portfolio State & Virtual Ledger Schemas (`virtual_portfolio.json`).
    * Dynamic Index Configuration Schemas.

## 4. Backtest Engine Harness
* **Per-Asset Validation Engine:** Lightweight Custom Event Vectorized Harness / Modular Engine
  * Optimized for rapid execution (< 15-minute SLA overall runtime).
  * Executes per-asset historical evaluation (12–24 months lookback) to compute Expected Value ($\text{EV} > 0$), Win Rate, and Maximum Drawdown before confirming signal generation.

## 5. Dispatch Engine & Testing Framework
* **Alert & Report Dispatch:** `python-telegram-bot` / `httpx`
  * Asynchronous delivery of daily screening summaries, virtual ledger executions, and portfolio adjustment signals to designated Telegram channels.
* **Testing & Quality Assurance:** `pytest` & `pytest-cov`
  * Comprehensive suite of unit and integration tests enforcing hard risk-limit validation, calculation precision, and schema integrity.

## 6. Future-Proofing Architecture (Mobile App & Cloud Migration Specs)
* **RESTful API Framework:** `fastapi`
  * Modular design ready to expose headless engine endpoints to future mobile and web frontends.
* **Identity & Authentication:** `passlib[bcrypt]` / `Argon2` & `PyJWT`
  * Built-in security architecture supporting user credential hashing and stateless OAuth2 / JWT session management.
* **Cloud Persistence Layer:** `SQLAlchemy` (v2.x) / `supabase-py`
  * Seamless evolution path from local JSON state to managed relational databases (PostgreSQL via Supabase or Neon).

---

## Technical Stack Summary Matrix

| Domain | Technology / Library | Architectural Role |
| :--- | :--- | :--- |
| **Runtime** | Python 3.11+ | Headless Engine Execution Base |
| **Data Engine** | `pandas`, `numpy` | Vectorized Technical & Indicator Computation |
| **Validation** | `pydantic` v2 | Schema Contracts & Data Integrity |
| **Market Data** | `yfinance` (Abstracted) | Market Ingestion Layer |
| **Dispatch** | `python-telegram-bot` | Outbound Signal Notification |
| **Testing** | `pytest` | Automated CI Verification Suite |
| **Future API** | `fastapi` | Headless REST Gateway |
| **Future Auth** | `PyJWT`, `bcrypt` | Token Auth & User Credential Hashing |
| **Future DB** | PostgreSQL / Supabase | Relational Cloud State Management |