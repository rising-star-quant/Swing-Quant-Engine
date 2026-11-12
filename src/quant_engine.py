from __future__ import annotations

from datetime import date
import logging
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

import numpy as np
import pandas as pd

from schemas import (
    ClosedTradeAuditSchema,
    DirectionalSignalSchema,
    ExitReason,
    IndexConfigSchema,
    IndexTier,
    MetaLabeledSignalSchema,
    MultiTenantStateStoreSchema,
    TripleBarrierPositionSchema,
    VirtualPortfolioLedgerSchema,
)

logger = logging.getLogger("SwingQuantEngine.QuantCore")


# =========================================================================
# 1. VECTORIZED FEATURE & PRIMARY SCREENING ENGINE (Step B.1)
# =========================================================================

class VectorizedFeatureEngine:
    """
    Computes stationary volatility-adjusted features (Wilder's ATR_14,
    Volatility-Adjusted Momentum, Standardized Volume Surge, Relative Strength)
    and executes index-tailored primary directional screening without Python loops.
    """

    def __init__(
        self,
        w_momentum: float = 0.45,
        w_volume: float = 0.30,
        w_rel_strength: float = 0.25,
    ) -> None:
        self.w_momentum = w_momentum
        self.w_volume = w_volume
        self.w_rel_strength = w_rel_strength

    def compute_universe_features(
        self,
        market_df: pd.DataFrame,
        as_of_date: date,
    ) -> pd.DataFrame:
        df = market_df.loc[
            market_df.index.get_level_values("date") <= pd.Timestamp(as_of_date)
        ].copy()
        if df.empty:
            return pd.DataFrame()

        df = df.sort_index(level=["ticker", "date"])
        grouped = df.groupby(level="ticker", group_keys=False)

        # 1. Previous Close & Wilder's True Range (ATR_14)
        df["prev_close"] = grouped["close"].shift(1)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["prev_close"]).abs()
        tr3 = (df["low"] - df["prev_close"]).abs()
        df["tr"] = np.maximum(tr1, np.maximum(tr2, tr3))

        df["atr_14"] = grouped["tr"].transform(
            lambda s: s.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
        )

        # 2. Moving Averages & Liquidity Baselines
        df["sma_20"] = grouped["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
        df["sma_50"] = grouped["close"].transform(lambda s: s.rolling(50, min_periods=50).mean())
        df["sma_200"] = grouped["close"].transform(lambda s: s.rolling(200, min_periods=200).mean())
        df["adv_30d"] = grouped["volume"].transform(lambda s: s.rolling(30, min_periods=30).mean())

        # 3. Prior N-Day Highs
        df["prior_high_20"] = grouped["high"].transform(
            lambda s: s.shift(1).rolling(20, min_periods=20).max()
        )
        df["prior_high_15"] = grouped["high"].transform(
            lambda s: s.shift(1).rolling(15, min_periods=15).max()
        )

        # 4. Volume Statistics (20-day mean & std)
        df["vol_sma_20"] = grouped["volume"].transform(
            lambda s: s.shift(1).rolling(20, min_periods=20).mean()
        )
        df["vol_std_20"] = grouped["volume"].transform(
            lambda s: s.shift(1).rolling(20, min_periods=20).std(ddof=1)
        )
        df["volume_ratio_20"] = df["volume"] / df["vol_sma_20"].replace(0, np.nan)
        df["volume_zscore"] = (df["volume"] - df["vol_sma_20"]) / df["vol_std_20"].replace(0, np.nan)

        # 5. López de Prado Stationary Volatility-Adjusted Momentum (M_vol_adj)
        close_20d_ago = grouped["close"].shift(20)
        df["vol_adj_momentum"] = (df["close"] - close_20d_ago) / (
            df["atr_14"] * np.sqrt(20.0)
        ).replace(0, np.nan)

        # 6. Daily & 60-Day Returns for Benchmark Relative Strength
        df["ret_1d"] = grouped["close"].pct_change(1)
        df["ret_60d"] = grouped["close"].pct_change(60)

        return df

    def screen_index_candidates(
        self,
        featured_df: pd.DataFrame,
        index_cfg: IndexConfigSchema,
        constituent_tickers: List[str],
        as_of_date: date,
        excluded_tickers: Optional[Set[str]] = None,
        top_n: int = 15,
    ) -> List[DirectionalSignalSchema]:
        if featured_df.empty:
            return []

        excluded = excluded_tickers or set()
        eligible_tickers = [t for t in constituent_tickers if t not in excluded]
        if not eligible_tickers:
            return []

        target_ts = pd.Timestamp(as_of_date)
        if target_ts not in featured_df.index.get_level_values("date"):
            logger.warning(f"No market bars found on exact date {as_of_date} for index {index_cfg.index_id}.")
            return []

        benchmark_symbol = index_cfg.benchmark_ticker.upper()
        rs_norm_map = self._compute_relative_strength_vs_benchmark(
            featured_df=featured_df,
            tickers=eligible_tickers,
            benchmark_ticker=benchmark_symbol,
            as_of_ts=target_ts,
        )

        daily_slice = featured_df.xs(target_ts, level="date").copy()
        daily_slice = daily_slice.loc[daily_slice.index.isin(eligible_tickers)].copy()
        if daily_slice.empty:
            return []

        daily_slice["norm_relative_strength"] = daily_slice.index.map(rs_norm_map)
        daily_slice = daily_slice.dropna(
            subset=[
                "close",
                "atr_14",
                "sma_20",
                "sma_50",
                "sma_200",
                "adv_30d",
                "prior_high_20",
                "prior_high_15",
                "volume_ratio_20",
                "vol_adj_momentum",
                "volume_zscore",
                "norm_relative_strength",
            ]
        )
        if daily_slice.empty:
            return []

        # Gate 1: Simons Liquidity & Price Gateways
        liquidity_mask = (
            (daily_slice["close"] >= index_cfg.min_price)
            & (daily_slice["adv_30d"] >= index_cfg.min_adv_30d)
            & (daily_slice["atr_14"] > 0.0)
        )
        daily_slice = daily_slice.loc[liquidity_mask]
        if daily_slice.empty:
            return []

        # Gate 2: Tailored Index Calculation Pipelines
        if index_cfg.tier == IndexTier.SMALL_CAP:
            regime_mask = (
                (daily_slice["close"] > daily_slice["sma_200"])
                & (daily_slice["close"] > daily_slice["sma_50"])
                & (daily_slice["close"] >= daily_slice["prior_high_20"])
                & (daily_slice["volume_ratio_20"] >= max(1.8, index_cfg.volume_surge_multiplier))
                & (daily_slice["norm_relative_strength"] > 0.25)
            )
        elif index_cfg.tier == IndexTier.MID_CAP:
            breakout_trigger = daily_slice["close"] >= daily_slice["prior_high_15"]
            pullback_trigger = (
                (daily_slice["low"] <= daily_slice["sma_20"] * 1.015)
                & (daily_slice["close"] > daily_slice["sma_20"])
                & (daily_slice["close"] > daily_slice["open"])
            )
            regime_mask = (
                (daily_slice["close"] > daily_slice["sma_200"])
                & (daily_slice["sma_20"] > daily_slice["sma_50"])
                & (breakout_trigger | pullback_trigger)
                & (daily_slice["volume_ratio_20"] >= max(1.4, index_cfg.volume_surge_multiplier))
                & (daily_slice["norm_relative_strength"] > 0.0)
            )
        else:
            regime_mask = (
                (daily_slice["close"] > daily_slice["sma_200"])
                & (daily_slice["close"] >= daily_slice["prior_high_20"])
                & (daily_slice["volume_ratio_20"] >= index_cfg.volume_surge_multiplier)
            )

        candidates = daily_slice.loc[regime_mask].copy()
        if candidates.empty:
            return []

        candidates["score_mom"] = self._winsorized_zscore_to_100(candidates["vol_adj_momentum"])
        candidates["score_vol"] = self._winsorized_zscore_to_100(candidates["volume_zscore"])
        candidates["score_rs"] = self._winsorized_zscore_to_100(candidates["norm_relative_strength"])

        candidates["primary_score"] = (
            self.w_momentum * candidates["score_mom"]
            + self.w_volume * candidates["score_vol"]
            + self.w_rel_strength * candidates["score_rs"]
        ).round(2)

        candidates = candidates.sort_values(by="primary_score", ascending=False).head(top_n)

        signals: List[DirectionalSignalSchema] = []
        for ticker, row in candidates.iterrows():
            signals.append(
                DirectionalSignalSchema(
                    as_of_date=as_of_date,
                    ticker=str(ticker),
                    index_id=index_cfg.index_id,
                    side=1,
                    close_price=round(float(row["close"]), 4),
                    atr_14=round(float(row["atr_14"]), 4),
                    adv_30d=round(float(row["adv_30d"]), 2),
                    vol_adj_momentum=round(float(row["vol_adj_momentum"]), 4),
                    volume_zscore=round(float(row["volume_zscore"]), 4),
                    norm_relative_strength=round(float(row["norm_relative_strength"]), 4),
                    primary_score=float(row["primary_score"]),
                )
            )
        return signals

    @staticmethod
    def _compute_relative_strength_vs_benchmark(
        featured_df: pd.DataFrame,
        tickers: List[str],
        benchmark_ticker: str,
        as_of_ts: pd.Timestamp,
    ) -> Dict[str, float]:
        if benchmark_ticker not in featured_df.index.get_level_values("ticker"):
            return {t: 0.5 for t in tickers}

        bench_series = (
            featured_df.xs(benchmark_ticker, level="ticker")["ret_1d"]
            .dropna()
            .tail(60)
        )
        if len(bench_series) < 30:
            return {t: 0.5 for t in tickers}

        rs_scores: Dict[str, float] = {}
        for ticker in tickers:
            if ticker not in featured_df.index.get_level_values("ticker"):
                continue
            asset_series = featured_df.xs(ticker, level="ticker")["ret_1d"].dropna().tail(60)
            common_dates = asset_series.index.intersection(bench_series.index)
            if len(common_dates) < 30:
                continue
            excess_daily = asset_series.loc[common_dates] - bench_series.loc[common_dates]
            tracking_std = float(excess_daily.std(ddof=1))
            if tracking_std <= 1e-8:
                rs_scores[ticker] = 0.0
            else:
                cum_excess = float(
                    (1.0 + asset_series.loc[common_dates]).prod()
                    - (1.0 + bench_series.loc[common_dates]).prod()
                )
                rs_scores[ticker] = cum_excess / (tracking_std * np.sqrt(len(common_dates)))
        return rs_scores

    @staticmethod
    def _winsorized_zscore_to_100(series: pd.Series) -> pd.Series:
        if len(series) <= 1:
            return pd.Series(75.0, index=series.index)
        lower = series.quantile(0.05)
        upper = series.quantile(0.95)
        clipped = series.clip(lower=lower, upper=upper)
        std = float(clipped.std(ddof=1))
        if std <= 1e-8:
            return pd.Series(50.0, index=series.index)
        z = ((clipped - float(clipped.mean())) / std).clip(-3.0, 3.0)
        return ((z + 3.0) / 6.0) * 100.0


# =========================================================================
# 2. 500-DAY WALK-FORWARD BACKTESTER & META-LABELING SIZER (Step B.2)
# =========================================================================

class WalkForwardBacktester:
    """
    Runs a strict Point-in-Time 500-day historical simulation on each candidate
    to compute empirical Expected Value (EV in R-multiples) and assign the
    López de Prado Meta-Labeling Conviction Scalar (phi_meta in [0.0, 1.25]).
    """

    def __init__(self, min_historical_trades: int = 3, min_win_rate: float = 0.38) -> None:
        self.min_historical_trades = min_historical_trades
        self.min_win_rate = min_win_rate

    def evaluate_and_meta_label(
        self,
        signal: DirectionalSignalSchema,
        featured_df: pd.DataFrame,
        index_cfg: IndexConfigSchema,
    ) -> MetaLabeledSignalSchema:
        ticker = signal.ticker
        asset_df = featured_df.xs(ticker, level="ticker").copy()
        hist_df = asset_df.loc[asset_df.index < pd.Timestamp(signal.as_of_date)].tail(500)

        r_multiples = self._simulate_historical_triple_barrier_trades(hist_df, index_cfg)

        if len(r_multiples) >= self.min_historical_trades:
            wins = [r for r in r_multiples if r > 0.0]
            win_rate = round(len(wins) / len(r_multiples), 4)
            ev_r = round(float(np.mean(r_multiples)), 4)
        else:
            win_rate = 0.45 if signal.primary_score >= 65.0 else 0.35
            ev_r = 0.35 if signal.primary_score >= 65.0 else -0.10

        phi_meta = self._compute_meta_conviction_scalar(
            primary_score=signal.primary_score,
            win_rate=win_rate,
            ev_r=ev_r,
        )
        is_approved = (ev_r > 0.0) and (win_rate >= self.min_win_rate) and (phi_meta > 0.0)

        initial_stop = round(signal.close_price - (index_cfg.k_stop_atr * signal.atr_14), 4)
        initial_stop = max(0.01, initial_stop)
        take_profit = round(signal.close_price + (index_cfg.k_profit_atr * signal.atr_14), 4)

        return MetaLabeledSignalSchema(
            primary_signal=signal,
            backtest_lookback_days=min(500, max(250, len(hist_df))),
            historical_win_rate=win_rate,
            historical_ev_r_multiple=ev_r,
            meta_conviction_scalar=phi_meta,
            is_approved=is_approved,
            initial_stop_price=initial_stop,
            take_profit_price=take_profit,
            max_holding_bars=index_cfg.max_holding_bars,
        )

    def _simulate_historical_triple_barrier_trades(
        self,
        hist_df: pd.DataFrame,
        index_cfg: IndexConfigSchema,
    ) -> List[float]:
        if len(hist_df) < 60:
            return []

        closes = hist_df["close"].to_numpy()
        highs = hist_df["high"].to_numpy()
        lows = hist_df["low"].to_numpy()
        atrs = hist_df["atr_14"].to_numpy()
        sma50 = hist_df["sma_50"].to_numpy()
        prior_h15 = hist_df["prior_high_15"].to_numpy()
        vol_ratio = hist_df["volume_ratio_20"].to_numpy()

        r_outcomes: List[float] = []
        i = 20
        n = len(hist_df)

        while i < n - index_cfg.max_holding_bars:
            if (
                not np.isnan(atrs[i])
                and atrs[i] > 0
                and closes[i] > sma50[i]
                and closes[i] >= prior_h15[i]
                and vol_ratio[i] >= 1.25
            ):
                entry_p = closes[i]
                initial_risk = index_cfg.k_stop_atr * atrs[i]
                trail_stop = entry_p - initial_risk
                target_p = entry_p + (index_cfg.k_profit_atr * atrs[i])
                highest_h = highs[i]

                exit_p = closes[min(i + index_cfg.max_holding_bars, n - 1)]
                bars_elapsed = index_cfg.max_holding_bars

                for step in range(1, index_cfg.max_holding_bars + 1):
                    idx = i + step
                    if lows[idx] <= trail_stop:
                        exit_p = trail_stop
                        bars_elapsed = step
                        break
                    if highs[idx] >= target_p:
                        exit_p = target_p
                        bars_elapsed = step
                        break
                    highest_h = max(highest_h, highs[idx])
                    candidate_stop = highest_h - (index_cfg.k_stop_atr * atrs[idx])
                    trail_stop = max(trail_stop, candidate_stop)

                r_mult = (exit_p - entry_p) / initial_risk
                r_outcomes.append(float(r_mult))
                i += bars_elapsed
            else:
                i += 1

        return r_outcomes

    def _compute_meta_conviction_scalar(
        self,
        primary_score: float,
        win_rate: float,
        ev_r: float,
    ) -> float:
        if ev_r <= 0.0 or win_rate < self.min_win_rate:
            return 0.0
        if primary_score >= 80.0 and ev_r >= 0.60 and win_rate >= 0.50:
            return 1.25
        if primary_score >= 60.0 and ev_r >= 0.25:
            return 1.00
        return 0.75


# Alias for specification compatibility
PerAssetTripleBarrierBacktester = WalkForwardBacktester


class MetaLabelingSizer:
    """
    Computes Volatility-Parity share allocations scaled by López de Prado's
    Meta-Labeling Conviction Scalar (phi_meta) and enforces the 6.0% Portfolio Heat
    Circuit Breaker.
    """

    def __init__(
        self,
        risk_per_trade_pct: float = 0.01,
        max_single_position_notional_pct: float = 0.15,
    ) -> None:
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_single_position_notional_pct = max_single_position_notional_pct

    def calculate_shares(
        self,
        portfolio: VirtualPortfolioLedgerSchema,
        signal: MetaLabeledSignalSchema,
    ) -> int:
        if not signal.is_approved or signal.meta_conviction_scalar <= 0.0:
            return 0

        entry_price = signal.primary_signal.close_price
        risk_per_share = entry_price - signal.initial_stop_price
        if risk_per_share <= 0.0:
            return 0

        base_dollar_risk = portfolio.total_equity * self.risk_per_trade_pct
        scaled_dollar_risk = base_dollar_risk * signal.meta_conviction_scalar
        raw_shares = int(np.floor(scaled_dollar_risk / risk_per_share))

        max_notional_dollars = min(
            portfolio.cash_balance,
            portfolio.total_equity * self.max_single_position_notional_pct,
        )
        max_notional_shares = int(np.floor(max_notional_dollars / entry_price))
        shares = max(0, min(raw_shares, max_notional_shares))
        if shares <= 0:
            return 0

        candidate_open_risk = max(0.0, risk_per_share * shares)
        current_open_risk = sum(p.open_dollar_risk for p in portfolio.open_positions.values())
        projected_heat_pct = (current_open_risk + candidate_open_risk) / portfolio.total_equity

        if projected_heat_pct > portfolio.max_portfolio_heat_pct:
            return 0

        return shares


# =========================================================================
# 3. TENANT-ISOLATED TRIPLE-BARRIER PORTFOLIO & RISK MANAGER
# =========================================================================

class TripleBarrierPortfolioManager:
    """
    Executes Zero-Override EOD reconciliation, enforces Tenant Isolation,
    Volatility-Parity position sizing via MetaLabelingSizer, and the 6% Portfolio
    Heat Circuit Breaker.
    """

    def __init__(
        self,
        risk_per_trade_pct: float = 0.01,
        max_single_position_notional_pct: float = 0.15,
    ) -> None:
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_single_position_notional_pct = max_single_position_notional_pct
        self.sizer = MetaLabelingSizer(
            risk_per_trade_pct=risk_per_trade_pct,
            max_single_position_notional_pct=max_single_position_notional_pct,
        )

    def reconcile_and_allocate_tenant_portfolio(
        self,
        portfolio: VirtualPortfolioLedgerSchema,
        featured_df: pd.DataFrame,
        approved_signals: List[MetaLabeledSignalSchema],
        index_registry: Dict[str, IndexConfigSchema],
        as_of_date: date,
    ) -> Tuple[List[ClosedTradeAuditSchema], List[TripleBarrierPositionSchema]]:
        target_ts = pd.Timestamp(as_of_date)
        daily_bars = (
            featured_df.xs(target_ts, level="date")
            if (not featured_df.empty and target_ts in featured_df.index.get_level_values("date"))
            else pd.DataFrame()
        )

        newly_closed: List[ClosedTradeAuditSchema] = []
        newly_opened: List[TripleBarrierPositionSchema] = []

        # STEP 1: EOD Triple-Barrier Evaluation on Existing Open Positions
        for ticker in list(portfolio.open_positions.keys()):
            pos = portfolio.open_positions[ticker]
            if pos.user_id != portfolio.user_id or pos.portfolio_id != portfolio.portfolio_id:
                raise PermissionError(f"Cross-tenant integrity violation on position {pos.position_id}")

            if daily_bars.empty or ticker not in daily_bars.index:
                continue

            bar = daily_bars.loc[ticker]
            high_t = float(bar["high"])
            low_t = float(bar["low"])
            close_t = float(bar["close"])
            atr_t = float(bar["atr_14"]) if not np.isnan(bar["atr_14"]) else pos.entry_atr_14
            idx_cfg = index_registry[pos.index_id]

            exit_reason: Optional[ExitReason] = None
            exit_price: float = close_t

            if low_t <= pos.trailing_stop_price:
                exit_reason = ExitReason.LOWER_BARRIER_SL
                exit_price = pos.trailing_stop_price
            elif high_t >= pos.take_profit_price:
                exit_reason = ExitReason.UPPER_BARRIER_TP
                exit_price = pos.take_profit_price
            elif (pos.bars_held + 1) >= pos.max_holding_bars:
                exit_reason = ExitReason.VERTICAL_BARRIER_TIME
                exit_price = close_t

            if exit_reason is not None:
                proceeds = round(exit_price * pos.shares, 2)
                cost_basis = round(pos.entry_price * pos.shares, 2)
                realized_pnl = round(proceeds - cost_basis, 2)
                initial_dollar_risk = (pos.entry_price - pos.initial_stop_price) * pos.shares
                r_mult = round(realized_pnl / initial_dollar_risk, 4) if initial_dollar_risk > 0 else 0.0

                audit_record = ClosedTradeAuditSchema(
                    position_id=pos.position_id,
                    user_id=portfolio.user_id,
                    portfolio_id=portfolio.portfolio_id,
                    ticker=pos.ticker,
                    index_id=pos.index_id,
                    entry_date=pos.entry_date,
                    exit_date=as_of_date,
                    entry_price=pos.entry_price,
                    exit_price=round(exit_price, 4),
                    shares=pos.shares,
                    bars_held=pos.bars_held + 1,
                    exit_reason=exit_reason,
                    realized_pnl_dollars=realized_pnl,
                    realized_r_multiple=r_mult,
                )
                portfolio.cash_balance = round(portfolio.cash_balance + proceeds, 2)
                portfolio.closed_trades_audit.append(audit_record)
                newly_closed.append(audit_record)
                del portfolio.open_positions[ticker]
            else:
                if as_of_date > pos.last_updated_date:
                    pos.ratchet_trailing_stop(
                        current_high=high_t,
                        current_atr_14=atr_t,
                        k_trail=idx_cfg.k_stop_atr,
                        current_date=as_of_date,
                    )

        # Update Marked-to-Market Total Portfolio Equity
        open_market_value = 0.0
        for ticker, pos in portfolio.open_positions.items():
            mark_price = (
                float(daily_bars.loc[ticker]["close"])
                if (not daily_bars.empty and ticker in daily_bars.index)
                else pos.entry_price
            )
            open_market_value += mark_price * pos.shares

        portfolio.total_equity = round(portfolio.cash_balance + open_market_value, 2)
        portfolio.as_of_date = as_of_date

        # STEP 2: Tenant-Specific Candidate Exclusion & New Allocations
        eligible_signals = [
            sig
            for sig in approved_signals
            if sig.is_approved
            and sig.primary_signal.index_id in portfolio.subscribed_indices
            and sig.primary_signal.ticker not in portfolio.open_positions
        ]
        eligible_signals.sort(
            key=lambda s: s.primary_signal.primary_score * s.meta_conviction_scalar,
            reverse=True,
        )

        for sig in eligible_signals:
            if len(portfolio.open_positions) >= portfolio.max_concurrent_positions:
                break

            shares = self.sizer.calculate_shares(portfolio=portfolio, signal=sig)
            if shares <= 0:
                continue

            entry_price = sig.primary_signal.close_price
            notional_cost = round(shares * entry_price, 2)
            if notional_cost > portfolio.cash_balance:
                continue

            new_pos = TripleBarrierPositionSchema(
                user_id=portfolio.user_id,
                portfolio_id=portfolio.portfolio_id,
                ticker=sig.primary_signal.ticker,
                index_id=sig.primary_signal.index_id,
                entry_date=as_of_date,
                entry_price=entry_price,
                shares=shares,
                entry_atr_14=sig.primary_signal.atr_14,
                initial_stop_price=sig.initial_stop_price,
                trailing_stop_price=sig.initial_stop_price,
                take_profit_price=sig.take_profit_price,
                highest_high_since_entry=entry_price,
                bars_held=0,
                max_holding_bars=sig.max_holding_bars,
                last_updated_date=as_of_date,
            )
            portfolio.cash_balance = round(portfolio.cash_balance - notional_cost, 2)
            portfolio.open_positions[new_pos.ticker] = new_pos
            newly_opened.append(new_pos)

        VirtualPortfolioLedgerSchema.model_validate(portfolio.model_dump())
        return newly_closed, newly_opened


# =========================================================================
# 4. DAILY END-TO-END QUANT ENGINE ORCHESTRATOR
# =========================================================================

class SwingQuantEngineOrchestrator:
    """
    Coordinates the Global Signal Pass (executed once across active indices)
    and the Per-Tenant Portfolio Reconciliation Loop.
    """

    def __init__(self) -> None:
        self.feature_engine = VectorizedFeatureEngine()
        self.backtester = WalkForwardBacktester()
        self.portfolio_manager = TripleBarrierPortfolioManager()

    def execute_daily_quant_cycle(
        self,
        market_df: pd.DataFrame,
        state_store: MultiTenantStateStoreSchema,
        index_constituents_map: Dict[str, List[str]],
        as_of_date: date,
    ) -> Dict[UUID, Dict[str, List]]:
        featured_df = self.feature_engine.compute_universe_features(market_df, as_of_date)
        if featured_df.empty:
            logger.warning(f"Feature DataFrame is empty for {as_of_date}. Aborting cycle.")
            return {}

        if state_store.tenant_portfolios:
            universally_held_tickers = set.intersection(
                *(set(p.open_positions.keys()) for p in state_store.tenant_portfolios.values())
            )
        else:
            universally_held_tickers = set()

        global_approved_signals: List[MetaLabeledSignalSchema] = []
        for idx_id, idx_cfg in state_store.index_registry.items():
            if not idx_cfg.is_active:
                continue
            constituents = index_constituents_map.get(idx_id, [])
            primary_signals = self.feature_engine.screen_index_candidates(
                featured_df=featured_df,
                index_cfg=idx_cfg,
                constituent_tickers=constituents,
                as_of_date=as_of_date,
                excluded_tickers=universally_held_tickers,
            )
            for prim_sig in primary_signals:
                meta_sig = self.backtester.evaluate_and_meta_label(
                    signal=prim_sig,
                    featured_df=featured_df,
                    index_cfg=idx_cfg,
                )
                if meta_sig.is_approved:
                    global_approved_signals.append(meta_sig)

        dispatch_telemetry: Dict[UUID, Dict[str, List]] = {}
        for portfolio_id, portfolio in state_store.tenant_portfolios.items():
            closed_trades, opened_positions = (
                self.portfolio_manager.reconcile_and_allocate_tenant_portfolio(
                    portfolio=portfolio,
                    featured_df=featured_df,
                    approved_signals=global_approved_signals,
                    index_registry=state_store.index_registry,
                    as_of_date=as_of_date,
                )
            )
            dispatch_telemetry[portfolio_id] = {
                "approved_signals": global_approved_signals,
                "opened_positions": opened_positions,
                "closed_trades": closed_trades,
            }

        return dispatch_telemetry
