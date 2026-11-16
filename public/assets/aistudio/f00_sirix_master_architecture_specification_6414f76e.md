# F00: SIRIX Master System Architecture Specification

## 1. Executive Summary & Architectural Vision

**SIRIX** is an institutional-grade, autonomous quantitative swing-trading platform built on the core principles of **Jim Simons' Zero-Override Execution** (*Renaissance Technologies*) and **Dr. Marcos López de Prado's** quantitative risk engineering (*Advances in Financial Machine Learning*).

The system is architected as a decoupled, deterministic, **Unified Single-Origin** platform:
1. **Headless Quantitative Batch Worker (EOD Engine):** Executes post-market (`21:45 UTC`, Monday–Friday) via GitHub Actions with an NYSE Market Calendar Gate, evaluating open positions under the Triple-Barrier Method (Ratchet-Only Chandelier Stop-Loss, ATR Take-Profit, 14-day Vertical Time Barrier) and screening new candidates via Volatility-Adjusted Momentum and Meta-Labeling.
2. **Unified Single-Origin Cloud Run Service (API + PWA GUI):** A single Docker container running on **Google Cloud Run** (`Scale-to-Zero`, GCP Free Tier compliant) that serves both the **FastAPI Telemetry & Auth Bridge** (`/api/*`) and the compiled **React/Tailwind Progressive Web App (PWA)** (`/*`) under one domain—eliminating Vercel dependencies, cross-origin (CORS) complexity, and recurring hosting costs.
3. **Shared Cloud Storage Source of Truth (GCS):** Stateless persistence backed by **Google Cloud Storage** (`GCS_BUCKET_NAME`), ensuring zero local container state and atomic synchronization between the nightly batch worker and the user-facing dashboard.

---

## 2. Unified Single-Origin Topology (No Vercel / Zero-Cost Tier)

```
+-----------------------------------------------------------------------------+
|                     GITHUB ACTIONS EOD BATCH WORKER                         |
|  - Trigger: Mon-Fri 21:45 UTC (`daily_quant_pipeline.yml`)                  |
|  - Gate: NYSE Market Calendar (`SKIPPED_MARKET_CLOSED` on US holidays)      |
|  - Engine: 500d Parquet Cache + Split Guard + Triple-Barrier + Meta-Label   |
|  - Output: Atomic JSON/Parquet State Push -> GCS & Git (`[skip ci]`)        |
+-----------------------------------------------------------------------------+
                                      |
                                      | Atomic Object Write
                                      v
+-----------------------------------------------------------------------------+
|                  GOOGLE CLOUD STORAGE (`GCS_BUCKET_NAME`)                   |
|  - `state/virtual_portfolio.json`   (Active Positions, Cash, NAV, Heat)     |
|  - `state/equity_curve.json`        (Daily Historical NAV & Benchmark)      |
|  - `state/eod_telemetry.json`       (EOD Status, Timestamps, Audit Logs)    |
+-----------------------------------------------------------------------------+
                                      |
                                      | In-Memory TTL Read (60s)
                                      v
+-----------------------------------------------------------------------------+
|             GOOGLE CLOUD RUN (`sirix-platform`, Single-Origin)              |
|  - Scaling: `min-instances=0` (Scale-to-Zero), CPU-on-request ($0.00/mo)    |
|  - `/api/*` -> FastAPI (Argon2id + HttpOnly SameSite=Strict JWT + Telemetry)  |
|  - `/*`     -> Static PWA Bundle (`static_gui/` with SPA HTML5 Fallback)    |
+-----------------------------------------------------------------------------+
                                      |
                                      | HTTPS (Single Origin)
                                      v
+-----------------------------------------------------------------------------+
|                  CLIENT DEVICES (iPhone PWA & Chromebook)                   |
|  - Installed Progressive Web App (Offline Shell, Service Worker, Manifest)  |
+-----------------------------------------------------------------------------+
```

### Key Architectural Decisions
* **Decommissioning of Vercel:** All frontend hosting on Vercel is permanently removed. No cross-origin CORS headers or external `VITE_API_BASE_URL` environment overrides are required; the PWA issues relative requests directly to `/api/...`.
* **Multi-Stage Docker Build:** The root `Dockerfile` compiles the React/Tailwind frontend (`npm run build` $\rightarrow$ `dist/`) in Stage 1 and copies the static bundle into `static_gui/` inside the Python 3.11 FastAPI runtime image in Stage 2.
* **SPA Routing & PWA Asset Compliance:** FastAPI serves static assets with strict MIME headers (`manifest.webmanifest`, `sw.js`, icons) and falls back to `static_gui/index.html` for all non-`/api/*` client-side routes (e.g., `/inspector/:ticker`, `/audit`) so browser refreshes never return `404`.
* **GCP Free Tier Optimization:** Cloud Run is configured with `min-instances=0`, `max-instances=2`, and `CPU allocated only during request processing`. FastAPI caches GCS state payloads in memory for 60 seconds (or invalidates immediately upon internal EOD completion webhook) to minimize GCS Class B read operations.

---

## 3. Zero-Trust Single-Origin Security Model

Because the Cloud Run service permits public HTTPS ingress (`Allow unauthenticated invocations`) to support mobile and Chromebook PWA access, all authentication and authorization are enforced strictly at the application layer:
* **Credential Verification:** Single-operator or multi-tenant credentials hashed via **Argon2id** (`passlib` / `argon2-cffi`), with zero plaintext secrets stored in code or container layers.
* **Single-Origin Cookie Session:** Upon successful login (`POST /api/auth/login`), FastAPI issues a signed **HS256 JWT** inside an **`HttpOnly; Secure; SameSite=Strict`** cookie—eliminating XSS token theft and CSRF vulnerabilities inherent to split-domain architectures.
* **Brute-Force Protection:** In-memory sliding-window rate limiting on `/api/auth/login` (max 5 failed attempts per 15 minutes per IP).
* **Internal Webhook Protection:** Administrative endpoints such as `POST /api/internal/trigger-eod` require a cryptographic bearer secret (`X-Sirix-Scheduler-Token`) or Google Cloud Scheduler OIDC token.

---

## 4. Integration Contract with EOD Orchestration Pipeline

The Cloud Run web tier acts as a **read-only consumer** of the state produced by the nightly quantitative engine (specified in full in **Step D.2: `GitHub_Actions_Pipeline_Spec.md`** and **Step E.3: `Production_Deployment_Runbook.md`**):
1. **Atomic Read Consistency:** The EOD pipeline writes to temporary GCS objects before performing atomic overwrites of `virtual_portfolio.json` and `eod_telemetry.json`, guaranteeing that Cloud Run never serves partially written JSON payloads.
2. **Transparent EOD Status Surfacing:** The GUI consumes `eod_telemetry.json` via `GET /api/system/status` to display real-time operational health (`IDLE`, `RUNNING_EOD`, `SKIPPED_MARKET_CLOSED`, `FAILED_DATA_DELAY`, `CRITICAL_ERROR`) alongside `last_successful_eod_timestamp` and `last_trading_date_processed`.
3. **Zero-Override Enforcement:** The GUI exposes **zero** manual trade-execution, stop-loss override, or signal-rejection controls. Users interact with the system strictly for portfolio telemetry, position inspection, risk-budget auditing, and historical performance review.

---

## 5. Document Suite Manifest (`docs/ui-spec/`)

| Document ID | Filename | Scope & Responsibilities |
| :--- | :--- | :--- |
| **F00** | `F00_SIRIX_MASTER_ARCHITECTURE.md` | Unified Single-Origin Cloud Run + GCS topology, security model, and EOD integration contract. |
| **F01** | `F01_data_contracts_auth_edge_states_spec.md` | Pydantic v2 API response schemas, EOD telemetry states, auth flows, and graceful degradation edge states. |
| **F02** | `F02_dashboard_and_inspector_ux_spec.md` | Executive Dashboard, Portfolio Heat gauge, Equity Curve, and Triple-Barrier Position Inspector UI/UX. |
| **F03** | `F03_audit_ledger_and_pwa_spec.md` | Closed Trade Audit Ledger, Corporate Action logs, and iOS/Chromebook PWA offline manifest specification. |

---

## 6. Acceptance Criteria (for AI Studio Implementation)

1. **Single-Origin Container:** `Dockerfile` builds both the React/Tailwind PWA and the FastAPI backend into a single runnable image listening on `$PORT` (`8080`), with zero references to Vercel.
2. **SPA & PWA Routing Integrity:** Navigating directly or refreshing on `/`, `/inspector/CRS`, or `/audit` returns `200 OK` with `index.html`, while `/api/health` and `/api/system/status` return valid JSON.
3. **Stateless GCS Persistence:** Deleting or restarting the Cloud Run container instance causes zero data loss; all portfolio and telemetry data is hydrated cleanly from `GCS_BUCKET_NAME` (with local fallback `data/state/` for offline development).
4. **Hardened Cookie Auth:** Authentication sets an `HttpOnly; Secure; SameSite=Strict` JWT cookie and rejects unauthenticated requests to protected `/api/portfolio/*` routes with `401 Unauthorized`.
5. **EOD Telemetry Visibility:** The dashboard accurately renders `eod_status` and `last_successful_eod_timestamp` from the latest nightly run.