from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import logging
import sys
import time
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

import pandas as pd

try:
    from src.config import (
        SystemSettings,
        get_active_indices,
        get_settings,
        load_index_registry,
    )
    from src.data_ingestion import (
        DataIngestionPipeline,
        MarketDataProvider,
        YFinanceMarketDataProvider,
    )
    from src.notifier import TelegramNotifier, TenantDailyReportPayload
    from src.quant_engine import (
        FeatureEngineer,
        MetaLabelingBacktestEngine,
        PrimaryScreeningEngine,
        TenantPortfolioReconciler,
    )
    from src.schemas import (
        ClosedTradeAuditSchema,
        DirectionalSignalSchema,
        IndexConfigSchema,
        MetaLabeledSignalSchema,
        MultiTenantStateStoreSchema,
        TripleBarrierPositionSchema,
        VirtualPortfolioLedgerSchema,
    )
    from src.storage import (
        DEFAULT_ADMIN_PORTFOLIO_ID,
        DEFAULT_ADMIN_USER_ID,
        JsonPortfolioStateRepository,
        MarketDataRepository,
        ParquetMarketDataRepository,
        PortfolioStateRepository,
    )
except ImportError:
    from config import (  # type: ignore[no-redef]
        SystemSettings,
        get_active_indices,
        get_settings,
        load_index_registry,
    )
    from data_ingestion import (  # type: ignore[no-redef]
        DataIngestionPipeline,
        MarketDataProvider,
        YFinanceMarketDataProvider,
    )
    from notifier import TelegramNotifier, TenantDailyReportPayload  # type: ignore[no-redef]
    from quant_engine import (  # type: ignore[no-redef]
        FeatureEngineer,
        MetaLabelingBacktestEngine,
        PrimaryScreeningEngine,
        TenantPortfolioReconciler,
    )
    from schemas import (  # type: ignore[no-redef]
        ClosedTradeAuditSchema,
        DirectionalSignalSchema,
        IndexConfigSchema,
        MetaLabeledSignalSchema,
        MultiTenantStateStoreSchema,
        TripleBarrierPositionSchema,
        VirtualPortfolioLedgerSchema,
    )
    from storage import (  # type: ignore[no-redef]
        DEFAULT_ADMIN_PORTFOLIO_ID,
        DEFAULT_ADMIN_USER_ID,
        JsonPortfolioStateRepository,
        MarketDataRepository,
        ParquetMarketDataRepository,
        PortfolioStateRepository,
    )


# =============================================================================
# 1. STRUCTURED LOGGING CONFIGURATION
# =============================================================================


def configure_logging(level: str = "INFO") -> logging.Logger:
    """
    Configures clean timestamped UTC stdout logging.
    """
    numeric_level = getattr(logging, level.strip().upper(), logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    formatter.converter = time.gmtime

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    if not root_logger.handlers:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)

    return logging.getLogger("SwingQuantEngine.Orchestrator")


# =============================================================================
# 2. AUTONOMOUS HEADLESS QUANT PIPELINE ORCHESTRATOR
# =============================================================================


class QuantPipelineOrchestrator:
    """
    Autonomous Headless Daily Execution Worker enforcing the two-stage
    Global Shared Compute / Isolated Tenant Reconciliation architecture
    and the < 15-minute (900s) execution SLA.
    """

    SLA_MAX_SECONDS = 900.0

    def __init__(
        self,
        settings: Optional[SystemSettings] = None,
        provider: Optional[MarketDataProvider] = None,
        market_repo: Optional[MarketDataRepository] = None,
        state_repo: Optional[PortfolioStateRepository] = None,
        notifier: Optional[TelegramNotifier] = None,
    ) -> None:
        self.settings: SystemSettings = settings or get_settings()
        self.logger = logging.getLogger("SwingQuantEngine.Orchestrator")

        self.provider: MarketDataProvider = provider or YFinanceMarketDataProvider(
            settings=self.settings
        )
        self.market_repo: MarketDataRepository = market_repo or ParquetMarketDataRepository(
            settings=self.settings
        )
        self.state_repo: PortfolioStateRepository = state_repo or JsonPortfolioStateRepository(
            settings=self.settings
        )
        self.notifier: TelegramNotifier = notifier or TelegramNotifier(settings=self.settings)

        self.ingestion_pipeline = DataIngestionPipeline(
            provider=self.provider,
            repository=self.market_repo,
            settings=self.settings,
        )
        self.screening_engine = PrimaryScreeningEngine(settings=self.settings)
        self.backtest_engine = MetaLabelingBacktestEngine(settings=self.settings)
        self.reconciler = TenantPortfolioReconciler(settings=self.settings)

    def ensure_default_tenant_initialized(
        self,
        state: MultiTenantStateStoreSchema,
        as_of_date: date,
    ) -> MultiTenantStateStoreSchema:
        """
        If `state.tenant_portfolios` is empty on first cold-start boot, automatically
        initializes a default primary shadow portfolio ($100,000 cash & total equity,
        max_portfolio_heat_pct = settings.default_max_portfolio_heat_pct,
        subscribed_indices = list(active_indices.keys())) and persists it via `state_repo.save_state`.
        """
        if state.tenant_portfolios:
            return state

        active_index_ids = [
            idx_id for idx_id, cfg in state.index_registry.items() if cfg.is_active
        ]
        if not active_index_ids:
            active_index_ids = list(state.index_registry.keys())

        default_ledger = VirtualPortfolioLedgerSchema(
            portfolio_id=DEFAULT_ADMIN_PORTFOLIO_ID,
            user_id=DEFAULT_ADMIN_USER_ID,
            portfolio_name="Primary Swing Shadow Portfolio",
            as_of_date=as_of_date,
            cash_balance=100_000.0,
            total_equity=100_000.0,
            max_portfolio_heat_pct=self.settings.default_max_portfolio_heat_pct,
            max_concurrent_positions=10,
            subscribed_indices=active_index_ids,
        )

        updated_portfolios = dict(state.tenant_portfolios)
        updated_portfolios[default_ledger.portfolio_id] = default_ledger

        initialized_state = MultiTenantStateStoreSchema(
            schema_version=state.schema_version,
            last_updated_utc=datetime.now(timezone.utc),
            index_registry=state.index_registry,
            tenant_portfolios=updated_portfolios,
        )

        self.state_repo.save_state(initialized_state)
        self.logger.info(
            f"Initialized default primary shadow portfolio ({default_ledger.portfolio_id}) "
            f"subscribed to indices: {active_index_ids}."
        )
        return initialized_state

    def run_daily_cycle(self, as_of_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Executes the five-phase daily EOD quantitative execution cycle:
        Phase 1: Load Multi-Tenant State & Active Index Registry
        Phase 2: Global Market Data Ingestion & t-1 Split Guard
        Phase 3: Global Shared Compute (Primary Screening + 500d Meta-Labeling Backtest)
        Phase 4: Per-Tenant Isolated Reconciliation & Execution Loop
        Phase 5: SLA Verification & Global Circuit Breaker
        """
        start_time = time.monotonic()
        target_date: date = as_of_date or datetime.now(timezone.utc).date()

        self.logger.info(
            f"=== Starting QuantPipelineOrchestrator Cycle (target_date={target_date}, "
            f"environment={self.settings.environment}, dry_run={self.settings.dry_run}) ==="
        )

        try:
            # -----------------------------------------------------------------
            # Phase 1 — Load Multi-Tenant State & Active Index Registry
            # -----------------------------------------------------------------
            state = self.state_repo.load_state()
            if not state.index_registry:
                registry = load_index_registry(self.settings.index_registry_path)
                state = MultiTenantStateStoreSchema(
                    schema_version=state.schema_version,
                    last_updated_utc=state.last_updated_utc,
                    index_registry=registry,
                    tenant_portfolios=state.tenant_portfolios,
                )

            state = self.ensure_default_tenant_initialized(state, target_date)

            active_indices: Dict[str, IndexConfigSchema] = {
                idx_id: cfg
                for idx_id, cfg in state.index_registry.items()
                if cfg.is_active
            }
            if not active_indices:
                active_indices = get_active_indices(self.settings)

            # Collect union and intersection of open positions across all tenants:
            # - `all_open_position_tickers` (union): MUST be synced so Phase 4 can evaluate EOD barriers & ratchets.
            # - `universally_held_tickers` (intersection): skipped during Phase 3 candidate screening only if held by EVERY tenant.
            tenant_holding_sets: List[Set[str]] = [
                {t.strip().upper() for t in ledger.open_positions.keys()}
                for ledger in state.tenant_portfolios.values()
            ]
            all_open_position_tickers: Set[str] = (
                set().union(*tenant_holding_sets) if tenant_holding_sets else set()
            )
            universally_held_tickers: Set[str] = (
                set.intersection(*tenant_holding_sets) if tenant_holding_sets else set()
            )
            # Only exclude from ingestion those universally held tickers that do not need EOD open-position bar evaluation
            global_excluded_tickers: Set[str] = universally_held_tickers - all_open_position_tickers

            # -----------------------------------------------------------------
            # Phase 2 — Global Market Data Ingestion & t-1 Split Guard
            # -----------------------------------------------------------------
            synced_constituents_map = self.ingestion_pipeline.sync_universe_ohlcv(
                active_indices=active_indices,
                excluded_tickers=global_excluded_tickers,
                as_of_date=target_date,
            )

            # Ensure any open position tickers not already part of active index rosters are also synced
            all_synced_symbols: Set[str] = set()
            for tickers_list in synced_constituents_map.values():
                all_synced_symbols.update(tickers_list)

            unsynced_held_tickers = sorted(all_open_position_tickers - all_synced_symbols)
            if unsynced_held_tickers:
                for ticker in unsynced_held_tickers:
                    cached_df = self.market_repo.load_ohlcv(
                        ticker,
                        lookback_days=self.settings.backtest_lookback_days,
                    )
                    if cached_df is None or cached_df.empty or cached_df.index[-1].date() < target_date:
                        fetched_map = self.provider.fetch_daily_ohlcv_batch(
                            tickers=[ticker],
                            start_date=date.fromordinal(target_date.toordinal() - 35),
                            end_date=target_date,
                        )
                        if ticker in fetched_map:
                            self.ingestion_pipeline._upsert_to_repository(ticker, fetched_map[ticker])

            # Load benchmark OHLCV frames from market_repo
            benchmark_frames: Dict[str, pd.DataFrame] = {}
            for idx_id, cfg in active_indices.items():
                bench_symbol = cfg.benchmark_ticker.strip().upper()
                if bench_symbol not in benchmark_frames:
                    bench_df = self.market_repo.load_ohlcv(
                        bench_symbol,
                        lookback_days=self.settings.backtest_lookback_days,
                    )
                    if bench_df is not None and not bench_df.empty:
                        benchmark_frames[bench_symbol] = bench_df

            # -----------------------------------------------------------------
            # Phase 3 — Global Shared Compute (Primary Screening + 500d Meta-Labeling)
            # -----------------------------------------------------------------
            primary_signals_by_index: Dict[str, List[DirectionalSignalSchema]] = {}
            approved_signals: List[MetaLabeledSignalSchema] = []
            vetoed_signals: List[MetaLabeledSignalSchema] = []

            for idx_id, idx_cfg in active_indices.items():
                bench_symbol = idx_cfg.benchmark_ticker.strip().upper()
                bench_df = benchmark_frames.get(bench_symbol)
                if bench_df is None or bench_df.empty:
                    self.logger.warning(
                        f"Benchmark '{bench_symbol}' unavailable for index '{idx_id}'; skipping screening."
                    )
                    continue

                constituent_tickers = synced_constituents_map.get(idx_id, [])
                ohlcv_index_map: Dict[str, pd.DataFrame] = {}
                for ticker in constituent_tickers:
                    if ticker in universally_held_tickers:
                        continue
                    t_df = self.market_repo.load_ohlcv(
                        ticker,
                        lookback_days=self.settings.backtest_lookback_days,
                    )
                    if t_df is not None and not t_df.empty:
                        ohlcv_index_map[ticker] = t_df

                spread_map = self.provider.fetch_current_quotes_spread_proxy(
                    list(ohlcv_index_map.keys())
                )

                shortlisted_primary = self.screening_engine.screen_index_universe(
                    ohlcv_map=ohlcv_index_map,
                    benchmark_df=bench_df,
                    index_cfg=idx_cfg,
                    as_of_date=target_date,
                    spread_map=spread_map,
                    excluded_tickers=universally_held_tickers,
                    top_n=self.settings.top_n_candidates_per_index,
                )
                primary_signals_by_index[idx_id] = shortlisted_primary

                for prim_sig in shortlisted_primary:
                    asset_df = ohlcv_index_map.get(prim_sig.ticker)
                    if asset_df is None or asset_df.empty:
                        continue

                    meta_sig = self.backtest_engine.evaluate_candidate(
                        signal=prim_sig,
                        asset_df=asset_df,
                        benchmark_df=bench_df,
                        index_cfg=idx_cfg,
                    )
                    if meta_sig.is_approved:
                        approved_signals.append(meta_sig)
                    else:
                        vetoed_signals.append(meta_sig)

            # -----------------------------------------------------------------
            # Phase 4 — Per-Tenant Isolated Reconciliation & Execution Loop
            # -----------------------------------------------------------------
            tenant_reports: Dict[UUID, TenantDailyReportPayload] = {}
            total_opened_count = 0
            total_closed_count = 0

            for portfolio_id, ledger in state.tenant_portfolios.items():
                # Load OHLCV frames for all open positions held by this tenant
                tenant_open_ohlcv: Dict[str, pd.DataFrame] = {}
                for held_ticker in list(ledger.open_positions.keys()):
                    held_df = self.market_repo.load_ohlcv(
                        held_ticker,
                        lookback_days=self.settings.screening_lookback_days,
                    )
                    if held_df is not None and not held_df.empty:
                        held_df = held_df.copy()
                        held_df["ATR_14"] = FeatureEngineer.compute_atr_14(held_df, period=14)
                        tenant_open_ohlcv[held_ticker] = held_df

                closed_trades: List[ClosedTradeAuditSchema] = (
                    self.reconciler.reconcile_open_positions(
                        ledger=ledger,
                        ohlcv_map=tenant_open_ohlcv,
                        index_registry=state.index_registry,
                        as_of_date=target_date,
                    )
                )

                opened_positions: List[TripleBarrierPositionSchema] = (
                    self.reconciler.allocate_new_signals(
                        ledger=ledger,
                        approved_signals=approved_signals,
                        as_of_date=target_date,
                    )
                )

                total_closed_count += len(closed_trades)
                total_opened_count += len(opened_positions)

                # Persist updated state atomically per tenant reconciliation
                if not self.settings.dry_run:
                    self.state_repo.save_state(state)

                report_payload = TenantDailyReportPayload(
                    as_of_date=target_date,
                    ledger=ledger,
                    opened_positions=opened_positions,
                    closed_trades=closed_trades,
                    approved_signals=approved_signals,
                    vetoed_signals=vetoed_signals,
                    dry_run=self.settings.dry_run,
                )
                tenant_reports[portfolio_id] = report_payload
                self.notifier.dispatch_tenant_report(report_payload)

            if self.settings.dry_run:
                self.logger.info(
                    "Dry-run mode active: skipped production state persistence to disk."
                )

            # -----------------------------------------------------------------
            # Phase 5 — SLA Verification & Telemetry Summary
            # -----------------------------------------------------------------
            elapsed_sec = round(time.monotonic() - start_time, 2)
            if elapsed_sec > self.SLA_MAX_SECONDS:
                self.logger.warning(
                    f"SLA WARNING: Daily quant cycle elapsed {elapsed_sec:.2f}s, "
                    f"exceeding the {self.SLA_MAX_SECONDS:.1f}s (15-minute) ceiling!"
                )
            else:
                self.logger.info(
                    f"Daily quant cycle completed in {elapsed_sec:.2f}s "
                    f"(approved_signals={len(approved_signals)}, vetoed_signals={len(vetoed_signals)}, "
                    f"opened={total_opened_count}, closed={total_closed_count})."
                )

            return {
                "as_of_date": target_date,
                "elapsed_sec": elapsed_sec,
                "active_indices": list(active_indices.keys()),
                "primary_signals_count": sum(len(v) for v in primary_signals_by_index.values()),
                "approved_signals": approved_signals,
                "vetoed_signals": vetoed_signals,
                "tenant_reports": tenant_reports,
                "state": state,
            }

        except Exception as exc:
            self.logger.exception(f"CRITICAL PIPELINE FAILURE on {target_date}: {exc}")
            self.notifier.dispatch_critical_alert(
                error_message=str(exc),
                stage="QuantPipelineOrchestrator.run_daily_cycle",
                as_of_date=target_date,
            )
            raise


# =============================================================================
# 3. CLI ENTRYPOINT
# =============================================================================


def parse_cli_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Swing Quant Engine - Autonomous Headless Daily Execution Worker"
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "sandbox"],
        default="daily",
        help="Execution mode: 'daily' production/dry-run worker or 'sandbox' end-to-end harness.",
    )
    parser.add_argument(
        "--date",
        "--as-of-date",
        dest="date",
        type=str,
        default=None,
        help="Optional ISO YYYY-MM-DD target EOD date override for deterministic replays.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute pipeline in dry-run mode without mutating persistent production state.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_cli_args(argv)
    base_settings = get_settings()

    if args.dry_run and not base_settings.dry_run:
        settings = base_settings.model_copy(update={"dry_run": True})
    else:
        settings = base_settings

    configure_logging(settings.log_level)

    if args.mode == "sandbox":
        try:
            from src.sandbox_runner import SandboxDryRunHarness
        except ImportError:
            from sandbox_runner import SandboxDryRunHarness  # type: ignore[no-redef]

        harness = SandboxDryRunHarness()
        return 0 if harness.run() else 1

    target_date: Optional[date] = (
        date.fromisoformat(args.date) if args.date else None
    )
    orchestrator = QuantPipelineOrchestrator(settings=settings)
    orchestrator.run_daily_cycle(as_of_date=target_date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
