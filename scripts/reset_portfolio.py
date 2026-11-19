#!/usr/bin/env python3
"""
SIRIX E.1 Atomic Portfolio Epoch Reset & 4-Layer Cache Invalidation Engine.

Enforces Zero-Override: performs ONLY a system-wide Hard Epoch Reset triggered
via GitHub Actions (`workflow_dispatch`) with strict double-confirmation (`RESET`)
and sanitized `epoch_alias` validation before touching GCS.

Atomic Transaction Flow (E.1 Section 3.2):
  1. Isolated Pre-Reset Snapshot backup in GCS (`backups/pre_reset_epoch_{old_id}_{timestamp}/`).
  2. Force-liquidation of all active positions with exit reason `EPOCH_RESET_LIQUIDATION`.
  3. Closing equity computation & sealing of prior epoch in `portfolio_epochs.json`.
  4. Portfolio reset ($100,000.00 cash, 0 holdings, 0.00% heat, Kill-Switch ARMED_READY)
     and root `state_revision_id` bump (`epoch_{id}_{YYYYMMDDTHHMMSSZ}`).
  5. Continuous Time-Weighted Return (TWR) update in `equity_history.json` & `equity_curve.json`
     with 0.00% reset-day jump and `epoch_marker` injection.
  6. Structured Telegram Epoch Reset Card via `NotificationHub` + Cloud Run cache flush webhook.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api_exporter import (
    PRIMARY_SIRIX_USER_ID,
    SirixCloudExporter,
    StateStorageAdapter,
    UserPreferencesContract,
)
from src.config import SystemSettings, get_settings
from src.notifier import NotificationHub
from src.schemas import (
    ClosedTradeAuditSchema,
    EpochMarkerSchema,
    EquityHistoryPointSchema,
    ExitReason,
    MultiTenantStateStoreSchema,
    PortfolioEpochRecordSchema,
    PortfolioEpochsStoreSchema,
    StateRevisionMetadataSchema,
    TripleBarrierPositionSchema,
    VirtualPortfolioLedgerSchema,
)
from src.storage import (
    DEFAULT_ADMIN_PORTFOLIO_ID,
    DEFAULT_ADMIN_USER_ID,
    JsonPortfolioStateRepository,
    ParquetMarketDataRepository,
    StatelessGCSStateReader,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("SIRIX.EpochReset")

BASELINE_STARTING_EQUITY_USD: float = 100_000.00
STRICT_CONFIRMATION_TOKEN: str = "RESET"
EPOCH_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/-]{1,62}[A-Za-z0-9]$")
FORBIDDEN_ALIAS_TOKENS: Tuple[str, ...] = ("..", "<", ">", ";", "&", "$", "`", '"', "'", "\\", "\n", "\r")
MANAGED_TENANT_USER_IDS: Tuple[str, ...] = (
    PRIMARY_SIRIX_USER_ID,
    "usr_sirix_pro",
    "usr_sirix_free",
)


class EpochResetValidationError(ValueError):
    """Raised when operator input fails E.1 pre-flight confirmation or sanitization."""


def validate_reset_inputs(epoch_alias: str, confirm_reset: str) -> str:
    """
    Strictly validates operator inputs BEFORE any GCS read/write occurs:
    - `confirm_reset` MUST equal `"RESET"` exactly.
    - `epoch_alias` MUST be >= 3 chars, <= 64 chars, and free of dangerous characters.
    """
    if confirm_reset != STRICT_CONFIRMATION_TOKEN:
        raise EpochResetValidationError(
            f"Confirmation mismatch: expected exact string '{STRICT_CONFIRMATION_TOKEN}', "
            f"received '{confirm_reset}'. Aborting immediately without modifying GCS."
        )

    cleaned_alias = (epoch_alias or "").strip()
    if len(cleaned_alias) < 3:
        raise EpochResetValidationError(
            f"epoch_alias must be at least 3 characters long (got {len(cleaned_alias)})."
        )
    if len(cleaned_alias) > 64:
        raise EpochResetValidationError(
            f"epoch_alias must be at most 64 characters long (got {len(cleaned_alias)})."
        )
    if any(tok in cleaned_alias for tok in FORBIDDEN_ALIAS_TOKENS):
        raise EpochResetValidationError(
            "epoch_alias contains forbidden special characters or path traversal sequences."
        )
    if not EPOCH_ALIAS_PATTERN.match(cleaned_alias):
        raise EpochResetValidationError(
            "epoch_alias may only contain alphanumeric characters, spaces, and safe punctuation (._:/-)."
        )
    return cleaned_alias


def _resolve_mark_to_market_price(
    pos: TripleBarrierPositionSchema,
    market_repo: ParquetMarketDataRepository,
) -> float:
    """Fetches latest Close from Parquet cache, falling back to last recorded high/entry price."""
    try:
        df_latest = market_repo.load_ohlcv(pos.ticker, lookback_days=1)
        if df_latest is not None and not df_latest.empty:
            close_val = float(df_latest["Close"].iloc[-1])
            if close_val > 0.0:
                return round(close_val, 4)
    except Exception as exc:
        logger.debug("Parquet mark-to-market fallback for %s: %s", pos.ticker, exc)
    fallback_price = max(float(pos.entry_price), float(pos.highest_high_since_entry) * 0.985)
    return round(fallback_price, 4)


def _compute_continuous_twr(
    existing_points: List[Dict[str, Any]],
    prior_starting_equity: float,
    closing_equity_before_reset: float,
) -> float:
    """
    Calculates unbroken Time-Weighted Return (cumulative_algo_return_pct) right up to
    the moment before reset so the reset itself contributes strictly 0.00% return.
    """
    if existing_points:
        last_pt = existing_points[-1]
        prev_cum_pct = float(last_pt.get("cumulative_algo_return_pct", 0.0))
        prev_raw_val = float(
            last_pt.get("raw_portfolio_value")
            or last_pt.get("portfolio_nav")
            or prior_starting_equity
            or BASELINE_STARTING_EQUITY_USD
        )
        if prev_raw_val > 0.0:
            step_factor = closing_equity_before_reset / prev_raw_val
            chained = ((1.0 + prev_cum_pct / 100.0) * step_factor - 1.0) * 100.0
            return round(chained, 4)
        return round(prev_cum_pct, 4)

    base = prior_starting_equity if prior_starting_equity > 0.0 else BASELINE_STARTING_EQUITY_USD
    return round(((closing_equity_before_reset - base) / base) * 100.0, 4)


def _trigger_cloud_run_invalidation(cloud_run_url: str, scheduler_token: str) -> bool:
    """Layer 2 webhook: flushes any warm Cloud Run container cache immediately after reset."""
    clean_url = (cloud_run_url or "").strip().rstrip("/")
    clean_token = (scheduler_token or "").strip()
    if not clean_url or not clean_token:
        logger.info("Cloud Run invalidation webhook skipped (SIRIX_CLOUD_RUN_URL or INTERNAL_SCHEDULER_TOKEN unset).")
        return False

    endpoint = f"{clean_url}/api/internal/trigger-eod"
    req = urllib_request.Request(
        endpoint,
        data=b"{}",
        method="POST",
        headers={
            "X-Sirix-Scheduler-Token": clean_token,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=15) as resp:
            status_code = getattr(resp, "status", 200)
            logger.info("Cloud Run cache invalidation webhook succeeded (HTTP %s).", status_code)
            return 200 <= status_code < 300
    except (urllib_error.URLError, urllib_error.HTTPError, OSError) as exc:
        logger.warning("Cloud Run cache invalidation webhook failed (%s): %s", endpoint, exc)
        return False


def execute_portfolio_epoch_reset(
    epoch_alias: str,
    confirm_reset: str,
    target_date: Optional[date] = None,
    triggered_by: str = "GITHUB_ACTIONS_MANUAL",
    dry_run: bool = False,
    settings: Optional[SystemSettings] = None,
) -> Dict[str, Any]:
    """
    Executes the full E.1 atomic Hard Epoch Reset across GCS, local state files,
    user-scoped API contracts, NotificationHub (Telegram), and Cloud Run cache webhook.
    """
    sanitized_alias = validate_reset_inputs(epoch_alias=epoch_alias, confirm_reset=confirm_reset)
    resolved_settings = settings or get_settings()
    now_utc = datetime.now(timezone.utc)
    reset_iso_utc = now_utc.isoformat().replace("+00:00", "Z")
    compact_ts = now_utc.strftime("%Y%m%dT%H%M%SZ")
    as_of = target_date or now_utc.date()

    bucket_name = (
        os.environ.get("SIRIX_GCS_BUCKET", "").strip()
        or os.environ.get("GCS_BUCKET_NAME", "").strip()
        or None
    )
    gcs_reader = StatelessGCSStateReader(
        settings=resolved_settings,
        bucket_name=bucket_name,
        cache_ttl_seconds=0.0,
    )
    json_repo = JsonPortfolioStateRepository(settings=resolved_settings)
    market_repo = ParquetMarketDataRepository(settings=resolved_settings)
    storage_adapter = StateStorageAdapter(
        gcs_bucket_name=bucket_name,
        local_data_dir=(resolved_settings.base_dir / "data"),
    )

    # Load existing epochs store & active portfolio state (GCS-first, local fallback)
    raw_epochs_doc, _ = gcs_reader.read_portfolio_epochs()
    epochs_store = PortfolioEpochsStoreSchema.model_validate(raw_epochs_doc)
    old_epoch_id = int(epochs_store.active_epoch_id)
    old_epoch_alias = str(epochs_store.active_epoch_alias)
    new_epoch_id = old_epoch_id + 1
    new_state_revision_id = f"epoch_{new_epoch_id}_{compact_ts}"

    try:
        current_state, _ = gcs_reader.read_virtual_portfolio()
    except Exception:
        current_state = json_repo.load_or_initialize_state(as_of_date=as_of)

    if not current_state.tenant_portfolios:
        current_state = json_repo.load_or_initialize_state(as_of_date=as_of)

    # -------------------------------------------------------------------------
    # STEP 1: Isolated Pre-Reset Backup Snapshot (GCS + Local)
    # -------------------------------------------------------------------------
    backup_prefix = f"backups/pre_reset_epoch_{old_epoch_id}_{compact_ts}"
    objects_to_backup = [
        "state/virtual_portfolio.json",
        "state/state.json",
        "state/portfolio_epochs.json",
        "state/equity_history.json",
        "state/equity_curve.json",
        "state/trade_history.json",
        "state/eod_telemetry.json",
        "state/eod_heartbeat.json",
        f"users/{PRIMARY_SIRIX_USER_ID}/portfolio_state.json",
        f"users/{PRIMARY_SIRIX_USER_ID}/positions_detail.json",
        f"users/{PRIMARY_SIRIX_USER_ID}/audit_log.json",
        f"users/{PRIMARY_SIRIX_USER_ID}/preferences.json",
    ]
    backed_up_gcs_keys: List[str] = []
    if not dry_run:
        backed_up_gcs_keys = gcs_reader.backup_objects_in_gcs(backup_prefix, objects_to_backup)
        local_backup_dir = (resolved_settings.base_dir / "data" / backup_prefix).resolve()
        local_backup_dir.mkdir(parents=True, exist_ok=True)
        JsonPortfolioStateRepository._write_text_atomically(
            local_backup_dir / "virtual_portfolio.json",
            current_state.model_dump_json(indent=2),
        )
        JsonPortfolioStateRepository._write_text_atomically(
            local_backup_dir / "portfolio_epochs.json",
            epochs_store.model_dump_json(indent=2),
        )
    logger.info(
        "Step 1/6 complete: Pre-reset backup prepared at %s (GCS objects copied: %d)",
        backup_prefix,
        len(backed_up_gcs_keys),
    )

    # -------------------------------------------------------------------------
    # STEP 2 & STEP 3: Force-Liquidate Open Positions & Compute Closing Equity
    # -------------------------------------------------------------------------
    all_liquidated_trades: List[ClosedTradeAuditSchema] = []
    primary_closing_equity: Optional[float] = None
    updated_portfolios: Dict[Any, VirtualPortfolioLedgerSchema] = {}

    for pid, ledger in current_state.tenant_portfolios.items():
        liquidated_proceeds = 0.0
        ledger_closed_trades = list(ledger.closed_trades_audit)

        for ticker, pos in sorted(ledger.open_positions.items()):
            exit_price = _resolve_mark_to_market_price(pos, market_repo)
            proceeds = round(exit_price * pos.shares, 2)
            liquidated_proceeds += proceeds
            realized_pnl = round((exit_price - pos.entry_price) * pos.shares, 2)
            unit_risk = max(1e-6, pos.entry_price - pos.initial_stop_price)
            realized_r = round((exit_price - pos.entry_price) / unit_risk, 4)
            safe_exit_date = max(as_of, pos.entry_date)

            audit_record = ClosedTradeAuditSchema(
                position_id=pos.position_id,
                user_id=pos.user_id,
                portfolio_id=pos.portfolio_id,
                ticker=pos.ticker,
                index_id=pos.index_id,
                entry_date=pos.entry_date,
                exit_date=safe_exit_date,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                shares=pos.shares,
                bars_held=max(1, pos.bars_held),
                exit_reason=ExitReason.EPOCH_RESET_LIQUIDATION,
                realized_pnl_dollars=realized_pnl,
                realized_r_multiple=realized_r,
            )
            ledger_closed_trades.append(audit_record)
            all_liquidated_trades.append(audit_record)

        closing_equity = round(float(ledger.cash_balance) + liquidated_proceeds, 2)
        if closing_equity <= 0.0:
            closing_equity = round(float(ledger.total_equity), 2)

        if pid == DEFAULT_ADMIN_PORTFOLIO_ID or primary_closing_equity is None:
            primary_closing_equity = closing_equity

        # STEP 4 (Ledger Reset): Clear open_positions, reset cash/equity to $100,000.00, 0% heat
        reset_ledger = VirtualPortfolioLedgerSchema(
            portfolio_id=ledger.portfolio_id,
            user_id=ledger.user_id,
            portfolio_name=ledger.portfolio_name,
            as_of_date=as_of,
            cash_balance=BASELINE_STARTING_EQUITY_USD,
            total_equity=BASELINE_STARTING_EQUITY_USD,
            max_portfolio_heat_pct=ledger.max_portfolio_heat_pct,
            max_concurrent_positions=ledger.max_concurrent_positions,
            subscribed_indices=list(ledger.subscribed_indices),
            open_positions={},
            closed_trades_audit=ledger_closed_trades,
        )
        updated_portfolios[pid] = reset_ledger

    closing_equity_before_reset = (
        primary_closing_equity
        if primary_closing_equity is not None
        else BASELINE_STARTING_EQUITY_USD
    )
    positions_liquidated_count = len(all_liquidated_trades)

    # Seal prior epoch & open next epoch in portfolio_epochs.json
    prior_starting_equity = BASELINE_STARTING_EQUITY_USD
    updated_epoch_records: List[PortfolioEpochRecordSchema] = []
    prior_found = False
    for rec in epochs_store.epochs:
        if rec.epoch_id == old_epoch_id:
            prior_found = True
            prior_starting_equity = float(rec.starting_equity)
            prior_return_pct = round(
                ((closing_equity_before_reset - prior_starting_equity) / prior_starting_equity)
                * 100.0,
                4,
            )
            updated_epoch_records.append(
                rec.model_copy(
                    update={
                        "closing_equity_before_reset": closing_equity_before_reset,
                        "positions_liquidated_count": positions_liquidated_count,
                        "closed_at_utc": reset_iso_utc,
                        "epoch_return_pct": prior_return_pct,
                    }
                )
            )
        else:
            updated_epoch_records.append(rec)

    closed_epoch_return_pct = round(
        ((closing_equity_before_reset - prior_starting_equity) / prior_starting_equity) * 100.0,
        4,
    )
    if not prior_found:
        updated_epoch_records.append(
            PortfolioEpochRecordSchema(
                epoch_id=old_epoch_id,
                epoch_alias=old_epoch_alias,
                reset_timestamp_utc=current_state.last_updated_utc.isoformat().replace("+00:00", "Z"),
                closing_equity_before_reset=closing_equity_before_reset,
                starting_equity=prior_starting_equity,
                positions_liquidated_count=positions_liquidated_count,
                triggered_by="GENESIS",
                closed_at_utc=reset_iso_utc,
                epoch_return_pct=closed_epoch_return_pct,
            )
        )

    new_epoch_record = PortfolioEpochRecordSchema(
        epoch_id=new_epoch_id,
        epoch_alias=sanitized_alias,
        reset_timestamp_utc=reset_iso_utc,
        closing_equity_before_reset=closing_equity_before_reset,
        starting_equity=BASELINE_STARTING_EQUITY_USD,
        positions_liquidated_count=positions_liquidated_count,
        triggered_by=triggered_by if triggered_by in ("GENESIS", "GITHUB_ACTIONS_MANUAL", "PWA_AUTHORIZED_USER") else "GITHUB_ACTIONS_MANUAL",
        closed_at_utc=None,
        epoch_return_pct=0.0,
    )
    updated_epoch_records.append(new_epoch_record)

    updated_epochs_store = PortfolioEpochsStoreSchema(
        active_epoch_id=new_epoch_id,
        active_epoch_alias=sanitized_alias,
        state_revision_id=new_state_revision_id,
        epochs=updated_epoch_records,
    )

    reset_state_store = MultiTenantStateStoreSchema(
        schema_version="2.1.0",
        epoch_id=new_epoch_id,
        epoch_alias=sanitized_alias,
        state_revision_id=new_state_revision_id,
        last_updated_utc=now_utc,
        index_registry=current_state.index_registry,
        tenant_portfolios=updated_portfolios,
    )

    state_revision_doc = StateRevisionMetadataSchema(
        state_revision_id=new_state_revision_id,
        epoch_id=new_epoch_id,
        epoch_alias=sanitized_alias,
        last_updated_utc=reset_iso_utc,
        cash_balance=BASELINE_STARTING_EQUITY_USD,
        total_equity=BASELINE_STARTING_EQUITY_USD,
        portfolio_heat_pct=0.0,
        open_positions_count=0,
        kill_switch_status="ARMED_READY",
        kill_switch_active=False,
    )

    # -------------------------------------------------------------------------
    # STEP 5: Continuous TWR Equity History Update (0.00% jump on reset day)
    # -------------------------------------------------------------------------
    existing_history, _ = gcs_reader.read_equity_history()
    normalized_history: List[Dict[str, Any]] = []
    for raw_pt in existing_history:
        if not isinstance(raw_pt, dict) or not raw_pt.get("date"):
            continue
        raw_val = float(raw_pt.get("raw_portfolio_value") or raw_pt.get("portfolio_nav") or BASELINE_STARTING_EQUITY_USD)
        cum_ret = float(
            raw_pt.get(
                "cumulative_algo_return_pct",
                round(((raw_val - BASELINE_STARTING_EQUITY_USD) / BASELINE_STARTING_EQUITY_USD) * 100.0, 4),
            )
        )
        normalized_history.append(
            {
                "date": str(raw_pt["date"]),
                "raw_portfolio_value": round(raw_val, 2),
                "portfolio_nav": round(raw_val, 2),
                "cumulative_algo_return_pct": round(cum_ret, 4),
                "epoch_id": int(raw_pt.get("epoch_id", old_epoch_id)),
                "epoch_marker": raw_pt.get("epoch_marker"),
                "heat_pct": float(raw_pt.get("heat_pct", 0.0)),
                "benchmark_iwm_norm": float(raw_pt.get("benchmark_iwm_norm", 100.0)),
                "benchmark_mdy_norm": float(raw_pt.get("benchmark_mdy_norm", 100.0)),
            }
        )

    continuous_twr_pct = _compute_continuous_twr(
        existing_points=normalized_history,
        prior_starting_equity=prior_starting_equity,
        closing_equity_before_reset=closing_equity_before_reset,
    )
    last_iwm = float(normalized_history[-1]["benchmark_iwm_norm"]) if normalized_history else 100.0
    last_mdy = float(normalized_history[-1]["benchmark_mdy_norm"]) if normalized_history else 100.0

    reset_point = EquityHistoryPointSchema(
        date=as_of.isoformat(),
        raw_portfolio_value=BASELINE_STARTING_EQUITY_USD,
        cumulative_algo_return_pct=continuous_twr_pct,
        epoch_id=new_epoch_id,
        epoch_marker=EpochMarkerSchema(epoch_id=new_epoch_id, alias=sanitized_alias),
        heat_pct=0.0,
        benchmark_iwm_norm=last_iwm,
        benchmark_mdy_norm=last_mdy,
    )
    reset_point_dict = reset_point.model_dump(mode="json")
    reset_point_dict["portfolio_nav"] = BASELINE_STARTING_EQUITY_USD

    # Replace same-date entry if resetting on the same calendar date, else append
    if normalized_history and normalized_history[-1]["date"] == as_of.isoformat():
        normalized_history[-1] = reset_point_dict
    else:
        normalized_history.append(reset_point_dict)

    # Append liquidated trades into state/trade_history.json
    existing_trade_history = storage_adapter.read_root_json("state/trade_history.json")
    trade_history_list: List[Dict[str, Any]] = (
        list(existing_trade_history) if isinstance(existing_trade_history, list) else []
    )
    for trade in all_liquidated_trades:
        trade_entry = trade.model_dump(mode="json")
        trade_entry["epoch_id"] = old_epoch_id
        trade_entry["state_revision_id"] = new_state_revision_id
        trade_history_list.append(trade_entry)

    telemetry_payload: Dict[str, Any] = {
        "eod_status": "IDLE",
        "last_successful_eod_timestamp": reset_iso_utc,
        "last_updated_utc": reset_iso_utc,
        "last_trading_date_processed": as_of.isoformat(),
        "trading_date": as_of.isoformat(),
        "current_portfolio_heat_pct": 0.0,
        "portfolio_heat_pct": 0.0,
        "open_positions_count": 0,
        "total_equity": BASELINE_STARTING_EQUITY_USD,
        "cash_balance": BASELINE_STARTING_EQUITY_USD,
        "kill_switch_status": "ARMED_READY",
        "kill_switch_active": False,
        "epoch_id": new_epoch_id,
        "epoch_alias": sanitized_alias,
        "state_revision_id": new_state_revision_id,
    }

    if not dry_run:
        # Persist root & state/* JSON artifacts with Layer 1 no-cache headers
        json_repo.save_state(reset_state_store)
        json_repo.save_eod_heartbeat(reset_state_store, trading_date=as_of, eod_status="IDLE")

        epochs_payload = updated_epochs_store.model_dump(mode="json")
        state_rev_payload = state_revision_doc.model_dump(mode="json")
        vp_payload = json.loads(reset_state_store.model_dump_json())

        gcs_reader.write_json_atomically("state/virtual_portfolio.json", vp_payload)
        gcs_reader.write_json_atomically("state/state.json", state_rev_payload)
        gcs_reader.write_json_atomically("state/portfolio_epochs.json", epochs_payload)
        gcs_reader.write_json_atomically("state/equity_history.json", normalized_history)
        gcs_reader.write_json_atomically("state/equity_curve.json", normalized_history)
        gcs_reader.write_json_atomically("state/trade_history.json", trade_history_list)
        gcs_reader.write_json_atomically("state/eod_telemetry.json", telemetry_payload)
        gcs_reader.write_json_atomically("state/eod_heartbeat.json", telemetry_payload)

        # Also mirror root-level E.1 paths in GCS & local data/ for direct contract reads
        storage_adapter.write_root_json("state.json", state_rev_payload)
        storage_adapter.write_root_json("portfolio_epochs.json", epochs_payload)
        storage_adapter.write_root_json("equity_history.json", normalized_history)
        storage_adapter.write_root_json("trade_history.json", trade_history_list)

        # Update user-scoped telemetry contracts & re-arm kill_switch_active=False
        primary_ledger = updated_portfolios.get(DEFAULT_ADMIN_PORTFOLIO_ID) or next(
            iter(updated_portfolios.values())
        )
        exporter = SirixCloudExporter(storage_adapter=storage_adapter, market_repo=market_repo)
        for uid in MANAGED_TENANT_USER_IDS:
            exporter.export_all(
                ledger=primary_ledger,
                user_id=uid,
                as_of_date=as_of,
                initial_equity=BASELINE_STARTING_EQUITY_USD,
            )
            raw_prefs = storage_adapter.read_user_json(uid, "preferences.json")
            prefs_obj = (
                UserPreferencesContract.model_validate(raw_prefs)
                if raw_prefs is not None
                else UserPreferencesContract()
            )
            rearmed_prefs = prefs_obj.model_copy(
                update={
                    "guardrails": prefs_obj.guardrails.model_copy(
                        update={"kill_switch_active": False}
                    )
                }
            )
            storage_adapter.write_user_json(
                uid,
                "preferences.json",
                rearmed_prefs.model_dump(mode="json"),
            )

        # ---------------------------------------------------------------------
        # STEP 6: Dispatch Structured Telegram Alert via NotificationHub
        # ---------------------------------------------------------------------
        hub = NotificationHub(settings=resolved_settings)
        hub.dispatch_epoch_reset_summary(
            closed_epoch_id=old_epoch_id,
            closed_epoch_alias=old_epoch_alias,
            closing_equity_before_reset=closing_equity_before_reset,
            closed_epoch_return_pct=closed_epoch_return_pct,
            new_epoch_id=new_epoch_id,
            new_epoch_alias=sanitized_alias,
            starting_equity=BASELINE_STARTING_EQUITY_USD,
            cumulative_algo_return_pct=continuous_twr_pct,
            liquidated_trades=all_liquidated_trades,
            state_revision_id=new_state_revision_id,
            reset_timestamp_utc=reset_iso_utc,
            triggered_by=triggered_by,
        )

        # Layer 2 Cloud Run Cache Invalidation Webhook
        _trigger_cloud_run_invalidation(
            cloud_run_url=os.environ.get("SIRIX_CLOUD_RUN_URL", ""),
            scheduler_token=os.environ.get("INTERNAL_SCHEDULER_TOKEN", ""),
        )

    summary = {
        "status": "DRY_RUN_VALIDATED" if dry_run else "EPOCH_RESET_COMPLETED",
        "closed_epoch_id": old_epoch_id,
        "closed_epoch_alias": old_epoch_alias,
        "closing_equity_before_reset": closing_equity_before_reset,
        "closed_epoch_return_pct": closed_epoch_return_pct,
        "positions_liquidated_count": positions_liquidated_count,
        "new_epoch_id": new_epoch_id,
        "new_epoch_alias": sanitized_alias,
        "starting_equity": BASELINE_STARTING_EQUITY_USD,
        "portfolio_heat_pct": 0.0,
        "kill_switch_status": "ARMED_READY",
        "cumulative_algo_return_pct": continuous_twr_pct,
        "state_revision_id": new_state_revision_id,
        "backup_prefix": backup_prefix,
        "reset_timestamp_utc": reset_iso_utc,
    }
    logger.info("E.1 Portfolio Epoch Reset Summary:\n%s", json.dumps(summary, indent=2))
    return summary


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SIRIX E.1 Controlled Portfolio Epoch Reset & 4-Layer Cache Invalidation"
    )
    parser.add_argument(
        "--epoch-alias",
        required=True,
        help="Human-readable alias for the new trading epoch (min 3 chars, safe characters only).",
    )
    parser.add_argument(
        "--confirm-reset",
        required=True,
        help="Strict double-confirmation safeguard. Must equal 'RESET' exactly.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Optional ISO settlement date override (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--triggered-by",
        default="GITHUB_ACTIONS_MANUAL",
        choices=["GITHUB_ACTIONS_MANUAL", "PWA_AUTHORIZED_USER"],
        help="Audit source identifier for portfolio_epochs.json.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and simulate calculations without modifying GCS or local files.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_cli_parser()
    args = parser.parse_args(argv)

    parsed_date: Optional[date] = None
    if args.date:
        parsed_date = date.fromisoformat(args.date.strip())

    try:
        execute_portfolio_epoch_reset(
            epoch_alias=args.epoch_alias,
            confirm_reset=args.confirm_reset,
            target_date=parsed_date,
            triggered_by=args.triggered_by,
            dry_run=bool(args.dry_run),
        )
        return 0
    except EpochResetValidationError as exc:
        logger.error("EPOCH RESET ABORTED (PRE-FLIGHT VALIDATION FAILED): %s", exc)
        return 1
    except Exception as exc:
        logger.exception("EPOCH RESET FAILED WITH UNEXPECTED ERROR: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
