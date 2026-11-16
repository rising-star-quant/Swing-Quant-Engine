# Step D.2: GitHub Actions Workflow & EOD Orchestration Specification

## 1. Architectural Overview & Autonomous CI/CD Design

This specification defines the automated End-of-Day (EOD) execution pipeline for the **Swing Quant Engine (SIRIX)**, implemented via `.github/workflows/daily_quant_pipeline.yml`. Engineered under **Jim Simons' Zero-Override Policy** (*Renaissance Technologies*) and **Dr. Marcos López de Prado's** institutional production standards, the pipeline acts as a deterministic, self-healing headless worker that executes daily post-market without manual intervention.

### Key Operational Pillars
1. **Post-Settlement Cron Schedule (`45 21 * * 1-5`):** Triggers automatically Monday through Friday at `21:45 UTC` (`16:45 EST` / `17:45 EDT`), enforcing a mandatory **45-minute settlement buffer** after the `16:00 ET` NYSE/Nasdaq close so upstream data providers finalize official closing prices, volume aggregates, and corporate action adjustments (Splits/Dividends).
2. **NYSE Market Calendar Gate:** Evaluates the US Eastern (`America/New_York`) date against an authoritative NYSE trading calendar prior to data ingestion. Full market holidays short-circuit immediately with exit code `0` and status `SKIPPED_MARKET_CLOSED` in under 15 seconds, performing zero external fetches and zero state mutations.
3. **Strict Concurrency Locking:** Enforces single-instance execution (`concurrency: sirix-eod-prod`, `cancel-in-progress: false`) so manual dispatches and scheduled cron runs can never collide or corrupt persistent state.
4. **Pre-Flight Regression Gate:** Executes `ruff` static analysis and the deterministic `pytest` invariant suite (`tests/test_quant_engine.py`) before any portfolio state evaluation is permitted.
5. **Smart Sliding-Window Caching:** Persists the 500-day historical Parquet market window (`data/cache/market_data_window.parquet`) across runs via `actions/cache@v4`, reducing daily execution time from ~12 minutes to < 45 seconds.
6. **Atomic State Persistence & 60-Day Inactivity Guard:** Commits updated ledger and heartbeat metadata (`virtual_portfolio.json`, `eod_heartbeat.json`) with `[skip ci]` (and syncs to Google Cloud Storage when configured), ensuring atomic reads by the Cloud Run GUI and preventing GitHub's 60-day cron auto-disable rule.

---

## 2. Trigger Configuration & Manual Dispatch Contract

### A. Automated & Manual Triggers
* **Scheduled Cron (`schedule`):**
  * Expression: `'45 21 * * 1-5'` (active exclusively from the default `main` branch).
  * Half-Day / Early-Close Sessions (`13:00 ET` close): Standard `21:45 UTC` trigger remains valid and processes the official session close normally.
* **Controlled Manual Dispatch (`workflow_dispatch`):**
  * Exposes two explicit boolean inputs for sandbox verification, debugging, and recovery:
    * `dry_run` (boolean, default: `'false'`): Executes full ingestion, screening, and risk evaluation and dispatches a `[DRY-RUN]` badged Telegram report, while strictly prohibiting writes to persistent storage (`GCS` / `Git`).
    * `force_run` (boolean, default: `'false'`): Bypasses the NYSE Market Calendar Gate to allow weekend or holiday infrastructure testing.
* **Secondary Cloud Scheduler Failover Hook:**
  * Supports optional external triggering via authenticated HTTP webhook (`POST /api/internal/trigger-eod` protected by OIDC / shared bearer token) for future migration to Google Cloud Scheduler without altering engine logic.

---

## 3. Six-Stage EOD Execution State Machine

Every scheduled or manual workflow execution must progress sequentially through six deterministic stages. Out-of-order execution or stage skipping is strictly prohibited:

| Stage | State Identifier | Responsibilities & Guardrails | Failure / Exit Behavior |
| :--- | :--- | :--- | :--- |
| **1** | `LOCK_ACQUISITION` | Acquires workflow concurrency lock (`sirix-eod-prod`) and initializes Python 3.11 environment with pinned dependencies (`requirements.txt`). | Queues or aborts duplicate triggers cleanly to prevent race conditions. |
| **2** | `PREFLIGHT_VERIFICATION` | Validates required encrypted secrets, executes `ruff` + `pytest` regression gates, and evaluates the NYSE Market Calendar Gate (unless `force_run=true`). | Fails fast on missing secrets or failing unit tests; exits cleanly (`exit 0`, `SKIPPED_MARKET_CLOSED`) on US market holidays. |
| **3** | `DATA_INGESTION_AND_AUDIT` | Restores Parquet sliding-window cache, fetches incremental daily bars, runs $t-1$ overlap Split/Dividend detection, and audits data completeness ($\ge 98\%$ of active index constituents must contain valid $T_0$ close bars). | If $T_0$ close data is incomplete at `21:45 UTC`, enters an automated retry loop (**up to 3 retries with 10-minute backoff**). Aborts with `FAILED_DATA_DELAY` if threshold is not met after retries. |
| **4** | `QUANT_EVALUATION` | Evaluates open positions against Triple-Barrier exit rules (Take-Profit, Ratchet-Only Chandelier Stop-Loss, 14-day Vertical Time Barrier), then screens new candidates using Volatility-Adjusted Momentum and Meta-Labeling sizing. | Any Pydantic v2 contract violation halts execution immediately prior to state mutation. |
| **5** | `ATOMIC_STATE_PERSISTENCE` | Atomically writes updated portfolio ledger (`virtual_portfolio.json`), daily NAV equity snapshot, and EOD telemetry metadata (`last_successful_eod_timestamp`, `eod_status`) to persistent storage (`GCS` and/or atomic Git `[skip ci]` commit). | Uses temp-file write + atomic rename/object overwrite so Cloud Run GUI never reads partial state. Skipped when `dry_run=true`. |
| **6** | `TELEMETRY_AND_HEARTBEAT` | Dispatches formatted HTML execution summary (entries, exits, corporate actions, portfolio heat, and total NAV) to Telegram. | Retries transient HTTP 429/5xx errors with exponential backoff; guarantees daily heartbeat even on zero-trade days. |

---

## 4. Dead-Man's Switch & Failure Alerting Contract

* **Mandatory Daily Heartbeat:** On every valid trading day where Stage 5 completes—including quiet sessions with zero new entries and zero barrier exits—the workflow must dispatch an `EOD Heartbeat` confirmation to Telegram containing: Trading Date ($T_0$), Engine Status (`HEALTHY`), Portfolio Heat (`%`), Open Positions Count, and Total Portfolio Equity (`$`).
* **Critical Failure Alerting:** If any job step fails (non-zero exit code in Stages 2–5), a dedicated `if: failure()` notification step dispatches a high-priority `CRITICAL` alert to Telegram identifying the failed stage and workflow run URL, while leaving the prior day's portfolio state untouched.

---

## 5. GitHub Actions Workflow Specification (`.github/workflows/daily_quant_pipeline.yml`)

```yaml
name: Autonomous Swing Quant Engine (EOD Pipeline)

on:
  schedule:
    # Runs Monday-Friday at 21:45 UTC (45 mins after 16:00 ET NYSE/Nasdaq close)
    - cron: '45 21 * * 1-5'
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Run in non-mutating Sandbox Dry-Run mode (no state commits)'
        required: true
        default: 'false'
        type: choice
        options:
          - 'false'
          - 'true'
      force_run:
        description: 'Bypass NYSE Market Calendar Gate (for weekend/holiday testing)'
        required: true
        default: 'false'
        type: choice
        options:
          - 'false'
          - 'true'

permissions:
  contents: write

concurrency:
  group: sirix-eod-prod
  cancel-in-progress: false

env:
  PYTHON_VERSION: '3.11'
  TZ: 'UTC'

jobs:
  eod-quant-pipeline:
    name: EOD Quantitative Screening & Triple-Barrier Execution
    runs-on: ubuntu-latest
    timeout-minutes: 45

    steps:
      - name: Stage 1 - Checkout Repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 2

      - name: Stage 1 - Set up Python ${{ env.PYTHON_VERSION }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'

      - name: Stage 1 - Install Pinned Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Stage 2 - Pre-Flight Linter & Unit Test Gate
        run: |
          ruff check src tests
          pytest -v --tb=short

      - name: Stage 2 - NYSE Market Calendar Gate
        id: market_gate
        env:
          FORCE_RUN: ${{ github.event.inputs.force_run || 'false' }}
        run: |
          python -m src.main --check-market-calendar

      - name: Stage 3 - Restore 500d Sliding-Window Parquet Cache
        if: steps.market_gate.outputs.is_trading_day == 'true'
        uses: actions/cache@v4
        with:
          path: data/cache
          key: parquet-window-${{ hashFiles('config/index_registry.json', 'config/constituents/*.csv') }}-${{ github.run_id }}
          restore-keys: |
            parquet-window-${{ hashFiles('config/index_registry.json', 'config/constituents/*.csv') }}-
            parquet-window-

      - name: Stages 3-6 - Execute Autonomous EOD Pipeline (With Settlement Retry)
        if: steps.market_gate.outputs.is_trading_day == 'true'
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          JWT_SECRET_KEY: ${{ secrets.JWT_SECRET_KEY }}
          GCS_BUCKET_NAME: ${{ secrets.GCS_BUCKET_NAME }}
          DRY_RUN: ${{ github.event.inputs.dry_run || 'false' }}
        run: |
          python -m src.main --mode eod --retry-attempts 3 --retry-backoff-sec 600

      - name: Stage 5 - Atomic Git State Sync & 60-Day Cron Heartbeat
        if: steps.market_gate.outputs.is_trading_day == 'true' && (github.event.inputs.dry_run || 'false') == 'false'
        run: |
          git config user.name "sirix-quant-bot[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/state/virtual_portfolio.json data/state/eod_heartbeat.json
          if ! git diff --cached --quiet; then
            RUN_DATE=$(date -u +"%Y-%m-%d")
            git commit -m "chore(state): automated EOD portfolio ledger sync (${RUN_DATE}) [skip ci]"
            git push origin HEAD:main
          else
            echo "No ledger state delta detected."
          fi

      - name: Critical Failure Alert Dispatch
        if: failure()
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          python -m src.main --notify-failure --run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

---

## 6. Acceptance Criteria (for AI Studio Implementation)

1. **Automated Weekday Trigger:** Workflow runs automatically at `21:45 UTC` Monday–Friday on `main` without manual intervention.
2. **Holiday Short-Circuit:** On NYSE market holidays (when `force_run=false`), Stage 2 sets `is_trading_day=false`, skipping Stages 3–6 cleanly in < 15 seconds with zero file commits or alerts.
3. **Settlement Delay Resilience:** If upstream closing prices for $T_0$ are incomplete (< 98% coverage) at `21:45 UTC`, the runner executes up to 3 backoff retries (10 minutes apart) before failing safely with `FAILED_DATA_DELAY`.
4. **Zero-Mutation Dry-Run:** Triggering `workflow_dispatch` with `dry_run=true` executes the full quant evaluation and sends a `[DRY-RUN]` Telegram report while skipping Stage 5 persistence completely.
5. **Continuous Cron Health:** Each live run updates `data/state/eod_heartbeat.json` and pushes an atomic `[skip ci]` commit, preventing GitHub's 60-day schedule deactivation and synchronizing the Cloud Run GUI immediately.