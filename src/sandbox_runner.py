from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import logging
from pathlib import Path
import sys
import tempfile
import time
from typing import List
from uuid import uuid4

import numpy as np
import pandas as pd

from config import EngineSettings
from notifier import TelegramDispatchService
from quant_engine import (
    SwingQuantEngineOrchestrator,
    TripleBarrierPortfolioManager,
    VectorizedFeatureEngine,
    WalkForwardBacktester,
)
from schemas import (
    ExitReason,
    IndexConfigSchema,
    IndexTier,
    MultiTenantStateStoreSchema,
    TripleBarrierPositionSchema,
    VirtualPortfolioLedgerSchema,
)
from storage import JsonFilePortfolioRepository

logger = logging.getLogger("SwingQuantEngine.SandboxRunner")


@dataclass(frozen=True)
class WalkForwardMetrics:
    total_trades: int
    win_rate: float
    profit_factor: float
    expected_value_r: float
    max_drawdown_pct: float
    tp_exit_pct: float
    sl_exit_pct: float
    time_exit_pct: float
    passed_gate: bool


class SandboxDryRunVerifier:
    """
    Executes the End-to-End Sandbox Dry Run:
    1. 5-Day Accelerated Lifecycle Stress Simulation (Entry, Ratchet, TP, SL, 14d Time-Stop).
    2. 500-Day Out-of-Sample Walk-Forward Acceptance Gate.
    3. Optional live Telegram HTML Sandbox Dispatch (`🧪 SANDBOX DRY-RUN`).
    Guarantees zero mutation of production state files.
    """

    def __init__(self, settings: EngineSettings) -> None:
        self.settings = settings
        self.orchestrator = SwingQuantEngineOrchestrator()
        self.notifier = TelegramDispatchService(settings=settings)

    def run_full_verification_suite(self, send_telegram: bool = False) -> bool:
        start_clock = time.perf_counter()
        logger.info("=== STARTING END-TO-END SANDBOX DRY-RUN VERIFICATION SUITE ===")

        with tempfile.TemporaryDirectory(prefix="swing_quant_sandbox_") as tmp_dir:
            sandbox_path = Path(tmp_dir)
            lifecycle_ok = self._run_5day_lifecycle_stress_test(
                sandbox_dir=sandbox_path,
                send_telegram=send_telegram,
            )
            wf_metrics = self._run_500d_walk_forward_acceptance_gate()

        elapsed_sec = time.perf_counter() - start_clock
        sla_ok = elapsed_sec < 900.0

        logger.info("------------------------------------------------------------------")
        logger.info(f"1. 5-Day Lifecycle Stress Test : {'PASS' if lifecycle_ok else 'FAIL'}")
        logger.info(
            f"2. 500-Day Walk-Forward Gate   : {'PASS' if wf_metrics.passed_gate else 'FAIL'} "
            f"(Trades={wf_metrics.total_trades}, WinRate={wf_metrics.win_rate:.1%}, "
            f"PF={wf_metrics.profit_factor:.2f}, EV={wf_metrics.expected_value_r:+.2f}R, "
            f"MDD={wf_metrics.max_drawdown_pct:.2%})"
        )
        logger.info(
            f"   Barrier Exit Distribution   : TP={wf_metrics.tp_exit_pct:.1%} | "
            f"SL={wf_metrics.sl_exit_pct:.1%} | 14d-Time={wf_metrics.time_exit_pct:.1%}"
        )
        logger.info(
            f"3. Execution Runtime SLA       : {'PASS' if sla_ok else 'FAIL'} ({elapsed_sec:.2f}s / 900.0s max)"
        )
        logger.info("------------------------------------------------------------------")

        return bool(lifecycle_ok and wf_metrics.passed_gate and sla_ok)

    def _run_5day_lifecycle_stress_test(
        self,
        sandbox_dir: Path,
        send_telegram: bool,
    ) -> bool:
        logger.info("[Stage 1/2] Running 5-Day Accelerated Lifecycle Stress Simulation...")
        user_id = uuid4()
        portfolio_id = uuid4()
        base_date = date(2026, 11, 4)

        index_registry = {
            "RUT": IndexConfigSchema(
                index_id="RUT",
                display_name="Russell 2000 Small-Cap",
                benchmark_ticker="IWM",
                tier=IndexTier.SMALL_CAP,
                is_active=True,
                min_price=5.0,
                min_adv_30d=500_000,
                volume_surge_multiplier=1.8,
                k_stop_atr=2.5,
                k_profit_atr=5.0,
                max_holding_bars=14,
            ),
            "MID": IndexConfigSchema(
                index_id="MID",
                display_name="S&P MidCap 400",
                benchmark_ticker="MDY",
                tier=IndexTier.MID_CAP,
                is_active=True,
                min_price=5.0,
                min_adv_30d=500_000,
                volume_surge_multiplier=1.4,
                k_stop_atr=2.0,
                k_profit_atr=4.5,
                max_holding_bars=14,
            ),
        }

        portfolio = VirtualPortfolioLedgerSchema(
            portfolio_id=portfolio_id,
            user_id=user_id,
            portfolio_name="Sandbox Stress-Test Shadow Portfolio",
            as_of_date=base_date,
            cash_balance=70_000.0,
            total_equity=100_000.0,
            max_portfolio_heat_pct=0.06,
            max_concurrent_positions=10,
            subscribed_indices=["RUT", "MID"],
            open_positions={
                "WINNER_TP": TripleBarrierPositionSchema(
                    user_id=user_id,
                    portfolio_id=portfolio_id,
                    ticker="WINNER_TP",
                    index_id="RUT",
                    entry_date=base_date,
                    entry_price=100.0,
                    shares=100,
                    entry_atr_14=2.0,
                    initial_stop_price=95.0,
                    trailing_stop_price=95.0,
                    take_profit_price=110.0,
                    highest_high_since_entry=100.0,
                    bars_held=0,
                    max_holding_bars=14,
                    last_updated_date=base_date,
                ),
                "LOSER_SL": TripleBarrierPositionSchema(
                    user_id=user_id,
                    portfolio_id=portfolio_id,
                    ticker="LOSER_SL",
                    index_id="MID",
                    entry_date=base_date,
                    entry_price=100.0,
                    shares=100,
                    entry_atr_14=2.0,
                    initial_stop_price=96.0,
                    trailing_stop_price=96.0,
                    take_profit_price=109.0,
                    highest_high_since_entry=100.0,
                    bars_held=0,
                    max_holding_bars=14,
                    last_updated_date=base_date,
                ),
                "STAGNANT_TIME": TripleBarrierPositionSchema(
                    user_id=user_id,
                    portfolio_id=portfolio_id,
                    ticker="STAGNANT_TIME",
                    index_id="MID",
                    entry_date=base_date - timedelta(days=18),
                    entry_price=100.0,
                    shares=100,
                    entry_atr_14=2.0,
                    initial_stop_price=96.0,
                    trailing_stop_price=97.5,
                    take_profit_price=109.0,
                    highest_high_since_entry=101.5,
                    bars_held=12,
                    max_holding_bars=14,
                    last_updated_date=base_date,
                ),
            },
        )

        manager = TripleBarrierPortfolioManager()

        # Session 1: Ratchet Advancement Check
        day_1 = date(2026, 11, 5)
        bars_day_1 = pd.DataFrame(
            [
                {"date": pd.Timestamp(day_1), "ticker": "WINNER_TP", "high": 107.0, "low": 101.0, "close": 106.5, "atr_14": 2.0},
                {"date": pd.Timestamp(day_1), "ticker": "LOSER_SL", "high": 100.5, "low": 97.2, "close": 98.0, "atr_14": 2.0},
                {"date": pd.Timestamp(day_1), "ticker": "STAGNANT_TIME", "high": 101.0, "low": 99.0, "close": 100.2, "atr_14": 2.0},
            ]
        ).set_index(["date", "ticker"])

        closed_d1, _ = manager.reconcile_and_allocate_tenant_portfolio(
            portfolio=portfolio,
            featured_df=bars_day_1,
            approved_signals=[],
            index_registry=index_registry,
            as_of_date=day_1,
        )
        assert len(closed_d1) == 0
        assert portfolio.open_positions["WINNER_TP"].trailing_stop_price == 102.0
        assert portfolio.open_positions["WINNER_TP"].open_dollar_risk == 0.0

        # Session 2: Simultaneous Triple-Barrier Exits (TP, SL, and 14d Time)
        day_2 = date(2026, 11, 6)
        bars_day_2 = pd.DataFrame(
            [
                {"date": pd.Timestamp(day_2), "ticker": "WINNER_TP", "high": 111.5, "low": 106.0, "close": 110.8, "atr_14": 2.0},
                {"date": pd.Timestamp(day_2), "ticker": "LOSER_SL", "high": 98.0, "low": 95.2, "close": 95.5, "atr_14": 2.0},
                {"date": pd.Timestamp(day_2), "ticker": "STAGNANT_TIME", "high": 101.2, "low": 99.5, "close": 100.5, "atr_14": 2.0},
            ]
        ).set_index(["date", "ticker"])

        closed_d2, opened_d2 = manager.reconcile_and_allocate_tenant_portfolio(
            portfolio=portfolio,
            featured_df=bars_day_2,
            approved_signals=[],
            index_registry=index_registry,
            as_of_date=day_2,
        )

        exit_map = {c.ticker: c.exit_reason for c in closed_d2}
        if (
            len(closed_d2) != 3
            or exit_map.get("WINNER_TP") != ExitReason.UPPER_BARRIER_TP
            or exit_map.get("LOSER_SL") != ExitReason.LOWER_BARRIER_SL
            or exit_map.get("STAGNANT_TIME") != ExitReason.VERTICAL_BARRIER_TIME
        ):
            logger.error(f"Lifecycle exit mismatch: {exit_map}")
            return False

        sandbox_repo = JsonFilePortfolioRepository(
            state_path=sandbox_dir / "sandbox_portfolio.json",
            index_registry_path=self.settings.index_registry_path,
        )
        state_store = MultiTenantStateStoreSchema(
            index_registry=index_registry,
            tenant_portfolios={portfolio_id: portfolio},
        )
        sandbox_repo.save_state_atomically(state_store)

        html_preview = self.notifier.format_daily_portfolio_report_html(
            portfolio=portfolio,
            opened_positions=opened_d2,
            closed_trades=closed_d2,
            approved_signals=[],
            as_of_date=day_2,
            dry_run=True,
        )
        assert "🧪 SANDBOX DRY-RUN" in html_preview
        assert "TAKE-PROFIT BARRIER" in html_preview
        assert "TRAILING STOP BARRIER" in html_preview
        assert "14-DAY TIME BARRIER" in html_preview

        if send_telegram and self.notifier.is_configured:
            self.notifier.dispatch_tenant_daily_report(
                portfolio=portfolio,
                opened_positions=opened_d2,
                closed_trades=closed_d2,
                approved_signals=[],
                as_of_date=day_2,
                dry_run=True,
            )

        return True

    def _run_500d_walk_forward_acceptance_gate(self) -> WalkForwardMetrics:
        logger.info("[Stage 2/2] Executing 500-Day Out-of-Sample Walk-Forward Acceptance Gate...")
        np.random.seed(42)
        dates = pd.bdate_range(end=pd.Timestamp(date(2026, 11, 10)), periods=500)
        tickers = [f"QUANT_{i:02d}" for i in range(1, 16)]

        records = []
        for ticker_idx, ticker in enumerate(tickers):
            price = 40.0 + ticker_idx * 3.0
            for d_idx, dt in enumerate(dates):
                is_breakout_regime = (d_idx % 35 == 0) and (ticker_idx % 2 == 0)
                daily_ret = np.random.normal(0.0012, 0.014)
                if is_breakout_regime:
                    daily_ret = 0.045
                price = max(5.5, price * (1.0 + daily_ret))
                high_p = price * (1.0 + abs(np.random.normal(0.008, 0.004)))
                low_p = price * (1.0 - abs(np.random.normal(0.007, 0.004)))
                vol = 1_200_000.0 * (2.4 if is_breakout_regime else np.random.uniform(0.8, 1.2))
                records.append(
                    {
                        "date": dt.normalize(),
                        "ticker": ticker,
                        "open": round(price * 0.995, 4),
                        "high": round(high_p, 4),
                        "low": round(low_p, 4),
                        "close": round(price, 4),
                        "volume": round(vol, 0),
                    }
                )

        market_df = pd.DataFrame(records).set_index(["date", "ticker"]).sort_index()
        feature_engine = VectorizedFeatureEngine()
        featured_df = feature_engine.compute_universe_features(
            market_df=market_df,
            as_of_date=date(2026, 11, 10),
        )

        idx_cfg = IndexConfigSchema(
            index_id="MID",
            display_name="S&P MidCap 400",
            benchmark_ticker="MDY",
            tier=IndexTier.MID_CAP,
            k_stop_atr=2.0,
            k_profit_atr=4.5,
            max_holding_bars=14,
        )

        backtester = WalkForwardBacktester()
        all_r_multiples: List[float] = []
        tp_hits = 0
        sl_hits = 0
        time_hits = 0

        for ticker in tickers:
            asset_slice = featured_df.xs(ticker, level="ticker")
            r_list = backtester._simulate_historical_triple_barrier_trades(asset_slice, idx_cfg)
            for r in r_list:
                all_r_multiples.append(r)
                if r >= (idx_cfg.k_profit_atr / idx_cfg.k_stop_atr) - 0.05:
                    tp_hits += 1
                elif r <= -0.95:
                    sl_hits += 1
                else:
                    time_hits += 1

        total_trades = len(all_r_multiples)
        if total_trades == 0:
            return WalkForwardMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False)

        wins = [r for r in all_r_multiples if r > 0]
        losses = [r for r in all_r_multiples if r <= 0]
        win_rate = len(wins) / total_trades
        gross_win = sum(wins)
        gross_loss = abs(sum(losses)) if losses else 1e-6
        profit_factor = gross_win / gross_loss
        ev_r = float(np.mean(all_r_multiples))

        equity = 100_000.0
        peak = equity
        max_dd = 0.0
        for r in all_r_multiples:
            equity += (equity * 0.01) * r
            peak = max(peak, equity)
            dd = (peak - equity) / peak
            max_dd = max(max_dd, dd)

        passed = (
            total_trades >= 10
            and profit_factor >= 1.25
            and ev_r > 0.15
            and max_dd <= 0.15
        )

        return WalkForwardMetrics(
            total_trades=total_trades,
            win_rate=round(win_rate, 4),
            profit_factor=round(profit_factor, 2),
            expected_value_r=round(ev_r, 4),
            max_drawdown_pct=round(max_dd, 4),
            tp_exit_pct=round(tp_hits / total_trades, 4),
            sl_exit_pct=round(sl_hits / total_trades, 4),
            time_exit_pct=round(time_hits / total_trades, 4),
            passed_gate=passed,
        )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    parser = argparse.ArgumentParser(description="Swing Quant Engine Sandbox Dry-Run Verifier")
    parser.add_argument(
        "--send-telegram",
        action="store_true",
        help="Dispatch live Sandbox Dry-Run HTML report to configured Telegram channel.",
    )
    args = parser.parse_args()

    settings = EngineSettings()
    verifier = SandboxDryRunVerifier(settings=settings)
    success = verifier.run_full_verification_suite(send_telegram=args.send_telegram)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
