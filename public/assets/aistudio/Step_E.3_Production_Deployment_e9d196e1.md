# Step E.3: Production Deployment & Operational Runbook

## 1. Architectural Overview & Live Zero-Override Operations

This specification defines the production cutover procedure, operational monitoring protocols, emergency circuit breakers, and Phase 2 cloud scaling blueprint for the **Swing Quant Engine**. Engineered in strict compliance with **Jim Simons' Zero-Override Policy** (*Renaissance Technologies*) and **Dr. Marcos López de Prado's** institutional production standards (*Advances in Financial Machine Learning*), the deployed system operates as a deterministic, self-healing End-of-Day (EOD) quantitative worker.

```
+-------------------------------------------------------------------------+
|                   PHASE 1: SERVERLESS GITHUB PRODUCTION                 |
|  - Trigger: Mon-Fri 21:45 UTC Cron (`daily_quant_pipeline.yml`)         |
|  - Pre-Flight Gate: `ruff` + `pytest` (Suite 1-5 Invariants)            |
|  - Data Layer: 500d Smart Sliding Window Parquet Cache + Split Guard    |
|  - State Layer: Atomic POSIX JSON Ledger (`virtual_portfolio.json`)     |
|  - Telemetry: HTML Executive Dispatch & Dead-Man's Switch -> Telegram   |
+-------------------------------------------------------------------------+
                                    |
                                    | (Zero-Refactoring Repository Swap)
                                    v
+-------------------------------------------------------------------------+
|               PHASE 2: MULTI-TENANT CLOUD SAAS PRODUCTION               |
|  - Storage: Supabase / PostgreSQL with Row-Level Security (RLS)         |
|  - Auth & API: FastAPI + Argon2/PBKDF2 + Stateless HS256 JWT (`sub`)    |
|  - Client UI: Next.js / Flutter Mobile Dashboard (Isolated per Tenant)  |
+-------------------------------------------------------------------------+
```

---

## 2. Production Cutover Checklist (First-Time Go-Live)

Execute the following deterministic sequence to transition the repository from staging/sandbox into live autonomous production:

### Step 1: Repository Directory & Roster Initialization
Verify that the repository root contains the locked directory structure and constituent CSV rosters (`ticker` column header):
* `config/index_registry.json` (Active pipelines: `RUT_2000`, `SP_400`; pre-configured: `SP_500`).
* `config/constituents/RUT_2000.csv` and `config/constituents/SP_400.csv`.

### Step 2: Encrypted Vault Provisioning (GitHub Secrets)
Navigate to **GitHub Repository** $\rightarrow$ **Settings** $\rightarrow$ **Secrets and variables** $\rightarrow$ **Actions** and provision:
1. `TELEGRAM_BOT_TOKEN`: Production HTTP token issued by `@BotFather`.
2. `TELEGRAM_CHAT_ID`: Target production Telegram channel or group ID.
3. `JWT_SECRET_KEY`: 64-character cryptographic hex key generated via:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

### Step 3: Workflow Write Permissions & Branch Protection
1. Navigate to **Settings** $\rightarrow$ **Actions** $\rightarrow$ **General** $\rightarrow$ **Workflow permissions**.
2. Select **Read and write permissions** so `github-actions[bot]` is authorized to push atomic EOD state commits (`[skip ci]`).

### Step 4: Cold-Start Hydration & Sandbox Acceptance Gate
1. Trigger a manual Sandbox Dry Run via **Actions** $\rightarrow$ **Autonomous Swing Quant Engine (EOD Pipeline)** $\rightarrow$ **Run workflow** with `dry_run = true`.
2. Confirm that:
   * All `pytest` suites pass (`0` failures).
   * The 500-day Parquet cache (`data/cache/market_data_window.parquet`) is hydrated and saved in GitHub Actions Cache.
   * The `🧪 SANDBOX DRY-RUN` report arrives on Telegram.
3. Trigger the initial live production run with `dry_run = false` to initialize `data/state/virtual_portfolio.json` (`$100,000.00` initial equity) and activate the `21:45 UTC` weekday schedule.

---

## 3. Silent-Failure Prevention & Operational Telemetry

1. **GitHub Cron Keep-Alive Guarantee:**
   GitHub Actions automatically suspends scheduled workflows if a repository receives no commits for 60 consecutive days. Because `daily_quant_pipeline.yml` updates `last_updated_utc` and commits `virtual_portfolio.json` after every market session, the repository remains continuously active without manual intervention.
2. **Daily Dead-Man's Switch (EOD Heartbeat):**
   Even on flat market days when zero Triple-Barrier exits occur and zero new candidates pass the Meta-Labeling gate ($\phi_{\text{meta}} = 0.0$), `TelegramDispatchService` dispatches the daily Executive Portfolio Telemetry summary. If no Telegram report arrives by `22:05 UTC` on a US trading day, the operator knows immediately to inspect the runner logs.
3. **Portfolio Heat & Capacity Telemetry:**
   Every daily report explicitly logs current **Portfolio Heat** ($H_{\text{portfolio}} = \frac{1}{E_{\text{total}}} \sum \text{OpenRisk}_i \le 6.00\%$) and active slot utilization ($N_{\text{open}} \le 10$).

---

## 4. Emergency Kill-Switch & Point-in-Time Rollback Runbook

### A. Immediate Trading Halt (Zero-Code Kill-Switch)
If an upstream data vendor outage occurs (e.g., corrupted Yahoo Finance feeds across multiple indices), halt execution immediately via either method:
* **Method 1 (GitHub UI):** Navigate to **Actions** $\rightarrow$ **Autonomous Swing Quant Engine** $\rightarrow$ click the **`...`** menu $\rightarrow$ **Disable workflow**.
* **Method 2 (Index Registry Freeze):** Set `"is_active": false` for affected indices in `config/index_registry.json`. Existing open positions will still be reconciled against their Triple-Barrier exits, while new candidate entries are paused.

### B. Deterministic Point-in-Time State Rollback
Because every EOD portfolio mutation is recorded as an atomic Git commit (`chore(state): automated EOD portfolio ledger sync (YYYY-MM-DD) [skip ci]`), rolling back a corrupted session to the exact prior day's state requires a single command:

```bash
# View recent EOD state commits
git log --oneline -n 5 data/state/virtual_portfolio.json

# Revert the specific corrupted state commit and push atomically
git revert --no-edit <CORRUPTED_COMMIT_SHA>
git push origin main
```

---

## 5. Phase 2 Production Scaling Blueprint (PostgreSQL RLS & FastAPI Adapter)

When transitioning from Phase 1 (`virtual_portfolio.json`) to Phase 2 (Multi-User Web/Mobile Application backed by **Supabase / PostgreSQL**), the core quant modules (`schemas.py`, `data_ingestion.py`, `quant_engine.py`, `notifier.py`) require **zero modifications**.

Only the storage adapter is swapped by binding `PostgresMultiTenantRepository` to the SQL schema and **Row-Level Security (RLS)** policies defined in Step B.3:

```python
from contextlib import contextmanager
from typing import Iterator
from uuid import UUID
import psycopg

from schemas import JWTTokenPayload, VirtualPortfolioLedgerSchema
from security import MultiTenantSecurityService


class PostgresMultiTenantRepository:
    """
    Phase 2 Drop-in Relational Storage Adapter for Supabase / PostgreSQL.
    Binds the authenticated user's JWT `sub` claim directly into the PostgreSQL
    transaction context (`request.jwt.claim.sub`) so Row-Level Security (RLS)
    physically prevents cross-tenant data access at the database engine level.
    """

    def __init__(self, database_url: str, security_service: MultiTenantSecurityService) -> None:
        self.database_url = database_url
        self.security_service = security_service

    @contextmanager
    def tenant_scoped_transaction(self, jwt_token: str) -> Iterator[psycopg.Cursor]:
        """
        Verifies the user's JWT cryptographic signature and opens a PostgreSQL
        transaction scoped strictly to `token_payload.sub` via RLS session variables.
        """
        payload: JWTTokenPayload = self.security_service.verify_jwt(jwt_token)

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                # Bind authenticated user_id to local transaction scope for PostgreSQL RLS
                cur.execute(
                    "SELECT set_config('request.jwt.claim.sub', %s, true);",
                    (str(payload.sub),),
                )
                yield cur
            conn.commit()
```

---

## 6. Master Engineering Documentation Index (Repository `docs/` Manifest)

| Phase | Step | Document Filename | Primary Engineering Scope |
| :--- | :--- | :--- | :--- |
| **Phase A** | **A.1** | `BRD.md` | Business Requirements, Multi-Index Scope & Zero-Override Mandate |
| **Phase A** | **A.2** | `DSRD.md` | Data Hygiene, 250d/500d Windows, Liquidity Gates & 15-Min SLA |
| **Phase A** | **A.3** | `TSSD.md` | Technical Stack Selection (`Python 3.11`, `Pydantic v2`, `Parquet`, `GitHub Actions`) |
| **Phase B** | **B.1** | `Screening_Logic.md` | Volatility-Adjusted Momentum, Index Pipelines & Portfolio Exclusion |
| **Phase B** | **B.2** | `Risk_Management_Model.md` | Wilder's $\text{ATR}_{14}$, Triple-Barrier Cage, Meta-Labeling & $6\%$ Heat Cap |
| **Phase B** | **B.3** | `Data_Schemas_Spec.md` | Pydantic v2 Contracts, Multi-Tenant SQL Schema & PostgreSQL RLS |
| **Phase C** | **C.1** | `Data_Ingestion_Pipeline.md` | `src/data_ingestion.py` — Smart Sliding Window & $t-1$ Split Guard |
| **Phase C** | **C.2** | `Quant_Engine_Implementation.md` | `src/quant_engine.py` — Vectorized Features, 500d Backtester & Portfolio Manager |
| **Phase C** | **C.3** | `Unit_Testing_Spec.md` | `tests/test_quant_engine.py` — Deterministic `pytest` Invariant Suite |
| **Phase D** | **D.1** | `Environment_Setup_Spec.md` | `requirements.txt`, `pyproject.toml`, `src/storage.py` & `src/main.py` |
| **Phase D** | **D.2** | `GitHub_Actions_Pipeline_Spec.md` | `.github/workflows/daily_quant_pipeline.yml` — Automated EOD CI/CD Runner |
| **Phase D** | **D.3** | `Security_And_Secrets_Spec.md` | `src/config.py` & `src/security.py` — `SecretStr`, Log Redaction & JWT/RBAC |
| **Phase E** | **E.1** | `Telegram_Dispatch_Spec.md` | `src/notifier.py` — Resilient HTML Telemetry & Rate-Limit Chunking |
| **Phase E** | **E.2** | `Sandbox_Dry_Run_Spec.md` | `src/sandbox_runner.py` — 5-Day Lifecycle Stress Test & 500d Walk-Forward Gate |
| **Phase E** | **E.3** | `Production_Deployment_Runbook.md` | Go-Live Cutover Checklist, Kill-Switch Runbook & Phase 2 Cloud DB Adapter |