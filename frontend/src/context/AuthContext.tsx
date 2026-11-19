import React, { createContext, useContext, useState, useEffect } from 'react';
import { AccountTier } from '../types/sirix';
import { sirixClient } from '../api/client';
import { usePreferences } from './PreferencesContext';

interface AuthContextValue {
  isAuthenticated: boolean;
  authInitializing: boolean;
  userId: string;
  accountTier: AccountTier;
  simulateDefensiveCash: boolean;
  isSandbox: boolean;
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

  useEffect(() => {
    let active = true;
    sirixClient
      .restoreSession()
      .then(async (restored) => {
        if (!active) return;
        if (restored) {
          setUserId(restored.user_id);
          setAccountTier(restored.account_tier);
          syncTierWithPreferences(restored.account_tier);
          await refreshPreferences();
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
    syncTierWithPreferences(authRes.account_tier);
    await refreshPreferences();
    setIsAuthenticated(true);
  };

  const enterSandbox = (tier: AccountTier = 'PRO') => {
    sirixClient.setSession(`sirix_sandbox_${Date.now()}`, tier);
    setAccountTier(tier);
    syncTierWithPreferences(tier);
    void refreshPreferences();
    setIsAuthenticated(true);
  };

  const switchTier = (tier: AccountTier) => {
    sirixClient.setTier(tier);
    setAccountTier(tier);
    syncTierWithPreferences(tier);
  };

  const toggleDefensiveCash = (active: boolean) => {
    sirixClient.setSimulateDefensiveCash(active);
    setSimulateDefensiveCash(active);
  };

  const logout = () => {
    void sirixClient.logout();
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
        isSandbox: sirixClient.isOfflineOrSandbox(),
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
