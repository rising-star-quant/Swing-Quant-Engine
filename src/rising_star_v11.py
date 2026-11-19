from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Literal, Optional, Sequence

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# 1. DATA CONNECTOR NORMALIZED PAYLOAD (MASTER PRD v1.1 SECTION 2.1)
# =============================================================================


class MarketDataPayload(BaseModel):
    """
    Normalized equity ingestion payload standardizing fundamental S&P 500
    eligibility attributes alongside OHLCV market statistics.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str = Field(..., min_length=1, max_length=12)
    as_of_date: date
    us_incorporated: bool = Field(default=True)
    market_cap_usd: float = Field(..., ge=0.0)
    avg_daily_dollar_volume_usd: float = Field(..., ge=0.0)
    public_float_pct: float = Field(..., ge=0.0, le=100.0)
    gaap_profitable_ttm: bool = Field(default=False)
    gaap_profitable_latest_quarter: bool = Field(default=False)
    sector_sentiment_score: float = Field(default=50.0, ge=0.0, le=100.0)
    short_interest_pct: float = Field(default=3.0, ge=0.0, le=100.0)


# =============================================================================
# 2. RULE ENGINE — S&P 500 ELIGIBILITY GATE (MASTER PRD v1.1 SECTION 2.2)
# =============================================================================


@dataclass(frozen=True)
class RuleEvaluationResult:
    """Stateless outcome of S&P 500 Rising Star eligibility gate evaluation."""

    ticker: str
    is_eligible: bool
    failed_gates: List[str] = field(default_factory=list)


class RuleEngine:
    """
    Stateless fundamental eligibility engine enforcing S&P 500 transition criteria:
    - US incorporation
    - Market capitalization >= $18.0B
    - Minimum institutional liquidity (ADV dollar volume >= $25.0M)
    - Public float >= 10.0%
    - Positive GAAP profitability (TTM and most recent quarter)
    """

    MIN_MARKET_CAP_USD: float = 18_000_000_000.0
    MIN_DAILY_DOLLAR_VOLUME_USD: float = 25_000_000.0
    MIN_PUBLIC_FLOAT_PCT: float = 10.0

    def evaluate(self, payload: MarketDataPayload) -> RuleEvaluationResult:
        failed: List[str] = []
        if not payload.us_incorporated:
            failed.append("NON_US_INCORPORATION")
        if payload.market_cap_usd < self.MIN_MARKET_CAP_USD:
            failed.append("MARKET_CAP_BELOW_18B")
        if payload.avg_daily_dollar_volume_usd < self.MIN_DAILY_DOLLAR_VOLUME_USD:
            failed.append("LIQUIDITY_BELOW_THRESHOLD")
        if payload.public_float_pct < self.MIN_PUBLIC_FLOAT_PCT:
            failed.append("PUBLIC_FLOAT_BELOW_10PCT")
        if not (payload.gaap_profitable_ttm and payload.gaap_profitable_latest_quarter):
            failed.append("GAAP_UNPROFITABLE")

        return RuleEvaluationResult(
            ticker=payload.ticker.strip().upper(),
            is_eligible=len(failed) == 0,
            failed_gates=failed,
        )


# =============================================================================
# 3. INDICATOR ENGINE v1.1 (MASTER PRD v1.1 SECTION 3.1)
# =============================================================================


@dataclass(frozen=True)
class IndicatorSnapshot:
    """Computed v1.1 multi-indicator trend, momentum, volume, and ATR telemetry."""

    close_price: float
    ema_50: float
    sma_200: float
    rsi_14: float
    macd_line: float
    macd_signal: float
    macd_histogram: float
    macd_histogram_expanding: bool
    atr_14: float
    volume_ratio_20d: float
    trend_aligned: bool
    overbought_rejected: bool
    momentum_confirmed: bool
    breakout_triggered: bool


class IndicatorEngine:
    """
    Atomic quantitative module (Master PRD v1.1) calculating:
    - EMA(50) & SMA(200) institutional uptrend alignment (Price > EMA50 > SMA200)
    - RSI(14) overbought guard (reject BUY ALERTS if RSI(14) > 70)
    - MACD(12, 26, 9) confirmation (MACD Line > Signal Line & expanding upward histogram)
    - 14-period Average True Range (ATR(14))
    - 20-day Volume Accumulation ratio and 20-day breakout detection
    """

    def __init__(
        self,
        ema_period: int = 50,
        sma_period: int = 200,
        rsi_period: int = 14,
        atr_period: int = 14,
        breakout_window: int = 20,
    ) -> None:
        self.ema_period = ema_period
        self.sma_period = sma_period
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.breakout_window = breakout_window

    @staticmethod
    def _compute_rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gains = delta.clip(lower=0.0)
        losses = (-delta).clip(lower=0.0)
        avg_gain = gains.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        avg_loss = losses.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi.fillna(100.0).clip(0.0, 100.0)

    @staticmethod
    def _compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        prev_close = df["Close"].astype(float).shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    def compute(self, ohlcv: pd.DataFrame) -> IndicatorSnapshot:
        if len(ohlcv) < max(self.sma_period, 35):
            raise ValueError(
                f"IndicatorEngine requires at least {max(self.sma_period, 35)} bars; received {len(ohlcv)}."
            )

        close = ohlcv["Close"].astype(float)
        high = ohlcv["High"].astype(float)
        volume = ohlcv["Volume"].astype(float)

        ema_50_series = close.ewm(span=self.ema_period, adjust=False).mean()
        sma_200_series = close.rolling(window=self.sma_period, min_periods=self.sma_period).mean()
        rsi_14_series = self._compute_rsi(close, self.rsi_period)

        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        macd_line_series = ema_12 - ema_26
        macd_signal_series = macd_line_series.ewm(span=9, adjust=False).mean()
        macd_hist_series = macd_line_series - macd_signal_series

        atr_14_series = self._compute_atr(ohlcv, self.atr_period)
        avg_vol_20 = volume.rolling(window=20, min_periods=20).mean()

        latest_close = float(close.iloc[-1])
        latest_ema_50 = float(ema_50_series.iloc[-1])
        latest_sma_200 = float(sma_200_series.iloc[-1])
        latest_rsi = float(rsi_14_series.iloc[-1])
        latest_macd = float(macd_line_series.iloc[-1])
        latest_signal = float(macd_signal_series.iloc[-1])
        latest_hist = float(macd_hist_series.iloc[-1])
        prev_hist = float(macd_hist_series.iloc[-2])
        latest_atr = float(atr_14_series.iloc[-1])

        vol_denom = float(avg_vol_20.iloc[-1]) if float(avg_vol_20.iloc[-1]) > 0.0 else 1.0
        vol_ratio = float(volume.iloc[-1]) / vol_denom

        prior_breakout_high = float(
            high.iloc[-(self.breakout_window + 1) : -1].max()
        )
        trend_aligned = (latest_close > latest_ema_50) and (latest_ema_50 > latest_sma_200)
        overbought_rejected = latest_rsi > 70.0
        hist_expanding = (latest_hist > 0.0) and (latest_hist > prev_hist)
        momentum_confirmed = (
            (not overbought_rejected)
            and (latest_macd > latest_signal)
            and hist_expanding
        )
        breakout_triggered = (
            trend_aligned
            and momentum_confirmed
            and (latest_close >= prior_breakout_high)
            and (vol_ratio >= 1.20)
        )

        return IndicatorSnapshot(
            close_price=round(latest_close, 4),
            ema_50=round(latest_ema_50, 4),
            sma_200=round(latest_sma_200, 4),
            rsi_14=round(latest_rsi, 2),
            macd_line=round(latest_macd, 4),
            macd_signal=round(latest_signal, 4),
            macd_histogram=round(latest_hist, 4),
            macd_histogram_expanding=hist_expanding,
            atr_14=round(max(latest_atr, 1e-4), 4),
            volume_ratio_20d=round(vol_ratio, 3),
            trend_aligned=trend_aligned,
            overbought_rejected=overbought_rejected,
            momentum_confirmed=momentum_confirmed,
            breakout_triggered=breakout_triggered,
        )


# =============================================================================
# 4. SCORING ENGINE v1.1 (MASTER PRD v1.1 SECTION 3.3)
# =============================================================================


@dataclass(frozen=True)
class CompositeScoreResult:
    """Normalized 0-100 Rising Star composite score and BUY ALERT decision."""

    ticker: str
    is_eligible: bool
    trend_points: float
    momentum_volume_points: float
    sector_sentiment_points: float
    short_interest_points: float
    composite_score: float
    breakout_triggered: bool
    buy_alert_triggered: bool
    rejection_reasons: List[str] = field(default_factory=list)


class ScoringEngine:
    """
    Synthesizes RuleEngine and IndicatorEngine into a normalized 0-100 Rising Star Score:
    - Fundamental Gate: if is_eligible == False -> composite score forced to 0.0
    - Technical Trend Alignment (EMA/SMA & Breakout): 35 points
    - Momentum & Volume Structure (MACD, RSI, Accumulation Surge): 35 points
    - Sector Sentiment & Dynamic Weighting: 20 points
    - Short Interest Filter: 10 points
    - BUY ALERT Trigger: Composite Score >= 75 AND breakout_triggered == True
    """

    BUY_ALERT_MIN_SCORE: float = 75.0

    def score(
        self,
        payload: MarketDataPayload,
        rule_result: RuleEvaluationResult,
        indicators: IndicatorSnapshot,
    ) -> CompositeScoreResult:
        if not rule_result.is_eligible:
            return CompositeScoreResult(
                ticker=rule_result.ticker,
                is_eligible=False,
                trend_points=0.0,
                momentum_volume_points=0.0,
                sector_sentiment_points=0.0,
                short_interest_points=0.0,
                composite_score=0.0,
                breakout_triggered=False,
                buy_alert_triggered=False,
                rejection_reasons=list(rule_result.failed_gates),
            )

        rejections: List[str] = []
        if indicators.overbought_rejected:
            rejections.append("RSI_OVERBOUGHT_GT_70")
        if not indicators.trend_aligned:
            rejections.append("TREND_MISALIGNED_EMA50_SMA200")

        # 1. Technical Trend Alignment (0-35 pts)
        trend_pts = 0.0
        if indicators.close_price > indicators.ema_50:
            trend_pts += 12.0
        if indicators.ema_50 > indicators.sma_200:
            trend_pts += 13.0
        if indicators.breakout_triggered:
            trend_pts += 10.0

        # 2. Momentum & Volume Structure (0-35 pts)
        mom_vol_pts = 0.0
        if indicators.macd_line > indicators.macd_signal:
            mom_vol_pts += 10.0
        if indicators.macd_histogram_expanding:
            mom_vol_pts += 8.0
        if 45.0 <= indicators.rsi_14 <= 70.0:
            mom_vol_pts += 9.0
        elif indicators.rsi_14 < 45.0:
            mom_vol_pts += 4.0
        vol_bonus = min(8.0, max(0.0, (indicators.volume_ratio_20d - 1.0) * 10.0))
        mom_vol_pts += vol_bonus

        # 3. Sector Sentiment & Dynamic Weighting (0-20 pts)
        sector_pts = round((payload.sector_sentiment_score / 100.0) * 20.0, 2)

        # 4. Short Interest Filter (0-10 pts: lower crowded short interest scores higher)
        if payload.short_interest_pct <= 5.0:
            short_pts = 10.0
        elif payload.short_interest_pct <= 12.0:
            short_pts = round(10.0 - ((payload.short_interest_pct - 5.0) / 7.0) * 6.0, 2)
        else:
            short_pts = max(0.0, round(4.0 - (payload.short_interest_pct - 12.0) * 0.4, 2))

        composite = round(
            min(100.0, trend_pts + mom_vol_pts + sector_pts + short_pts),
            2,
        )
        buy_alert = (
            (composite >= self.BUY_ALERT_MIN_SCORE)
            and indicators.breakout_triggered
            and (not indicators.overbought_rejected)
        )

        return CompositeScoreResult(
            ticker=rule_result.ticker,
            is_eligible=True,
            trend_points=round(trend_pts, 2),
            momentum_volume_points=round(mom_vol_pts, 2),
            sector_sentiment_points=sector_pts,
            short_interest_points=short_pts,
            composite_score=composite,
            breakout_triggered=indicators.breakout_triggered,
            buy_alert_triggered=buy_alert,
            rejection_reasons=rejections,
        )


# =============================================================================
# 5. RISK GUARD v1.1 (MASTER PRD v1.1 SECTION 3.2)
# =============================================================================


RiskExitTrigger = Literal[
    "HOLD",
    "ATR_STOP_LOSS",
    "ATR_TAKE_PROFIT",
    "TRAILING_STOP_10PCT",
    "MA50_VOLUME_BREAKDOWN",
    "TIMEOUT_60D",
]


@dataclass(frozen=True)
class DynamicRiskCage:
    """Dynamic ATR-based initial risk levels enforcing a strict 1:2 Risk/Reward ratio."""

    entry_price: float
    atr_14: float
    stop_loss_price: float
    take_profit_price: float
    trailing_stop_fallback_price: float
    risk_reward_ratio: float


class RiskGuard:
    """
    Autonomous v1.1 exit & volatility risk guardrail manager:
    - Dynamic Stop Loss: Current Price - (1.5 * ATR_14)
    - Dynamic Take Profit: Current Price + (3.0 * ATR_14)  [1:2 R:R]
    - Fallback Trailing Stop: 10% below Peak High
    - Structural Breakdown Exit: Close < EMA(50) accompanied by >20% volume surge
    - Holding Timeout: 60 trading days
    """

    STOP_ATR_MULTIPLIER: float = 1.5
    TAKE_PROFIT_ATR_MULTIPLIER: float = 3.0
    TRAILING_FALLBACK_PCT: float = 0.10
    MA50_BREAKDOWN_VOLUME_RATIO: float = 1.20
    MAX_HOLDING_DAYS: int = 60

    def build_risk_cage(self, current_price: float, atr_14: float) -> DynamicRiskCage:
        if current_price <= 0.0 or atr_14 <= 0.0:
            raise ValueError("current_price and atr_14 must be strictly positive.")

        stop_loss = max(0.01, current_price - (self.STOP_ATR_MULTIPLIER * atr_14))
        take_profit = current_price + (self.TAKE_PROFIT_ATR_MULTIPLIER * atr_14)
        trailing_fallback = current_price * (1.0 - self.TRAILING_FALLBACK_PCT)
        risk_unit = max(1e-6, current_price - stop_loss)
        rr_ratio = round((take_profit - current_price) / risk_unit, 2)

        return DynamicRiskCage(
            entry_price=round(current_price, 4),
            atr_14=round(atr_14, 4),
            stop_loss_price=round(stop_loss, 4),
            take_profit_price=round(take_profit, 4),
            trailing_stop_fallback_price=round(trailing_fallback, 4),
            risk_reward_ratio=rr_ratio,
        )

    def evaluate_exit(
        self,
        current_price: float,
        highest_high: float,
        stop_loss_price: float,
        take_profit_price: float,
        ema_50: float,
        volume_ratio_20d: float,
        days_held: int,
    ) -> RiskExitTrigger:
        if current_price <= stop_loss_price:
            return "ATR_STOP_LOSS"
        trailing_floor = highest_high * (1.0 - self.TRAILING_FALLBACK_PCT)
        if current_price <= trailing_floor:
            return "TRAILING_STOP_10PCT"
        if current_price >= take_profit_price:
            return "ATR_TAKE_PROFIT"
        if current_price < ema_50 and volume_ratio_20d > self.MA50_BREAKDOWN_VOLUME_RATIO:
            return "MA50_VOLUME_BREAKDOWN"
        if days_held >= self.MAX_HOLDING_DAYS:
            return "TIMEOUT_60D"
        return "HOLD"
