import React, { useEffect, useState } from 'react';
import { X, Download, Lock, History, CheckCircle2 } from 'lucide-react';
import { AuditLogResponse, ClosedTradeRecord, ExitReasonCode } from '../../types/sirix';
import { sirixClient } from '../../api/client';
import { usePreferences } from '../../context/PreferencesContext';
import { useAuth } from '../../context/AuthContext';
import { TermTooltip } from '../common/TermTooltip';

interface AuditLogDrawerProps {
  open: boolean;
  onClose: () => void;
}

function getExitReasonBadgeStyle(reason: ExitReasonCode): {
  bg: string;
  color: string;
} {
  switch (reason) {
    case 'TAKE_PROFIT_HIT':
      return {
        bg: 'var(--semantic-emerald-subtle)',
        color: 'var(--semantic-emerald)',
      };
    case 'CHANDELIER_STOP_HIT':
      return {
        bg: 'var(--semantic-amber-subtle)',
        color: 'var(--semantic-amber)',
      };
    case 'TIME_BARRIER_EXPIRED':
      return {
        bg: 'var(--accent-brand-subtle)',
        color: 'var(--semantic-cyan)',
      };
    case 'EARNINGS_BLACKOUT_EXIT':
      return {
        bg: 'var(--semantic-violet-subtle)',
        color: 'var(--semantic-violet)',
      };
    case 'KILL_SWITCH_LIQUIDATION':
      return {
        bg: 'var(--semantic-crimson-subtle)',
        color: 'var(--semantic-crimson)',
      };
    case 'EPOCH_RESET_LIQUIDATION':
      return {
        bg: 'var(--accent-brand-subtle)',
        color: 'var(--accent-brand)',
      };
  }
}

export const AuditLogDrawer: React.FC<AuditLogDrawerProps> = ({ open, onClose }) => {
  const { t, language } = usePreferences();
  const { accountTier, switchTier } = useAuth();
  const [audit, setAudit] = useState<AuditLogResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    sirixClient
      .getAuditLog()
      .then((res) => setAudit(res))
      .finally(() => setLoading(false));
  }, [open, accountTier]);

  if (!open) return null;

  const handleExportCsv = () => {
    if (!audit || !audit.csv_export_allowed) return;
    const headers = [
      'Trade ID',
      'Ticker',
      'Company',
      'Universe',
      'Entry Date',
      'Exit Date',
      'Days Held',
      'Shares',
      'Entry Price',
      'Exit Price',
      'Realized PnL USD',
      'Realized PnL Pct',
      'R-Multiple',
      'Exit Reason',
    ];
    const rows = audit.trades.map((tr) => [
      tr.trade_id,
      tr.ticker,
      `"${tr.company_name}"`,
      tr.universe,
      tr.entry_date,
      tr.exit_date,
      tr.days_held,
      tr.shares,
      tr.entry_price.toFixed(2),
      tr.exit_price.toFixed(2),
      tr.realized_pnl.toFixed(2),
      tr.realized_pnl_pct.toFixed(2),
      tr.r_multiple.toFixed(2),
      tr.exit_reason,
    ]);
    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `sirix_closed_trades_audit_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t.audit.title}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl h-full sirix-canvas border-l border-[var(--border-strong)] flex flex-col justify-between overflow-hidden shadow-2xl"
      >
        {/* Top Drawer Header */}
        <div className="p-5 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <History className="w-5 h-5 text-[var(--accent-brand)]" />
            <div>
              <h2 className="text-base sm:text-lg font-bold text-[var(--text-primary)]">
                <TermTooltip term="Audit Log" language={language} labelOverride={t.audit.title} />
              </h2>
              <p className="text-xs text-[var(--text-secondary)]">{t.audit.subtitle}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {audit?.csv_export_allowed ? (
              <button
                type="button"
                onClick={handleExportCsv}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent-brand)] text-slate-950 font-semibold text-xs cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>{t.audit.exportCsvBtn}</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => switchTier('EXPERT')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-canvas)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-xs cursor-pointer"
              >
                <Lock className="w-3 h-3 text-[var(--accent-brand)]" />
                <span>{t.audit.exportExpertOnly}</span>
              </button>
            )}

            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-lg border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {loading || !audit ? (
            <div className="space-y-3 animate-pulse">
              <div className="h-20 rounded-xl sirix-surface border" />
              <div className="h-28 rounded-xl sirix-surface border" />
              <div className="h-28 rounded-xl sirix-surface border" />
            </div>
          ) : (
            <>
              {/* Summary Performance Strip */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                <div className="p-3 rounded-xl border sirix-surface">
                  <div className="text-[11px] text-[var(--text-muted)]">{t.audit.winRate}</div>
                  <div
                    dir="ltr"
                    className="text-lg font-bold font-mono-tabular text-[var(--semantic-emerald)] mt-0.5"
                  >
                    {audit.win_rate_pct.toFixed(1)}%
                  </div>
                </div>

                <div className="p-3 rounded-xl border sirix-surface">
                  <div className="text-[11px] text-[var(--text-muted)]">{t.audit.avgRMultiple}</div>
                  <div
                    dir="ltr"
                    className="text-lg font-bold font-mono-tabular text-[var(--accent-brand)] mt-0.5"
                  >
                    +{audit.avg_r_multiple.toFixed(2)}R
                  </div>
                </div>

                <div className="p-3 rounded-xl border sirix-surface">
                  <div className="text-[11px] text-[var(--text-muted)]">
                    {t.audit.cumulativeRealized}
                  </div>
                  <div
                    dir="ltr"
                    className="text-lg font-bold font-mono-tabular text-[var(--semantic-emerald)] mt-0.5"
                  >
                    +${audit.cumulative_realized_pnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </div>
                </div>

                <div className="p-3 rounded-xl border sirix-surface">
                  <div className="text-[11px] text-[var(--text-muted)]">{t.audit.totalClosed}</div>
                  <div dir="ltr" className="text-lg font-bold font-mono-tabular mt-0.5">
                    {audit.total_closed_trades}
                  </div>
                </div>
              </div>

              {/* Closed Trade Cards */}
              <div className="space-y-2.5">
                {audit.trades.map((trade: ClosedTradeRecord) => {
                  const isWin = trade.realized_pnl >= 0;
                  const badgeStyle = getExitReasonBadgeStyle(trade.exit_reason);

                  return (
                    <div
                      key={trade.trade_id}
                      className="p-4 rounded-xl border sirix-surface space-y-2.5"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-2">
                            <span
                              dir="ltr"
                              className="text-base font-bold font-mono-tabular text-[var(--text-primary)]"
                            >
                              {trade.ticker}
                            </span>
                            <span
                              dir="ltr"
                              className="text-[10px] font-mono-tabular px-1.5 py-0.5 rounded border border-[var(--border-strong)] text-[var(--text-secondary)]"
                            >
                              {trade.universe}
                            </span>
                            <span
                              dir="ltr"
                              className="text-[11px] font-mono-tabular px-2 py-0.5 rounded font-semibold"
                              style={{
                                backgroundColor: badgeStyle.bg,
                                color: badgeStyle.color,
                              }}
                            >
                              {trade.exit_reason_label}
                            </span>
                          </div>
                          <div className="text-xs text-[var(--text-secondary)] mt-0.5">
                            {trade.company_name} •{' '}
                            <span dir="ltr" className="font-mono-tabular text-[var(--text-muted)]">
                              {trade.trade_id}
                            </span>
                          </div>
                        </div>

                        <div className="text-right">
                          <div
                            dir="ltr"
                            className="text-sm font-bold font-mono-tabular"
                            style={{
                              color: isWin ? 'var(--semantic-emerald)' : 'var(--semantic-crimson)',
                            }}
                          >
                            {isWin ? '+' : ''}${trade.realized_pnl.toFixed(2)} (
                            {isWin ? '+' : ''}
                            {trade.realized_pnl_pct.toFixed(2)}%)
                          </div>
                          <div
                            dir="ltr"
                            className="text-xs font-mono-tabular font-semibold"
                            style={{
                              color: isWin ? 'var(--semantic-emerald)' : 'var(--semantic-crimson)',
                            }}
                          >
                            {trade.r_multiple >= 0 ? '+' : ''}
                            {trade.r_multiple.toFixed(2)}R
                          </div>
                        </div>
                      </div>

                      <div className="pt-2 border-t border-[var(--border-subtle)] flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--text-secondary)]">
                        <span dir="ltr" className="font-mono-tabular">
                          {trade.entry_date} → {trade.exit_date} ({trade.days_held}d)
                        </span>
                        <span dir="ltr" className="font-mono-tabular">
                          {trade.shares} {t.audit.shares} • ${trade.entry_price.toFixed(2)} →{' '}
                          <strong className="text-[var(--text-primary)]">
                            ${trade.exit_price.toFixed(2)}
                          </strong>
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* FREE Tier Truncation Banner */}
              {audit.is_truncated_for_tier && (
                <div className="p-3.5 rounded-xl border border-[var(--accent-brand)] bg-[var(--accent-brand-subtle)] flex items-center justify-between gap-3 text-xs">
                  <span className="text-[var(--text-secondary)]">
                    {t.audit.freeTruncationNote}
                  </span>
                  <button
                    type="button"
                    onClick={() => switchTier('PRO')}
                    className="shrink-0 px-3 py-1.5 rounded-lg bg-[var(--accent-brand)] text-slate-950 font-semibold cursor-pointer"
                  >
                    Unlock Full History
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] flex items-center justify-between text-xs text-[var(--text-muted)]">
          <span className="inline-flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-[var(--semantic-emerald)]" />
            <span>Verified Autonomous EOD Execution Ledger</span>
          </span>
          <span dir="ltr" className="font-mono-tabular">
            TIER: {accountTier}
          </span>
        </div>
      </div>
    </div>
  );
};
