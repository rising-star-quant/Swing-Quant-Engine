from __future__ import annotations

from datetime import date, datetime, timezone
import logging
from pathlib import Path
import sys
import tempfile
from typing import Dict, List, Optional, Sequence
from uuid import UUID, uuid4

import numpy as np
import pandas as pd

try:
    from src.config import SystemSettings, load_index_registry
    from src.data_ingestion import MarketDataProvider
    from src.main import QuantPipelineOrchestrator, configure_logging
    from src.notifier import TelegramNotifier
    from src.schemas import (
        IndexConfigSchema,
        IndexTier,
        MultiTenantStateStoreSchema,
        VirtualPortfolioLedgerSchema,
    )
    from src.storage import JsonPortfolioStateRepository, ParquetMarketDataRepository
except ImportError:
    from config import SystemSettings, load_index_registry  # type: ignore[no-redef]
    from data_ingestion import MarketDataProvider  # type: ignore[no-redef]
    from main import QuantPipelineOrchestrator, configure_logging  # type: ignore[no-redef]
    from notifier import TelegramNotifier  # type: ignore[no-redef]
    from schemas import (  # type: ignore[no-redef]
        IndexConfigSchema,
        IndexTier,
        MultiTenantStateStoreSchema,
        VirtualPortfolioLedgerSchema,
    )
    from storage import (  # type: ignore[no-redef]
        JsonPortfolioStateRepository,
        ParquetMarketDataRepository,
    )

logger = logging.getLogger("SwingQuantEngine.SandboxRunner")


# =============================================================================
# 1. DETERMINISTIC SYNTHETIC MARKET DATA PROVIDER
# =============================================================================


class SyntheticMarketDataProvider(MarketDataProvider):
    """
    Deterministic seeded (`numpy.random.default_rng(seed)`) market data generator
    producing realistic 500-trading-day daily OHLCV DataFrames (`Open`, `High`,
    `Low`, `Close`, `Volume`) ending on `as_of_date` for benchmark ETFs (`IWM`,
    `MDY`, `SPY`) and synthetic constituent rosters (16 tickers per index).

    Deliberately engineers multiple liquid, uptrending breakout candidates per index
    with positive 500-day Triple-Barrier historical expectancy (`EV > 0`),
    Price >= $25.00, and ADV >= 1,500,000 shares so the entire screening ->
    500d backtest -> Meta-Labeling -> Volatility-Parity sizing -> Virtual Ledger
    allocation pipeline exercises end-to-end.
    """

    def __init__(
        self,
        seed: int = 42,
        tickers_per_index: int = 16,
        total_trading_days: int = 520,
        final_sim_date: date = date(2026, 11, 12),
    ) -> None:
        self.seed = seed
        self.tickers_per_index = max(15, tickers_per_index)
        self.total_trading_days = max(505, total_trading_days)
        self.final_sim_date = final_sim_date
        self._series_cache: Dict[str, pd.DataFrame] = {}
        self._rosters: Dict[str, List[str]] = {}
        self._build_deterministic_universe()

    def _build_deterministic_universe(self) -> None:
        bdate_index = pd.bdate_range(
            end=pd.Timestamp(self.final_sim_date),
            periods=self.total_trading_days,
        ).normalize()
        bdate_index.name = "Date"

        # 1. Generate Benchmark ETFs (IWM, MDY, SPY) with moderate steady drift
        for bench_idx, bench_symbol in enumerate(("IWM", "MDY", "SPY")):
            rng = np.random.default_rng(self.seed + 100 + bench_idx)
            self._series_cache[bench_symbol] = self._generate_benchmark_df(
                bdate_index=bdate_index,
                rng=rng,
                base_price=180.0 + bench_idx * 40.0,
            )

        # 2. Generate 16 synthetic constituents per index tier
        index_prefixes = ("RUT", "MID", "SPX", "RUT_2000", "SP_400", "SP_500")
        for group_idx, prefix in enumerate(index_prefixes):
            roster: List[str] = []
            for k in range(1, self.tickers_per_index + 1):
                ticker = f"{prefix[:3]}Q{k:02d}"
                roster.append(ticker)
                if ticker in self._series_cache:
                    continue

                ticker_rng = np.random.default_rng(self.seed + group_idx * 1000 + k)
                # First 4 tickers per index are engineered as high-expectancy breakout leaders
                is_breakout_leader = k <= 4
                self._series_cache[ticker] = self._generate_constituent_df(
                    bdate_index=bdate_index,
                    rng=ticker_rng,
                    is_breakout_leader=is_breakout_leader,
                    base_price=35.0 + (k * 2.5),
                )
            self._rosters[prefix] = sorted(set(roster))

    @staticmethod
    def _generate_benchmark_df(
        bdate_index: pd.DatetimeIndex,
        rng: np.random.Generator,
        base_price: float,
    ) -> pd.DataFrame:
        n = len(bdate_index)
        opens = np.zeros(n, dtype=np.float64)
        highs = np.zeros(n, dtype=np.float64)
        lows = np.zeros(n, dtype=np.float64)
        closes = np.zeros(n, dtype=np.float64)
        volumes = np.zeros(n, dtype=np.float64)

        price = base_price
        for i in range(n):
            ret = float(rng.normal(0.0003, 0.006))
            close_p = max(25.0, price * (1.0 + ret))
            open_p = close_p * (1.0 - float(rng.uniform(-0.002, 0.002)))
            high_p = max(open_p, close_p) * (1.0 + float(rng.uniform(0.002, 0.006)))
            low_p = min(open_p, close_p) * (1.0 - float(rng.uniform(0.002, 0.006)))
            vol = float(rng.uniform(4_000_000.0, 6_500_000.0))

            opens[i] = round(open_p, 4)
            highs[i] = round(high_p, 4)
            lows[i] = round(low_p, 4)
            closes[i] = round(close_p, 4)
            volumes[i] = round(vol, 0)
            price = close_p

        return pd.DataFrame(
            {
                "Open": opens,
                "High": highs,
                "Low": lows,
                "Close": closes,
                "Volume": volumes,
            },
            index=bdate_index,
        )

    @staticmethod
    def _generate_constituent_df(
        bdate_index: pd.DatetimeIndex,
        rng: np.random.Generator,
        is_breakout_leader: bool,
        base_price: float,
    ) -> pd.DataFrame:
        """
        Generates a 520-bar OHLCV trajectory:
        - If `is_breakout_leader` is True:
          Maintains a steady structural uptrend (`Close > SMA_50 > SMA_200`, `Price >= $35`,
          `ADV >= 1,800,000`) and produces periodic 20-day high breakouts on 2.4x volume
          followed by strong multi-day follow-through rallies (so 500d historical Triple-Barrier
          simulations achieve high win rate and positive R-multiple expectancy), plus
          consecutive breakouts on the final 3 simulation sessions (`T-2`, `T-1`, `T`).
        """
        n = len(bdate_index)
        opens = np.zeros(n, dtype=np.float64)
        highs = np.zeros(n, dtype=np.float64)
        lows = np.zeros(n, dtype=np.float64)
        closes = np.zeros(n, dtype=np.float64)
        volumes = np.zeros(n, dtype=np.float64)

        price = max(30.0, base_price)
        follow_through_Remaining = 0

        for i in range(n):
            if is_breakout_leader:
                is_historical_trigger = (i >= 210) and (i < n - 18) and ((i - 210) % 28 == 0)
                is_final_window_trigger = i >= n - 3

                if is_historical_trigger or is_final_window_trigger:
                    prior_20_high = float(np.max(highs[max(0, i - 20) : i])) if i > 0 else price
                    close_p = max(price * 1.032, prior_20_high * 1.012)
                    open_p = close_p * 0.985
                    high_p = close_p * 1.004
                    low_p = open_p * 0.996
                    vol = float(rng.uniform(4_200_000.0, 5_200_000.0))
                    if is_historical_trigger:
                        follow_through_Remaining = 5
                elif follow_through_Remaining > 0:
                    # Strong post-breakout follow-through so Upper Take-Profit barrier is reached in backtest
                    close_p = price * 1.018
                    open_p = price * 1.002
                    high_p = close_p * 1.008
                    low_p = open_p * 0.997
                    vol = float(rng.uniform(2_200_000.0, 2_800_000.0))
                    follow_through_Remaining -= 1
                else:
                    # Controlled low-volatility uptrend consolidation
                    ret = float(rng.normal(0.0014, 0.0035))
                    close_p = max(28.0, price * (1.0 + ret))
                    open_p = close_p * 0.998
                    high_p = max(open_p, close_p) * 1.004
                    low_p = min(open_p, close_p) * 0.996
                    vol = float(rng.uniform(1_600_000.0, 2_000_000.0))
            else:
                # Range-bound / moderate noise stock
                ret = float(rng.normal(0.0001, 0.009))
                close_p = max(25.0, price * (1.0 + ret))
                open_p = close_p * (1.0 + float(rng.uniform(-0.003, 0.003)))
                high_p = max(open_p, close_p) * 1.007
                low_p = min(open_p, close_p) * 0.993
                vol = float(rng.uniform(1_500_000.0, 2_100_000.0))

            opens[i] = round(open_p, 4)
            highs[i] = round(high_p, 4)
            lows[i] = round(low_p, 4)
            closes[i] = round(close_p, 4)
            volumes[i] = round(vol, 0)
            price = close_p

        return pd.DataFrame(
            {
                "Open": opens,
                "High": highs,
                "Low": lows,
                "Close": closes,
                "Volume": volumes,
            },
            index=bdate_index,
        )

    def fetch_daily_ohlcv_batch(
        self,
        tickers: Sequence[str],
        start_date: date,
        end_date: date,
    ) -> Dict[str, pd.DataFrame]:
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        batch_out: Dict[str, pd.DataFrame] = {}

        for raw_t in tickers:
            t = raw_t.strip().upper()
            if t not in self._series_cache:
                rng = np.random.default_rng(self.seed + abs(hash(t)) % 10_000)
                bdate_idx = pd.bdate_range(
                    end=pd.Timestamp(self.final_sim_date),
                    periods=self.total_trading_days,
                ).normalize()
                bdate_idx.name = "Date"
                self._series_cache[t] = self._generate_constituent_df(
                    bdate_index=bdate_idx,
                    rng=rng,
                    is_breakout_leader=False,
                    base_price=40.0,
                )

            full_df = self._series_cache[t]
            sliced = full_df.loc[(full_df.index >= start_ts) & (full_df.index <= end_ts)].copy()
            if not sliced.empty:
                batch_out[t] = sliced

        return batch_out

    def fetch_index_constituents(self, index_config: IndexConfigSchema) -> List[str]:
        idx_id = index_config.index_id.strip().upper()
        if idx_id in self._rosters:
            return list(self._rosters[idx_id])
        prefix = "RUT" if index_config.tier == IndexTier.SMALL_CAP else (
            "MID" if index_config.tier == IndexTier.MID_CAP else "SPX"
        )
        return list(self._rosters[prefix])

    def fetch_current_quotes_spread_proxy(self, tickers: Sequence[str]) -> Dict[str, float]:
        return {t.strip().upper(): 0.0008 for t in tickers if t and t.strip()}


# =============================================================================
# 2. END-TO-END SANDBOX DRY-RUN HARNESS
# =============================================================================


class SandboxDryRunHarness:
    """
    Isolated End-to-End Sandbox Dry-Run Harness (Step E.2):
    - Creates an isolated temporary sandbox workspace (`tempfile.TemporaryDirectory`)
      with dedicated Parquet cache and `sandbox_virtual_portfolio.json`.
    - Seeds 2 distinct isolated tenant portfolios (`Tenant A` and `Tenant B`) with
      distinct UUIDs, initial $100,000 equity, 6.0% Portfolio Heat cap, and
      overlapping/distinct `subscribed_indices`.
    - Executes a 3-day simulated EOD walk-forward (`Day T-2`, `Day T-1`, `Day T`)
      through the real `QuantPipelineOrchestrator` with `dry_run=True`, then persists
      and verifies round-trip JSON state integrity.
    """

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.logger = logging.getLogger("SwingQuantEngine.SandboxRunner")

    def run(self) -> bool:
        configure_logging("INFO")
        self.logger.info("=== INITIALIZING ISOLATED END-TO-END SANDBOX DRY-RUN HARNESS ===")

        try:
            with tempfile.TemporaryDirectory(prefix="swing_quant_sandbox_") as tmp_dir:
                sandbox_root = Path(tmp_dir).resolve()
                parquet_dir = sandbox_root / "ohlcv_parquet"
                state_file = sandbox_root / "sandbox_virtual_portfolio.json"

                base_repo_dir = Path(__file__).resolve().parent.parent
                registry_path = base_repo_dir / "config" / "index_registry.json"
                index_registry = load_index_registry(registry_path)
                active_index_ids = [
                    idx_id for idx_id, cfg in index_registry.items() if cfg.is_active
                ]
                if not active_index_ids:
                    active_index_ids = list(index_registry.keys())

                sandbox_settings = SystemSettings(
                    environment="sandbox",
                    log_level="INFO",
                    dry_run=True,
                    base_dir=base_repo_dir,
                    index_registry_path=registry_path,
                    parquet_data_dir=parquet_dir,
                    virtual_portfolio_path=state_file,
                )

                # Define 3 consecutive business days (Day T-2, Day T-1, Day T)
                sim_days: List[date] = [
                    date(2026, 11, 10),
                    date(2026, 11, 11),
                    date(2026, 11, 12),
                ]
                seed_date = date(2026, 11, 9)

                # Seed 2 distinct isolated tenants (Tenant A: all active indices, Tenant B: single index)
                tenant_a_user_id: UUID = uuid4()
                tenant_a_portfolio_id: UUID = uuid4()
                tenant_b_user_id: UUID = uuid4()
                tenant_b_portfolio_id: UUID = uuid4()

                tenant_a_indices = list(active_index_ids)
                tenant_b_indices = [active_index_ids[0]]

                ledger_a = VirtualPortfolioLedgerSchema(
                    portfolio_id=tenant_a_portfolio_id,
                    user_id=tenant_a_user_id,
                    portfolio_name="Tenant A Multi-Index Alpha Fund",
                    as_of_date=seed_date,
                    cash_balance=100_000.0,
                    total_equity=100_000.0,
                    max_portfolio_heat_pct=0.06,
                    max_concurrent_positions=10,
                    subscribed_indices=tenant_a_indices,
                )

                ledger_b = VirtualPortfolioLedgerSchema(
                    portfolio_id=tenant_b_portfolio_id,
                    user_id=tenant_b_user_id,
                    portfolio_name="Tenant B Focused Small-Cap Portfolio",
                    as_of_date=seed_date,
                    cash_balance=100_000.0,
                    total_equity=100_000.0,
                    max_portfolio_heat_pct=0.06,
                    max_concurrent_positions=10,
                    subscribed_indices=tenant_b_indices,
                )

                initial_state = MultiTenantStateStoreSchema(
                    index_registry=index_registry,
                    tenant_portfolios={
                        tenant_a_portfolio_id: ledger_a,
                        tenant_b_portfolio_id: ledger_b,
                    },
                )

                state_repo = JsonPortfolioStateRepository(
                    settings=sandbox_settings,
                    state_path=state_file,
                    index_registry_path=registry_path,
                )
                state_repo.save_state(initial_state)

                market_repo = ParquetMarketDataRepository(settings=sandbox_settings)
                synthetic_provider = SyntheticMarketDataProvider(
                    seed=self.seed,
                    tickers_per_index=16,
                    total_trading_days=520,
                    final_sim_date=sim_days[-1],
                )
                notifier = TelegramNotifier(settings=sandbox_settings)

                orchestrator = QuantPipelineOrchestrator(
                    settings=sandbox_settings,
                    provider=synthetic_provider,
                    market_repo=market_repo,
                    state_repo=state_repo,
                    notifier=notifier,
                )

                last_cycle_result: Optional[Dict] = None
                for step_idx, sim_dt in enumerate(sim_days, start=1):
                    self.logger.info(
                        f"--- Executing Sandbox Walk-Forward Session {step_idx}/{len(sim_days)} ({sim_dt}) ---"
                    )
                    cycle_result = orchestrator.run_daily_cycle(as_of_date=sim_dt)
                    # Persist updated sandbox state between walk-forward days inside ephemeral temp dir
                    state_repo.save_state(cycle_result["state"])
                    last_cycle_result = cycle_result

                assert last_cycle_result is not None, "Sandbox walk-forward produced no cycle result."

                # Validate JSON round-trip persistence via JsonPortfolioStateRepository
                reloaded_state = state_repo.load_state()
                assert len(reloaded_state.tenant_portfolios) == 2, (
                    f"Expected 2 isolated tenant portfolios, found {len(reloaded_state.tenant_portfolios)}."
                )

                total_positions_allocated = 0
                for pid, ledger in reloaded_state.tenant_portfolios.items():
                    # 1. Verify Simons Portfolio Heat Cap Invariant (<= 6.0%)
                    assert ledger.current_portfolio_heat_pct <= ledger.max_portfolio_heat_pct + 1e-5, (
                        f"Portfolio Heat breach for {pid}: "
                        f"{ledger.current_portfolio_heat_pct:.4%} > {ledger.max_portfolio_heat_pct:.4%}"
                    )

                    # 2. Verify Zero Cross-Tenant Leakage & Monotonic Ratchet Stop Invariants
                    for ticker, pos in ledger.open_positions.items():
                        total_positions_allocated += 1
                        assert pos.user_id == ledger.user_id, (
                            f"Cross-tenant user_id breach on {ticker}: {pos.user_id} != {ledger.user_id}"
                        )
                        assert pos.portfolio_id == ledger.portfolio_id, (
                            f"Cross-portfolio ID breach on {ticker}: {pos.portfolio_id} != {ledger.portfolio_id}"
                        )
                        assert pos.index_id in ledger.subscribed_indices, (
                            f"Unsubscribed index allocation on {ticker}: {pos.index_id} not in {ledger.subscribed_indices}"
                        )
                        assert pos.trailing_stop_price + 1e-6 >= pos.initial_stop_price, (
                            f"Ratchet floor breach on {ticker}: trailing_stop ({pos.trailing_stop_price}) "
                            f"< initial_stop ({pos.initial_stop_price})"
                        )

                    self.logger.info(
                        f"[Sandbox Summary] {ledger.portfolio_name} | Equity=${ledger.total_equity:,.2f} | "
                        f"Cash=${ledger.cash_balance:,.2f} | OpenPositions={len(ledger.open_positions)} | "
                        f"ClosedTrades={len(ledger.closed_trades_audit)} | "
                        f"Heat={ledger.current_portfolio_heat_pct:.2%}/{ledger.max_portfolio_heat_pct:.2%}"
                    )

                assert total_positions_allocated > 0, (
                    "Expected synthetic breakout candidates to allocate at least 1 position across tenants."
                )

                self.logger.info(
                    "=== ALL SANDBOX DRY-RUN INVARIANTS PASSED (ZERO PRODUCTION MUTATIONS) ==="
                )
                return True

        except Exception as exc:
            self.logger.exception(f"Sandbox Dry-Run Harness failed verification: {exc}")
            return False


# Backward-compatible alias
SandboxDryRunVerifier = SandboxDryRunHarness


if __name__ == "__main__":
    sys.exit(0 if SandboxDryRunHarness().run() else 1)
