import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  AccountTier,
  RiskGuardrailConfig,
  SupportedLanguage,
  SupportedTheme,
  UserPreferencesResponse,
} from '../types/sirix';
import { UI_TRANSLATIONS, UITranslations } from '../i18n/translations';
import { sirixClient } from '../api/client';

const THEME_META_COLORS: Record<SupportedTheme, string> = {
  'obsidian-dark': '#090D16',
  'sirius-ice-light': '#F0F7FF',
  'midnight-sapphire': '#0B192C',
};

interface PreferencesContextValue {
  preferences: UserPreferencesResponse;
  language: SupportedLanguage;
  theme: SupportedTheme;
  isRTL: boolean;
  t: UITranslations;
  setLanguage: (lang: SupportedLanguage) => Promise<void>;
  setTheme: (theme: SupportedTheme) => Promise<void>;
  updateGuardrails: (patch: Partial<RiskGuardrailConfig>) => Promise<void>;
  syncTierWithPreferences: (tier: AccountTier) => void;
}

const DEFAULT_PREFERENCES: UserPreferencesResponse = {
  user_id: 'usr_sirix_institutional_01',
  account_tier: 'PRO',
  language: 'en',
  theme: 'obsidian-dark',
  notifications_enabled: true,
  guardrails_editable: false,
  guardrails: {
    max_portfolio_heat_pct: 5.0,
    risk_per_trade_pct: 1.0,
    time_barrier_days: 14,
    earnings_blackout_days: 5,
    active_universes: ['RUT', 'MID'],
    zero_override_enforced: true,
    kill_switch_active: false,
  },
};

const PreferencesContext = createContext<PreferencesContextValue | undefined>(undefined);

export const PreferencesProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [preferences, setPreferences] = useState<UserPreferencesResponse>(DEFAULT_PREFERENCES);

  // Apply DOM attributes (<html lang="..." dir="..." data-theme="..."> & <meta name="theme-color">)
  const applyDomAttributes = useCallback((lang: SupportedLanguage, theme: SupportedTheme) => {
    const htmlEl = document.documentElement;
    const isRtlLang = lang === 'he' || lang === 'ar';
    htmlEl.setAttribute('lang', lang);
    htmlEl.setAttribute('dir', isRtlLang ? 'rtl' : 'ltr');
    htmlEl.setAttribute('data-theme', theme);

    const metaTheme = document.getElementById('sirix-theme-color');
    if (metaTheme) {
      metaTheme.setAttribute('content', THEME_META_COLORS[theme]);
    }
  }, []);

  useEffect(() => {
    sirixClient.getPreferences().then((loaded) => {
      setPreferences(loaded);
      applyDomAttributes(loaded.language, loaded.theme);
    });
  }, [applyDomAttributes]);

  const setLanguage = async (language: SupportedLanguage) => {
    applyDomAttributes(language, preferences.theme);
    const updated = await sirixClient.updatePreferences(preferences, { language });
    setPreferences(updated);
  };

  const setTheme = async (theme: SupportedTheme) => {
    applyDomAttributes(preferences.language, theme);
    const updated = await sirixClient.updatePreferences(preferences, { theme });
    setPreferences(updated);
  };

  const updateGuardrails = async (guardrailPatch: Partial<RiskGuardrailConfig>) => {
    const updated = await sirixClient.updatePreferences(preferences, {
      guardrails: guardrailPatch,
    });
    setPreferences(updated);
  };

  const syncTierWithPreferences = useCallback((tier: AccountTier) => {
    setPreferences((prev) => ({
      ...prev,
      account_tier: tier,
      guardrails_editable: tier === 'EXPERT',
    }));
  }, []);

  const isRTL = preferences.language === 'he' || preferences.language === 'ar';
  const t = UI_TRANSLATIONS[preferences.language] || UI_TRANSLATIONS.en;

  return (
    <PreferencesContext.Provider
      value={{
        preferences,
        language: preferences.language,
        theme: preferences.theme,
        isRTL,
        t,
        setLanguage,
        setTheme,
        updateGuardrails,
        syncTierWithPreferences,
      }}
    >
      {children}
    </PreferencesContext.Provider>
  );
};

export const usePreferences = (): PreferencesContextValue => {
  const ctx = useContext(PreferencesContext);
  if (!ctx) {
    throw new Error('usePreferences must be used within PreferencesProvider');
  }
  return ctx;
};
