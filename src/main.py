from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import logging
import sys
from typing import Dict, List
from uuid import UUID

from config import EngineSettings, SecretRedactingFilter
from data_ingestion import SmartSlidingWindowOrchestrator, YFinanceProvider
from notifier import TelegramDispatchService
from quant_engine import SwingQuantEngineOrchestrator
from sandbox_runner import SandboxDryRunVerifier
from storage import JsonFilePortfolioRepository


def configure_logging(settings: EngineSettings) -> None:
    explicit_secrets: List[str] = []
    if settings.telegram_bot_token:
        explicit_secrets.append(settings.telegram_bot_token.get_secret_value())
    if settings.jwt_secret_key:
        explicit_secrets.append(settings.jwt_secret_key.get_secret_value())
    if settings.database_url:
        explicit_secrets.append(settings.database_url.get_secret_value())

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(SecretRedactingFilter(explicit_secrets=explicit_secrets))
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[handler],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Swing Quant Engine - Autonomous Headless EOD Execution Worker"
    )
    parser.add_argument(
        "--as-of-date",
        type=str,
        default=None,
        help="Target EOD market date in YYYY-MM-DD format (defaults to today UTC).",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default="default",
        help="Target tenant user_id UUID or 'default' for isolated execution.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run full pipeline and sandbox verification without mutating production portfolio state.",
    )
    return parser.parse_args()


def main() -> int:
    settings = EngineSettings()
    configure_logging(settings)
    logger = logging.getLogger("SwingQuantEngine.Main")
    args = parse_args()

    target_date = (
        date.fromisoformat(args.as_of_date)
        if args.as_of_date
        else datetime.now(tz=timezone.utc).date()
    )
    logger.info(
        f"=== Starting Autonomous Swing Quant Engine Cycle (as_of_date={target_date}, "
        f"user_id={args.user_id}, dry_run={args.dry_run}) ==="
    )

    # In --dry-run mode, run the deterministic 5-Day Lifecycle + 500-Day Walk-Forward Sandbox Suite
    if args.dry_run:
        verifier = SandboxDryRunVerifier(settings=settings)
        ok = verifier.run_full_verification_suite(send_telegram=False)
        if not ok:
            logger.error("Sandbox dry-run verification failed acceptance gates.")
            return 1
        logger.info("Sandbox dry-run completed successfully with zero production state mutations.")
        return 0

    repo = JsonFilePortfolioRepository(
        state_path=settings.state_store_path,
        index_registry_path=settings.index_registry_path,
    )
    state_store = repo.load_or_initialize_state(as_of_date=target_date)

    # Filter by specific tenant --user-id if a UUID was provided
    if args.user_id and args.user_id.lower() != "default":
        target_uuid = UUID(args.user_id)
        filtered_portfolios = {
            pid: p
            for pid, p in state_store.tenant_portfolios.items()
            if p.user_id == target_uuid
        }
        if not filtered_portfolios:
            logger.error(f"No portfolio found for tenant user_id={target_uuid}")
            return 1
        state_store.tenant_portfolios = filtered_portfolios

    provider = YFinanceProvider(constituent_lists_dir=settings.constituents_dir)
    window_manager = SmartSlidingWindowOrchestrator(
        provider=provider,
        cache_path=settings.parquet_cache_path,
        max_window_bars=500,
        min_required_bars=250,
    )

    market_df, _ = window_manager.sync_daily_market_window(
        state_store=state_store,
        as_of_date=target_date,
    )

    index_constituents_map: Dict[str, List[str]] = {
        idx_id: provider.fetch_index_constituents(idx_id)
        for idx_id, cfg in state_store.index_registry.items()
        if cfg.is_active
    }

    quant_orchestrator = SwingQuantEngineOrchestrator()
    dispatch_telemetry = quant_orchestrator.execute_daily_quant_cycle(
        market_df=market_df,
        state_store=state_store,
        index_constituents_map=index_constituents_map,
        as_of_date=target_date,
    )

    repo.save_state_atomically(state_store)

    notifier = TelegramDispatchService(settings=settings)
    for portfolio_id, telemetry in dispatch_telemetry.items():
        tenant_portfolio = state_store.tenant_portfolios[portfolio_id]
        notifier.dispatch_tenant_daily_report(
            portfolio=tenant_portfolio,
            opened_positions=telemetry["opened_positions"],
            closed_trades=telemetry["closed_trades"],
            approved_signals=telemetry["approved_signals"],
            as_of_date=target_date,
            dry_run=args.dry_run,
        )

    logger.info(
        f"=== Completed Swing Quant Engine Cycle for {len(dispatch_telemetry)} tenant portfolio(s) ==="
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
