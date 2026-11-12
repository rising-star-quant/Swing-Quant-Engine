from __future__ import annotations

from datetime import date
import logging
import math
from typing import Dict, List, Optional, Sequence, Set, Tuple
from uuid import UUID

import numpy as np
import pandas as pd

try:
    from src.config import SystemSettings, get_settings
    from src.schemas import (
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
except ImportError:
    from config import SystemSettings, get_settings  # type: ignore[no-redef]
    from schemas import (  # type: ignore[no-redef]
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


# =============================================================================
# 1. TECHNICAL INDICATORS & FEATURE ENGINEERING (FeatureEngineer)
# =============================================================================


class FeatureEngineer:
    """
    Computes strictly Point-in-Time (PiT) technical indicators and
    Dr. Marcos López de Prado's stationary volatility-normalized features
    using vectorized numpy and pandas operations.
    """

    @staticmethod
    def _normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
        working = df.copy()
        col_map: Dict[str, str] = {}
        canonical = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
        for col in working.columns:
            col_lower = str(col).strip().lower()
            if col_lower in canonical and col != canonical[col_lower]:
                col_map[col] = canonical[col_lower]
        if col_map:
            working = working.rename(columns=col_map)
        return working

    @staticmethod
    def compute_atr_14(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Computes True Range: max(High - Low, abs(High - Close.shift(1)), abs(Low - Close.shift(1)))
        and Wilder's / EMA smoothing (`ewm(alpha=1/period, min_periods=period, adjust=False).mean()`).
        """
        if df.empty:
            return pd.Series(dtype=np.float64)

        norm_df = FeatureEngineer._normalize_ohlcv_columns(df)
        high = norm_df["High"].astype(np.float64)
        low = norm_df["Low"].astype(np.float64)
        close = norm_df["Close"].astype(np.float64)
        prev_close = close.shift(1)

        tr_1 = high - low
        tr_2 = (high - prev_close).abs()
        tr_3 = (low - prev_close).abs()
        true_range = pd.Series(
            np.maximum(tr_1.to_numpy(), np.maximum(tr_2.to_numpy(), tr_3.to_numpy())),
            index=norm_df.index,
            dtype=np.float64,
        )

        atr = true_range.ewm(
            alpha=1.0 / float(period),
            min_periods=period,
            adjust=False,
        ).mean()
        atr.name = "ATR_14"
        return atr

    @staticmethod
    def compute_indicators(asset_df: pd.DataFrame, benchmark_df: pd.DataFrame) -> pd.DataFrame:
        """
        Aligns `asset_df` and `benchmark_df` strictly on dates `<= asset_df.index.max()`
        using forward-fill only where strictly necessary (`reindex(asset_df.index, method="ffill")`),
        and computes all moving averages, ATR_14, shifted N-day breakout highs, and
        López de Prado volatility-normalized features.
        """
        if asset_df.empty:
            return pd.DataFrame()

        df = FeatureEngineer._normalize_ohlcv_columns(asset_df)
        df = df.sort_index(ascending=True)
        max_asset_ts = df.index.max()

        # Align benchmark strictly on dates <= asset_df.index.max() with forward-fill
        if benchmark_df is not None and not benchmark_df.empty:
            bench = FeatureEngineer._normalize_ohlcv_columns(benchmark_df)
            bench = bench.sort_index(ascending=True)
            bench = bench.loc[bench.index <= max_asset_ts]
            aligned_bench_close = (
                bench["Close"]
                .astype(np.float64)
                .reindex(df.index, method="ffill")
            )
        else:
            aligned_bench_close = df["Close"].astype(np.float64).copy()

        close = df["Close"].astype(np.float64)
        high = df["High"].astype(np.float64)
        volume = df["Volume"].astype(np.float64)

        # Moving Averages on Close
        df["SMA_20"] = close.rolling(window=20, min_periods=20).mean()
        df["SMA_50"] = close.rolling(window=50, min_periods=50).mean()
        df["SMA_200"] = close.rolling(window=200, min_periods=200).mean()

        # Volume Moving Average, Standard Deviation, and 30-day ADV
        df["VOL_SMA_20"] = volume.rolling(window=20, min_periods=20).mean()
        df["VOL_STD_20"] = volume.rolling(window=20, min_periods=20).std(ddof=1)
        df["ADV_30"] = volume.rolling(window=30, min_periods=30).mean()

        # Wilder's 14-Period Average True Range
        df["ATR_14"] = FeatureEngineer.compute_atr_14(df, period=14)

        # Prior N-day highs strictly shifted by 1 bar to prevent look-ahead bias on breakouts
        df["HIGH_20_PREV"] = high.shift(1).rolling(window=20, min_periods=20).max()
        df["HIGH_15_PREV"] = high.shift(1).rolling(window=15, min_periods=15).max()

        # López de Prado Volatility-Normalized Features
        denom_mom = (df["ATR_14"] * np.sqrt(20.0)).replace(0.0, np.nan)
        df["M_vol_adj"] = (close - close.shift(20)) / denom_mom

        df["V_zscore"] = (volume - df["VOL_SMA_20"]) / df["VOL_STD_20"].replace(0.0, np.nan)

        bench_close_60 = aligned_bench_close.shift(60).replace(0.0, np.nan)
        bench_ratio_60 = (aligned_bench_close / bench_close_60).replace(0.0, np.nan)
        asset_ratio_60 = close / close.shift(60).replace(0.0, np.nan)
        df["RS_60_ratio"] = asset_ratio_60 / bench_ratio_60

        asset_ret_60 = (close / close.shift(60).replace(0.0, np.nan)) - 1.0
        bench_ret_60 = (aligned_bench_close / bench_close_60) - 1.0
        asset_daily_ret = close.pct_change(1)
        bench_daily_ret = aligned_bench_close.pct_change(1)
        daily_excess_ret = asset_daily_ret - bench_daily_ret
        tracking_vol_60 = (
            daily_excess_ret.rolling(window=60, min_periods=60).std(ddof=1) * np.sqrt(60.0)
        ).replace(0.0, np.nan)
        df["RS_norm"] = (asset_ret_60 - bench_ret_60) / tracking_vol_60

        return df


# =============================================================================
# 2. PRIMARY DIRECTIONAL MODEL & TAILORED INDEX PIPELINES (PrimaryScreeningEngine)
# =============================================================================


class PrimaryScreeningEngine:
    """
    Executes Step B.1 Primary Directional Model (Side = +1 Long-Only):
    1. Enforces Jim Simons' Liquidity & Slippage Gates.
    2. Routes candidates through tailored index calculation pipelines (SMALL_CAP, MID_CAP, LARGE_CAP).
    3. Applies cross-sectional 2.5th/97.5th percentile Winsorization, Z-score standardization,
       and normal CDF mapping onto [0.0, 100.0].
    """

    MIN_REQUIRED_BARS = 205

    def __init__(self, settings: Optional[SystemSettings] = None) -> None:
        self.settings: SystemSettings = settings or get_settings()

    @staticmethod
    def _passes_liquidity_gates(
        row: pd.Series,
        index_cfg: IndexConfigSchema,
        relative_spread: float = 0.0,
    ) -> bool:
        """
        Step 1 — Simons Liquidity & Slippage Gates:
        - close_price >= index_cfg.min_price
        - adv_30d >= index_cfg.min_adv_30d
        - relative_spread <= index_cfg.max_relative_spread
        - atr_14 > 0 and no NaN in required features
        """
        required_fields = (
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
            "SMA_20",
            "SMA_50",
            "SMA_200",
            "VOL_SMA_20",
            "ADV_30",
            "ATR_14",
            "HIGH_20_PREV",
            "HIGH_15_PREV",
            "M_vol_adj",
            "V_zscore",
            "RS_60_ratio",
            "RS_norm",
        )
        for field in required_fields:
            if field not in row or pd.isna(row[field]) or np.isinf(float(row[field])):
                return False

        close_price = float(row["Close"])
        adv_30d = float(row["ADV_30"])
        atr_14 = float(row["ATR_14"])

        if close_price < index_cfg.min_price:
            return False
        if adv_30d < float(index_cfg.min_adv_30d):
            return False
        if relative_spread > index_cfg.max_relative_spread:
            return False
        if atr_14 <= 0.0:
            return False

        return True

    @staticmethod
    def _passes_index_pipeline(row: pd.Series, index_cfg: IndexConfigSchema) -> bool:
        """
        Step 2 — Tailored Index Pipeline Rules:
        - SMALL_CAP: Close > SMA_200 and Close > SMA_50, Close >= HIGH_20_PREV,
                     Volume >= volume_surge_multiplier * VOL_SMA_20, RS_60_ratio > 1.05.
        - MID_CAP: Close > SMA_200 and SMA_20 > SMA_50,
                   (Close >= HIGH_15_PREV OR (Low <= SMA_20 * 1.015 and Close > SMA_20 and Close > Open)),
                   Volume >= volume_surge_multiplier * VOL_SMA_20.
        - LARGE_CAP: Close > SMA_200, Close > SMA_20, M_vol_adj > 0.5,
                     Volume >= volume_surge_multiplier * VOL_SMA_20.
        """
        try:
            open_p = float(row["Open"])
            low_p = float(row["Low"])
            close_p = float(row["Close"])
            vol = float(row["Volume"])
            sma_20 = float(row["SMA_20"])
            sma_50 = float(row["SMA_50"])
            sma_200 = float(row["SMA_200"])
            vol_sma_20 = float(row["VOL_SMA_20"])
            high_20_prev = float(row["HIGH_20_PREV"])
            high_15_prev = float(row["HIGH_15_PREV"])
            m_vol_adj = float(row["M_vol_adj"])
            rs_60_ratio = float(row["RS_60_ratio"])
        except (KeyError, TypeError, ValueError):
            return False

        if any(
            np.isnan(val)
            for val in (
                open_p,
                low_p,
                close_p,
                vol,
                sma_20,
                sma_50,
                sma_200,
                vol_sma_20,
                high_20_prev,
                high_15_prev,
                m_vol_adj,
                rs_60_ratio,
            )
        ):
            return False

        vol_threshold = index_cfg.volume_surge_multiplier * vol_sma_20

        if index_cfg.tier == IndexTier.SMALL_CAP:
            trend_ok = (close_p > sma_200) and (close_p > sma_50)
            trigger_ok = (close_p >= high_20_prev) and (vol >= vol_threshold)
            rs_ok = rs_60_ratio > 1.05
            return bool(trend_ok and trigger_ok and rs_ok)

        if index_cfg.tier == IndexTier.MID_CAP:
            trend_ok = (close_p > sma_200) and (sma_20 > sma_50)
            breakout_cond = close_p >= high_15_prev
            pullback_cond = (
                (low_p <= sma_20 * 1.015)
                and (close_p > sma_20)
                and (close_p > open_p)
            )
            trigger_ok = (breakout_cond or pullback_cond) and (vol >= vol_threshold)
            return bool(trend_ok and trigger_ok)

        # IndexTier.LARGE_CAP
        trend_ok = close_p > sma_200
        trigger_ok = (
            (close_p > sma_20)
            and (m_vol_adj > 0.5)
            and (vol >= vol_threshold)
        )
        return bool(trend_ok and trigger_ok)

    @staticmethod
    def _winsorize_and_zscore(values: np.ndarray) -> np.ndarray:
        """
        Winsorizes a 1D feature vector at the 2.5th and 97.5th percentiles
        and standardizes to cross-sectional Z-scores (returning zeros if < 2 candidates or std == 0).
        """
        n = len(values)
        if n < 2:
            return np.zeros(n, dtype=np.float64)

        p_low, p_high = np.nanpercentile(values, [2.5, 97.5])
        clipped = np.clip(values, p_low, p_high)
        mean_val = float(np.nanmean(clipped))
        std_val = float(np.nanstd(clipped, ddof=1))

        if np.isnan(std_val) or std_val <= 1e-9:
            return np.zeros(n, dtype=np.float64)

        return (clipped - mean_val) / std_val

    @staticmethod
    def _normal_cdf_score(z_val: float) -> float:
        """Maps a composite Z-score onto [0.0, 100.0] via the standard normal CDF."""
        score = 50.0 * (1.0 + math.erf(float(z_val) / math.sqrt(2.0)))
        return round(float(np.clip(score, 0.0, 100.0)), 4)

    def score_and_rank_candidates(
        self,
        candidate_rows: Dict[str, pd.Series],
        index_cfg: IndexConfigSchema,
        as_of_date: date,
        top_n: Optional[int] = None,
    ) -> List[DirectionalSignalSchema]:
        """
        Step 3 — Cross-Sectional Winsorization, Z-Score Standardization & Ranking:
        Winsorizes M_vol_adj, V_zscore, and RS_norm at [2.5, 97.5] percentiles,
        computes weighted composite Z_comp, maps to [0.0, 100.0] via standard normal CDF,
        and returns the top_n validated DirectionalSignalSchema instances sorted descending.
        """
        if not candidate_rows:
            return []

        limit_n = top_n if top_n is not None else self.settings.top_n_candidates_per_index
        tickers = list(candidate_rows.keys())

        m_arr = np.array([float(candidate_rows[t]["M_vol_adj"]) for t in tickers], dtype=np.float64)
        v_arr = np.array([float(candidate_rows[t]["V_zscore"]) for t in tickers], dtype=np.float64)
        rs_arr = np.array([float(candidate_rows[t]["RS_norm"]) for t in tickers], dtype=np.float64)

        z_m = self._winsorize_and_zscore(m_arr)
        z_v = self._winsorize_and_zscore(v_arr)
        z_rs = self._winsorize_and_zscore(rs_arr)

        z_comp = (
            index_cfg.weight_momentum * z_m
            + index_cfg.weight_volume * z_v
            + index_cfg.weight_rs * z_rs
        )

        signals: List[DirectionalSignalSchema] = []
        for idx, ticker in enumerate(tickers):
            row = candidate_rows[ticker]
            primary_score = self._normal_cdf_score(float(z_comp[idx]))
            signals.append(
                DirectionalSignalSchema(
                    as_of_date=as_of_date,
                    ticker=ticker,
                    index_id=index_cfg.index_id,
                    side=1,
                    close_price=round(float(row["Close"]), 4),
                    atr_14=round(float(row["ATR_14"]), 4),
                    adv_30d=round(float(row["ADV_30"]), 2),
                    vol_adj_momentum=round(float(row["M_vol_adj"]), 4),
                    volume_zscore=round(float(row["V_zscore"]), 4),
                    norm_relative_strength=round(float(row["RS_norm"]), 4),
                    primary_score=primary_score,
                )
            )

        signals.sort(key=lambda s: (s.primary_score, s.vol_adj_momentum), reverse=True)
        return signals[:limit_n]

    def screen_index_universe(
        self,
        ohlcv_map: Dict[str, pd.DataFrame],
        benchmark_df: pd.DataFrame,
        index_cfg: IndexConfigSchema,
        as_of_date: date,
        spread_map: Optional[Dict[str, float]] = None,
        excluded_tickers: Optional[Set[str]] = None,
        top_n: Optional[int] = None,
    ) -> List[DirectionalSignalSchema]:
        """
        Evaluates all constituent OHLCV DataFrames for an index strictly up to `as_of_date`,
        filtering through Liquidity Gates and Tailored Index Pipeline Rules, then scoring and ranking.
        """
        if benchmark_df is None or benchmark_df.empty:
            return []

        excluded = {t.strip().upper() for t in (excluded_tickers or set())}
        spreads = spread_map or {}
        as_of_ts = pd.Timestamp(as_of_date)

        bench_truncated = benchmark_df.loc[benchmark_df.index <= as_of_ts]
        if len(bench_truncated) < self.MIN_REQUIRED_BARS:
            return []

        passing_rows: Dict[str, pd.Series] = {}

        for raw_ticker, asset_df in ohlcv_map.items():
            ticker = raw_ticker.strip().upper()
            if ticker in excluded or asset_df is None or asset_df.empty:
                continue

            truncated = asset_df.loc[asset_df.index <= as_of_ts]
            if len(truncated) < self.MIN_REQUIRED_BARS:
                continue

            latest_bar_ts = truncated.index[-1]
            if latest_bar_ts != as_of_ts:
                continue

            ind_df = FeatureEngineer.compute_indicators(truncated, bench_truncated)
            if ind_df.empty or as_of_ts not in ind_df.index:
                continue

            row = ind_df.loc[as_of_ts]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]

            rel_spread = float(spreads.get(ticker, 0.0))
            if not self._passes_liquidity_gates(row, index_cfg, relative_spread=rel_spread):
                continue

            if not self._passes_index_pipeline(row, index_cfg):
                continue

            passing_rows[ticker] = row

        return self.score_and_rank_candidates(
            candidate_rows=passing_rows,
            index_cfg=index_cfg,
            as_of_date=as_of_date,
            top_n=top_n,
        )


# =============================================================================
# 3. 500-DAY PER-ASSET TRIPLE-BARRIER BACKTEST HARNESS & META-LABELING ENGINE
# =============================================================================


class MetaLabelingBacktestEngine:
    """
    Implements Dr. Marcos López de Prado's secondary Meta-Labeling gate on up to
    `settings.backtest_lookback_days` (500 trading days) strictly prior to `as_of_date`.
    Simulates non-overlapping Triple-Barrier trades with conservative intra-bar stop priority
    and Chandelier trailing stop ratcheting.
    """

    MIN_HISTORICAL_TRADES = 3
    MIN_WIN_RATE_THRESHOLD = 0.30

    def __init__(self, settings: Optional[SystemSettings] = None) -> None:
        self.settings: SystemSettings = settings or get_settings()

    def evaluate_candidate(
        self,
        signal: DirectionalSignalSchema,
        asset_df: pd.DataFrame,
        benchmark_df: pd.DataFrame,
        index_cfg: IndexConfigSchema,
    ) -> MetaLabeledSignalSchema:
        """
        Executes a 500-day walk-forward Triple-Barrier simulation on `asset_df` strictly
        bounded by `<= signal.as_of_date`, computes empirical win rate and EV in R-multiples,
        and determines the Meta-Labeling conviction scalar `phi_meta` in [0.0, 1.25].
        """
        as_of_ts = pd.Timestamp(signal.as_of_date)
        max_lookback = self.settings.backtest_lookback_days

        asset_pit = asset_df.loc[asset_df.index <= as_of_ts].tail(max_lookback).copy()
        bench_pit = benchmark_df.loc[benchmark_df.index <= as_of_ts].tail(max_lookback).copy()

        ind_df = FeatureEngineer.compute_indicators(asset_pit, bench_pit)
        r_multiples = self._simulate_historical_triple_barrier_trades(ind_df, index_cfg)

        if len(r_multiples) < self.MIN_HISTORICAL_TRADES:
            historical_win_rate = 0.0
            historical_ev_r_multiple = 0.0
        else:
            wins = sum(1 for r in r_multiples if r > 0.0)
            historical_win_rate = round(float(wins) / float(len(r_multiples)), 4)
            historical_ev_r_multiple = round(float(np.mean(r_multiples)), 4)

        if (
            historical_ev_r_multiple <= 0.0
            or historical_win_rate < self.MIN_WIN_RATE_THRESHOLD
        ):
            is_approved = False
            meta_conviction_scalar = 0.0
        else:
            is_approved = True
            raw_phi = (
                0.50
                + 0.35 * min(historical_ev_r_multiple, 1.5)
                + 0.225 * (signal.primary_score / 100.0)
            )
            meta_conviction_scalar = round(float(np.clip(raw_phi, 0.50, 1.25)), 4)

        initial_stop_price = round(
            max(0.01, signal.close_price - index_cfg.k_stop_atr * signal.atr_14),
            4,
        )
        take_profit_price = round(
            signal.close_price + index_cfg.k_profit_atr * signal.atr_14,
            4,
        )
        lookback_used = int(np.clip(len(ind_df), 250, max(250, max_lookback)))

        return MetaLabeledSignalSchema(
            primary_signal=signal,
            backtest_lookback_days=lookback_used,
            historical_win_rate=historical_win_rate,
            historical_ev_r_multiple=historical_ev_r_multiple,
            meta_conviction_scalar=meta_conviction_scalar,
            is_approved=is_approved,
            initial_stop_price=initial_stop_price,
            take_profit_price=take_profit_price,
            max_holding_bars=index_cfg.max_holding_bars,
        )

    def _simulate_historical_triple_barrier_trades(
        self,
        ind_df: pd.DataFrame,
        index_cfg: IndexConfigSchema,
    ) -> List[float]:
        """
        Steps across historical bars `[200 ... T - max_holding_bars - 1]`, triggering non-overlapping
        simulated trades whenever `_passes_index_pipeline` is True, and resolving exits via
        Lower Barrier (SL), Upper Barrier (TP), or Vertical Barrier (Time-Stop).
        """
        total_bars = len(ind_df)
        max_hold = index_cfg.max_holding_bars
        if total_bars <= 200 + max_hold:
            return []

        opens = ind_df["Open"].to_numpy(dtype=np.float64)
        highs = ind_df["High"].to_numpy(dtype=np.float64)
        lows = ind_df["Low"].to_numpy(dtype=np.float64)
        closes = ind_df["Close"].to_numpy(dtype=np.float64)
        atrs = ind_df["ATR_14"].to_numpy(dtype=np.float64)

        r_multiples: List[float] = []
        i = 200
        upper_entry_bound = total_bars - max_hold - 1

        while i <= upper_entry_bound:
            row = ind_df.iloc[i]
            if (
                PrimaryScreeningEngine._passes_liquidity_gates(row, index_cfg, 0.0)
                and PrimaryScreeningEngine._passes_index_pipeline(row, index_cfg)
            ):
                entry_price = float(closes[i])
                entry_atr = float(atrs[i])
                sl_0 = entry_price - index_cfg.k_stop_atr * entry_atr
                initial_risk = entry_price - sl_0

                if initial_risk <= 1e-6:
                    i += 1
                    continue

                sl_current = sl_0
                tp_price = entry_price + index_cfg.k_profit_atr * entry_atr
                highest_high = float(highs[i])

                exit_price = entry_price
                exit_bar_index = i + max_hold

                for j in range(i + 1, min(i + max_hold, total_bars - 1) + 1):
                    open_j = float(opens[j])
                    high_j = float(highs[j])
                    low_j = float(lows[j])
                    close_j = float(closes[j])
                    atr_j = float(atrs[j]) if not np.isnan(atrs[j]) and atrs[j] > 0 else entry_atr

                    # 1. Conservative intra-bar Lower Barrier (Stop-Loss) check first
                    if low_j <= sl_current:
                        exit_price = min(open_j, sl_current)
                        exit_bar_index = j
                        break

                    # 2. Upper Barrier (Take-Profit) check
                    if high_j >= tp_price:
                        exit_price = max(open_j, tp_price)
                        exit_bar_index = j
                        break

                    # 3. Ratchet Chandelier trailing stop upward
                    highest_high = max(highest_high, high_j)
                    candidate_sl = highest_high - index_cfg.k_stop_atr * atr_j
                    sl_current = max(sl_current, candidate_sl)

                    # 4. Vertical Barrier (Time-Stop) check at max_holding_bars
                    if j == i + max_hold:
                        exit_price = close_j
                        exit_bar_index = j
                        break

                realized_r = (exit_price - entry_price) / initial_risk
                r_multiples.append(float(realized_r))
                # Advance past exit_bar_index to guarantee non-overlapping trade windows
                i = exit_bar_index + 1
            else:
                i += 1

        return r_multiples


# =============================================================================
# 4. PER-TENANT PORTFOLIO RECONCILIATION & RISK SIZING ENGINE
# =============================================================================


class TenantPortfolioReconciler:
    """
    Executes Jim Simons' Zero-Override position management and risk gates
    strictly isolated per `VirtualPortfolioLedgerSchema`.
    """

    def __init__(self, settings: Optional[SystemSettings] = None) -> None:
        self.settings: SystemSettings = settings or get_settings()

    def reconcile_open_positions(
        self,
        ledger: VirtualPortfolioLedgerSchema,
        ohlcv_map: Dict[str, pd.DataFrame],
        index_registry: Dict[str, IndexConfigSchema],
        as_of_date: date,
    ) -> List[ClosedTradeAuditSchema]:
        """
        Step 1 — EOD Triple-Barrier Evaluation on Open Positions:
        Evaluates all open positions in `ledger.open_positions` against Lower Barrier (SL),
        Upper Barrier (TP), and Vertical Barrier (Time-Stop), or ratchets trailing stops upward.
        Marks `ledger.total_equity` to market and updates `ledger.as_of_date`.
        """
        as_of_ts = pd.Timestamp(as_of_date)
        closed_events: List[ClosedTradeAuditSchema] = []
        latest_close_lookup: Dict[str, float] = {}

        for ticker in list(ledger.open_positions.keys()):
            pos = ledger.open_positions[ticker]

            if pos.user_id != ledger.user_id or pos.portfolio_id != ledger.portfolio_id:
                raise ValueError(
                    f"CRITICAL SECURITY BREACH: Cross-tenant position detected for {ticker}!"
                )

            raw_df = ohlcv_map.get(ticker)
            if raw_df is None or raw_df.empty:
                latest_close_lookup[ticker] = pos.entry_price
                continue

            norm_df = FeatureEngineer._normalize_ohlcv_columns(raw_df)
            norm_df = norm_df.loc[norm_df.index <= as_of_ts].sort_index(ascending=True)
            if norm_df.empty:
                latest_close_lookup[ticker] = pos.entry_price
                continue

            latest_close_lookup[ticker] = float(norm_df.iloc[-1]["Close"])

            # Preserve idempotency if already updated on or after as_of_date
            if as_of_date <= pos.last_updated_date:
                continue

            if as_of_ts not in norm_df.index:
                continue

            bar = norm_df.loc[as_of_ts]
            if isinstance(bar, pd.DataFrame):
                bar = bar.iloc[-1]

            open_t = float(bar["Open"]) if "Open" in bar and not pd.isna(bar["Open"]) else float(bar["Close"])
            high_t = float(bar["High"])
            low_t = float(bar["Low"])
            close_t = float(bar["Close"])

            if "ATR_14" in bar and not pd.isna(bar["ATR_14"]) and float(bar["ATR_14"]) > 0.0:
                current_atr = float(bar["ATR_14"])
            elif "atr_14" in bar and not pd.isna(bar["atr_14"]) and float(bar["atr_14"]) > 0.0:
                current_atr = float(bar["atr_14"])
            else:
                atr_series = FeatureEngineer.compute_atr_14(norm_df, period=14)
                atr_val = float(atr_series.iloc[-1]) if not atr_series.empty else np.nan
                current_atr = atr_val if not np.isnan(atr_val) and atr_val > 0.0 else pos.entry_atr_14

            index_cfg = index_registry.get(pos.index_id)
            k_trail = index_cfg.k_stop_atr if index_cfg is not None else 2.0

            exit_reason: Optional[ExitReason] = None
            exit_price: float = close_t

            # Priority 1: Lower Barrier (Stop-Loss Hit)
            if low_t <= pos.trailing_stop_price:
                exit_price = round(min(open_t, pos.trailing_stop_price), 4)
                exit_reason = ExitReason.LOWER_BARRIER_SL

            # Priority 2: Upper Barrier (Take-Profit Hit)
            elif high_t >= pos.take_profit_price:
                exit_price = round(max(open_t, pos.take_profit_price), 4)
                exit_reason = ExitReason.UPPER_BARRIER_TP

            # Priority 3: Vertical Barrier (Time-Stop Hit)
            elif (pos.bars_held + 1) >= pos.max_holding_bars:
                exit_price = round(close_t, 4)
                exit_reason = ExitReason.VERTICAL_BARRIER_TIME

            if exit_reason is not None:
                realized_pnl_dollars = round((exit_price - pos.entry_price) * pos.shares, 2)
                initial_risk_per_share = max(pos.entry_price - pos.initial_stop_price, 1e-6)
                realized_r_multiple = round(
                    (exit_price - pos.entry_price) / initial_risk_per_share,
                    4,
                )

                ledger.cash_balance = round(
                    ledger.cash_balance + round(exit_price * pos.shares, 2),
                    2,
                )

                audit_event = ClosedTradeAuditSchema(
                    position_id=pos.position_id,
                    user_id=ledger.user_id,
                    portfolio_id=ledger.portfolio_id,
                    ticker=pos.ticker,
                    index_id=pos.index_id,
                    entry_date=pos.entry_date,
                    exit_date=as_of_date,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    shares=pos.shares,
                    bars_held=pos.bars_held + 1,
                    exit_reason=exit_reason,
                    realized_pnl_dollars=realized_pnl_dollars,
                    realized_r_multiple=realized_r_multiple,
                )
                ledger.closed_trades_audit.append(audit_event)
                closed_events.append(audit_event)
                del ledger.open_positions[ticker]
            else:
                pos.ratchet_trailing_stop(
                    current_high=high_t,
                    current_atr_14=current_atr,
                    k_trail=k_trail,
                    current_date=as_of_date,
                )

        # Mark-to-market total portfolio equity
        open_positions_market_value = 0.0
        for ticker, pos in ledger.open_positions.items():
            latest_px = latest_close_lookup.get(ticker, pos.entry_price)
            open_positions_market_value += pos.shares * latest_px

        ledger.total_equity = round(ledger.cash_balance + open_positions_market_value, 2)
        ledger.as_of_date = as_of_date
        return closed_events

    def allocate_new_signals(
        self,
        ledger: VirtualPortfolioLedgerSchema,
        approved_signals: Sequence[MetaLabeledSignalSchema],
        as_of_date: date,
    ) -> List[TripleBarrierPositionSchema]:
        """
        Step 2 — Meta-Labeled Entry Sizing & Portfolio Heat Gate:
        Filters approved signals for subscribed indices and unheld tickers,
        ranks by `(meta_conviction_scalar * primary_score)`, sizes shares under
        Volatility-Parity and remaining Portfolio Heat budget, and allocates positions.
        """
        eligible_candidates: List[MetaLabeledSignalSchema] = [
            sig
            for sig in approved_signals
            if sig.is_approved
            and sig.primary_signal.index_id in ledger.subscribed_indices
            and sig.primary_signal.ticker not in ledger.open_positions
        ]

        eligible_candidates.sort(
            key=lambda s: (
                s.meta_conviction_scalar * s.primary_signal.primary_score,
                s.historical_ev_r_multiple,
            ),
            reverse=True,
        )

        newly_opened: List[TripleBarrierPositionSchema] = []

        for sig in eligible_candidates:
            if len(ledger.open_positions) >= ledger.max_concurrent_positions:
                break

            ticker = sig.primary_signal.ticker
            if ticker in ledger.open_positions:
                continue

            current_open_risk_dollars = sum(
                p.open_dollar_risk for p in ledger.open_positions.values()
            )
            max_heat_dollars = ledger.max_portfolio_heat_pct * ledger.total_equity
            remaining_heat_dollars = max_heat_dollars - current_open_risk_dollars

            if remaining_heat_dollars <= 0.0:
                break

            target_risk_dollars = min(
                ledger.total_equity
                * self.settings.base_risk_per_trade_pct
                * sig.meta_conviction_scalar,
                remaining_heat_dollars,
            )

            entry_price = sig.primary_signal.close_price
            risk_per_share = entry_price - sig.initial_stop_price
            if risk_per_share <= 0.0:
                continue

            shares = int(math.floor(target_risk_dollars / risk_per_share))
            max_affordable_shares = int(math.floor(ledger.cash_balance / entry_price))
            shares = min(shares, max_affordable_shares)

            if shares <= 0:
                continue

            cost_dollars = round(shares * entry_price, 2)
            if cost_dollars > ledger.cash_balance:
                continue

            ledger.cash_balance = round(ledger.cash_balance - cost_dollars, 2)

            new_position = TripleBarrierPositionSchema(
                user_id=ledger.user_id,
                portfolio_id=ledger.portfolio_id,
                ticker=ticker,
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

            ledger.open_positions[ticker] = new_position
            newly_opened.append(new_position)

        VirtualPortfolioLedgerSchema.model_validate(ledger.model_dump())
        return newly_opened


# =============================================================================
# 5. MULTI-INDEX VECTORIZED COMPATIBILITY & ORCHESTRATION ADAPTERS
# =============================================================================


class VectorizedFeatureEngine:
    """
    Vectorized MultiIndex `(date, ticker)` feature computation and screening engine
    maintaining full compatibility with existing test suites and orchestrators.
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

        df["prev_close"] = grouped["close"].shift(1)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["prev_close"]).abs()
        tr3 = (df["low"] - df["prev_close"]).abs()
        df["tr"] = np.maximum(tr1, np.maximum(tr2, tr3))

        df["atr_14"] = grouped["tr"].transform(
            lambda s: s.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
        )

        df["sma_20"] = grouped["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
        df["sma_50"] = grouped["close"].transform(lambda s: s.rolling(50, min_periods=50).mean())
        df["sma_200"] = grouped["close"].transform(lambda s: s.rolling(200, min_periods=200).mean())
        df["adv_30d"] = grouped["volume"].transform(lambda s: s.rolling(30, min_periods=30).mean())

        df["prior_high_20"] = grouped["high"].transform(
            lambda s: s.shift(1).rolling(20, min_periods=20).max()
        )
        df["prior_high_15"] = grouped["high"].transform(
            lambda s: s.shift(1).rolling(15, min_periods=15).max()
        )

        df["vol_sma_20"] = grouped["volume"].transform(
            lambda s: s.shift(1).rolling(20, min_periods=20).mean()
        )
        df["vol_std_20"] = grouped["volume"].transform(
            lambda s: s.shift(1).rolling(20, min_periods=20).std(ddof=1)
        )
        df["volume_ratio_20"] = df["volume"] / df["vol_sma_20"].replace(0, np.nan)
        df["volume_zscore"] = (df["volume"] - df["vol_sma_20"]) / df["vol_std_20"].replace(0, np.nan)

        close_20d_ago = grouped["close"].shift(20)
        df["vol_adj_momentum"] = (df["close"] - close_20d_ago) / (
            df["atr_14"] * np.sqrt(20.0)
        ).replace(0, np.nan)

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
            return []

        benchmark_symbol = index_cfg.benchmark_ticker.upper()
        rs_norm_map = self._compute_relative_strength_vs_benchmark(
            featured_df=featured_df,
            tickers=eligible_tickers,
            benchmark_ticker=benchmark_symbol,
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

        liquidity_mask = (
            (daily_slice["close"] >= index_cfg.min_price)
            & (daily_slice["adv_30d"] >= index_cfg.min_adv_30d)
            & (daily_slice["atr_14"] > 0.0)
        )
        daily_slice = daily_slice.loc[liquidity_mask]
        if daily_slice.empty:
            return []

        if index_cfg.tier == IndexTier.SMALL_CAP:
            regime_mask = (
                (daily_slice["close"] > daily_slice["sma_200"])
                & (daily_slice["close"] > daily_slice["sma_50"])
                & (daily_slice["close"] >= daily_slice["prior_high_20"])
                & (daily_slice["volume_ratio_20"] >= index_cfg.volume_surge_multiplier)
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
                & (daily_slice["volume_ratio_20"] >= index_cfg.volume_surge_multiplier)
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

        z_m = PrimaryScreeningEngine._winsorize_and_zscore(
            candidates["vol_adj_momentum"].to_numpy(dtype=np.float64)
        )
        z_v = PrimaryScreeningEngine._winsorize_and_zscore(
            candidates["volume_zscore"].to_numpy(dtype=np.float64)
        )
        z_rs = PrimaryScreeningEngine._winsorize_and_zscore(
            candidates["norm_relative_strength"].to_numpy(dtype=np.float64)
        )

        z_comp = (
            index_cfg.weight_momentum * z_m
            + index_cfg.weight_volume * z_v
            + index_cfg.weight_rs * z_rs
        )
        candidates["primary_score"] = [
            PrimaryScreeningEngine._normal_cdf_score(float(z)) for z in z_comp
        ]

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


class WalkForwardBacktester(MetaLabelingBacktestEngine):
    """
    Backward-compatible adapter extending `MetaLabelingBacktestEngine` with
    MultiIndex `(date, ticker)` helper methods.
    """

    def evaluate_and_meta_label(
        self,
        signal: DirectionalSignalSchema,
        featured_df: pd.DataFrame,
        index_cfg: IndexConfigSchema,
    ) -> MetaLabeledSignalSchema:
        ticker = signal.ticker
        asset_df = featured_df.xs(ticker, level="ticker").copy()
        bench_ticker = index_cfg.benchmark_ticker.upper()
        if bench_ticker in featured_df.index.get_level_values("ticker"):
            bench_df = featured_df.xs(bench_ticker, level="ticker").copy()
        else:
            bench_df = asset_df.copy()

        return self.evaluate_candidate(
            signal=signal,
            asset_df=asset_df,
            benchmark_df=bench_df,
            index_cfg=index_cfg,
        )

    def _simulate_historical_triple_barrier_trades(  # type: ignore[override]
        self,
        hist_df: pd.DataFrame,
        index_cfg: IndexConfigSchema,
    ) -> List[float]:
        if "Close" in hist_df.columns and "HIGH_15_PREV" in hist_df.columns:
            return super()._simulate_historical_triple_barrier_trades(hist_df, index_cfg)

        if len(hist_df) < 60:
            return []

        norm_df = FeatureEngineer._normalize_ohlcv_columns(hist_df)
        closes = norm_df["Close"].to_numpy(dtype=np.float64)
        highs = norm_df["High"].to_numpy(dtype=np.float64)
        lows = norm_df["Low"].to_numpy(dtype=np.float64)
        opens = (
            norm_df["Open"].to_numpy(dtype=np.float64)
            if "Open" in norm_df.columns
            else closes.copy()
        )
        atrs = (
            hist_df["atr_14"].to_numpy(dtype=np.float64)
            if "atr_14" in hist_df.columns
            else FeatureEngineer.compute_atr_14(norm_df).to_numpy(dtype=np.float64)
        )
        sma50 = (
            hist_df["sma_50"].to_numpy(dtype=np.float64)
            if "sma_50" in hist_df.columns
            else norm_df["Close"].rolling(50, min_periods=50).mean().to_numpy(dtype=np.float64)
        )
        prior_h15 = (
            hist_df["prior_high_15"].to_numpy(dtype=np.float64)
            if "prior_high_15" in hist_df.columns
            else norm_df["High"].shift(1).rolling(15, min_periods=15).max().to_numpy(dtype=np.float64)
        )
        vol_ratio = (
            hist_df["volume_ratio_20"].to_numpy(dtype=np.float64)
            if "volume_ratio_20" in hist_df.columns
            else (
                norm_df["Volume"]
                / norm_df["Volume"].shift(1).rolling(20, min_periods=20).mean().replace(0, np.nan)
            ).to_numpy(dtype=np.float64)
        )

        r_outcomes: List[float] = []
        i = 20
        n = len(hist_df)
        max_hold = index_cfg.max_holding_bars

        while i < n - max_hold:
            if (
                not np.isnan(atrs[i])
                and atrs[i] > 0.0
                and closes[i] > sma50[i]
                and closes[i] >= prior_h15[i]
                and vol_ratio[i] >= 1.25
            ):
                entry_p = float(closes[i])
                initial_risk = index_cfg.k_stop_atr * float(atrs[i])
                trail_stop = entry_p - initial_risk
                target_p = entry_p + (index_cfg.k_profit_atr * float(atrs[i]))
                highest_h = float(highs[i])

                exit_p = float(closes[min(i + max_hold, n - 1)])
                bars_elapsed = max_hold

                for step in range(1, max_hold + 1):
                    idx = i + step
                    if lows[idx] <= trail_stop:
                        exit_p = min(float(opens[idx]), trail_stop)
                        bars_elapsed = step
                        break
                    if highs[idx] >= target_p:
                        exit_p = max(float(opens[idx]), target_p)
                        bars_elapsed = step
                        break
                    highest_h = max(highest_h, float(highs[idx]))
                    atr_step = float(atrs[idx]) if not np.isnan(atrs[idx]) else float(atrs[i])
                    candidate_stop = highest_h - (index_cfg.k_stop_atr * atr_step)
                    trail_stop = max(trail_stop, candidate_stop)

                r_mult = (exit_p - entry_p) / initial_risk
                r_outcomes.append(float(r_mult))
                i += bars_elapsed
            else:
                i += 1

        return r_outcomes


PerAssetTripleBarrierBacktester = WalkForwardBacktester


class TripleBarrierPortfolioManager(TenantPortfolioReconciler):
    """
    Adapter bridging `TenantPortfolioReconciler` to the `(date, ticker)` MultiIndex
    `reconcile_and_allocate_tenant_portfolio` signature used by existing tests and runners.
    """

    def __init__(
        self,
        risk_per_trade_pct: float = 0.01,
        max_single_position_notional_pct: float = 0.15,
        settings: Optional[SystemSettings] = None,
    ) -> None:
        super().__init__(settings=settings)
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_single_position_notional_pct = max_single_position_notional_pct

    def reconcile_and_allocate_tenant_portfolio(
        self,
        portfolio: VirtualPortfolioLedgerSchema,
        featured_df: pd.DataFrame,
        approved_signals: List[MetaLabeledSignalSchema],
        index_registry: Dict[str, IndexConfigSchema],
        as_of_date: date,
    ) -> Tuple[List[ClosedTradeAuditSchema], List[TripleBarrierPositionSchema]]:
        ohlcv_map: Dict[str, pd.DataFrame] = {}
        if not featured_df.empty:
            if isinstance(featured_df.index, pd.MultiIndex):
                for ticker, sub_df in featured_df.groupby(level="ticker"):
                    single_df = sub_df.droplevel("ticker").copy()
                    if "Open" not in single_df.columns and "open" not in single_df.columns:
                        single_df["Open"] = single_df["close"]
                    ohlcv_map[str(ticker)] = single_df
            else:
                for ticker in portfolio.open_positions:
                    ohlcv_map[ticker] = featured_df

        closed_trades = self.reconcile_open_positions(
            ledger=portfolio,
            ohlcv_map=ohlcv_map,
            index_registry=index_registry,
            as_of_date=as_of_date,
        )
        opened_positions = self.allocate_new_signals(
            ledger=portfolio,
            approved_signals=approved_signals,
            as_of_date=as_of_date,
        )
        return closed_trades, opened_positions


class SwingQuantEngineOrchestrator:
    """
    Coordinates the Global Signal Pass (executed once across active indices)
    and the Per-Tenant Portfolio Reconciliation Loop.
    """

    def __init__(self, settings: Optional[SystemSettings] = None) -> None:
        self.settings: SystemSettings = settings or get_settings()
        self.feature_engine = VectorizedFeatureEngine()
        self.backtester = WalkForwardBacktester(settings=self.settings)
        self.portfolio_manager = TripleBarrierPortfolioManager(settings=self.settings)

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
                top_n=self.settings.top_n_candidates_per_index,
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
