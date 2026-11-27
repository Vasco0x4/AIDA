/**
 * Authentication Context
 * Manages JWT auth state, login, password change, and logout.
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  getStoredToken, getStoredUser, clearAuth, storeUser,
  login as apiLogin, fetchMe, fetchSetupStatus, setupAdmin as apiSetupAdmin,
} from '../services/authService';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getStoredUser);
  const [token, setToken] = useState(getStoredToken);
  const [loading, setLoading] = useState(true);
  const [backendUnreachable, setBackendUnreachable] = useState(false);
  const [setupRequired, setSetupRequired] = useState(false);
  const [setupCodeRequired, setSetupCodeRequired] = useState(false);

  // On mount: check whether the platform needs initial setup, then validate
  // any stored token by fetching /auth/me.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const { setup_required, setup_code_required } = await fetchSetupStatus();
        if (cancelled) return;
        setSetupRequired(setup_required);
        setSetupCodeRequired(!!setup_code_required);
        setBackendUnreachable(false);

        if (setup_required) {
          // No accounts yet — skip token validation, render setup wizard.
          setLoading(false);
          return;
        }

        if (!token) {
          setLoading(false);
          return;
        }

        try {
          const freshUser = await fetchMe();
          if (cancelled) return;
          setUser(freshUser);
          storeUser(freshUser);
        } catch (err) {
          if (cancelled) return;
          if (err?.response?.status === 401) {
            clearAuth();
            setToken(null);
            setUser(null);
          } else {
            setBackendUnreachable(true);
          }
        } finally {
          if (!cancelled) setLoading(false);
        }
      } catch {
        if (cancelled) return;
        setBackendUnreachable(true);
        setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [token]);

  const login = useCallback(async (username, password) => {
    const result = await apiLogin(username, password);
    setToken(result.token);
    setUser(result.user);
    setBackendUnreachable(false);
    window.dispatchEvent(new CustomEvent('aida:auth-loaded'));
    return result;
  }, []);

  const completeSetup = useCallback(async (username, password, email, setupCode) => {
    const result = await apiSetupAdmin(username, password, email, setupCode);
    setToken(result.token);
    setUser(result.user);
    setSetupRequired(false);
    setBackendUnreachable(false);
    window.dispatchEvent(new CustomEvent('aida:auth-loaded'));
    return result;
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setToken(null);
    setUser(null);
  }, []);

  // Listen for 401s emitted by the axios interceptor (token expired or
  // revoked while the app was running) and reset auth state without reloading.
  useEffect(() => {
    const onCleared = () => {
      setToken(null);
      setUser(null);
    };
    window.addEventListener('aida:auth-cleared', onCleared);
    return () => window.removeEventListener('aida:auth-cleared', onCleared);
  }, []);

  const refreshUser = useCallback((freshUser) => {
    setUser(freshUser);
    storeUser(freshUser);
  }, []);

  const isAuthenticated = !!token && !!user;
  const mustChangePassword = !!user?.must_change_password;

  return (
    <AuthContext.Provider value={{
      user, token, loading,
      isAuthenticated,
      mustChangePassword,
      setupRequired,
      setupCodeRequired,
      backendUnreachable,
      login, logout, refreshUser, completeSetup,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
