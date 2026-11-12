# Step A.2: Data & System Requirements Document (DSRD)

## 1. Data Ingestion & Provider Architecture

* **Market Data Provider:** 
  * Baseline integration utilizing the `yfinance` API for daily OHLCV (Open, High, Low, Close, Volume) data ingestion.
  * Encapsulated behind a modular Data Abstraction Layer to allow seamless future migration to enterprise APIs (e.g., Financial Modeling Prep, Polygon.io, or Interactive Brokers API) without refactoring core engine logic.

* **Dynamic Index Registry & Strategy Pipelines:**
  * **Dynamic Index Registry:** Configuration-driven registry pattern allowing users to dynamically register, suspend, or add benchmark indices (e.g., Russell 2000, S&P MidCap 400, S&P 500, Nasdaq 100) without modifying core engine source code.
  * **Tailored Calculation Pipelines:** Custom calculation strategy pipelines per index, catering to distinct volatility profiles, structural complexities, and liquidity constraints:
    * Index-specific volatility thresholds and dynamic ATR multiples.
    * Tiered volume (ADV) and Bid-Ask spread gatekeeping rules per index.
    * Index-tailored momentum screening logic where applicable.

* **Resilience & Rate Limiting:**
  * Asynchronous and batched requests with exponential backoff and randomized retry strategies to protect against rate-limiting and IP throttling.

## 2. Data Depth & Temporal Granularity

* **Timeframe Resolution:** Daily historical bars exclusively (`1d` granularity), optimized for 3–14 day swing trading horizons.

* **Operational Screening Lookback:** **250 trading days (~1 calendar year)** of historical price action per ticker for calculating long-term moving averages (SMA200), ATR volatility metrics, and trend momentum indicators.

* **Per-Asset Backtest Window:** **500 trading days (~2 calendar years)** of deep lookback for shortlisted candidates to validate historic strategy expectancy and risk profiles prior to signal confirmation.

## 3. Headless Engine Architecture

* **Decoupled Headless Design:** 
  * The computational core, screening modules, backtest engine, and virtual ledger runtime operate as a fully decoupled **Headless Backend Worker**.
  * Complete isolation from presentation layers, outputting signals and state via structured communication interfaces (Telegram API for MVP; RESTful API / GraphQL layer for future mobile/web clients).

## 4. Virtual Ledger & State Persistence Evolution

* **Storage & Persistence Lifecycle:**
  * **Phase 1 (MVP Sandbox):** Local state persistence using a strictly typed, schema-validated JSON store (`virtual_portfolio.json`) tracked under Git version control and updated automatically post-market close.
  * **Phase 2 (Production & Mobile Expansion):** Seamless migration path to a managed Relational Cloud Database (e.g., PostgreSQL via Supabase or Neon) supporting multi-user state isolation, audit logs, and real-time transaction history.

## 5. Identity, Authentication & Security Infrastructure

* **User Authentication Framework:**
  * Enterprise-grade identity architecture supporting **Username & Password** authentication utilizing secure cryptographic hashing (`bcrypt` / `Argon2`).

* **Session Management:**
  * Stateless **JWT (JSON Web Tokens)** / OAuth2 token exchange standardizing secure client-server communication between future mobile/web clients and the headless backend API.

* **Role-Based Access Control (RBAC):**
  * Clear authorization boundary separating read-only consumer clients (viewing portfolio state and signals) from administrative system runners (executing daily market scans).

## 6. System Constraints & SLA

* **Execution Environment:** Headless Ubuntu container running within a managed **GitHub Actions Runner**.

* **Runtime SLA Window:** Total end-to-end execution (data ingestion, dynamic index processing, per-asset backtesting, virtual ledger reconciliation, and alert dispatching) must complete in **< 15 minutes**.