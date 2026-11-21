import React from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  History,
  ChevronRight,
  Lock,
  Layers,
  Clock,
  TrendingUp,
  TrendingDown,
  Flame,
  Flag,
} from 'lucide-react';
import {
  EquityHistoryPoint,
  HoldingSummaryCard,
  PortfolioEpochRecord,
  PortfolioOverviewResponse,
  TimeBarrierUrgency,
} from '../../types/sirix';
import { usePreferences } from '../../context/PreferencesContext';
import { useAuth } from '../../context/AuthContext';
import { TermTooltip } from '../common/TermTooltip';
import { ContinuousEquityChart } from './ContinuousEquityChart';

interface PortfolioHomeViewProps {
  overview: PortfolioOverviewResponse | null;
  equityHistory: EquityHistoryPoint[];
  epochs: PortfolioEpochRecord[];
  loading: boolean;
  selectedTicker: string | null;
  onSelectTicker: (ticker: string) => void;
  onOpenAuditLog: () => void;
}

function formatCurrency(val: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
}

function formatSignedCurrency(val: number): string {
  const prefix = val >= 0 ? '+' : '-';
  return `${prefix}${formatCurrency(Math.abs(val))}`;
}

function formatSignedPct(val: number): string {
  const prefix = val >= 0 ? '+' : '';
  return `${prefix}${val.toFixed(2)}%`;
}

function getUrgencyStyles(urgency: TimeBarrierUrgency): {
  barColor: string;
  badgeBg: string;
  badgeText: string;
} {
  switch (urgency) {
    case 'FRESH':
      return {
        barColor: 'var(--semantic-cyan)',
        badgeBg: 'var(--accent-brand-subtle)',
        badgeText: 'var(--semantic-cyan)',
      };
    case 'MATURING':
      return {
        barColor: 'var(--semantic-amber)',
        badgeBg: 'var(--semantic-amber-subtle)',
        badgeText: 'var(--semantic-amber)',
      };
    case 'CRITICAL':
      return {
        barColor: 'var(--semantic-crimson)',
        badgeBg: 'var(--semantic-crimson-subtle)',
        badgeText: 'var(--semantic-crimson)',
      };
  }
}

export const PortfolioHomeView: React.FC<PortfolioHomeViewProps> = ({
  overview,
  equityHistory,
  epochs,
  loading,
  selectedTicker,
  onSelectTicker,
  onOpenAuditLog,
}) => {
  const { t, language } = usePreferences();
  const { isSandbox, switchTier } = useAuth();

  // CLS = 0 Geometry-Matched Skeleton Loader
  if (loading || !overview) {
    return (
      <div className="space-y-4" aria-busy="true">
        <div className="h-[188px] rounded-2xl border sirix-surface p-5 animate-pulse" />
        <div className="h-[52px] rounded-xl border sirix-surface px-4 animate-pulse" />
        <div className="space-y-3">
          {[1, 2, 3].map((idx) => (
            <div key={idx} className="h-[132px] rounded-xl border sirix-surface p-4 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const heatRatio =
    overview.max_portfolio_heat_pct > 0
      ? Math.min(100, (overview.portfolio_heat_pct / overview.max_portfolio_heat_pct) * 100)
      : 0;

  const isDailyPositive = overview.daily_change_usd >= 0;
  const isInceptionPositive = overview.inception_return_usd >= 0;

  return (
    <div className="space-y-4">
      {/* 1. Hero Macro Header (CLS-Locked Minimum Height) */}
      <section className="min-h-[188px] rounded-2xl border sirix-surface p-5 flex flex-col justify-between">
        <div className="flex flex-wrap items-start justify-between gap-4">
          {/* Total Equity & Daily / Inception P&L */}
          <div>
            <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wider text-[var(--text-secondary)] mb-1.5">
              <span>{t.portfolio.totalEquity}</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-[var(--bg-canvas)] border border-[var(--border-subtle)] font-mono-tabular text-[var(--text-muted)]">
                EOD {overview.as_of_timestamp.slice(0, 10)}
              </span>
              <span
                dir="ltr"
                title={overview.state_revision_id || undefined}
                className="inline-flex items-center gap-1 text-[10px] normal-case tracking-normal font-semibold px-2 py-0.5 rounded bg-[var(--accent-brand-subtle)] border border-[var(--accent-brand)]/40 font-mono-tabular text-[var(--accent-brand)]"
              >
                <Flag className="w-3 h-3" />
                Epoch #{overview.epoch_id ?? 1} • {overview.epoch_alias || 'Genesis Epoch'}
              </span>
            </div>
            <div
              dir="ltr"
              className="text-3xl sm:text-4xl font-bold font-mono-tabular tracking-tight text-[var(--text-primary)]"
            >
              {formatCurrency(overview.total_equity)}
            </div>

            <div className="mt-2.5 flex flex-wrap items-center gap-3 text-xs">
              <div className="inline-flex items-center gap-1.5">
                <span className="text-[var(--text-muted)]">{t.portfolio.dailyChange}:</span>
                <span
                  dir="ltr"
                  className="font-mono-tabular font-semibold inline-flex items-center gap-1 px-2 py-0.5 rounded"
                  style={{
                    backgroundColor: isDailyPositive
                      ? 'var(--semantic-emerald-subtle)'
                      : 'var(--semantic-crimson-subtle)',
                    color: isDailyPositive ? 'var(--semantic-emerald)' : 'var(--semantic-crimson)',
                  }}
                >
                  {isDailyPositive ? (
                    <TrendingUp className="w-3.5 h-3.5" />
                  ) : (
                    <TrendingDown className="w-3.5 h-3.5" />
                  )}
                  {formatSignedCurrency(overview.daily_change_usd)} (
                  {formatSignedPct(overview.daily_change_pct)})
                </span>
              </div>

              <div className="inline-flex items-center gap-1.5">
                <span className="text-[var(--text-muted)]">{t.portfolio.inceptionReturn}:</span>
                <span
                  dir="ltr"
                  className="font-mono-tabular font-semibold"
                  style={{
                    color: isInceptionPositive
                      ? 'var(--semantic-emerald)'
                      : 'var(--semantic-crimson)',
                  }}
                >
                  {formatSignedCurrency(overview.inception_return_usd)} (
                  {formatSignedPct(overview.inception_return_pct)})
                </span>
              </div>
            </div>
          </div>

          {/* Cash vs Invested Split */}
          <div className="flex sm:flex-col gap-4 sm:gap-1.5 text-xs sm:text-right border-t sm:border-t-0 pt-3 sm:pt-0 border-[var(--border-subtle)] w-full sm:w-auto justify-between">
            <div>
              <span className="text-[var(--text-muted)] block">{t.portfolio.investedCapital}</span>
              <span dir="ltr" className="font-mono-tabular font-semibold text-sm">
                {formatCurrency(overview.invested_capital)}
              </span>
            </div>
            <div>
              <span className="text-[var(--text-muted)] block">{t.portfolio.cashBalance}</span>
              <span dir="ltr" className="font-mono-tabular font-semibold text-sm text-[var(--accent-brand)]">
                {formatCurrency(overview.cash_balance)}
              </span>
            </div>
          </div>
        </div>

        {/* Portfolio Heat Gauge Bar */}
        <div className="mt-5 pt-3.5 border-t border-[var(--border-subtle)]">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <div className="inline-flex items-center gap-1.5 text-[var(--text-secondary)]">
              <Flame className="w-3.5 h-3.5 text-[var(--semantic-amber)]" />
              <TermTooltip term="Portfolio Heat" language={language} />
            </div>
            <div dir="ltr" className="font-mono-tabular text-xs">
              <span className="font-semibold text-[var(--text-primary)]">
                {overview.portfolio_heat_pct.toFixed(2)}%
              </span>
              <span className="text-[var(--text-muted)]">
                {' '}
                / {overview.max_portfolio_heat_pct.toFixed(2)}% {t.portfolio.openRiskCap}
              </span>
            </div>
          </div>
          <div className="w-full h-2 rounded-full bg-[var(--bg-canvas)] overflow-hidden border border-[var(--border-subtle)]">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${heatRatio}%`,
                backgroundColor:
                  heatRatio > 85
                    ? 'var(--semantic-crimson)'
                    : heatRatio > 65
                    ? 'var(--semantic-amber)'
                    : 'var(--semantic-emerald)',
              }}
            />
          </div>
        </div>
      </section>

      {/* 1B. Continuous Algo Performance Chart (E.1 All-Epochs TWR % vs Single-Epoch $) */}
      <ContinuousEquityChart
        points={equityHistory}
        epochs={epochs}
        activeEpochId={overview.epoch_id ?? 1}
        loading={loading}
      />

      {/* 2. Seam Audit Log Quick-Access Bar (F02 Section 2.2) */}
      <button
        type="button"
        onClick={onOpenAuditLog}
        className="w-full min-h-[52px] rounded-xl border sirix-surface sirix-surface-hover px-4 py-3 flex items-center justify-between transition-colors cursor-pointer"
      >
        <div className="flex items-center gap-2.5 text-xs sm:text-sm">
          <History className="w-4 h-4 text-[var(--accent-brand)] shrink-0" />
          <TermTooltip term="Audit Log" language={language} />
          <span className="text-[var(--text-secondary)] hidden sm:inline">
            — {t.portfolio.auditSeamlessCta}
          </span>
        </div>
        <div className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--accent-brand)]">
          <span>{t.portfolio.viewClosedTrades}</span>
          <ChevronRight className="w-4 h-4" />
        </div>
      </button>

      {/* 3. Defensive Cash Mode Card (When 0 Active Holdings / Regime Filter Active) */}
      {overview.defensive_mode_context && overview.defensive_mode_context.is_active && (
        <section className="rounded-2xl border-2 border-[var(--semantic-amber)] bg-[var(--bg-surface)] p-5 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md text-xs font-mono-tabular font-semibold bg-[var(--semantic-amber-subtle)] text-[var(--semantic-amber)]">
              <ShieldAlert className="w-4 h-4" />
              {t.portfolio.defensiveModeBadge}
            </span>
            <span dir="ltr" className="text-xs font-mono-tabular text-[var(--text-muted)]">
              {overview.defensive_mode_context.reason_code}
            </span>
          </div>

          <h2 className="text-base sm:text-lg font-semibold text-[var(--text-primary)]">
            {overview.defensive_mode_context.title}
          </h2>
          <p className="text-xs sm:text-sm text-[var(--text-secondary)] leading-relaxed">
            {overview.defensive_mode_context.explanation}
          </p>

          <div className="grid grid-cols-2 gap-3 pt-2">
            <div className="p-3 rounded-xl bg-[var(--bg-canvas)] border border-[var(--border-subtle)]">
              <div className="text-[11px] text-[var(--text-muted)]">
                {t.portfolio.candidatesScanned}
              </div>
              <div dir="ltr" className="text-base font-bold font-mono-tabular mt-0.5">
                {overview.defensive_mode_context.candidates_evaluated.toLocaleString()}
              </div>
            </div>
            <div className="p-3 rounded-xl bg-[var(--bg-canvas)] border border-[var(--border-subtle)]">
              <div className="text-[11px] text-[var(--text-muted)]">
                {t.portfolio.capitalPreserved}
              </div>
              <div
                dir="ltr"
                className="text-base font-bold font-mono-tabular mt-0.5 text-[var(--semantic-emerald)]"
              >
                {overview.defensive_mode_context.capital_preserved_pct.toFixed(1)}%
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 4. Active Autonomous Holdings Section Header */}
      {overview.holdings.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-[var(--accent-brand)]" />
              <h2 className="text-sm font-semibold tracking-tight">
                {t.portfolio.activeHoldings}
              </h2>
              <span
                dir="ltr"
                className="text-xs font-mono-tabular px-2 py-0.5 rounded-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] text-[var(--text-secondary)]"
              >
                {overview.visible_positions_count} / {overview.active_positions_count}
              </span>
            </div>
            <div className="text-xs text-[var(--text-muted)]">
              <TermTooltip term="Time Barrier" language={language} />
            </div>
          </div>

          {/* Holdings Cards List */}
          <div className="space-y-3">
            {overview.holdings.map((holding: HoldingSummaryCard) => {
              const isSelected = selectedTicker === holding.ticker;
              const isPositive = holding.unrealized_pnl >= 0;
              const urgencyStyle = getUrgencyStyles(holding.time_barrier_urgency);
              const timeProgressPct = Math.min(
                100,
                Math.round((holding.days_held / holding.max_hold_days) * 100)
              );

              const urgencyLabel =
                holding.time_barrier_urgency === 'FRESH'
                  ? t.portfolio.urgencyFresh
                  : holding.time_barrier_urgency === 'MATURING'
                  ? t.portfolio.urgencyMaturing
                  : t.portfolio.urgencyCritical;

              return (
                <div
                  key={holding.ticker}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelectTicker(holding.ticker)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelectTicker(holding.ticker);
                    }
                  }}
                  className={`min-h-[132px] rounded-xl border transition-all overflow-hidden flex flex-col justify-between cursor-pointer ${
                    isSelected
                      ? 'border-[var(--accent-brand)] bg-[var(--bg-surface-hover)] shadow-lg'
                      : 'sirix-surface sirix-surface-hover'
                  }`}
                >
                  <div className="p-4 space-y-3">
                    {/* Top Row: Ticker, Company, Universe Badge & Unrealized P&L */}
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span
                            dir="ltr"
                            className="text-lg font-bold font-mono-tabular tracking-tight text-[var(--text-primary)]"
                          >
                            {holding.ticker}
                          </span>
                          <span
                            dir="ltr"
                            className="text-[10px] font-mono-tabular font-semibold px-1.5 py-0.5 rounded border border-[var(--border-strong)] text-[var(--text-secondary)]"
                          >
                            {holding.universe}
                          </span>
                          {holding.conviction_score !== null ? (
                            <span
                              dir="ltr"
                              className="text-[11px] font-mono-tabular px-2 py-0.5 rounded bg-[var(--accent-brand-subtle)] text-[var(--accent-brand)]"
                            >
                              Conviction {holding.conviction_score.toFixed(1)}
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[10px] font-mono-tabular px-2 py-0.5 rounded bg-[var(--bg-canvas)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
                              <Lock className="w-2.5 h-2.5" /> PRO
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-[var(--text-secondary)] mt-0.5">
                          {holding.company_name}
                        </div>
                      </div>

                      <div className="text-right">
                        <div
                          dir="ltr"
                          className="text-base font-bold font-mono-tabular"
                          style={{
                            color: isPositive
                              ? 'var(--semantic-emerald)'
                              : 'var(--semantic-crimson)',
                          }}
                        >
                          {formatSignedPct(holding.unrealized_pnl_pct)}
                        </div>
                        <div
                          dir="ltr"
                          className="text-xs font-mono-tabular"
                          style={{
                            color: isPositive
                              ? 'var(--semantic-emerald)'
                              : 'var(--semantic-crimson)',
                          }}
                        >
                          {formatSignedCurrency(holding.unrealized_pnl)}
                        </div>
                      </div>
                    </div>

                    {/* Middle Telemetry Row: Value, Shares, Entry -> Last, Stop ATR, Time Barrier Day */}
                    <div className="pt-2 border-t border-[var(--border-subtle)] flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-3">
                        <span dir="ltr" className="font-mono-tabular text-[var(--text-primary)] font-medium">
                          {formatCurrency(holding.position_value)}
                        </span>
                        <span dir="ltr" className="font-mono-tabular text-[var(--text-muted)]">
                          ({holding.shares} {t.portfolio.shares} • {holding.weight_pct.toFixed(1)}%)
                        </span>
                      </div>

                      <div className="flex items-center gap-3">
                        <span dir="ltr" className="font-mono-tabular text-[var(--text-secondary)]">
                          {t.portfolio.entry} ${holding.entry_price.toFixed(2)} → {t.portfolio.last}{' '}
                          <strong className="text-[var(--text-primary)]">
                            ${holding.current_price.toFixed(2)}
                          </strong>
                        </span>

                        {/* 14-Day Time Barrier Pill */}
                        <span
                          dir="ltr"
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-mono-tabular text-[11px] font-semibold"
                          style={{
                            backgroundColor: urgencyStyle.badgeBg,
                            color: urgencyStyle.badgeText,
                          }}
                        >
                          <Clock className="w-3 h-3" />
                          {t.portfolio.day} {holding.days_held}/{holding.max_hold_days} •{' '}
                          {urgencyLabel}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Bottom Edge-to-Edge 14-Day Timeline Progress Bar (F03 Section 2.3) */}
                  <div className="w-full h-1.5 bg-[var(--bg-canvas)]">
                    <div
                      className="h-full transition-all duration-300"
                      style={{
                        width: `${timeProgressPct}%`,
                        backgroundColor: urgencyStyle.barColor,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 5. FREE Tier Truncation Upgrade Banner */}
      {overview.is_truncated_for_tier && (
        <div className="rounded-xl border border-[var(--accent-brand)] bg-[var(--accent-brand-subtle)] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-xs font-semibold text-[var(--accent-brand)]">
              <Lock className="w-3.5 h-3.5" />
              <span>{t.portfolio.freeTierBannerTitle}</span>
            </div>
            <p className="text-xs text-[var(--text-secondary)]">
              {t.portfolio.freeTierBannerSubtitle}
            </p>
          </div>
          {isSandbox && (
            <button
              type="button"
              onClick={() => switchTier('PRO')}
              className="shrink-0 px-3.5 py-2 rounded-lg bg-[var(--accent-brand)] text-slate-950 font-semibold text-xs hover:opacity-95 transition-opacity cursor-pointer"
            >
              {t.portfolio.upgradeToProCta}
            </button>
          )}
        </div>
      )}

      {/* Zero-Override Footer Guarantee */}
      <div className="pt-2 flex items-center justify-between text-[11px] text-[var(--text-muted)] px-1">
        <span className="inline-flex items-center gap-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-[var(--semantic-emerald)]" />
          <TermTooltip term="Zero-Override" language={language} />
        </span>
        <span dir="ltr" className="font-mono-tabular">
          RUT • MID EOD ENGINE
        </span>
      </div>
    </div>
  );
};
