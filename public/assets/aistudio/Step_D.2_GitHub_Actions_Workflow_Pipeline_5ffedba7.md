# Step D.2: GitHub Actions Workflow Pipeline Specification

## 1. Architectural Overview & Zero-Override Automation

The **GitHub Actions Workflow Pipeline** (`.github/workflows/daily_quant_pipeline.yml`) operationalizes the **Swing Quant Engine** as a serverless, autonomous End-of-Day (EOD) execution worker. Engineered in strict compliance with **Jim Simons' Zero-Override Policy** (*Renaissance Technologies*) and **Dr. Marcos López de Prado's** operational rigor (*Advances in Financial Machine Learning*), the workflow executes deterministically after US market settlement without human intervention.

### Core Operational Guarantees:

1. **Post-Settlement Market Timing (`21:45 UTC` Mon–Fri):** Triggered 45–105 minutes after the `16:00 ET` NYSE/Nasdaq close, ensuring final closing auction prints and overnight corporate action flags (splits/dividends) have propagated to data vendors.
2. **Pre-Flight Mathematical Gate (`pytest`):** Before any market data is fetched or any portfolio state is touched, the runner executes the complete Step C.3 verification suite. If a single invariant fails, the pipeline halts immediately (`Fail-Fast`).
3. **Rolling Parquet Window Persistence (`actions/cache@v4`):** Preserves the 500-day Apache Parquet sliding window (`data/cache/market_data_window.parquet`) across ephemeral GitHub Actions runners so daily executions only fetch a 2-day delta ($t-1$ and $t$).
4. **Concurrency Locking & Atomic State Commits:** Prevents overlapping runs via a strict `concurrency` group and commits updated multi-tenant portfolio state (`data/state/virtual_portfolio.json`) back to the repository with `[skip ci]` to prevent infinite trigger loops.

```
+-------------------------------------------------------------------------+
|        Trigger: Mon-Fri 21:45 UTC Cron OR Manual workflow_dispatch      |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|         Concurrency Lock: `swing-quant-engine-eod-state-lock`           |
|           (Queues or blocks overlapping runs to prevent races)          |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|         Step 1: Checkout Repository & Restore Locked Python 3.11        |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|         Step 2: Pre-Flight Mathematical Verification (`pytest`)         |
|     [Pass] -> Continue                  [Fail] -> HALT & Alert Admin    |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|         Step 3: Restore 500-Day Parquet Sliding Window Cache            |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|         Step 4: Execute Autonomous Quant Engine (`src/main.py`)         |
|   - 2-Day Delta Sync & Split Guard    - Triple-Barrier EOD Exits        |
|   - Index-Tailored Screening          - Volatility-Parity Allocation    |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|         Step 5: Save Updated Parquet Cache & Atomic Git Commit          |
|         (`chore(state): automated EOD portfolio sync [skip ci]`)        |
+-------------------------------------------------------------------------+
```

---

## 2. Production GitHub Actions Workflow (`.github/workflows/daily_quant_pipeline.yml`)

```yaml
name: Autonomous Swing Quant Engine (EOD Pipeline)

on:
  schedule:
    # Runs at 21:45 UTC Monday through Friday (Post-US Market Settlement)
    - cron: "45 21 * * 1-5"
  workflow_dispatch:
    inputs:
      as_of_date:
        description: "Optional target EOD date (YYYY-MM-DD). Leave blank for today UTC."
        required: false
        default: ""
      dry_run:
        description: "Run pipeline in dry-run mode without committing state changes"
        required: false
        type: boolean
        default: false

# Enforce strict single-instance execution to prevent race conditions on virtual_portfolio.json
concurrency:
  group: swing-quant-engine-eod-state-lock
  cancel-in-progress: false

permissions:
  contents: write  # Required for committing updated virtual_portfolio.json state

env:
  PYTHON_VERSION: "3.11"
  QUANT_ENV: "production"
  LOG_LEVEL: "INFO"
  STATE_STORE_PATH: "data/state/virtual_portfolio.json"
  PARQUET_CACHE_PATH: "data/cache/market_data_window.parquet"
  CONSTITUENTS_DIR: "config/constituents"

jobs:
  execute-quant-cycle:
    name: EOD Screening, Triple-Barrier & Portfolio Sync
    runs-on: ubuntu-latest
    timeout-minutes: 15  # Hard ceiling per Step A.2 DSRD SLA

    steps:
      # -------------------------------------------------------------------
      # 1. REPOSITORY CHECKOUT & PYTHON ENVIRONMENT INITIALIZATION
      # -------------------------------------------------------------------
      - name: Checkout Repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - name: Set Up Python ${{ env.PYTHON_VERSION }} with Pip Cache
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: "pip"
          cache-dependency-path: "requirements.txt"

      - name: Install Locked Production & Verification Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      # -------------------------------------------------------------------
      # 2. PRE-FLIGHT CODE QUALITY & MATHEMATICAL INVARIANT GATE (Step C.3)
      # -------------------------------------------------------------------
      - name: Run Ruff Static Linter Gate
        run: ruff check src/ tests/

      - name: Execute Pre-Flight Pytest Verification Suite
        run: pytest tests/test_quant_engine.py -v --tb=short

      # -------------------------------------------------------------------
      # 3. SMART SLIDING WINDOW PARQUET CACHE RESTORATION (Step C.1)
      # -------------------------------------------------------------------
      - name: Restore 500-Day Rolling Market Data Parquet Cache
        uses: actions/cache@v4
        with:
          path: data/cache
          # Restores the most recent sliding window cache and saves a new key per run
          key: parquet-sliding-window-${{ runner.os }}-${{ github.run_id }}
          restore-keys: |
            parquet-sliding-window-${{ runner.os }}-

      # -------------------------------------------------------------------
      # 4. HEADLESS ZERO-OVERRIDE QUANT ENGINE EXECUTION
      # -------------------------------------------------------------------
      - name: Run Autonomous Swing Quant Engine Cycle
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          CMD="python src/main.py"
          if [ -n "${{ github.event.inputs.as_of_date }}" ]; then
            CMD="$CMD --as-of-date ${{ github.event.inputs.as_of_date }}"
          fi
          if [ "${{ github.event.inputs.dry_run }}" == "true" ]; then
            CMD="$CMD --dry-run"
          fi
          echo "Executing: $CMD"
          $CMD

      # -------------------------------------------------------------------
      # 5. ATOMIC REPOSITORY STATE COMMIT (Phase 1 JSON Ledger Persistence)
      # -------------------------------------------------------------------
      - name: Commit Updated Multi-Tenant Portfolio Ledger
        if: ${{ success() && github.event.inputs.dry_run != 'true' }}
        run: |
          git config --local user.name "github-actions[bot]"
          git config --local user.email "41898282+github-actions[bot]@users.noreply.github.com"

          git add "${{ env.STATE_STORE_PATH }}"

          if git diff --staged --quiet; then
            echo "No portfolio state changes detected for today's session."
          else
            RUN_DATE=$(date -u +"%Y-%m-%d")
            git commit -m "chore(state): automated EOD portfolio ledger sync (${RUN_DATE}) [skip ci]"
            git pull --rebase origin "${GITHUB_REF_NAME}"
            git push origin HEAD:"${GITHUB_REF_NAME}"
            echo "Successfully committed and pushed updated portfolio ledger."
          fi

      # -------------------------------------------------------------------
      # 6. FAILURE TELEMETRY ALERT (Circuit Breaker Notification)
      # -------------------------------------------------------------------
      - name: Dispatch Pipeline Failure Alert to Telegram
        if: ${{ failure() }}
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
            curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
              -d chat_id="${TELEGRAM_CHAT_ID}" \
              -d parse_mode="Markdown" \
              -d text="🚨 *CRITICAL: Swing Quant Engine Pipeline Failed*%0A*Run ID:* \`${{ github.run_id }}\`%0A*Commit:* \`${{ github.sha }}\`%0A*Action Required:* Inspect GitHub Actions logs immediately. Portfolio state was NOT modified." > /dev/null
          fi
```

---

## 3. Operational Resilience & Safeguards

1. **Infinite Loop Prevention (`[skip ci]`):** Every automated commit includes `[skip ci]` in its commit message, ensuring GitHub Actions never triggers a recursive workflow cascade.
2. **Rebase Conflict Protection (`git pull --rebase`):** Before pushing the updated `virtual_portfolio.json`, the step rebases against `origin` so manual documentation or configuration commits pushed during the run never cause a rejected push.
3. **15-Minute Hard SLA Ceiling (`timeout-minutes: 15`):** Prevents hung network sockets from consuming GitHub Actions runner minutes.
4. **Immediate Failure Telemetry (`if: ${{ failure() }}`):** If either `pytest` or the runtime execution fails, the workflow leaves `virtual_portfolio.json` untouched and dispatches an instant alert to Telegram.