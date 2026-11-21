import React from 'react';
import {
  X,
  Lock,
  ShieldCheck,
  Calendar,
  Clock,
  Activity,
  Compass,
  AlertTriangle,
} from 'lucide-react';
import { DailyCandleBar, PositionDeepDiveResponse } from '../../types/sirix';
import { usePreferences } from '../../context/PreferencesContext';
import { useAuth } from '../../context/AuthContext';
import { TermTooltip } from '../common/TermTooltip';

interface PositionInspectorProps {
  deepDive: PositionDeepDiveResponse | null;
  loading: boolean;
  onClose: () => void;
}

/**
 * 7-Day OHLC Candlestick SVG Chart with Autonomous Triple-Barrier Overlays
 * Plots daily candles alongside Take-Profit Ceiling, Entry Anchor, and Chandelier Stop Floor.
 */
const SevenDayCandlestickChart: React.FC<{
  candles: DailyCandleBar[];
  takeProfit: number | null;
  entryPrice: number;
  chandelierStop: number | null;
}> = ({ candles, takeProfit, entryPrice, chandelierStop }) => {
  if (!candles || candles.length === 0) return null;

  const width = 520;
  const height = 210;
  const padLeft = 14;
  const padRight = 68;
  const padTop = 18;
  const padBottom = 26;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;

  const prices: number[] = [entryPrice];
  candles.forEach((c) => {
    prices.push(c.high, c.low);
  });
  if (takeProfit !== null) prices.push(takeProfit);
  if (chandelierStop !== null) prices.push(chandelierStop);

  const minPrice = Math.min(...prices) * 0.992;
  const maxPrice = Math.max(...prices) * 1.008;
  const priceSpan = Math.max(0.01, maxPrice - minPrice);

  const yForPrice = (p: number) =>
    padTop + plotHeight - ((p - minPrice) / priceSpan) * plotHeight;

  const stepX = plotWidth / candles.length;
  const candleWidth = Math.min(24, stepX * 0.52);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full h-48 sm:h-52 overflow-visible select-none"
      role="img"
      aria-label="7-Day OHLC Candlestick Chart with Triple-Barrier Overlays"
    >
      {/* Background Subtle Grid Lines */}
      {[0.2, 0.5, 0.8].map((ratio, idx) => {
        const y = padTop + plotHeight * ratio;
        const labelPrice = maxPrice - priceSpan * ratio;
        return (
          <g key={idx}>
            <line
              x1={padLeft}
              y1={y}
              x2={width - padRight}
              y2={y}
              stroke="var(--border-subtle)"
              strokeDasharray="2 4"
              strokeWidth="1"
            />
            <text
              x={width - padRight + 6}
              y={y + 3}
              fill="var(--text-muted)"
              fontSize="9.5"
              fontFamily="JetBrains Mono, monospace"
            >
              ${labelPrice.toFixed(2)}
            </text>
          </g>
        );
      })}

      {/* Take-Profit Ceiling Line (Emerald) */}
      {takeProfit !== null && (
        <g>
          <line
            x1={padLeft}
            y1={yForPrice(takeProfit)}
            x2={width - padRight}
            y2={yForPrice(takeProfit)}
            stroke="var(--semantic-emerald)"
            strokeWidth="1.5"
            strokeDasharray="5 3"
          />
          <rect
            x={width - padRight + 4}
            y={yForPrice(takeProfit) - 8}
            width={60}
            height={16}
            rx={3}
            fill="var(--semantic-emerald-subtle)"
          />
          <text
            x={width - padRight + 8}
            y={yForPrice(takeProfit) + 3}
            fill="var(--semantic-emerald)"
            fontSize="9.5"
            fontWeight="600"
            fontFamily="JetBrains Mono, monospace"
          >
            TP ${takeProfit.toFixed(1)}
          </text>
        </g>
      )}

      {/* Entry Anchor Line (Neutral Slate/Brand) */}
      <g>
        <line
          x1={padLeft}
          y1={yForPrice(entryPrice)}
          x2={width - padRight}
          y2={yForPrice(entryPrice)}
          stroke="var(--text-muted)"
          strokeWidth="1"
          strokeDasharray="3 3"
        />
        <text
          x={padLeft + 4}
          y={yForPrice(entryPrice) - 4}
          fill="var(--text-secondary)"
          fontSize="9"
          fontFamily="JetBrains Mono, monospace"
        >
          Entry ${entryPrice.toFixed(2)}
        </text>
      </g>

      {/* Chandelier Stop Floor Line (Amber/Crimson) */}
      {chandelierStop !== null && (
        <g>
          <line
            x1={padLeft}
            y1={yForPrice(chandelierStop)}
            x2={width - padRight}
            y2={yForPrice(chandelierStop)}
            stroke="var(--semantic-amber)"
            strokeWidth="1.5"
            strokeDasharray="5 3"
          />
          <rect
            x={width - padRight + 4}
            y={yForPrice(chandelierStop) - 8}
            width={60}
            height={16}
            rx={3}
            fill="var(--semantic-amber-subtle)"
          />
          <text
            x={width - padRight + 8}
            y={yForPrice(chandelierStop) + 3}
            fill="var(--semantic-amber)"
            fontSize="9.5"
            fontWeight="600"
            fontFamily="JetBrains Mono, monospace"
          >
            SL ${chandelierStop.toFixed(1)}
          </text>
        </g>
      )}

      {/* 7 Daily OHLC Candlesticks */}
      {candles.map((bar, i) => {
        const cx = padLeft + stepX * i + stepX / 2;
        const isBull = bar.close >= bar.open;
        const color = isBull ? 'var(--semantic-emerald)' : 'var(--semantic-crimson)';
        const highY = yForPrice(bar.high);
        const lowY = yForPrice(bar.low);
        const openY = yForPrice(bar.open);
        const closeY = yForPrice(bar.close);
        const bodyTop = Math.min(openY, closeY);
        const bodyHeight = Math.max(3, Math.abs(closeY - openY));

        return (
          <g key={bar.date}>
            {/* High-Low Wick */}
            <line
              x1={cx}
              y1={highY}
              x2={cx}
              y2={lowY}
              stroke={color}
              strokeWidth="1.5"
            />
            {/* Open-Close Body */}
            <rect
              x={cx - candleWidth / 2}
              y={bodyTop}
              width={candleWidth}
              height={bodyHeight}
              rx={2}
              fill={color}
            />
            {/* Date Label (MM-DD) */}
            <text
              x={cx}
              y={height - 6}
              textAnchor="middle"
              fill="var(--text-muted)"
              fontSize="9"
              fontFamily="JetBrains Mono, monospace"
            >
              {bar.date.slice(5)}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

export const PositionInspector: React.FC<PositionInspectorProps> = ({
  deepDive,
  loading,
  onClose,
}) => {
  const { t, language } = usePreferences();
  const { isSandbox, switchTier } = useAuth();

  if (loading || !deepDive) {
    return (
      <div className="rounded-2xl border sirix-surface p-5 space-y-4 animate-pulse min-h-[540px]">
        <div className="h-8 w-1/2 rounded bg-[var(--bg-canvas)]" />
        <div className="h-48 rounded-xl bg-[var(--bg-canvas)]" />
        <div className="h-36 rounded-xl bg-[var(--bg-canvas)]" />
      </div>
    );
  }

  const { triple_barrier: tb, is_tier_restricted: isRestricted } = deepDive;
  const isPositive = deepDive.unrealized_pnl >= 0;

  // Compute where current_price sits inside [chandelier_stop_price, take_profit_price]
  let barrierPositionPct = 55;
  if (tb.chandelier_stop_price !== null && tb.take_profit_price !== null) {
    const range = Math.max(0.01, tb.take_profit_price - tb.chandelier_stop_price);
    barrierPositionPct = Math.min(
      100,
      Math.max(0, ((tb.current_price - tb.chandelier_stop_price) / range) * 100)
    );
  }

  return (
    <aside
      aria-label={t.inspector.title}
      className="rounded-2xl border sirix-surface p-5 space-y-5 shadow-xl"
    >
      {/* 1. Inspector Header */}
      <div className="flex items-start justify-between gap-3 pb-3 border-b border-[var(--border-subtle)]">
        <div>
          <div className="flex items-center gap-2">
            <h2
              dir="ltr"
              className="text-xl font-bold font-mono-tabular tracking-tight text-[var(--text-primary)]"
            >
              {deepDive.ticker}
            </h2>
            <span
              dir="ltr"
              className="text-xs font-mono-tabular px-2 py-0.5 rounded border border-[var(--border-strong)] text-[var(--accent-brand)]"
            >
              {deepDive.universe}
            </span>
            {deepDive.r_multiple_current !== null && (
              <span
                dir="ltr"
                className="text-xs font-mono-tabular font-semibold px-2 py-0.5 rounded"
                style={{
                  backgroundColor: isPositive
                    ? 'var(--semantic-emerald-subtle)'
                    : 'var(--semantic-crimson-subtle)',
                  color: isPositive ? 'var(--semantic-emerald)' : 'var(--semantic-crimson)',
                }}
              >
                {deepDive.r_multiple_current >= 0 ? '+' : ''}
                {deepDive.r_multiple_current.toFixed(2)}R
              </span>
            )}
          </div>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5">
            {deepDive.company_name} • <span className="text-[var(--text-muted)]">{deepDive.sector}</span>
          </p>
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label={t.inspector.closeInspector}
          className="p-1.5 rounded-lg border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--border-strong)] transition-colors cursor-pointer"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* 2. 7-Day OHLC Candlestick Chart */}
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-3.5">
        <div className="flex items-center justify-between text-xs text-[var(--text-secondary)] mb-2">
          <span>{t.inspector.ohlcChartSubtitle}</span>
          <span dir="ltr" className="font-mono-tabular font-semibold text-[var(--text-primary)]">
            ${tb.current_price.toFixed(2)} ({deepDive.unrealized_pnl_pct >= 0 ? '+' : ''}
            {deepDive.unrealized_pnl_pct.toFixed(2)}%)
          </span>
        </div>
        <SevenDayCandlestickChart
          candles={deepDive.recent_candles}
          takeProfit={tb.take_profit_price}
          entryPrice={tb.entry_price}
          chandelierStop={tb.chandelier_stop_price}
        />
      </div>

      {/* 3. Interactive Triple-Barrier Price Cage Visualization */}
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold text-[var(--text-primary)] flex items-center gap-1.5">
            <Compass className="w-4 h-4 text-[var(--accent-brand)]" />
            <TermTooltip term="Triple-Barrier" language={language} />
          </div>
          {tb.stop_distance_atr !== null && (
            <span
              dir="ltr"
              className="text-xs font-mono-tabular px-2 py-0.5 rounded bg-[var(--bg-surface)] border border-[var(--border-subtle)] text-[var(--text-secondary)]"
            >
              {t.inspector.stopDistanceLabel}: <strong>{tb.stop_distance_atr.toFixed(2)} ATR</strong>
            </span>
          )}
        </div>

        {isRestricted ? (
          /* FREE Tier Restricted Overlay for Exact Barrier Coordinates */
          <div className="rounded-lg border border-[var(--accent-brand)] bg-[var(--accent-brand-subtle)] p-3.5 space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-[var(--accent-brand)]">
              <Lock className="w-3.5 h-3.5" />
              <span>{t.inspector.lockedTelemetryTitle}</span>
            </div>
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
              {t.inspector.lockedTelemetryDesc}
            </p>
            {isSandbox && (
              <button
                type="button"
                onClick={() => switchTier('PRO')}
                className="px-3 py-1.5 rounded-md bg-[var(--accent-brand)] text-slate-950 font-semibold text-xs cursor-pointer"
              >
                Unlock PRO Telemetry
              </button>
            )}
          </div>
        ) : (
          <>
            {/* Visual Horizontal Cage Gauge: Floor (Chandelier Stop) -> Current -> Ceiling (Take-Profit) */}
            <div className="space-y-1.5 pt-1">
              <div className="flex items-center justify-between text-[11px] font-mono-tabular">
                <span className="text-[var(--semantic-amber)]">
                  SL ${tb.chandelier_stop_price?.toFixed(2)} ({tb.chandelier_stop_pct?.toFixed(2)}%)
                </span>
                <span className="text-[var(--text-primary)] font-bold">
                  Now ${tb.current_price.toFixed(2)}
                </span>
                <span className="text-[var(--semantic-emerald)]">
                  TP ${tb.take_profit_price?.toFixed(2)} (+{tb.take_profit_pct?.toFixed(2)}%)
                </span>
              </div>

              <div className="relative h-3 rounded-full bg-[var(--bg-surface)] border border-[var(--border-strong)] overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${barrierPositionPct}%`,
                    background:
                      'linear-gradient(90deg, var(--semantic-amber) 0%, var(--accent-brand) 55%, var(--semantic-emerald) 100%)',
                  }}
                />
              </div>
            </div>

            {/* 3-Row Explicit Barrier Coordinate Readout */}
            <div className="grid grid-cols-3 gap-2 pt-2 text-xs">
              <div className="p-2.5 rounded-lg bg-[var(--bg-surface)] border border-[var(--border-subtle)]">
                <div className="text-[10px] text-[var(--text-muted)]">
                  <TermTooltip term="Take-Profit" language={language} />
                </div>
                <div
                  dir="ltr"
                  className="font-mono-tabular font-bold text-sm text-[var(--semantic-emerald)] mt-0.5"
                >
                  ${tb.take_profit_price?.toFixed(2)}
                </div>
              </div>

              <div className="p-2.5 rounded-lg bg-[var(--bg-surface)] border border-[var(--border-subtle)]">
                <div className="text-[10px] text-[var(--text-muted)]">
                  {t.inspector.entryAnchorLabel}
                </div>
                <div
                  dir="ltr"
                  className="font-mono-tabular font-bold text-sm text-[var(--text-primary)] mt-0.5"
                >
                  ${tb.entry_price.toFixed(2)}
                </div>
              </div>

              <div className="p-2.5 rounded-lg bg-[var(--bg-surface)] border border-[var(--border-subtle)]">
                <div className="text-[10px] text-[var(--text-muted)]">
                  <TermTooltip term="Chandelier Stop" language={language} />
                </div>
                <div
                  dir="ltr"
                  className="font-mono-tabular font-bold text-sm text-[var(--semantic-amber)] mt-0.5"
                >
                  ${tb.chandelier_stop_price?.toFixed(2)}
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* 4. Quantitative Telemetry Grid: Conviction, ATR, 14-Day Time Barrier & Next Earnings */}
      <div className="grid grid-cols-2 gap-3 text-xs">
        {/* Conviction & Momentum */}
        <div className="p-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)]">
          <div className="text-[var(--text-muted)] flex items-center gap-1">
            <Activity className="w-3.5 h-3.5 text-[var(--accent-brand)]" />
            <TermTooltip term="Conviction" language={language} />
          </div>
          <div dir="ltr" className="mt-1 font-mono-tabular text-base font-bold">
            {deepDive.conviction_score !== null ? (
              <span className="text-[var(--accent-brand)]">
                {deepDive.conviction_score.toFixed(1)} / 100
              </span>
            ) : (
              <span className="text-xs text-[var(--text-muted)] inline-flex items-center gap-1">
                <Lock className="w-3 h-3" /> PRO Tier
              </span>
            )}
          </div>
        </div>

        {/* 14-Day Time Barrier Countdown */}
        <div className="p-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)]">
          <div className="text-[var(--text-muted)] flex items-center gap-1">
            <Clock className="w-3.5 h-3.5 text-[var(--semantic-amber)]" />
            <TermTooltip term="Time Barrier" language={language} />
          </div>
          <div dir="ltr" className="mt-1 font-mono-tabular text-sm font-bold">
            Day {deepDive.days_held}/{deepDive.max_hold_days}{' '}
            <span className="text-xs font-normal text-[var(--text-secondary)]">
              ({deepDive.days_remaining}d left)
            </span>
          </div>
        </div>

        {/* ATR Volatility Cushion */}
        <div className="p-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)]">
          <div className="text-[var(--text-muted)] flex items-center gap-1">
            <TermTooltip term="ATR" language={language} />
            <span>(14D)</span>
          </div>
          <div dir="ltr" className="mt-1 font-mono-tabular text-sm font-bold">
            {tb.atr_14 !== null ? (
              <span>
                ${tb.atr_14.toFixed(2)} ({tb.stop_distance_atr?.toFixed(2)}x Cushion)
              </span>
            ) : (
              <span className="text-xs text-[var(--text-muted)] inline-flex items-center gap-1">
                <Lock className="w-3 h-3" /> PRO Tier
              </span>
            )}
          </div>
        </div>

        {/* Next Earnings Blackout Shield */}
        <div className="p-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)]">
          <div className="text-[var(--text-muted)] flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5 text-[var(--semantic-violet)]" />
            <TermTooltip term="Earnings Blackout" language={language} />
          </div>
          <div dir="ltr" className="mt-1 font-mono-tabular text-xs font-semibold flex items-center gap-1.5">
            {deepDive.earnings_blackout_SAFE ? (
              <span className="text-[var(--semantic-emerald)]">
                {deepDive.next_earnings_date} ({deepDive.days_until_earnings}d • SAFE)
              </span>
            ) : (
              <span className="text-[var(--semantic-amber)] inline-flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                {deepDive.days_until_earnings}d • SHIELD ARMED
              </span>
            )}
          </div>
        </div>
      </div>

      {/* 5. Quantitative Strategy Rationale */}
      <div className="p-3.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1.5">
        <div className="text-xs font-semibold text-[var(--text-secondary)]">
          {t.inspector.strategyRationaleLabel}
        </div>
        <p className="text-xs text-[var(--text-primary)] leading-relaxed">
          {deepDive.strategy_rationale}
        </p>
      </div>

      {/* 6. Immutable Zero-Override Notice */}
      <div className="pt-2 border-t border-[var(--border-subtle)] flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
        <ShieldCheck className="w-4 h-4 text-[var(--semantic-emerald)] shrink-0" />
        <span>{t.inspector.readOnlyNotice}</span>
      </div>
    </aside>
  );
};
