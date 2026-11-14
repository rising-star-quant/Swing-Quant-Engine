import React, { createContext, useContext, useState } from 'react';
import { AccountTier } from '../types/sirix';
import { sirixClient } from '../api/client';
import { usePreferences } from './PreferencesContext';

interface AuthContextValue {
  isAuthenticated: boolean;
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
  const { syncTierWithPreferences } = usePreferences();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(true);
  const [userId, setUserId] = useState<string>('usr_sirix_institutional_01');
  const [accountTier, setAccountTier] = useState<AccountTier>('PRO');
  const [simulateDefensiveCash, setSimulateDefensiveCash] = useState<boolean>(false);

  const login = async (email: string, password: string, tier: AccountTier = 'PRO') => {
    const authRes = await sirixClient.login(email, password, tier);
    setUserId(authRes.user_id);
    setAccountTier(authRes.account_tier);
    syncTierWithPreferences(authRes.account_tier);
    setIsAuthenticated(true);
  };

  const enterSandbox = (tier: AccountTier = 'PRO') => {
    sirixClient.setSession(`sirix_sandbox_${Date.now()}`, tier);
    setAccountTier(tier);
    syncTierWithPreferences(tier);
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
    sirixClient.setSession(null, 'FREE');
    setIsAuthenticated(false);
  };

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
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
