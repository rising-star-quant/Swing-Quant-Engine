import React, { useState, useEffect } from 'react';
import {
  Search,
  CheckCircle2,
  XCircle,
  ArrowUpRight,
  Lock,
  Sparkles,
  Filter,
  AlertTriangle,
} from 'lucide-react';
import { TickerSearchResult } from '../../types/sirix';
import { sirixClient } from '../../api/client';
import { usePreferences } from '../../context/PreferencesContext';
import { useAuth } from '../../context/AuthContext';
import { TermTooltip } from '../common/TermTooltip';

interface UniverseSearchViewProps {
  onInspectHeldTicker: (ticker: string) => void;
}

const QUICK_SAMPLE_TICKERS = [
  { ticker: 'DUOL', tag: 'MID' },
  { ticker: 'MSTR', tag: 'MID' },
  { ticker: 'CAVA', tag: 'MID' },
  { ticker: 'CELH', tag: 'MID' },
  { ticker: 'FN', tag: 'RUT' },
];

export const UniverseSearchView: React.FC<UniverseSearchViewProps> = ({
  onInspectHeldTicker,
}) => {
  const { t, language } = usePreferences();
  const { accountTier, isSandbox, switchTier } = useAuth();
  const [query, setQuery] = useState('DUOL');
  const [result, setResult] = useState<TickerSearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const runSearch = async (tickerToSearch: string) => {
    const cleaned = tickerToSearch.trim().toUpperCase();
    if (!cleaned) return;
    setLoading(true);
    setSearchError(null);
    try {
      const res = await sirixClient.searchUniverseTicker(cleaned);
      setResult(res);
    } catch (err) {
      setResult(null);
      setSearchError(
        err instanceof Error
          ? err.message
          : `Failed to query live screening ledger for ${cleaned}.`
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void runSearch(query);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountTier]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void runSearch(query);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      {/* 1. Search Header & Input Bar */}
      <section className="rounded-2xl border sirix-surface p-5 space-y-4">
        <div>
          <div className="flex items-center gap-2 text-xs text-[var(--accent-brand)] font-semibold uppercase tracking-wider mb-1">
            <Filter className="w-3.5 h-3.5" />
            <span>RUT • MID 4-Stage Screening Transparency</span>
          </div>
          <h1 className="text-lg sm:text-xl font-bold text-[var(--text-primary)]">
            {t.search.title}
          </h1>
          <p className="text-xs sm:text-sm text-[var(--text-secondary)] mt-1">
            {t.search.subtitle}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2.5">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-[var(--text-muted)] absolute left-3.5 top-3" />
            <input
              type="text"
              dir="ltr"
              value={query}
              onChange={(e) => setQuery(e.target.value.toUpperCase())}
              placeholder={t.search.placeholder}
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] text-sm font-mono-tabular text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-brand)]"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2.5 rounded-xl bg-[var(--accent-brand)] text-slate-950 font-semibold text-sm hover:opacity-95 transition-opacity cursor-pointer disabled:opacity-60"
          >
            {t.search.searchButton}
          </button>
        </form>

        {/* Quick-Pick Screened Ticker Chips */}
        <div className="pt-1 flex flex-wrap items-center gap-2">
          <span className="text-xs text-[var(--text-muted)]">{t.search.quickPickTitle}</span>
          {QUICK_SAMPLE_TICKERS.map((item) => (
            <button
              key={item.ticker}
              type="button"
              onClick={() => {
                setQuery(item.ticker);
                void runSearch(item.ticker);
              }}
              className={`px-2.5 py-1 rounded-lg border text-xs font-mono-tabular transition-colors cursor-pointer ${
                result?.query_ticker === item.ticker
                  ? 'border-[var(--accent-brand)] bg-[var(--accent-brand-subtle)] text-[var(--accent-brand)] font-semibold'
                  : 'border-[var(--border-subtle)] bg-[var(--bg-canvas)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]'
              }`}
            >
              <span dir="ltr">{item.ticker}</span>
              <span className="text-[10px] text-[var(--text-muted)] ml-1.5 hidden sm:inline">
                ({item.tag})
              </span>
            </button>
          ))}
        </div>
      </section>

      {/* Live Search Error Banner */}
      {searchError && (
        <div
          role="alert"
          className="rounded-xl border border-[var(--semantic-crimson)] bg-[var(--semantic-crimson-subtle)] p-4 flex items-start gap-2.5 text-xs text-[var(--semantic-crimson)]"
        >
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-semibold">Live Universe Search Failed</div>
            <p className="text-[var(--text-primary)]">{searchError}</p>
          </div>
        </div>
      )}

      {/* 2. Search Verdict Card */}
      {loading && (
        <div className="h-[340px] rounded-2xl border sirix-surface p-6 animate-pulse" />
      )}

      {!loading && result && (
        <section className="rounded-2xl border sirix-surface p-5 sm:p-6 space-y-5">
          {/* Top Verdict Banner */}
          <div className="flex flex-wrap items-start justify-between gap-4 pb-4 border-b border-[var(--border-subtle)]">
            <div>
              <div className="flex items-center gap-2.5">
                <span
                  dir="ltr"
                  className="text-2xl font-bold font-mono-tabular text-[var(--text-primary)]"
                >
                  {result.query_ticker}
                </span>
                <span
                  dir="ltr"
                  className="text-xs font-mono-tabular px-2 py-0.5 rounded border border-[var(--border-strong)] text-[var(--text-secondary)]"
                >
                  <TermTooltip term={result.universe} language={language} />
                </span>
                <span
                  dir="ltr"
                  className="text-xs font-mono-tabular text-[var(--text-muted)]"
                >
                  EOD {result.as_of_date}
                </span>
              </div>
              <div className="text-sm text-[var(--text-secondary)] mt-0.5">
                {result.company_name}
              </div>
            </div>

            {/* HELD vs REJECTED Status Pill */}
            <div className="flex items-center gap-2">
              {result.status === 'HELD' ? (
                <span
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono-tabular font-semibold"
                  style={{
                    backgroundColor: 'var(--semantic-emerald-subtle)',
                    color: 'var(--semantic-emerald)',
                  }}
                >
                  <CheckCircle2 className="w-4 h-4" />
                  {t.search.statusHeld}
                </span>
              ) : (
                <span
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono-tabular font-semibold"
                  style={{
                    backgroundColor: 'var(--semantic-amber-subtle)',
                    color: 'var(--semantic-amber)',
                  }}
                >
                  <XCircle className="w-4 h-4" />
                  {t.search.statusRejected}
                </span>
              )}
            </div>
          </div>

          {/* Headline Verdict & Plain-English Quantitative Explanation */}
          <div className="p-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-base font-bold text-[var(--text-primary)]">
                {result.headline_verdict}
              </h2>
              {result.conviction_score !== null && (
                <span
                  dir="ltr"
                  className="text-xs font-mono-tabular px-2.5 py-1 rounded bg-[var(--accent-brand-subtle)] text-[var(--accent-brand)] font-semibold"
                >
                  Conviction: {result.conviction_score.toFixed(1)} / 100
                </span>
              )}
            </div>
            <p className="text-xs sm:text-sm text-[var(--text-secondary)] leading-relaxed">
              {result.plain_English_explanation}
            </p>

            {/* If HELD: Direct CTA to open in Portfolio Inspector */}
            {result.status === 'HELD' && (
              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => onInspectHeldTicker(result.query_ticker)}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent-brand)] text-slate-950 font-semibold text-xs hover:opacity-95 transition-opacity cursor-pointer"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>{t.search.viewInPortfolioBtn}</span>
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>

          {/* 4-Stage Quantitative Screening Pipeline Breakdown */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
              {t.search.gateBreakdownTitle}
            </h3>

            {result.account_tier === 'FREE' ? (
              <div className="rounded-xl border border-[var(--accent-brand)] bg-[var(--accent-brand-subtle)] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-xs font-semibold text-[var(--accent-brand)]">
                    <Lock className="w-3.5 h-3.5" />
                    <span>{t.search.proGateLockedTitle}</span>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)]">
                    {t.search.proGateLockedDesc}
                  </p>
                </div>
                {isSandbox && (
                  <button
                    type="button"
                    onClick={() => switchTier('PRO')}
                    className="shrink-0 px-3.5 py-2 rounded-lg bg-[var(--accent-brand)] text-slate-950 font-semibold text-xs cursor-pointer"
                  >
                    Unlock PRO Gate Metrics
                  </button>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {result.gate_checks.map((gate) => (
                  <div
                    key={gate.stage}
                    className={`p-3.5 rounded-xl border transition-colors ${
                      gate.passed
                        ? 'border-[var(--border-subtle)] bg-[var(--bg-canvas)]'
                        : 'border-[var(--semantic-crimson)] bg-[var(--semantic-crimson-subtle)]'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <span className="text-xs font-semibold text-[var(--text-primary)]">
                        {gate.stage}
                      </span>
                      <span
                        dir="ltr"
                        className="inline-flex items-center gap-1 text-[11px] font-mono-tabular font-semibold px-2 py-0.5 rounded"
                        style={{
                          backgroundColor: gate.passed
                            ? 'var(--semantic-emerald-subtle)'
                            : 'var(--semantic-crimson-subtle)',
                          color: gate.passed
                            ? 'var(--semantic-emerald)'
                            : 'var(--semantic-crimson)',
                        }}
                      >
                        {gate.passed ? (
                          <CheckCircle2 className="w-3 h-3" />
                        ) : (
                          <XCircle className="w-3 h-3" />
                        )}
                        {gate.passed ? t.search.gatePassed : t.search.gateFailed}
                      </span>
                    </div>

                    <div className="flex items-baseline justify-between text-xs pt-1 border-t border-[var(--border-subtle)]">
                      <span className="text-[var(--text-muted)]">{gate.metric_label}:</span>
                      <span dir="ltr" className="font-mono-tabular font-bold text-[var(--text-primary)]">
                        {gate.metric_value}
                      </span>
                    </div>
                    <div className="flex items-baseline justify-between text-[11px] mt-1">
                      <span className="text-[var(--text-muted)]">
                        {t.search.thresholdRequired}:
                      </span>
                      <span dir="ltr" className="font-mono-tabular text-[var(--text-secondary)]">
                        {gate.threshold_required}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
};
