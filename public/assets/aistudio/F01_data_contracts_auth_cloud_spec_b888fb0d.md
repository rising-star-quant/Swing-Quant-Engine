# F01: SIRIX Data Contracts, Authentication, Tier Gating & Cloud Infrastructure Specification

**Module:** `docs/ui-spec/F01_data_contracts_auth_edge_states_spec.md`  
**Branch:** `feat/adaptive-client`  
**Target Stack:** FastAPI + Pydantic v2 on Google Cloud Run (Backend) | TypeScript + PWA Service Worker (Frontend)  
**Zero-Override Policy:** Enforced at API boundary (no manual buy/sell execution endpoints exist).

---

## 1. Authentication & Session Lifecycle

### 1.1 Security Architecture
- **Password Hashing:** `Argon2id` (aligned with `src/security.py`).
- **Session Tokens:**
  - **Access Token:** Short-lived `JWT` (`HS256` / `RS256`, TTL: `15 minutes`), transmitted via `Authorization: Bearer <token>` header.
  - **Refresh Token:** Long-lived opaque/JWT token (TTL: `30 days`), stored strictly in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie to prevent XSS token theft on PWA mobile and desktop clients.
- **Multi-Tenant Isolation:** Every API query resolves `user_id` exclusively from the verified JWT `sub` claim—never from client-supplied query parameters or request bodies.

### 1.2 Auth Endpoints
- `POST /api/v1/auth/login`
  - **Request:** `{ "email": "string", "password": "string" }`
  - **Response (`200 OK`):**
    ```json
    {
      "access_token": "eyJhbGciOi...",
      "token_type": "bearer",
      "expires_in": 900,
      "user": {
        "user_id": "usr_sirix_primary",
        "email": "trader@sirix.quant",
        "account_tier": "EXPERT",
        "preferences": {
          "language": "he",
          "theme": "obsidian-dark"
        }
      }
    }
    ```
- `POST /api/v1/auth/refresh` — Rotates the `HttpOnly` refresh cookie and returns a fresh `access_token`.
- `POST /api/v1/auth/logout` — Revokes the refresh session and clears the cookie.

---

## 2. Core REST API Data Contracts

All numeric currency and percentage fields are returned as standard JSON numbers; the frontend formats them using `Intl.NumberFormat` with `dir="ltr"` isolation and `font-variant-numeric: tabular-nums`.

### 2.1 Portfolio Home Overview (`GET /api/v1/portfolio`)
Feeds the 3-tier Home screen (Macro Portfolio Header, `Audit Log` quick-access badge, and clean scrolling holdings list with bottom 14-day `Timeline Bar`).

```json
{
  "as_of_eod": "2026-11-13T21:00:00Z",
  "market_status": "CLOSED",
  "defensive_cash_mode": false,
  "summary": {
    "total_equity": 104820.50,
    "daily_change_amount": 1420.80,
    "daily_change_pct": 1.37,
    "inception_change_amount": 4820.50,
    "inception_change_pct": 4.82,
    "cash_balance": 18450.00,
    "invested_value": 86370.50,
    "portfolio_heat_pct": 5.4,
    "max_portfolio_heat_pct": 6.0
  },
  "audit_badge": {
    "closed_trades_count": 28,
    "win_rate_pct": 64.3
  },
  "holdings": [
    {
      "ticker": "SMCI",
      "universe": "RUT",
      "current_price": 53.90,
      "position_value": 13475.00,
      "unrealized_pnl_pct": 11.83,
      "days_held": 6,
      "max_days": 14,
      "timeline_phase": "FRESH"
    },
    {
      "ticker": "CELH",
      "universe": "RUT",
      "current_price": 34.10,
      "position_value": 10230.00,
      "unrealized_pnl_pct": 8.25,
      "days_held": 12,
      "max_days": 14,
      "timeline_phase": "CRITICAL"
    }
  ],
  "truncated_count": 0
}
```
*Note on `timeline_phase`:* Server pre-computes `"FRESH"` (Days 1–7, Cyan `#06B6D4`), `"MATURING"` (Days 8–11, Amber `#F59E0B`), or `"CRITICAL"` (Days 12–14, Crimson `#EF4444`).

### 2.2 Position Deep-Dive Inspector (`GET /api/v1/positions/{ticker}`)
Triggered on row/card tap (Mobile Bottom Sheet / Desktop Split-View Inspector).

```json
{
  "ticker": "SMCI",
  "company_name": "Super Micro Computer, Inc.",
  "universe": "RUT",
  "shares": 250,
  "entry_date": "2026-11-05",
  "entry_price": 48.20,
  "current_price": 53.90,
  "position_value": 13475.00,
  "unrealized_pnl_amount": 1425.00,
  "unrealized_pnl_pct": 11.83,
  "barriers": {
    "chandelier_stop": 49.50,
    "take_profit": 57.80,
    "days_held": 6,
    "max_days": 14,
    "stop_distance_atr": 1.63
  },
  "quant_metrics": {
    "atr_14": 2.70,
    "atr_pct": 5.01,
    "conviction_score": 0.84,
    "portfolio_risk_contribution_pct": 0.72,
    "next_earnings_date": "2027-01-28",
    "earnings_blackout_active": false
  },
  "ohlc_7d": [
    { "date": "2026-11-05", "open": 48.10, "high": 49.20, "low": 47.80, "close": 48.90 },
    { "date": "2026-11-06", "open": 49.00, "high": 50.40, "low": 48.75, "close": 50.10 },
    { "date": "2026-11-09", "open": 50.25, "high": 51.10, "low": 49.60, "close": 50.80 },
    { "date": "2026-11-10", "open": 50.70, "high": 51.90, "low": 50.10, "close": 51.50 },
    { "date": "2026-11-11", "open": 51.60, "high": 52.80, "low": 51.20, "close": 52.40 },
    { "date": "2026-11-12", "open": 52.30, "high": 53.50, "low": 51.95, "close": 53.10 },
    { "date": "2026-11-13", "open": 53.20, "high": 54.40, "low": 52.90, "close": 53.90 }
  ]
}
```

### 2.3 Algorithmic Transparency Search (`GET /api/v1/search/{ticker}`)
Allows users to inspect any ticker across `RUT` / `MID`. If held, returns `status: "HELD"` and redirects to the Position Inspector. If not held, explains why the autonomous engine filtered it out.

```json
{
  "ticker": "NVAX",
  "company_name": "Novavax, Inc.",
  "universe": "RUT",
  "status": "REJECTED",
  "last_scan_eod": "2026-11-13T21:00:00Z",
  "current_price": 9.42,
  "rejection_reasons": [
    {
      "code": "EARNINGS_BLACKOUT",
      "canonical_term": "Earnings Blackout",
      "metric_value": "2 days to report",
      "threshold_value": ">= 5 trading days required"
    },
    {
      "code": "LOW_CONVICTION",
      "canonical_term": "Conviction",
      "metric_value": "0.58",
      "threshold_value": ">= 0.72 required"
    }
  ]
}
```

### 2.4 Closed Trades Audit Log (`GET /api/v1/audit-log`)
```json
{
  "total_count": 28,
  "items": [
    {
      "trade_id": "trd_9941",
      "ticker": "ANF",
      "universe": "MID",
      "entry_date": "2026-10-22",
      "exit_date": "2026-11-04",
      "days_held": 9,
      "entry_price": 138.50,
      "exit_price": 154.20,
      "realized_pnl_pct": 11.34,
      "realized_pnl_amount": 1570.00,
      "exit_reason": "TAKE_PROFIT",
      "conviction_at_entry": 0.86
    }
  ]
}
```
*Valid `exit_reason` enums:* `"TAKE_PROFIT"`, `"CHANDELIER_STOP"`, `"TIME_BARRIER"`, `"EARNINGS_BLACKOUT"`, `"KILL_SWITCH"`.

### 2.5 User Preferences & Risk Guardrails (`GET` & `PATCH /api/v1/preferences`)
```json
{
  "ui": {
    "language": "he",
    "theme": "obsidian-dark"
  },
  "guardrails": {
    "max_portfolio_heat_pct": 6.0,
    "risk_per_trade_pct": 1.0,
    "time_barrier_days": 14,
    "earnings_blackout_days": 5,
    "zero_override_enforced": true,
    "kill_switch_active": false
  }
}
```
*Strict Pydantic Validation Bounds on `PATCH`:*
- `max_portfolio_heat_pct`: `1.0` to `10.0` (step `0.5`)
- `risk_per_trade_pct`: `0.25` to `2.0` (step `0.25`)
- `time_barrier_days`: `5` to `30`
- `earnings_blackout_days`: `3` to `10`
- `zero_override_enforced`: Immutable `true` (cannot be disabled via API).

---

## 3. Account Tier Gating Matrix (Server-Enforced)

Tier restrictions are enforced directly inside the FastAPI dependency layer (`get_current_user`) before serializing JSON payloads:

| Capability / Field | `FREE` | `PRO` | `EXPERT` |
| :--- | :--- | :--- | :--- |
| **Active Holdings Returned** | Max `3` (`truncated_count` > 0) | Unlimited | Unlimited |
| **Deep-Dive 7-Day Candlestick** | Visible | Visible | Visible |
| **`Conviction` & `ATR` Telemetry** | Masked (`null` in payload) | Visible | Visible |
| **Algorithmic Search (`Rejection Reasons`)** | Status only (`REJECTED`) | Full `rejection_reasons` | Full `rejection_reasons` |
| **`Audit Log` History Depth** | Latest `5` closed trades | Full history | Full history + CSV export |
| **Risk Guardrails (`PATCH /preferences`)** | Read-only (`403 Forbidden`) | Read-only (`403 Forbidden`) | Full read/write within safe bounds |

---

## 4. Edge Cases, Resilience & PWA Offline States

1. **Defensive Cash Mode (`100% Cash` / `holdings: []`):**
   - When market regime filters or `Earnings Blackout` windows suppress all entries, `defensive_cash_mode` is `true` and `holdings` is empty (`[]`).
   - UI renders an institutional status card (*"Defensive Cash Mode — Engine scanning RUT & MID universes for qualified setups"*) instead of an empty list.
2. **Stale-While-Revalidate (`Offline Snapshot`):**
   - The PWA Service Worker caches the latest `200 OK` JSON responses from `/api/v1/portfolio` and `/api/v1/positions/*` in `IndexedDB` / Cache Storage.
   - If `navigator.onLine === false` or the API times out (`> 5000ms`), the UI renders the cached snapshot with a subtle top status pill (`Offline Snapshot • Synced [timestamp]`) and disables `PATCH /preferences` until connectivity returns.
3. **Skeleton Loading States:**
   - Initial load displays geometry-matched pulsing skeletons (`120ms` delay threshold to avoid flash on fast connections) matching the exact height of the Hero Equity block and `64px` holding rows so zero Cumulative Layout Shift (`CLS = 0`) occurs.
4. **HTTP Error Contract:**
   - All API errors follow a uniform structure: `{ "error_code": "TIER_RESTRICTED | TICKER_NOT_FOUND | VALIDATION_ERROR", "detail": "Human-readable message" }`.

---

## 5. Cloud Infrastructure & Engine-to-API Sync Pipeline

### 5.1 Serverless Hosting Architecture (Google Cloud Run)
- **Runtime:** Stateless container deployed on **Google Cloud Run** (`Scale-to-Zero` enabled, dynamic `$PORT` binding via `uvicorn`, running as non-root `appuser`).
- **Health Probe:** `GET /healthz` returns service status and active storage mode (`gcs` vs. `local_fallback`).
- **Secrets Management:** Sensitive runtime variables (`SIRIX_JWT_SECRET`, `SIRIX_GCS_BUCKET`, `SIRIX_CORS_ORIGINS`) are injected exclusively via **Google Cloud Secret Manager** and environment configuration—never committed to Git.

### 5.2 Single Source of Truth (Google Cloud Storage Bridge)
- **Bucket Structure:** All telemetry and per-user preferences are persisted in a private GCS bucket (`SIRIX_GCS_BUCKET`, canonical name `sirix-quant-state-prod`) isolated by tenant prefix (`users/{user_id}/`):
  - `users/{user_id}/portfolio_state.json` — Macro portfolio metrics, `Portfolio Heat`, and active holdings list.
  - `users/{user_id}/positions_detail.json` — Deep-dive position telemetry (`Triple-Barrier` levels, `ATR`, `Conviction`, and 7-day OHLC series).
  - `users/{user_id}/audit_log.json` — Historical closed trades and exit reasons.
  - `users/{user_id}/scan_rejections.json` — EOD screening rejection log for algorithmic transparency search.
  - `users/{user_id}/preferences.json` — User UI selections (`language`, `theme`) and `EXPERT`-tier risk guardrails.
- **Local Development Fallback:** When `SIRIX_GCS_BUCKET` is unset, `StateStorageAdapter` seamlessly falls back to reading/writing local JSON files under `data/`.

### 5.3 GitHub Actions EOD Synchronization & OIDC Security
- **Keyless Authentication:** GitHub Actions authenticates to Google Cloud using **Workload Identity Federation (OIDC)** (`google-github-actions/auth@v2`) scoped strictly to `Storage Object Admin` on the target state bucket—eliminating static JSON service account keys.
- **Bidirectional Sync Loop:**
  1. **Pre-Run Read:** At the start of the daily EOD workflow, the quant engine reads `users/{user_id}/preferences.json` from GCS to respect user-configured `RiskGuardrails` (`max_portfolio_heat_pct`, `time_barrier_days`, `kill_switch_active`).
  2. **Post-Run Export:** Upon completing EOD calculations, `SirixCloudExporter` (`src/api_exporter.py`) serializes the 4 telemetry JSON contracts and publishes them to GCS for immediate consumption by the SIRIX PWA.