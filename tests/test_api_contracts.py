from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterator
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from api.main import (
    REFRESH_COOKIE_NAME,
    app,
    get_default_audit_log_seed,
    get_default_portfolio_seed,
    get_default_positions_seed,
    get_default_rejections_seed,
    get_storage_adapter,
)
from src.api_exporter import (
    PRIMARY_SIRIX_USER_ID,
    SirixCloudExporter,
    StateStorageAdapter,
    compute_timeline_phase,
    load_user_guardrails,
)
from src.schemas import VirtualPortfolioLedgerSchema


@pytest.fixture()
def isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StateStorageAdapter:
    monkeypatch.delenv("SIRIX_GCS_BUCKET", raising=False)
    monkeypatch.delenv("GCS_BUCKET_NAME", raising=False)
    adapter = StateStorageAdapter(gcs_bucket_name=None, local_data_dir=tmp_path)

    # Verify the production cold-start seed is a clean Day-1 empty slate
    clean_day1_seed = get_default_portfolio_seed()
    assert clean_day1_seed["holdings"] == []
    assert clean_day1_seed["defensive_cash_mode"] is True
    assert clean_day1_seed["summary"]["cash_balance"] == 100000.0
    assert clean_day1_seed["summary"]["total_equity"] == 100000.0
    assert clean_day1_seed["summary"]["invested_value"] == 0.0
    assert clean_day1_seed["audit_badge"]["closed_trades_count"] == 0

    sample_holdings_fixture = {
        **clean_day1_seed,
        "defensive_cash_mode": False,
        "holdings": [
            {
                "ticker": tkr,
                "company_name": f"{tkr} Holdings Inc.",
                "universe": "RUT",
                "shares": 100.0,
                "entry_price": 100.0,
                "current_price": 105.0,
                "market_value": 10500.0,
                "unrealized_pnl_amount": 500.0,
                "unrealized_pnl_pct": 5.0,
                "days_held": 3,
                "max_hold_days": 14,
                "timeline_phase": "FRESH",
                "stop_loss_price": 95.0,
                "take_profit_price": 115.0,
                "atr_14": 2.5,
                "composite_score": 88.0,
            }
            for tkr in ("SMCI", "DUOL", "CELH", "ONTO", "ELF")
        ],
    }

    for uid in (PRIMARY_SIRIX_USER_ID, "usr_sirix_pro", "usr_sirix_free"):
        adapter.write_user_json(uid, "portfolio_state.json", sample_holdings_fixture)
        adapter.write_user_json(uid, "positions_detail.json", get_default_positions_seed())
        adapter.write_user_json(uid, "audit_log.json", get_default_audit_log_seed())
        adapter.write_user_json(uid, "scan_rejections.json", get_default_rejections_seed())

    return adapter


@pytest.fixture()
def client(isolated_storage: StateStorageAdapter) -> Iterator[TestClient]:
    app.dependency_overrides[get_storage_adapter] = lambda: isolated_storage
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _login_for_tier(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SirixQuant#2026!"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert REFRESH_COOKIE_NAME in resp.cookies
    return str(body["access_token"])


# =============================================================================
# 1. HEALTHZ & AUTHENTICATION LIFECYCLE TESTS
# =============================================================================


def test_healthz_probe(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["storage_mode"] == "local_fallback"
    assert data["zero_override_enforced"] is True


def test_jwt_auth_login_refresh_and_logout_lifecycle(client: TestClient) -> None:
    # 1. Invalid password rejected with unified error contract
    bad_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "trader@sirix.quant", "password": "WrongPassword999!"},
    )
    assert bad_resp.status_code == 401
    assert bad_resp.json()["error_code"] == "AUTHENTICATION_FAILED"

    # 2. Valid login issues 15m access token and sets HttpOnly refresh cookie
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "trader@sirix.quant", "password": "SirixQuant#2026!"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert login_data["user"]["user_id"] == PRIMARY_SIRIX_USER_ID
    assert login_data["user"]["account_tier"] == "EXPERT"

    refresh_cookie_val = login_resp.cookies.get(REFRESH_COOKIE_NAME)
    assert refresh_cookie_val is not None

    # 3. Rotate refresh token via POST /api/v1/auth/refresh
    client.cookies.set(REFRESH_COOKIE_NAME, refresh_cookie_val)
    refresh_resp = client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()
    rotated_cookie_val = refresh_resp.cookies.get(REFRESH_COOKIE_NAME)
    assert rotated_cookie_val is not None
    assert rotated_cookie_val != refresh_cookie_val

    # 4. Logout revokes refresh session
    client.cookies.set(REFRESH_COOKIE_NAME, rotated_cookie_val)
    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200

    # Reusing revoked refresh token must fail with 401
    client.cookies.set(REFRESH_COOKIE_NAME, rotated_cookie_val)
    replay_resp = client.post("/api/v1/auth/refresh")
    assert replay_resp.status_code == 401
    assert replay_resp.json()["error_code"] == "TOKEN_REVOKED"


# =============================================================================
# 2. SERVER-SIDE TIER GATING TESTS (FREE vs PRO vs EXPERT)
# =============================================================================


def test_free_tier_gating_restrictions(client: TestClient) -> None:
    token = _login_for_tier(client, "free@sirix.quant")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Portfolio limited to max 3 holdings with truncated_count > 0
    port_resp = client.get("/api/v1/portfolio", headers=headers)
    assert port_resp.status_code == 200
    port_data = port_resp.json()
    assert len(port_data["holdings"]) == 3
    assert port_data["truncated_count"] == 2

    # 2. Deep-Dive Inspector masks ATR, Conviction, and Risk Contribution as null
    pos_resp = client.get("/api/v1/positions/SMCI", headers=headers)
    assert pos_resp.status_code == 200
    pos_data = pos_resp.json()
    qm = pos_data["quant_metrics"]
    assert qm["atr_14"] is None
    assert qm["atr_pct"] is None
    assert qm["conviction_score"] is None
    assert qm["portfolio_risk_contribution_pct"] is None
    assert len(pos_data["ohlc_7d"]) == 7

    # 3. Search returns REJECTED status without rejection_reasons
    search_resp = client.get("/api/v1/search/NVAX", headers=headers)
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["status"] == "REJECTED"
    assert search_data["rejection_reasons"] is None

    # 4. Audit log truncated to latest 5 closed trades
    audit_resp = client.get("/api/v1/audit-log", headers=headers)
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["total_count"] == 6
    assert len(audit_data["items"]) == 5

    # 5. PATCH /preferences guardrails blocked with 403 Forbidden
    patch_resp = client.patch(
        "/api/v1/preferences",
        headers=headers,
        json={"guardrails": {"max_portfolio_heat_pct": 5.0}},
    )
    assert patch_resp.status_code == 403
    assert patch_resp.json()["error_code"] == "TIER_RESTRICTED"


def test_pro_tier_entitlements_and_guardrail_protection(client: TestClient) -> None:
    token = _login_for_tier(client, "pro@sirix.quant")
    headers = {"Authorization": f"Bearer {token}"}

    # Unlimited holdings
    port_resp = client.get("/api/v1/portfolio", headers=headers)
    assert port_resp.status_code == 200
    assert len(port_resp.json()["holdings"]) == 5
    assert port_resp.json()["truncated_count"] == 0

    # Full quant metrics visible
    pos_resp = client.get("/api/v1/positions/SMCI", headers=headers)
    assert pos_resp.status_code == 200
    qm = pos_resp.json()["quant_metrics"]
    assert qm["atr_14"] == 2.70
    assert qm["conviction_score"] == 0.84

    # Full search rejection reasons visible
    search_resp = client.get("/api/v1/search/NVAX", headers=headers)
    assert search_resp.status_code == 200
    reasons = search_resp.json()["rejection_reasons"]
    assert isinstance(reasons, list) and len(reasons) == 2
    assert reasons[0]["code"] == "EARNINGS_BLACKOUT"

    # Held ticker search returns HELD status
    held_search = client.get("/api/v1/search/SMCI", headers=headers)
    assert held_search.status_code == 200
    assert held_search.json()["status"] == "HELD"

    # Full audit log visible (all 6 items)
    audit_resp = client.get("/api/v1/audit-log", headers=headers)
    assert audit_resp.status_code == 200
    assert len(audit_resp.json()["items"]) == 6

    # Guardrail mutation still forbidden for PRO tier (403)
    patch_guardrails = client.patch(
        "/api/v1/preferences",
        headers=headers,
        json={"guardrails": {"max_portfolio_heat_pct": 5.5}},
    )
    assert patch_guardrails.status_code == 403
    assert patch_guardrails.json()["error_code"] == "TIER_RESTRICTED"

    # UI preferences update allowed for PRO tier
    patch_ui = client.patch(
        "/api/v1/preferences",
        headers=headers,
        json={"ui": {"language": "en", "theme": "midnight-sapphire"}},
    )
    assert patch_ui.status_code == 200
    assert patch_ui.json()["ui"]["theme"] == "midnight-sapphire"


def test_expert_tier_guardrail_bounds_and_zero_override_immutability(
    client: TestClient,
) -> None:
    token = _login_for_tier(client, "trader@sirix.quant")
    headers = {"Authorization": f"Bearer {token}"}

    # Valid EXPERT guardrail update
    valid_patch = client.patch(
        "/api/v1/preferences",
        headers=headers,
        json={
            "ui": {"language": "he", "theme": "sirius-ice-light"},
            "guardrails": {
                "max_portfolio_heat_pct": 7.5,
                "risk_per_trade_pct": 1.25,
                "time_barrier_days": 12,
                "earnings_blackout_days": 6,
                "zero_override_enforced": True,
                "kill_switch_active": True,
            },
        },
    )
    assert valid_patch.status_code == 200
    updated = valid_patch.json()
    assert updated["guardrails"]["max_portfolio_heat_pct"] == 7.5
    assert updated["guardrails"]["risk_per_trade_pct"] == 1.25
    assert updated["guardrails"]["kill_switch_active"] is True

    # Out-of-bounds max_portfolio_heat_pct (> 10.0) rejected
    oob_heat = client.patch(
        "/api/v1/preferences",
        headers=headers,
        json={"guardrails": {"max_portfolio_heat_pct": 12.0}},
    )
    assert oob_heat.status_code == 422
    assert oob_heat.json()["error_code"] == "VALIDATION_ERROR"

    # Attempt to disable zero_override_enforced rejected
    override_attempt = client.patch(
        "/api/v1/preferences",
        headers=headers,
        json={"guardrails": {"zero_override_enforced": False}},
    )
    assert override_attempt.status_code == 422
    assert override_attempt.json()["error_code"] == "VALIDATION_ERROR"


# =============================================================================
# 3. DEFENSIVE CASH MODE, TIMELINE PHASES & EXPORTER TESTS
# =============================================================================


def test_timeline_phase_boundaries() -> None:
    assert compute_timeline_phase(1, 14) == "FRESH"
    assert compute_timeline_phase(7, 14) == "FRESH"  # 50.0%
    assert compute_timeline_phase(8, 14) == "MATURING"
    assert compute_timeline_phase(11, 14) == "MATURING"  # 78.6% <= 80%
    assert compute_timeline_phase(12, 14) == "CRITICAL"  # 85.7% > 80%
    assert compute_timeline_phase(14, 14) == "CRITICAL"


def test_defensive_cash_mode_and_cloud_exporter(
    client: TestClient,
    isolated_storage: StateStorageAdapter,
) -> None:
    # Export a 100%-cash ledger via SirixCloudExporter
    empty_ledger = VirtualPortfolioLedgerSchema(
        portfolio_id=UUID("00000000-0000-4000-8000-000000000101"),
        user_id=UUID("00000000-0000-4000-8000-000000000001"),
        portfolio_name="Defensive Cash Portfolio",
        as_of_date=date(2026, 11, 13),
        cash_balance=100_000.0,
        total_equity=100_000.0,
        max_portfolio_heat_pct=0.06,
        max_concurrent_positions=10,
        subscribed_indices=["RUT_2000", "SP_400"],
        open_positions={},
        closed_trades_audit=[],
    )

    exporter = SirixCloudExporter(storage_adapter=isolated_storage)
    exported = exporter.export_all(
        ledger=empty_ledger,
        user_id=PRIMARY_SIRIX_USER_ID,
        as_of_date=date(2026, 11, 13),
    )
    assert exported["portfolio_state"]["defensive_cash_mode"] is True

    token = _login_for_tier(client, "trader@sirix.quant")
    port_resp = client.get(
        "/api/v1/portfolio",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert port_resp.status_code == 200
    body = port_resp.json()
    assert body["defensive_cash_mode"] is True
    assert body["holdings"] == []

    # Verify load_user_guardrails helper reads persisted preferences cleanly
    prefs = load_user_guardrails(
        user_id=PRIMARY_SIRIX_USER_ID,
        local_data_dir=isolated_storage.local_data_dir,
    )
    assert prefs.guardrails.zero_override_enforced is True
