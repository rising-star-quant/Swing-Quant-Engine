from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict, List
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from data_ingestion import BaseMarketDataProvider, SmartSlidingWindowOrchestrator
from quant_engine import (
    TripleBarrierPortfolioManager,
    VectorizedFeatureEngine,
)
from schemas import (
    ExitReason,
    IndexConfigSchema,
    IndexTier,
    MultiTenantStateStoreSchema,
    TripleBarrierPositionSchema,
    VirtualPortfolioLedgerSchema,
)


class MockDeterministicDataProvider(BaseMarketDataProvider):
    """
    In-memory mock provider for deterministic unit testing of the Smart Sliding Window
    and Corporate Action Split Guard without external network calls.
    """

    def __init__(
        self,
        full_history_df: pd.DataFrame,
        delta_df: pd.DataFrame,
        constituents_map: Dict[str, List[str]],
    ) -> None:
        self.full_history_df = full_history_df
        self.delta_df = delta_df
        self.constituents_map = constituents_map
        self.full_hydration_calls: List[List[str]] = []
        self.delta_fetch_calls: List[List[str]] = []

    def fetch_index_constituents(self, index_id: str) -> List[str]:
        return self.constituents_map.get(index_id, [])

    def fetch_ohlcv_batch(
        self,
        tickers: List[str],
        start_date: date,
        end_date_inclusive: date,
    ) -> pd.DataFrame:
        days_span = (end_date_inclusive - start_date).days
        if days_span > 30:
            self.full_hydration_calls.append(sorted(tickers))
            source_df = self.full_history_df
        else:
            self.delta_fetch_calls.append(sorted(tickers))
            source_df = self.delta_df

        if source_df.empty:
            return pd.DataFrame()

        mask = (
            source_df.index.get_level_values("ticker").isin(tickers)
            & (source_df.index.get_level_values("date") >= pd.Timestamp(start_date))
            & (source_df.index.get_level_values("date") <= pd.Timestamp(end_date_inclusive))
        )
        return source_df.loc[mask].copy().sort_index()


def generate_synthetic_market_df(
    tickers: List[str],
    num_days: int = 300,
    end_date: date = date(2026, 11, 10),
    breakout_ticker: str = "ALPHA",
) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp(end_date), periods=num_days)
    records = []

    for ticker in tickers:
        np.random.seed(abs(hash(ticker)) % (2**31))
        base_price = 50.0
        for idx, dt in enumerate(dates):
            if ticker == breakout_ticker:
                drift = 0.0025 * idx
                close_p = round(base_price * (1.0 + drift), 4)
                high_p = round(close_p * 1.01, 4)
                low_p = round(close_p * 0.99, 4)
                open_p = round(close_p * 0.995, 4)
                vol = 1_000_000.0
                if idx == num_days - 1:
                    close_p = round(close_p * 1.06, 4)
                    high_p = round(close_p * 1.005, 4)
                    low_p = round(open_p * 0.998, 4)
                    vol = 2_800_000.0
            else:
                close_p = round(base_price + np.sin(idx * 0.1), 4)
                high_p = round(close_p + 0.5, 4)
                low_p = round(close_p - 0.5, 4)
                open_p = close_p
                vol = 800_000.0

            records.append(
                {
                    "date": dt.normalize(),
                    "ticker": ticker,
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": close_p,
                    "volume": vol,
                    "dividends": 0.0,
                    "splits": 0.0,
                }
            )

    return pd.DataFrame(records).set_index(["date", "ticker"]).sort_index()


@pytest.fixture
def sample_index_registry() -> Dict[str, IndexConfigSchema]:
    return {
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


def test_chandelier_stop_ratchet_monotonicity() -> None:
    """
    Verifies that TripleBarrierPositionSchema.ratchet_trailing_stop()
    strictly increases on new highs, never decreases on pullbacks or ATR expansion,
    and rejects downward stop mutations or Point-in-Time date regressions.
    """
    user_id = uuid4()
    portfolio_id = uuid4()
    entry_dt = date(2026, 11, 2)

    pos = TripleBarrierPositionSchema(
        user_id=user_id,
        portfolio_id=portfolio_id,
        ticker="ALPHA",
        index_id="RUT",
        entry_date=entry_dt,
        entry_price=100.0,
        shares=50,
        entry_atr_14=2.0,
        initial_stop_price=95.0,
        trailing_stop_price=95.0,
        take_profit_price=110.0,
        highest_high_since_entry=100.0,
        bars_held=0,
        max_holding_bars=14,
        last_updated_date=entry_dt,
    )

    pos.ratchet_trailing_stop(
        current_high=106.0,
        current_atr_14=2.0,
        k_trail=2.5,
        current_date=date(2026, 11, 3),
    )
    assert pos.trailing_stop_price == 101.0
    assert pos.bars_held == 1
    assert pos.open_dollar_risk == 0.0

    pos.ratchet_trailing_stop(
        current_high=102.0,
        current_atr_14=4.0,
        k_trail=2.5,
        current_date=date(2026, 11, 4),
    )
    assert pos.trailing_stop_price == 101.0
    assert pos.bars_held == 2

    with pytest.raises(ValueError, match="RATCHET VIOLATION"):
        pos.update_trailing_stop(98.5)

    with pytest.raises(ValueError, match="Point-in-Time violation"):
        pos.ratchet_trailing_stop(
            current_high=108.0,
            current_atr_14=2.0,
            k_trail=2.5,
            current_date=date(2026, 11, 4),
        )


def test_triple_barrier_exit_hierarchy(sample_index_registry: Dict[str, IndexConfigSchema]) -> None:
    """
    Verifies deterministic EOD liquidation across all three barriers:
    1. Lower Barrier (Stop-Loss)
    2. Upper Barrier (Take-Profit)
    3. Vertical Barrier (14-Day Time Stop)
    """
    user_id = uuid4()
    portfolio_id = uuid4()
    as_of = date(2026, 11, 10)
    prev_dt = date(2026, 11, 9)

    portfolio = VirtualPortfolioLedgerSchema(
        portfolio_id=portfolio_id,
        user_id=user_id,
        as_of_date=prev_dt,
        cash_balance=70_000.0,
        total_equity=100_000.0,
        open_positions={
            "SL_HIT": TripleBarrierPositionSchema(
                user_id=user_id,
                portfolio_id=portfolio_id,
                ticker="SL_HIT",
                index_id="MID",
                entry_date=date(2026, 11, 1),
                entry_price=100.0,
                shares=100,
                entry_atr_14=2.0,
                initial_stop_price=96.0,
                trailing_stop_price=96.0,
                take_profit_price=109.0,
                highest_high_since_entry=101.0,
                bars_held=4,
                max_holding_bars=14,
                last_updated_date=prev_dt,
            ),
            "TP_HIT": TripleBarrierPositionSchema(
                user_id=user_id,
                portfolio_id=portfolio_id,
                ticker="TP_HIT",
                index_id="MID",
                entry_date=date(2026, 11, 1),
                entry_price=100.0,
                shares=100,
                entry_atr_14=2.0,
                initial_stop_price=96.0,
                trailing_stop_price=98.0,
                take_profit_price=109.0,
                highest_high_since_entry=105.0,
                bars_held=5,
                max_holding_bars=14,
                last_updated_date=prev_dt,
            ),
            "TIME_EXPIRED": TripleBarrierPositionSchema(
                user_id=user_id,
                portfolio_id=portfolio_id,
                ticker="TIME_EXPIRED",
                index_id="MID",
                entry_date=date(2026, 10, 20),
                entry_price=100.0,
                shares=100,
                entry_atr_14=2.0,
                initial_stop_price=96.0,
                trailing_stop_price=97.0,
                take_profit_price=109.0,
                highest_high_since_entry=103.0,
                bars_held=13,
                max_holding_bars=14,
                last_updated_date=prev_dt,
            ),
        },
    )

    featured_df = pd.DataFrame(
        [
            {"date": pd.Timestamp(as_of), "ticker": "SL_HIT", "high": 99.0, "low": 95.5, "close": 95.8, "atr_14": 2.0},
            {"date": pd.Timestamp(as_of), "ticker": "TP_HIT", "high": 110.2, "low": 104.0, "close": 109.5, "atr_14": 2.0},
            {"date": pd.Timestamp(as_of), "ticker": "TIME_EXPIRED", "high": 102.0, "low": 99.0, "close": 101.0, "atr_14": 2.0},
        ]
    ).set_index(["date", "ticker"])

    manager = TripleBarrierPortfolioManager()
    closed, _ = manager.reconcile_and_allocate_tenant_portfolio(
        portfolio=portfolio,
        featured_df=featured_df,
        approved_signals=[],
        index_registry=sample_index_registry,
        as_of_date=as_of,
    )

    assert len(closed) == 3
    assert len(portfolio.open_positions) == 0
    reasons = {c.ticker: c.exit_reason for c in closed}
    assert reasons["SL_HIT"] == ExitReason.LOWER_BARRIER_SL
    assert reasons["TP_HIT"] == ExitReason.UPPER_BARRIER_TP
    assert reasons["TIME_EXPIRED"] == ExitReason.VERTICAL_BARRIER_TIME


def test_sliding_window_fifo_and_split_guard(
    tmp_path: Path,
    sample_index_registry: Dict[str, IndexConfigSchema],
) -> None:
    """
    Verifies that:
    1. A normal daily delta update appends day t and drops the oldest bar without re-fetching 500 days.
    2. A discrepancy on day t-1 (2-for-1 stock split) is caught by the overlap detector and
       triggers a full history re-hydration ONLY for the split ticker.
    """
    t_minus_1 = date(2026, 11, 9)
    t_current = date(2026, 11, 10)
    tickers = ["CLEAN_STOCK", "SPLIT_STOCK", "IWM", "MDY"]

    cached_df = generate_synthetic_market_df(tickers=tickers, num_days=10, end_date=t_minus_1)
    cache_file = tmp_path / "market_data_window.parquet"
    cached_df.to_parquet(cache_file)

    full_rehydrated_df = generate_synthetic_market_df(tickers=tickers, num_days=10, end_date=t_current)
    split_mask_full = full_rehydrated_df.index.get_level_values("ticker") == "SPLIT_STOCK"
    for col in ["open", "high", "low", "close"]:
        full_rehydrated_df.loc[split_mask_full, col] *= 0.5

    delta_df = generate_synthetic_market_df(tickers=tickers, num_days=10, end_date=t_current)
    delta_df = delta_df.groupby(level="ticker", group_keys=False).tail(2)
    split_mask_delta = delta_df.index.get_level_values("ticker") == "SPLIT_STOCK"
    for col in ["open", "high", "low", "close"]:
        delta_df.loc[split_mask_delta, col] *= 0.5

    provider = MockDeterministicDataProvider(
        full_history_df=full_rehydrated_df,
        delta_df=delta_df,
        constituents_map={"RUT": ["CLEAN_STOCK", "SPLIT_STOCK"], "MID": []},
    )

    orchestrator = SmartSlidingWindowOrchestrator(
        provider=provider,
        cache_path=cache_file,
        max_window_bars=10,
        min_required_bars=5,
    )

    state_store = MultiTenantStateStoreSchema(
        index_registry=sample_index_registry,
        tenant_portfolios={},
    )

    synced_df, _ = orchestrator.sync_daily_market_window(state_store=state_store, as_of_date=t_current)

    assert len(provider.delta_fetch_calls) == 1
    assert provider.full_hydration_calls == [["SPLIT_STOCK"]]

    clean_bars = synced_df.xs("CLEAN_STOCK", level="ticker")
    assert len(clean_bars) == 10
    assert clean_bars.index.max() == pd.Timestamp(t_current)


def test_multi_tenant_isolation_and_heat_cap() -> None:
    """
    Verifies that:
    1. Attaching a position with user_id of Tenant B into Tenant A's portfolio raises ValidationError.
    2. Breaching the 6.0% Maximum Portfolio Heat cap raises ValidationError.
    """
    tenant_a_user = uuid4()
    tenant_a_portfolio = uuid4()
    tenant_b_user = uuid4()

    rogue_position = TripleBarrierPositionSchema(
        user_id=tenant_b_user,
        portfolio_id=tenant_a_portfolio,
        ticker="NVDA",
        index_id="MID",
        entry_date=date(2026, 11, 10),
        entry_price=100.0,
        shares=10,
        entry_atr_14=2.0,
        initial_stop_price=96.0,
        trailing_stop_price=96.0,
        take_profit_price=109.0,
        highest_high_since_entry=100.0,
        last_updated_date=date(2026, 11, 10),
    )

    with pytest.raises(ValidationError, match="CRITICAL SECURITY BREACH: Cross-tenant position detected"):
        VirtualPortfolioLedgerSchema(
            portfolio_id=tenant_a_portfolio,
            user_id=tenant_a_user,
            as_of_date=date(2026, 11, 10),
            cash_balance=90_000.0,
            total_equity=100_000.0,
            open_positions={"NVDA": rogue_position},
        )

    excessive_risk_pos = TripleBarrierPositionSchema(
        user_id=tenant_a_user,
        portfolio_id=tenant_a_portfolio,
        ticker="TSLA",
        index_id="MID",
        entry_date=date(2026, 11, 10),
        entry_price=100.0,
        shares=1_000,
        entry_atr_14=3.5,
        initial_stop_price=93.0,
        trailing_stop_price=93.0,
        take_profit_price=115.0,
        highest_high_since_entry=100.0,
        last_updated_date=date(2026, 11, 10),
    )

    with pytest.raises(ValidationError, match="Portfolio Heat circuit breaker breached"):
        VirtualPortfolioLedgerSchema(
            portfolio_id=tenant_a_portfolio,
            user_id=tenant_a_user,
            as_of_date=date(2026, 11, 10),
            cash_balance=0.0,
            total_equity=100_000.0,
            max_portfolio_heat_pct=0.06,
            open_positions={"TSLA": excessive_risk_pos},
        )


def test_portfolio_exclusion_and_point_in_time_no_lookahead(
    sample_index_registry: Dict[str, IndexConfigSchema],
) -> None:
    """
    Verifies that:
    1. A ticker in excluded_tickers is completely bypassed during screening.
    2. Modifying future bars (t+1) has zero effect on features or signals computed at date t.
    """
    target_date = date(2026, 11, 9)
    future_date = date(2026, 11, 10)
    tickers = ["ALPHA", "BETA", "IWM"]

    df_full = generate_synthetic_market_df(
        tickers=tickers,
        num_days=260,
        end_date=future_date,
        breakout_ticker="ALPHA",
    )
    alpha_target_idx = (pd.Timestamp(target_date), "ALPHA")
    df_full.loc[alpha_target_idx, "close"] = df_full.loc[alpha_target_idx, "close"] * 1.08
    df_full.loc[alpha_target_idx, "high"] = df_full.loc[alpha_target_idx, "close"] * 1.01
    df_full.loc[alpha_target_idx, "volume"] = 3_500_000.0

    engine = VectorizedFeatureEngine()
    features_clean = engine.compute_universe_features(df_full, as_of_date=target_date)

    df_corrupted_future = df_full.copy()
    future_idx = (pd.Timestamp(future_date), "ALPHA")
    df_corrupted_future.loc[future_idx, "close"] *= 6.0
    df_corrupted_future.loc[future_idx, "high"] *= 6.0
    df_corrupted_future.loc[future_idx, "volume"] *= 50.0

    features_with_corrupted_future = engine.compute_universe_features(
        df_corrupted_future,
        as_of_date=target_date,
    )

    pd.testing.assert_frame_equal(
        features_clean,
        features_with_corrupted_future,
        check_exact=False,
        atol=1e-8,
        rtol=1e-8,
    )

    signals_included = engine.screen_index_candidates(
        featured_df=features_clean,
        index_cfg=sample_index_registry["RUT"],
        constituent_tickers=["ALPHA", "BETA"],
        as_of_date=target_date,
        excluded_tickers=set(),
    )
    assert any(s.ticker == "ALPHA" for s in signals_included)

    signals_excluded = engine.screen_index_candidates(
        featured_df=features_clean,
        index_cfg=sample_index_registry["RUT"],
        constituent_tickers=["ALPHA", "BETA"],
        as_of_date=target_date,
        excluded_tickers={"ALPHA"},
    )
    assert all(s.ticker != "ALPHA" for s in signals_excluded)
