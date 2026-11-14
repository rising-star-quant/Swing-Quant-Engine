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
} from 'lucide-react';
import {
  AccountTier,
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
    accountTier,
    simulateDefensiveCash,
    isSandbox,
    switchTier,
    logout,
  } = useAuth();
  const { preferences, t } = usePreferences();

  const [activeTab, setActiveTab] = useState<ActiveWorkspaceTab>('portfolio');
  const [overview, setOverview] = useState<PortfolioOverviewResponse | null>(null);
  const [loadingOverview, setLoadingOverview] = useState<boolean>(true);

  const [selectedTicker, setSelectedTicker] = useState<string | null>('CELH');
  const [deepDive, setDeepDive] = useState<PositionDeepDiveResponse | null>(null);
  const [loadingDeepDive, setLoadingDeepDive] = useState<boolean>(false);
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState<boolean>(false);
  const [auditDrawerOpen, setAuditDrawerOpen] = useState<boolean>(false);

  const killSwitchActive = preferences.guardrails.kill_switch_active;

  // Fetch Portfolio Overview
  const fetchOverview = useCallback(async () => {
    setLoadingOverview(true);
    try {
      const data = await sirixClient.getPortfolioOverview(killSwitchActive);
      setOverview(data);
      if (data.holdings.length > 0) {
        const currentValid = data.holdings.some((h) => h.ticker === selectedTicker);
        if (!currentValid) {
          setSelectedTicker(data.holdings[0].ticker);
        }
      } else {
        setSelectedTicker(null);
        setDeepDive(null);
      }
    } finally {
      setLoadingOverview(false);
    }
  }, [killSwitchActive, selectedTicker]);

  useEffect(() => {
    if (isAuthenticated) {
      fetchOverview();
    }
  }, [isAuthenticated, accountTier, simulateDefensiveCash, killSwitchActive, fetchOverview]);

  // Fetch Deep Dive when selectedTicker or accountTier changes
  useEffect(() => {
    if (!isAuthenticated || !selectedTicker) {
      setDeepDive(null);
      return;
    }
    setLoadingDeepDive(true);
    sirixClient
      .getPositionDeepDive(selectedTicker)
      .then((res) => setDeepDive(res))
      .finally(() => setLoadingDeepDive(false));
  }, [isAuthenticated, selectedTicker, accountTier]);

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
                  <Database className="w-3 h-3 text-[var(--accent-brand)]" />
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

          {/* Right Quick Tier Switcher & Audit Button */}
          <div className="flex items-center gap-2">
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

        {/* Workspace Container */}
        <main className="flex-1 p-4 sm:p-6 max-w-[1600px] w-full mx-auto">
          {activeTab === 'portfolio' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* Left 5-Column Master Stream */}
              <div className="lg:col-span-5">
                <PortfolioHomeView
                  overview={overview}
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
