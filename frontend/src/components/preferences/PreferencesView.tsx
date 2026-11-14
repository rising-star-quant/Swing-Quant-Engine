import React, { useState } from 'react';
import {
  Globe,
  Palette,
  ShieldCheck,
  Sliders,
  AlertOctagon,
  Lock,
  Check,
  FlaskConical,
} from 'lucide-react';
import {
  AccountTier,
  SupportedLanguage,
  SupportedTheme,
  UniverseCode,
} from '../../types/sirix';
import { usePreferences } from '../../context/PreferencesContext';
import { useAuth } from '../../context/AuthContext';
import { TermTooltip } from '../common/TermTooltip';

const LANGUAGE_OPTIONS: { code: SupportedLanguage; nativeLabel: string; dirLabel: string }[] = [
  { code: 'en', nativeLabel: 'English', dirLabel: 'LTR' },
  { code: 'he', nativeLabel: 'עברית', dirLabel: 'RTL' },
  { code: 'ar', nativeLabel: 'العربية', dirLabel: 'RTL' },
  { code: 'ru', nativeLabel: 'Русский', dirLabel: 'LTR' },
];

export const PreferencesView: React.FC = () => {
  const {
    preferences,
    language,
    theme,
    t,
    setLanguage,
    setTheme,
    updateGuardrails,
  } = usePreferences();
  const {
    accountTier,
    switchTier,
    simulateDefensiveCash,
    toggleDefensiveCash,
  } = useAuth();

  const [maxHeat, setMaxHeat] = useState<number>(preferences.guardrails.max_portfolio_heat_pct);
  const [riskPerTrade, setRiskPerTrade] = useState<number>(
    preferences.guardrails.risk_per_trade_pct
  );
  const [timeBarrierDays, setTimeBarrierDays] = useState<number>(
    preferences.guardrails.time_barrier_days
  );
  const [blackoutDays, setBlackoutDays] = useState<number>(
    preferences.guardrails.earnings_blackout_days
  );
  const [universes, setUniverses] = useState<UniverseCode[]>(
    preferences.guardrails.active_universes
  );
  const [savedBanner, setSavedBanner] = useState(false);
  const [confirmingKillSwitch, setConfirmingKillSwitch] = useState(false);

  const isExpert = accountTier === 'EXPERT';
  const killSwitchActive = preferences.guardrails.kill_switch_active;

  const handleToggleUniverse = (u: UniverseCode) => {
    if (!isExpert) return;
    if (universes.includes(u)) {
      if (universes.length > 1) {
        setUniverses(universes.filter((item) => item !== u));
      }
    } else {
      setUniverses([...universes, u]);
    }
  };

  const handleSaveGuardrails = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isExpert) return;
    await updateGuardrails({
      max_portfolio_heat_pct: maxHeat,
      risk_per_trade_pct: riskPerTrade,
      time_barrier_days: timeBarrierDays,
      earnings_blackout_days: blackoutDays,
      active_universes: universes,
    });
    setSavedBanner(true);
    setTimeout(() => setSavedBanner(false), 3000);
  };

  const handleKillSwitchToggle = async (activate: boolean) => {
    if (!isExpert) return;
    await updateGuardrails({ kill_switch_active: activate });
    setConfirmingKillSwitch(false);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-10">
      {/* Header */}
      <div className="rounded-2xl border sirix-surface p-5">
        <h1 className="text-lg sm:text-xl font-bold text-[var(--text-primary)]">
          {t.preferences.title}
        </h1>
        <p className="text-xs sm:text-sm text-[var(--text-secondary)] mt-1">
          {t.preferences.subtitle}
        </p>
      </div>

      {/* Interactive Sandbox Tier & Edge-State Controls */}
      <section className="rounded-2xl border border-[var(--accent-brand)] bg-[var(--bg-surface)] p-5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-[var(--accent-brand)]" />
            <h2 className="text-sm font-bold text-[var(--text-primary)]">
              {t.preferences.demoTierSwitcherTitle}
            </h2>
          </div>
          <span
            dir="ltr"
            className="text-xs font-mono-tabular px-2 py-0.5 rounded bg-[var(--accent-brand-subtle)] text-[var(--accent-brand)] font-semibold"
          >
            ACTIVE TIER: {accountTier}
          </span>
        </div>
        <p className="text-xs text-[var(--text-secondary)]">{t.preferences.demoTierSwitcherDesc}</p>

        <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
          <div className="flex items-center gap-2">
            {(['FREE', 'PRO', 'EXPERT'] as AccountTier[]).map((tier) => (
              <button
                key={tier}
                type="button"
                onClick={() => switchTier(tier)}
                className={`px-3.5 py-2 rounded-xl text-xs font-mono-tabular font-semibold border transition-all cursor-pointer ${
                  accountTier === tier
                    ? 'border-[var(--accent-brand)] bg-[var(--accent-brand)] text-slate-950'
                    : 'border-[var(--border-subtle)] bg-[var(--bg-canvas)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]'
                }`}
              >
                {tier}
              </button>
            ))}
          </div>

          <label className="inline-flex items-center gap-2.5 text-xs text-[var(--text-primary)] cursor-pointer select-none">
            <input
              type="checkbox"
              checked={simulateDefensiveCash}
              onChange={(e) => toggleDefensiveCash(e.target.checked)}
              className="w-4 h-4 accent-[var(--accent-brand)] rounded cursor-pointer"
            />
            <span>{t.preferences.simulateDefensiveCash}</span>
          </label>
        </div>
      </section>

      {/* 1. Multilingual Localization & RTL/LTR Switcher */}
      <section className="rounded-2xl border sirix-surface p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-[var(--accent-brand)]" />
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            {t.preferences.languageSection}
          </h2>
        </div>
        <p className="text-xs text-[var(--text-secondary)]">{t.preferences.languageDesc}</p>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          {LANGUAGE_OPTIONS.map((opt) => {
            const active = language === opt.code;
            return (
              <button
                key={opt.code}
                type="button"
                onClick={() => setLanguage(opt.code)}
                className={`p-3 rounded-xl border text-left transition-all flex items-center justify-between cursor-pointer ${
                  active
                    ? 'border-[var(--accent-brand)] bg-[var(--accent-brand-subtle)]'
                    : 'border-[var(--border-subtle)] bg-[var(--bg-canvas)] hover:border-[var(--border-strong)]'
                }`}
              >
                <div>
                  <div className="text-sm font-semibold text-[var(--text-primary)]">
                    {opt.nativeLabel}
                  </div>
                  <div dir="ltr" className="text-[10px] font-mono-tabular text-[var(--text-muted)]">
                    {opt.code.toUpperCase()} • {opt.dirLabel}
                  </div>
                </div>
                {active && <Check className="w-4 h-4 text-[var(--accent-brand)]" />}
              </button>
            );
          })}
        </div>
      </section>

      {/* 2. Three Curated Theme Palettes */}
      <section className="rounded-2xl border sirix-surface p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Palette className="w-4 h-4 text-[var(--accent-brand)]" />
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            {t.preferences.themeSection}
          </h2>
        </div>
        <p className="text-xs text-[var(--text-secondary)]">{t.preferences.themeDesc}</p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {(
            [
              {
                id: 'obsidian-dark' as SupportedTheme,
                title: t.preferences.themeObsidian,
                desc: t.preferences.themeObsidianDesc,
                bgSwatch: '#090D16',
                cardSwatch: '#111827',
                accentSwatch: '#06B6D4',
              },
              {
                id: 'sirius-ice-light' as SupportedTheme,
                title: t.preferences.themeSiriusIce,
                desc: t.preferences.themeSiriusIceDesc,
                bgSwatch: '#F0F7FF',
                cardSwatch: '#FFFFFF',
                accentSwatch: '#0284C7',
              },
              {
                id: 'midnight-sapphire' as SupportedTheme,
                title: t.preferences.themeSapphire,
                desc: t.preferences.themeSapphireDesc,
                bgSwatch: '#0B192C',
                cardSwatch: '#132743',
                accentSwatch: '#38BDF8',
              },
            ] as const
          ).map((swatch) => {
            const active = theme === swatch.id;
            return (
              <button
                key={swatch.id}
                type="button"
                onClick={() => setTheme(swatch.id)}
                className={`p-4 rounded-xl border text-left transition-all flex flex-col justify-between cursor-pointer ${
                  active
                    ? 'border-[var(--accent-brand)] bg-[var(--accent-brand-subtle)]'
                    : 'border-[var(--border-subtle)] bg-[var(--bg-canvas)] hover:border-[var(--border-strong)]'
                }`}
              >
                <div className="space-y-2.5">
                  {/* Visual Color Swatch Preview Bar */}
                  <div className="flex items-center gap-1.5">
                    <span
                      className="w-6 h-6 rounded-md border border-slate-500/40"
                      style={{ backgroundColor: swatch.bgSwatch }}
                    />
                    <span
                      className="w-6 h-6 rounded-md border border-slate-500/40"
                      style={{ backgroundColor: swatch.cardSwatch }}
                    />
                    <span
                      className="w-6 h-6 rounded-md border border-slate-500/40"
                      style={{ backgroundColor: swatch.accentSwatch }}
                    />
                  </div>
                  <div className="text-sm font-bold text-[var(--text-primary)]">{swatch.title}</div>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                    {swatch.desc}
                  </p>
                </div>

                <div
                  dir="ltr"
                  className="mt-3 pt-2 border-t border-[var(--border-subtle)] flex items-center justify-between text-[11px] font-mono-tabular text-[var(--text-muted)]"
                >
                  <span>{swatch.id}</span>
                  {active && <Check className="w-4 h-4 text-[var(--accent-brand)]" />}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* 3. Quantitative Risk Guardrails (EXPERT Tier Editable) */}
      <section className="rounded-2xl border sirix-surface p-5 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-[var(--accent-brand)]" />
            <h2 className="text-sm font-bold text-[var(--text-primary)]">
              {t.preferences.guardrailsSection}
            </h2>
          </div>

          <span
            dir="ltr"
            className="inline-flex items-center gap-1.5 text-xs font-mono-tabular px-2.5 py-1 rounded-md bg-[var(--semantic-emerald-subtle)] text-[var(--semantic-emerald)] font-semibold"
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <TermTooltip term="Zero-Override" language={language} /> • {t.preferences.immutableEnforced}
          </span>
        </div>

        <p className="text-xs text-[var(--text-secondary)]">{t.preferences.guardrailsDesc}</p>

        {!isExpert && (
          <div className="rounded-xl border border-[var(--accent-brand)] bg-[var(--accent-brand-subtle)] p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-[var(--text-primary)]">
              <Lock className="w-4 h-4 text-[var(--accent-brand)] shrink-0" />
              <span>{t.preferences.expertRequiredBanner}</span>
            </div>
            <button
              type="button"
              onClick={() => switchTier('EXPERT')}
              className="shrink-0 px-3 py-1.5 rounded-lg bg-[var(--accent-brand)] text-slate-950 font-semibold text-xs cursor-pointer"
            >
              Switch to EXPERT Tier
            </button>
          </div>
        )}

        <form onSubmit={handleSaveGuardrails} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Max Portfolio Heat (%) */}
            <div className="p-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-[var(--text-secondary)]">{t.preferences.maxHeatLabel}</span>
                <span dir="ltr" className="font-mono-tabular font-bold text-[var(--accent-brand)]">
                  {maxHeat.toFixed(1)}%
                </span>
              </div>
              <input
                type="range"
                min={1.0}
                max={10.0}
                step={0.5}
                disabled={!isExpert}
                value={maxHeat}
                onChange={(e) => setMaxHeat(parseFloat(e.target.value))}
                className="w-full accent-[var(--accent-brand)] cursor-pointer disabled:opacity-50"
              />
              <div dir="ltr" className="flex justify-between text-[10px] font-mono-tabular text-[var(--text-muted)]">
                <span>1.0% (Conservative)</span>
                <span>5.0% (Default)</span>
                <span>10.0% (Max)</span>
              </div>
            </div>

            {/* Risk Per Trade (%) */}
            <div className="p-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-[var(--text-secondary)]">
                  {t.preferences.riskPerTradeLabel}
                </span>
                <span dir="ltr" className="font-mono-tabular font-bold text-[var(--accent-brand)]">
                  {riskPerTrade.toFixed(2)}%
                </span>
              </div>
              <input
                type="range"
                min={0.25}
                max={2.0}
                step={0.25}
                disabled={!isExpert}
                value={riskPerTrade}
                onChange={(e) => setRiskPerTrade(parseFloat(e.target.value))}
                className="w-full accent-[var(--accent-brand)] cursor-pointer disabled:opacity-50"
              />
              <div dir="ltr" className="flex justify-between text-[10px] font-mono-tabular text-[var(--text-muted)]">
                <span>0.25%</span>
                <span>1.00% (Default)</span>
                <span>2.00%</span>
              </div>
            </div>

            {/* Time Barrier Horizon (5 - 30 Trading Days) */}
            <div className="p-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-[var(--text-secondary)]">
                  {t.preferences.timeBarrierLabel}
                </span>
                <span dir="ltr" className="font-mono-tabular font-bold text-[var(--text-primary)]">
                  {timeBarrierDays}d
                </span>
              </div>
              <input
                type="range"
                min={5}
                max={30}
                step={1}
                disabled={!isExpert}
                value={timeBarrierDays}
                onChange={(e) => setTimeBarrierDays(parseInt(e.target.value, 10))}
                className="w-full accent-[var(--accent-brand)] cursor-pointer disabled:opacity-50"
              />
              <div dir="ltr" className="flex justify-between text-[10px] font-mono-tabular text-[var(--text-muted)]">
                <span>5d</span>
                <span>14d (Canonical)</span>
                <span>30d</span>
              </div>
            </div>

            {/* Pre-Earnings Blackout Window (3 - 10 Days) */}
            <div className="p-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-[var(--text-secondary)]">
                  {t.preferences.earningsBlackoutLabel}
                </span>
                <span dir="ltr" className="font-mono-tabular font-bold text-[var(--text-primary)]">
                  {blackoutDays}d
                </span>
              </div>
              <input
                type="range"
                min={3}
                max={10}
                step={1}
                disabled={!isExpert}
                value={blackoutDays}
                onChange={(e) => setBlackoutDays(parseInt(e.target.value, 10))}
                className="w-full accent-[var(--accent-brand)] cursor-pointer disabled:opacity-50"
              />
              <div dir="ltr" className="flex justify-between text-[10px] font-mono-tabular text-[var(--text-muted)]">
                <span>3d</span>
                <span>5d (Canonical)</span>
                <span>10d</span>
              </div>
            </div>
          </div>

          {/* Active Index Universes (RUT & MID) */}
          <div className="p-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs font-medium text-[var(--text-secondary)]">
              {t.preferences.activeUniversesLabel}
            </div>
            <div className="flex items-center gap-2.5">
              {(['RUT', 'MID'] as UniverseCode[]).map((u) => {
                const isSelected = universes.includes(u);
                return (
                  <button
                    key={u}
                    type="button"
                    disabled={!isExpert}
                    onClick={() => handleToggleUniverse(u)}
                    className={`px-3 py-1.5 rounded-lg border text-xs font-mono-tabular font-semibold transition-colors cursor-pointer disabled:opacity-60 ${
                      isSelected
                        ? 'border-[var(--accent-brand)] bg-[var(--accent-brand-subtle)] text-[var(--accent-brand)]'
                        : 'border-[var(--border-subtle)] text-[var(--text-muted)]'
                    }`}
                  >
                    {u}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex items-center justify-between gap-3">
            {savedBanner ? (
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--semantic-emerald)]">
                <Check className="w-4 h-4" />
                {t.preferences.savedSuccess}
              </span>
            ) : (
              <span />
            )}

            <button
              type="submit"
              disabled={!isExpert}
              className="px-5 py-2.5 rounded-xl bg-[var(--accent-brand)] text-slate-950 font-semibold text-xs hover:opacity-95 transition-opacity cursor-pointer disabled:opacity-40"
            >
              {t.preferences.saveGuardrailsBtn}
            </button>
          </div>
        </form>
      </section>

      {/* 4. Two-Step Emergency Autonomous Kill-Switch */}
      <section className="rounded-2xl border-2 border-[var(--semantic-crimson)] bg-[var(--bg-surface)] p-5 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-bold text-[var(--semantic-crimson)]">
            <AlertOctagon className="w-4 h-4" />
            <span>{t.preferences.killSwitchTitle}</span>
          </div>
          <span dir="ltr" className="text-xs font-mono-tabular font-semibold text-[var(--text-muted)]">
            STATUS: {killSwitchActive ? 'HALTED_KILL_SWITCH' : 'ARMED_READY'}
          </span>
        </div>

        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          {t.preferences.killSwitchDesc}
        </p>

        {killSwitchActive ? (
          <button
            type="button"
            disabled={!isExpert}
            onClick={() => handleKillSwitchToggle(false)}
            className="px-4 py-2.5 rounded-xl bg-[var(--semantic-emerald)] text-slate-950 font-semibold text-xs cursor-pointer disabled:opacity-40"
          >
            {t.preferences.resumeEngineBtn}
          </button>
        ) : !confirmingKillSwitch ? (
          <button
            type="button"
            disabled={!isExpert}
            onClick={() => setConfirmingKillSwitch(true)}
            className="px-4 py-2.5 rounded-xl border border-[var(--semantic-crimson)] bg-[var(--semantic-crimson-subtle)] text-[var(--semantic-crimson)] font-semibold text-xs hover:opacity-90 cursor-pointer disabled:opacity-40"
          >
            {t.preferences.armKillSwitchBtn}
          </button>
        ) : (
          <div className="flex flex-wrap items-center gap-2.5 pt-1">
            <button
              type="button"
              onClick={() => handleKillSwitchToggle(true)}
              className="px-4 py-2.5 rounded-xl bg-[var(--semantic-crimson)] text-white font-semibold text-xs cursor-pointer"
            >
              {t.preferences.confirmKillSwitchBtn}
            </button>
            <button
              type="button"
              onClick={() => setConfirmingKillSwitch(false)}
              className="px-3.5 py-2.5 rounded-xl border border-[var(--border-strong)] text-xs text-[var(--text-secondary)] cursor-pointer"
            >
              {t.preferences.cancelBtn}
            </button>
          </div>
        )}
      </section>
    </div>
  );
};
