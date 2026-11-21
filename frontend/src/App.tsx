import React, { useState, useEffect, useCallback } from 'react';
import {
  Briefcase,
  Search,
  Sliders,
  History,
  Sparkles,
  LogOut,
  Wifi,
  Database,
  RefreshCw,
  Flag,
  AlertTriangle,
  X,
} from 'lucide-react';
import {
  AccountTier,
  EpochChangeEvent,
  EquityHistoryPoint,
  PortfolioEpochRecord,
  PortfolioOverviewResponse,
  PositionDeepDiveResponse,
} from './types/sirix';
import { sirixClient } from './api/client';
import { PreferencesProvider, usePreferences } from './context/PreferencesContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { LoginScreen } from './components/auth/LoginScreen';
import { PortfolioHomeView } from './components/portfolio/PortfolioHomeView';
import { PositionInspector } from './components/inspector/PositionInspector';
import { UniverseSearchView } from './components/search/UniverseSearchView';
import { AuditLogDrawer } from './components/audit/AuditLogDrawer';
import { PreferencesView } from './components/preferences/PreferencesView';

type ActiveWorkspaceTab = 'portfolio' | 'search' | 'preferences';

const SirixTerminalShell: React.FC = () => {
  const {
    isAuthenticated,
    authInitializing,
    accountTier,
    simulateDefensiveCash,
    isSandbox,
    switchTier,
    logout,
  } = useAuth();
  const { preferences, refreshPreferences, t } = usePreferences();

  const [activeTab, setActiveTab] = useState<ActiveWorkspaceTab>('portfolio');
  const [overview, setOverview] = useState<PortfolioOverviewResponse | null>(null);
  const [equityHistory, setEquityHistory] = useState<EquityHistoryPoint[]>([]);
  const [epochs, setEpochs] = useState<PortfolioEpochRecord[]>([]);
  const [loadingOverview, setLoadingOverview] = useState<boolean>(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [forceSyncing, setForceSyncing] = useState<boolean>(false);
  const [epochToast, setEpochToast] = useState<EpochChangeEvent | null>(null);

  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [deepDive, setDeepDive] = useState<PositionDeepDiveResponse | null>(null);
  const [loadingDeepDive, setLoadingDeepDive] = useState<boolean>(false);
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState<boolean>(false);
  const [auditDrawerOpen, setAuditDrawerOpen] = useState<boolean>(false);

  const killSwitchActive = preferences.guardrails.kill_switch_active;

  // Fetch Portfolio Overview + E.1 Epochs & Continuous TWR Equity History (fail-loud, zero mock fallback)
  const fetchOverview = useCallback(
    async (forceBust = false) => {
      setLoadingOverview(true);
      setApiError(null);
      try {
        const [data, epochsRes, historyRes] = await Promise.all([
          sirixClient.getPortfolioOverview(killSwitchActive, forceBust),
          sirixClient.getPortfolioEpochs(forceBust),
          sirixClient.getEquityHistory(forceBust),
        ]);
        setOverview(data);
        setEpochs(epochsRes.epochs || []);
        setEquityHistory(historyRes.points || []);
        if (data.holdings.length > 0) {
          setSelectedTicker((prev) =>
            prev && data.holdings.some((h) => h.ticker === prev) ? prev : data.holdings[0].ticker
          );
        } else {
          setSelectedTicker(null);
          setDeepDive(null);
        }
      } catch (err) {
        const message =
          err instanceof Error
            ? err.message
            : `Failed to fetch live portfolio state from ${sirixClient.getApiOriginDisplay()}.`;
        setApiError(message);
      } finally {
        setLoadingOverview(false);
      }
    },
    [killSwitchActive]
  );

  // E.1 Manual Force Sync Button (clears localStorage cache + appends ?t=<timestamp>)
  const handleForceSync = useCallback(async () => {
    if (forceSyncing) return;
    setForceSyncing(true);
    try {
      sirixClient.clearLocalCache();
      await Promise.allSettled([refreshPreferences(), fetchOverview(true)]);
    } finally {
      setForceSyncing(false);
    }
  }, [forceSyncing, refreshPreferences, fetchOverview]);

  useEffect(() => {
    if (isAuthenticated) {
      void fetchOverview(false);
    }
  }, [isAuthenticated, accountTier, simulateDefensiveCash, killSwitchActive, fetchOverview]);

  // E.1 Layer 4: Epoch-Change Guard Subscriber (reset React state + display New Epoch Toast)
  useEffect(() => {
    const unsubscribe = sirixClient.subscribeEpochChange((event) => {
      setOverview(null);
      setDeepDive(null);
      setSelectedTicker(null);
      setEquityHistory([]);
      setEpochs([]);
      setEpochToast(event);
      void refreshPreferences().catch(() => undefined);
      void fetchOverview(true);
    });
    return unsubscribe;
  }, [refreshPreferences, fetchOverview]);

  // E.1 Layer 4: Re-check Server Epoch / Revision on visibilitychange (iPhone / Chromebook wake)
  useEffect(() => {
    if (!isAuthenticated) return;
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void fetchOverview(true);
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [isAuthenticated, fetchOverview]);

  // Fetch Deep Dive when selectedTicker or accountTier changes
  useEffect(() => {
    if (!isAuthenticated || !selectedTicker) {
      setDeepDive(null);
      return;
    }
    let active = true;
    setLoadingDeepDive(true);
    sirixClient
      .getPositionDeepDive(selectedTicker)
      .then((res) => {
        if (active) {
          setDeepDive(res);
        }
      })
      .catch((err) => {
        if (active) {
          setDeepDive(null);
          setApiError(
            err instanceof Error
              ? err.message
              : `Unable to load live position deep dive for ${selectedTicker}.`
          );
        }
      })
      .finally(() => {
        if (active) {
          setLoadingDeepDive(false);
        }
      });
    return () => {
      active = false;
    };
  }, [isAuthenticated, selectedTicker, accountTier]);

  if (authInitializing) {
    return (
      <div className="min-h-screen sirix-canvas flex items-center justify-center">
        <div className="flex items-center gap-2.5 text-xs font-mono-tabular text-[var(--text-secondary)]">
          <RefreshCw className="w-4 h-4 text-[var(--accent-brand)] animate-spin" />
          <span>Syncing SIRIX session...</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginScreen />;
  }

  const handleSelectHolding = (ticker: string) => {
    setSelectedTicker(ticker);
    setMobileInspectorOpen(true);
  };

  const handleInspectFromSearch = (ticker: string) => {
    setSelectedTicker(ticker);
    setActiveTab('portfolio');
    setMobileInspectorOpen(true);
  };

  return (
    <div className="min-h-screen sirix-canvas flex flex-col lg:flex-row">
      {/* Desktop Left Vertical Icon Rail (>= 1024px, 64px width) */}
      <aside className="hidden lg:flex lg:w-16 lg:flex-col lg:items-center lg:justify-between lg:py-5 border-r border-[var(--border-subtle)] bg-[var(--bg-surface)] shrink-0 z-30">
        <div className="flex flex-col items-center gap-6">
          {/* SIRIX Brand Mark */}
          <button
            type="button"
            onClick={() => setActiveTab('portfolio')}
            title="SIRIX Autonomous Quant Terminal"
            className="w-10 h-10 rounded-xl flex items-center justify-center bg-[var(--accent-brand-subtle)] border border-[var(--accent-brand)] cursor-pointer"
          >
            <Sparkles className="w-5 h-5 text-[var(--accent-brand)]" />
          </button>

          {/* 3 Primary Navigation Icons */}
          <nav className="flex flex-col items-center gap-3" aria-label="Primary Navigation">
            <button
              type="button"
              onClick={() => setActiveTab('portfolio')}
              title={t.nav.portfolio}
              className={`w-10 h-10 rounded-xl flex items-center justify-center transition-colors cursor-pointer ${
                activeTab === 'portfolio'
                  ? 'bg-[var(--accent-brand)] text-slate-950'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)]'
              }`}
            >
              <Briefcase className="w-5 h-5" />
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('search')}
              title={t.nav.search}
              className={`w-10 h-10 rounded-xl flex items-center justify-center transition-colors cursor-pointer ${
                activeTab === 'search'
                  ? 'bg-[var(--accent-brand)] text-slate-950'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)]'
              }`}
            >
              <Search className="w-5 h-5" />
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('preferences')}
              title={t.nav.preferences}
              className={`w-10 h-10 rounded-xl flex items-center justify-center transition-colors cursor-pointer ${
                activeTab === 'preferences'
                  ? 'bg-[var(--accent-brand)] text-slate-950'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)]'
              }`}
            >
              <Sliders className="w-5 h-5" />
            </button>

            <button
              type="button"
              onClick={() => setAuditDrawerOpen(true)}
              title={t.nav.auditLog}
              className="w-10 h-10 rounded-xl flex items-center justify-center text-[var(--text-secondary)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
            >
              <History className="w-5 h-5" />
            </button>
          </nav>
        </div>

        <button
          type="button"
          onClick={logout}
          title={t.nav.signOut}
          className="w-10 h-10 rounded-xl flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--semantic-crimson)] transition-colors cursor-pointer"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 pb-20 lg:pb-0">
        {/* Top Institutional Telemetry Bar */}
        <header className="sticky top-0 z-20 h-14 px-4 sm:px-6 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)]/95 backdrop-blur-md flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 lg:hidden">
              <Sparkles className="w-4 h-4 text-[var(--accent-brand)]" />
              <span dir="ltr" className="font-mono-tabular font-bold tracking-wider text-sm">
                SIRIX
              </span>
            </div>
            <span className="hidden sm:inline-block text-xs font-medium text-[var(--text-secondary)]">
              {t.header.autonomousTelemetry}
            </span>
            <span
              dir="ltr"
              className="inline-flex items-center gap-1.5 text-[11px] font-mono-tabular px-2 py-0.5 rounded bg-[var(--bg-canvas)] border border-[var(--border-subtle)] text-[var(--text-secondary)]"
            >
              {isSandbox ? (
                <>
                  <Database className="w-3 h-3 text-[var(--semantic-amber)]" />
                  <span>{t.header.sandboxMode}</span>
                </>
              ) : (
                <>
                  <Wifi className="w-3 h-3 text-[var(--semantic-emerald)]" />
                  <span>{t.header.eodSynced}</span>
                </>
              )}
            </span>
          </div>

          {/* Right Tier Indicator (Switcher in explicit sandbox only), Force Sync & Audit Button */}
          <div className="flex items-center gap-2">
            {isSandbox ? (
              <div
                dir="ltr"
                className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-0.5"
              >
                {(['FREE', 'PRO', 'EXPERT'] as AccountTier[]).map((tier) => (
                  <button
                    key={tier}
                    type="button"
                    onClick={() => switchTier(tier)}
                    className={`px-2 py-1 rounded-md text-[10px] font-mono-tabular font-semibold transition-all cursor-pointer ${
                      accountTier === tier
                        ? 'bg-[var(--accent-brand)] text-slate-950'
                        : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    {tier}
                  </button>
                ))}
              </div>
            ) : (
              <span
                dir="ltr"
                className="px-2.5 py-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] text-[10px] font-mono-tabular font-semibold text-[var(--accent-brand)]"
              >
                {accountTier}
              </span>
            )}

            <button
              type="button"
              onClick={handleForceSync}
              disabled={forceSyncing}
              title="Force Sync (Clear local cache & fetch fresh state from GCS)"
              className="px-2.5 py-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] hover:border-[var(--accent-brand)] text-xs font-medium inline-flex items-center gap-1.5 cursor-pointer disabled:opacity-60"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 text-[var(--accent-brand)] ${
                  forceSyncing ? 'animate-spin' : ''
                }`}
              />
              <span className="hidden sm:inline">Force Sync</span>
            </button>

            <button
              type="button"
              onClick={() => setAuditDrawerOpen(true)}
              className="px-2.5 py-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] hover:border-[var(--border-strong)] text-xs font-medium inline-flex items-center gap-1.5 cursor-pointer"
            >
              <History className="w-3.5 h-3.5 text-[var(--accent-brand)]" />
              <span className="hidden sm:inline">{t.nav.auditLog}</span>
            </button>
          </div>
        </header>

        {/* Live API Diagnostic Error Banner (Fail-Loud — Never Masks Errors with Mock Data) */}
        {apiError && (
          <div
            role="alert"
            className="mx-4 sm:mx-6 mt-3 rounded-xl border border-[var(--semantic-crimson)] bg-[var(--semantic-crimson-subtle)] px-4 py-3 flex flex-wrap items-center justify-between gap-3 text-xs"
          >
            <div className="flex items-start gap-2.5 text-[var(--semantic-crimson)] min-w-0">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="space-y-0.5 min-w-0">
                <div className="font-semibold">
                  Live SIRIX Backend Telemetry Sync Failed ({sirixClient.getApiOriginDisplay()})
                </div>
                <div className="text-[var(--text-primary)] break-words">{apiError}</div>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={handleForceSync}
                disabled={forceSyncing}
                className="px-3 py-1.5 rounded-lg bg-[var(--semantic-crimson)] text-white font-semibold cursor-pointer disabled:opacity-60"
              >
                Retry Live Sync
              </button>
              <button
                type="button"
                onClick={() => setApiError(null)}
                aria-label="Dismiss API error banner"
                className="p-1 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* E.1 Layer 4 New Epoch Toast Banner */}
        {epochToast && (
          <div
            role="status"
            aria-live="polite"
            className="mx-4 sm:mx-6 mt-3 rounded-xl border border-[var(--accent-brand)] bg-[var(--accent-brand-subtle)] px-4 py-2.5 flex items-center justify-between gap-3 text-xs"
          >
            <div className="flex items-center gap-2.5 text-[var(--text-primary)]">
              <Flag className="w-4 h-4 text-[var(--accent-brand)] shrink-0" />
              <span>
                <strong className="text-[var(--accent-brand)]">
                  New Portfolio Epoch Activated:
                </strong>{' '}
                Epoch #{epochToast.newEpochId} • {epochToast.newEpochAlias} (Local cache purged &amp;
                synced to fresh GCS revision{' '}
                <code dir="ltr" className="font-mono-tabular">
                  {epochToast.newStateRev}
                </code>
                )
              </span>
            </div>
            <button
              type="button"
              onClick={() => setEpochToast(null)}
              aria-label="Dismiss epoch notification"
              className="p-1 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Workspace Container */}
        <main className="flex-1 p-4 sm:p-6 max-w-[1600px] w-full mx-auto">
          {activeTab === 'portfolio' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* Left 5-Column Master Stream */}
              <div className="lg:col-span-5">
                <PortfolioHomeView
                  overview={overview}
                  equityHistory={equityHistory}
                  epochs={epochs}
                  loading={loadingOverview}
                  selectedTicker={selectedTicker}
                  onSelectTicker={handleSelectHolding}
                  onOpenAuditLog={() => setAuditDrawerOpen(true)}
                />
              </div>

              {/* Right 7-Column Sticky Detail Inspector (Desktop >= 1024px) */}
              <div className="hidden lg:block lg:col-span-7 lg:sticky lg:top-20">
                {selectedTicker ? (
                  <PositionInspector
                    deepDive={deepDive}
                    loading={loadingDeepDive}
                    onClose={() => setSelectedTicker(null)}
                  />
                ) : (
                  <div className="rounded-2xl border sirix-surface p-8 text-center space-y-2 min-h-[320px] flex flex-col items-center justify-center">
                    <Sparkles className="w-8 h-8 text-[var(--accent-brand)] opacity-80" />
                    <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                      {overview && overview.holdings.length === 0
                        ? t.portfolio.noHoldingsTitle
                        : t.portfolio.selectPositionPrompt}
                    </h3>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'search' && (
            <UniverseSearchView onInspectHeldTicker={handleInspectFromSearch} />
          )}

          {activeTab === 'preferences' && <PreferencesView />}
        </main>
      </div>

      {/* Mobile Slide-Up Bottom Sheet Inspector (< 1024px) */}
      {mobileInspectorOpen && selectedTicker && (
        <div
          className="fixed inset-0 z-40 lg:hidden bg-black/65 backdrop-blur-xs flex flex-col justify-end"
          onClick={() => setMobileInspectorOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="max-h-[88vh] overflow-y-auto rounded-t-2xl sirix-canvas p-2"
          >
            <div className="w-10 h-1 rounded-full bg-[var(--border-strong)] mx-auto my-2" />
            <PositionInspector
              deepDive={deepDive}
              loading={loadingDeepDive}
              onClose={() => setMobileInspectorOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Mobile Persistent 3-Icon Bottom Navigation Bar (< 1024px) */}
      <nav
        aria-label="Mobile Bottom Navigation"
        className="fixed bottom-0 left-0 right-0 z-30 h-16 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]/95 backdrop-blur-md grid grid-cols-3 lg:hidden"
      >
        <button
          type="button"
          onClick={() => setActiveTab('portfolio')}
          className={`flex flex-col items-center justify-center gap-1 text-xs font-medium cursor-pointer ${
            activeTab === 'portfolio'
              ? 'text-[var(--accent-brand)]'
              : 'text-[var(--text-secondary)]'
          }`}
        >
          <Briefcase className="w-4 h-4" />
          <span>{t.nav.portfolio}</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('search')}
          className={`flex flex-col items-center justify-center gap-1 text-xs font-medium cursor-pointer ${
            activeTab === 'search'
              ? 'text-[var(--accent-brand)]'
              : 'text-[var(--text-secondary)]'
          }`}
        >
          <Search className="w-4 h-4" />
          <span>{t.nav.search}</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('preferences')}
          className={`flex flex-col items-center justify-center gap-1 text-xs font-medium cursor-pointer ${
            activeTab === 'preferences'
              ? 'text-[var(--accent-brand)]'
              : 'text-[var(--text-secondary)]'
          }`}
        >
          <Sliders className="w-4 h-4" />
          <span>{t.nav.preferences}</span>
        </button>
      </nav>

      {/* Closed Trades Audit Log Drawer */}
      <AuditLogDrawer open={auditDrawerOpen} onClose={() => setAuditDrawerOpen(false)} />
    </div>
  );
};

export function App() {
  return (
    <PreferencesProvider>
      <AuthProvider>
        <SirixTerminalShell />
      </AuthProvider>
    </PreferencesProvider>
  );
}

export default App;
