import React, { useMemo, useState } from 'react';
import { Flag, LineChart } from 'lucide-react';
import {
  EquityHistoryPoint,
  PortfolioEpochRecord,
} from '../../types/sirix';

interface ContinuousEquityChartProps {
  points: EquityHistoryPoint[];
  epochs: PortfolioEpochRecord[];
  activeEpochId: number;
  loading?: boolean;
}

type ChartViewMode = 'ALL_EPOCHS_TWR' | 'SINGLE_EPOCH_USD';

function formatUsd(val: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
}

function formatPct(val: number): string {
  const prefix = val >= 0 ? '+' : '';
  return `${prefix}${val.toFixed(2)}%`;
}

export const ContinuousEquityChart: React.FC<ContinuousEquityChartProps> = ({
  points,
  epochs,
  activeEpochId,
  loading = false,
}) => {
  const [viewMode, setViewMode] = useState<ChartViewMode>('ALL_EPOCHS_TWR');
  const [selectedEpochId, setSelectedEpochId] = useState<number>(activeEpochId);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const epochLookup = useMemo(() => {
    const map = new Map<number, PortfolioEpochRecord>();
    epochs.forEach((ep) => map.set(ep.epoch_id, ep));
    return map;
  }, [epochs]);

  const effectiveEpochId = useMemo(() => {
    if (epochs.some((ep) => ep.epoch_id === selectedEpochId)) {
      return selectedEpochId;
    }
    return activeEpochId;
  }, [epochs, selectedEpochId, activeEpochId]);

  const displayedPoints = useMemo(() => {
    if (viewMode === 'ALL_EPOCHS_TWR') {
      return points;
    }
    const filtered = points.filter((pt) => pt.epoch_id === effectiveEpochId);
    return filtered.length > 0 ? filtered : points;
  }, [points, viewMode, effectiveEpochId]);

  if (loading && points.length === 0) {
    return (
      <section className="rounded-2xl border sirix-surface p-4 space-y-3 animate-pulse">
        <div className="h-5 w-48 rounded bg-[var(--bg-canvas)]" />
        <div className="h-[190px] rounded-xl bg-[var(--bg-canvas)]" />
      </section>
    );
  }

  if (displayedPoints.length === 0) {
    return null;
  }

  const width = 560;
  const height = 210;
  const padLeft = 56;
  const padRight = 18;
  const padTop = 28;
  const padBottom = 28;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const values = displayedPoints.map((pt) =>
    viewMode === 'ALL_EPOCHS_TWR' ? pt.cumulative_algo_return_pct : pt.raw_portfolio_value
  );
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const span = rawMax - rawMin;
  const minVal = span < 1e-4 ? rawMin - (viewMode === 'ALL_EPOCHS_TWR' ? 1.0 : 1000.0) : rawMin - span * 0.14;
  const maxVal = span < 1e-4 ? rawMax + (viewMode === 'ALL_EPOCHS_TWR' ? 1.0 : 1000.0) : rawMax + span * 0.18;

  const getX = (idx: number): number => {
    if (displayedPoints.length <= 1) return padLeft + plotW / 2;
    return padLeft + (idx / (displayedPoints.length - 1)) * plotW;
  };

  const getY = (val: number): number => {
    const ratio = (val - minVal) / (maxVal - minVal || 1);
    return padTop + plotH - ratio * plotH;
  };

  const linePath = displayedPoints
    .map((pt, idx) => {
      const val =
        viewMode === 'ALL_EPOCHS_TWR' ? pt.cumulative_algo_return_pct : pt.raw_portfolio_value;
      return `${idx === 0 ? 'M' : 'L'} ${getX(idx).toFixed(2)} ${getY(val).toFixed(2)}`;
    })
    .join(' ');

  const areaPath = `${linePath} L ${getX(displayedPoints.length - 1).toFixed(2)} ${(
    padTop + plotH
  ).toFixed(2)} L ${getX(0).toFixed(2)} ${(padTop + plotH).toFixed(2)} Z`;

  const lastValue = values[values.length - 1];
  const isPositiveSeries =
    viewMode === 'ALL_EPOCHS_TWR' ? lastValue >= 0 : lastValue >= 100000;
  const strokeColor = isPositiveSeries ? 'var(--semantic-emerald)' : 'var(--semantic-crimson)';

  const hoveredPoint =
    hoverIdx !== null && hoverIdx >= 0 && hoverIdx < displayedPoints.length
      ? displayedPoints[hoverIdx]
      : null;

  const hoveredMarkerEpochRecord = hoveredPoint?.epoch_marker
    ? epochLookup.get(hoveredPoint.epoch_marker.epoch_id)
    : undefined;

  const prevEpochRecord = hoveredPoint?.epoch_marker
    ? epochLookup.get(hoveredPoint.epoch_marker.epoch_id - 1)
    : undefined;

  const closingBeforeReset =
    hoveredMarkerEpochRecord?.closing_equity_before_reset ??
    prevEpochRecord?.closing_equity_before_reset ??
    null;

  const yTicks = [0, 0.5, 1].map((fraction) => {
    const tickVal = minVal + (maxVal - minVal) * fraction;
    return {
      val: tickVal,
      y: getY(tickVal),
      label:
        viewMode === 'ALL_EPOCHS_TWR'
          ? `${tickVal >= 0 ? '+' : ''}${tickVal.toFixed(1)}%`
          : `$${(tickVal / 1000).toFixed(1)}k`,
    };
  });

  return (
    <section className="rounded-2xl border sirix-surface p-4 space-y-3">
      {/* Header & Epoch Mode Toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <LineChart className="w-4 h-4 text-[var(--accent-brand)]" />
          <div>
            <h2 className="text-xs sm:text-sm font-semibold text-[var(--text-primary)]">
              {viewMode === 'ALL_EPOCHS_TWR'
                ? 'Continuous Algo Proof (TWR %)'
                : `Epoch #${effectiveEpochId} Equity Curve ($)`}
            </h2>
            <p className="text-[11px] text-[var(--text-muted)]">
              {viewMode === 'ALL_EPOCHS_TWR'
                ? 'Unbroken Time-Weighted Return across all epochs'
                : epochLookup.get(effectiveEpochId)?.epoch_alias || `Epoch #${effectiveEpochId}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <div
            dir="ltr"
            className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-0.5 text-[11px] font-mono-tabular"
          >
            <button
              type="button"
              onClick={() => {
                setViewMode('ALL_EPOCHS_TWR');
                setHoverIdx(null);
              }}
              className={`px-2 py-1 rounded-md font-semibold transition-colors cursor-pointer ${
                viewMode === 'ALL_EPOCHS_TWR'
                  ? 'bg-[var(--accent-brand)] text-slate-950'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
            >
              All Epochs (%)
            </button>
            <button
              type="button"
              onClick={() => {
                setViewMode('SINGLE_EPOCH_USD');
                setSelectedEpochId(activeEpochId);
                setHoverIdx(null);
              }}
              className={`px-2 py-1 rounded-md font-semibold transition-colors cursor-pointer ${
                viewMode === 'SINGLE_EPOCH_USD'
                  ? 'bg-[var(--accent-brand)] text-slate-950'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
            >
              Epoch ($)
            </button>
          </div>

          {viewMode === 'SINGLE_EPOCH_USD' && epochs.length > 1 && (
            <select
              aria-label="Select Portfolio Epoch"
              value={effectiveEpochId}
              onChange={(e) => {
                setSelectedEpochId(Number(e.target.value));
                setHoverIdx(null);
              }}
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] px-2 py-1 text-[11px] font-mono-tabular text-[var(--text-primary)] cursor-pointer"
            >
              {epochs.map((ep) => (
                <option key={ep.epoch_id} value={ep.epoch_id}>
                  #{ep.epoch_id} • {ep.epoch_alias}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Interactive SVG Equity Curve */}
      <div className="relative w-full">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto overflow-visible select-none"
          role="img"
          aria-label="Continuous Portfolio Performance Chart"
          onMouseLeave={() => setHoverIdx(null)}
        >
          <defs>
            <linearGradient id="sirixTwrFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.24" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Horizontal Gridlines & Y-Axis Labels */}
          {yTicks.map((tick, i) => (
            <g key={i}>
              <line
                x1={padLeft}
                x2={width - padRight}
                y1={tick.y}
                y2={tick.y}
                stroke="var(--border-subtle)"
                strokeDasharray="3 4"
                strokeWidth="1"
              />
              <text
                x={padLeft - 8}
                y={tick.y + 3}
                textAnchor="end"
                fill="var(--text-muted)"
                fontSize="10"
                className="font-mono-tabular"
              >
                {tick.label}
              </text>
            </g>
          ))}

          {/* Area & Continuous Curve */}
          <path d={areaPath} fill="url(#sirixTwrFill)" />
          <path
            d={linePath}
            fill="none"
            stroke={strokeColor}
            strokeWidth="2.25"
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* Vertical Dashed Epoch Reset Markers (All Epochs View) */}
          {viewMode === 'ALL_EPOCHS_TWR' &&
            displayedPoints.map((pt, idx) => {
              if (!pt.epoch_marker) return null;
              const xPos = getX(idx);
              const yPos = getY(pt.cumulative_algo_return_pct);
              return (
                <g key={`marker-${pt.epoch_marker.epoch_id}-${pt.date}`}>
                  <line
                    x1={xPos}
                    x2={xPos}
                    y1={padTop - 8}
                    y2={padTop + plotH}
                    stroke="var(--accent-brand)"
                    strokeWidth="1.4"
                    strokeDasharray="4 3"
                  />
                  <circle
                    cx={xPos}
                    cy={yPos}
                    r="4.5"
                    fill="var(--bg-surface)"
                    stroke="var(--accent-brand)"
                    strokeWidth="2"
                  />
                  <g transform={`translate(${Math.min(width - 132, Math.max(padLeft, xPos - 58))}, 4)`}>
                    <rect
                      width="116"
                      height="18"
                      rx="4"
                      fill="var(--bg-canvas)"
                      stroke="var(--accent-brand)"
                      strokeWidth="1"
                    />
                    <text
                      x="58"
                      y="12.5"
                      textAnchor="middle"
                      fill="var(--accent-brand)"
                      fontSize="9"
                      fontWeight="700"
                      className="font-mono-tabular"
                    >
                      {`E#${pt.epoch_marker.epoch_id} ${pt.epoch_marker.alias.slice(0, 14)}`}
                    </text>
                  </g>
                </g>
              );
            })}

          {/* Hovered Point Crosshair */}
          {hoveredPoint && hoverIdx !== null && (
            <g>
              <line
                x1={getX(hoverIdx)}
                x2={getX(hoverIdx)}
                y1={padTop}
                y2={padTop + plotH}
                stroke="var(--text-muted)"
                strokeDasharray="2 2"
                strokeWidth="1"
              />
              <circle
                cx={getX(hoverIdx)}
                cy={getY(
                  viewMode === 'ALL_EPOCHS_TWR'
                    ? hoveredPoint.cumulative_algo_return_pct
                    : hoveredPoint.raw_portfolio_value
                )}
                r="4.5"
                fill={strokeColor}
                stroke="var(--bg-surface)"
                strokeWidth="2"
              />
            </g>
          )}

          {/* X-Axis Start / End Date Labels */}
          <text
            x={padLeft}
            y={height - 6}
            textAnchor="start"
            fill="var(--text-muted)"
            fontSize="10"
            className="font-mono-tabular"
          >
            {displayedPoints[0].date}
          </text>
          <text
            x={width - padRight}
            y={height - 6}
            textAnchor="end"
            fill="var(--text-muted)"
            fontSize="10"
            className="font-mono-tabular"
          >
            {displayedPoints[displayedPoints.length - 1].date}
          </text>

          {/* Invisible Hover Hit Zones */}
          {displayedPoints.map((pt, idx) => {
            const bandW = plotW / Math.max(1, displayedPoints.length);
            const cx = getX(idx);
            return (
              <rect
                key={`hit-${pt.date}-${idx}`}
                x={Math.max(padLeft, cx - bandW / 2)}
                y={padTop}
                width={Math.max(10, bandW)}
                height={plotH}
                fill="transparent"
                onMouseEnter={() => setHoverIdx(idx)}
                onTouchStart={() => setHoverIdx(idx)}
              />
            );
          })}
        </svg>

        {/* Interactive Telemetry Readout / Epoch Reset Tooltip */}
        {hoveredPoint && (
          <div className="mt-2 rounded-xl border border-[var(--border-strong)] bg-[var(--bg-canvas)] px-3 py-2 text-xs flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span dir="ltr" className="font-mono-tabular font-semibold text-[var(--text-primary)]">
                {hoveredPoint.date}
              </span>
              <span
                dir="ltr"
                className="text-[10px] font-mono-tabular px-1.5 py-0.5 rounded bg-[var(--accent-brand-subtle)] text-[var(--accent-brand)]"
              >
                Epoch #{hoveredPoint.epoch_id}
              </span>
            </div>

            <div dir="ltr" className="flex flex-wrap items-center gap-3 font-mono-tabular">
              <span
                className="font-semibold"
                style={{
                  color:
                    hoveredPoint.cumulative_algo_return_pct >= 0
                      ? 'var(--semantic-emerald)'
                      : 'var(--semantic-crimson)',
                }}
              >
                TWR {formatPct(hoveredPoint.cumulative_algo_return_pct)}
              </span>
              <span className="text-[var(--text-secondary)]">
                NAV {formatUsd(hoveredPoint.raw_portfolio_value)}
              </span>
            </div>

            {hoveredPoint.epoch_marker && (
              <div className="w-full pt-1.5 mt-0.5 border-t border-[var(--border-subtle)] flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--accent-brand)]">
                <span className="inline-flex items-center gap-1 font-semibold">
                  <Flag className="w-3 h-3" />
                  Epoch #{hoveredPoint.epoch_marker.epoch_id}: {hoveredPoint.epoch_marker.alias}
                </span>
                {closingBeforeReset !== null && (
                  <span dir="ltr" className="font-mono-tabular text-[var(--text-secondary)]">
                    Prior Closing Equity: <strong className="text-[var(--text-primary)]">{formatUsd(closingBeforeReset)}</strong>
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
};
