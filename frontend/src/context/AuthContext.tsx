import React, { createContext, useContext, useState, useEffect } from 'react';
import { AccountTier } from '../types/sirix';
import { sirixClient } from '../api/client';
import { RUNTIME_CONFIG } from '../config/runtimeConfig';
import { usePreferences } from './PreferencesContext';

interface AuthContextValue {
  isAuthenticated: boolean;
  authInitializing: boolean;
  userId: string;
  accountTier: AccountTier;
  simulateDefensiveCash: boolean;
  isSandbox: boolean;
  isSandboxAllowed: boolean;
  login: (email: string, password: string, tier?: AccountTier) => Promise<void>;
  enterSandbox: (tier?: AccountTier) => void;
  switchTier: (tier: AccountTier) => void;
  toggleDefensiveCash: (active: boolean) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { syncTierWithPreferences, refreshPreferences } = usePreferences();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [authInitializing, setAuthInitializing] = useState<boolean>(true);
  const [userId, setUserId] = useState<string>('usr_sirix_primary');
  const [accountTier, setAccountTier] = useState<AccountTier>('PRO');
  const [simulateDefensiveCash, setSimulateDefensiveCash] = useState<boolean>(false);
  const [isSandbox, setIsSandbox] = useState<boolean>(false);

  useEffect(() => {
    let active = true;
    sirixClient
      .restoreSession()
      .then(async (restored) => {
        if (!active) return;
        if (restored) {
          setUserId(restored.user_id);
          setAccountTier(restored.account_tier);
          setIsSandbox(false);
          syncTierWithPreferences(restored.account_tier);
          try {
            await refreshPreferences();
          } catch {
            // Preferences fetch errors will surface in UI without silently switching to sandbox
          }
          setIsAuthenticated(true);
        }
      })
      .finally(() => {
        if (active) {
          setAuthInitializing(false);
        }
      });
    return () => {
      active = false;
    };
  }, [syncTierWithPreferences, refreshPreferences]);

  const login = async (email: string, password: string, tier: AccountTier = 'PRO') => {
    const authRes = await sirixClient.login(email, password, tier);
    setUserId(authRes.user_id);
    setAccountTier(authRes.account_tier);
    setIsSandbox(false);
    setSimulateDefensiveCash(false);
    sirixClient.setSimulateDefensiveCash(false);
    syncTierWithPreferences(authRes.account_tier);
    try {
      await refreshPreferences();
    } catch {
      // Allow live portfolio dashboard to load and display diagnostic errors if preferences endpoint fails
    }
    setIsAuthenticated(true);
  };

  const enterSandbox = (tier: AccountTier = 'PRO') => {
    if (!RUNTIME_CONFIG.isSandboxAllowed) {
      return;
    }
    sirixClient.setSession(`sirix_sandbox_${Date.now()}`, tier);
    setUserId('usr_sirix_sandbox');
    setAccountTier(tier);
    setIsSandbox(true);
    syncTierWithPreferences(tier);
    void refreshPreferences();
    setIsAuthenticated(true);
  };

  const switchTier = (tier: AccountTier) => {
    if (!isSandbox) {
      return;
    }
    sirixClient.setTier(tier);
    setAccountTier(tier);
    syncTierWithPreferences(tier);
  };

  const toggleDefensiveCash = (active: boolean) => {
    if (!isSandbox) {
      return;
    }
    sirixClient.setSimulateDefensiveCash(active);
    setSimulateDefensiveCash(active);
  };

  const logout = () => {
    void sirixClient.logout();
    setIsSandbox(false);
    setSimulateDefensiveCash(false);
    setIsAuthenticated(false);
  };

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        authInitializing,
        userId,
        accountTier,
        simulateDefensiveCash,
        isSandbox,
        isSandboxAllowed: RUNTIME_CONFIG.isSandboxAllowed,
        login,
        enterSandbox,
        switchTier,
        toggleDefensiveCash,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
};
