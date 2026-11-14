import React, { useState } from 'react';
import { ShieldCheck, Lock, Sparkles, ArrowRight } from 'lucide-react';
import { AccountTier } from '../../types/sirix';
import { useAuth } from '../../context/AuthContext';
import { usePreferences } from '../../context/PreferencesContext';
import { TermTooltip } from '../common/TermTooltip';

export const LoginScreen: React.FC = () => {
  const { login, enterSandbox } = useAuth();
  const { t, language } = usePreferences();
  const [email, setEmail] = useState('institutional@sirix-quant.io');
  const [password, setPassword] = useState('••••••••••••••••');
  const [selectedTier, setSelectedTier] = useState<AccountTier>('PRO');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password, selectedTier);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen sirix-canvas flex flex-col justify-center items-center px-4 py-12">
      <div className="w-full max-w-md rounded-2xl border sirix-surface p-6 sm:p-8 shadow-2xl">
        {/* Brand Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-[var(--accent-brand-subtle)] border border-[var(--accent-brand)]">
              <Sparkles className="w-5 h-5 text-[var(--accent-brand)]" />
            </div>
            <div>
              <h1 dir="ltr" className="text-xl font-bold tracking-wider font-mono-tabular">
                SIRIX
              </h1>
              <p className="text-xs text-[var(--text-secondary)]">{t.auth.subtitle}</p>
            </div>
          </div>
          <span
            dir="ltr"
            className="text-[11px] font-mono-tabular px-2.5 py-1 rounded-md border border-[var(--border-strong)] text-[var(--accent-brand)]"
          >
            RUT • MID
          </span>
        </div>

        {/* Tier Selector for Instant Demo / Auth Testing */}
        <div className="mb-6 p-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)]">
          <div className="text-xs font-medium text-[var(--text-secondary)] mb-2">
            Select Telemetry Access Tier:
          </div>
          <div className="grid grid-cols-3 gap-2">
            {(['FREE', 'PRO', 'EXPERT'] as AccountTier[]).map((tier) => (
              <button
                key={tier}
                type="button"
                onClick={() => setSelectedTier(tier)}
                className={`py-2 px-3 rounded-lg text-xs font-mono-tabular font-semibold border transition-all cursor-pointer ${
                  selectedTier === tier
                    ? 'border-[var(--accent-brand)] bg-[var(--accent-brand-subtle)] text-[var(--accent-brand)]'
                    : 'border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]'
                }`}
              >
                {tier}
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
              {t.auth.emailLabel}
            </label>
            <input
              type="email"
              required
              dir="ltr"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] text-sm font-mono-tabular text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-brand)]"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
              {t.auth.passwordLabel}
            </label>
            <div className="relative">
              <input
                type="password"
                required
                dir="ltr"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] text-sm font-mono-tabular text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-brand)]"
              />
              <Lock className="w-4 h-4 text-[var(--text-muted)] absolute right-3.5 top-3" />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-lg bg-[var(--accent-brand)] text-slate-950 font-semibold text-sm flex items-center justify-center gap-2 hover:opacity-95 transition-opacity cursor-pointer"
          >
            <span>{t.auth.signInBtn}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        <div className="my-4 flex items-center gap-3">
          <div className="h-px flex-1 bg-[var(--border-subtle)]" />
          <span className="text-[11px] uppercase tracking-wider text-[var(--text-muted)]">OR</span>
          <div className="h-px flex-1 bg-[var(--border-subtle)]" />
        </div>

        <button
          type="button"
          onClick={() => enterSandbox(selectedTier)}
          className="w-full py-2.5 px-4 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-canvas)] hover:bg-[var(--bg-surface-hover)] text-xs font-medium text-[var(--text-primary)] transition-colors cursor-pointer"
        >
          {t.auth.sandboxBtn} ({selectedTier})
        </button>

        {/* Zero-Override Institutional Notice */}
        <div className="mt-6 pt-4 border-t border-[var(--border-subtle)] flex items-center justify-between text-xs text-[var(--text-muted)]">
          <span className="inline-flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-[var(--semantic-emerald)] shrink-0" />
            <TermTooltip term="Zero-Override" language={language} />
          </span>
          <span className="text-[11px]">{t.auth.zeroOverridePromise.split('•')[1]}</span>
        </div>
      </div>
    </div>
  );
};
