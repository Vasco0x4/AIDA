/* eslint-disable react-refresh/only-export-components -- context hooks are the public API */
/**
 * Authentication Context
 * Manages JWT auth state, login, password change, and logout.
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  getStoredToken, getStoredUser, clearAuth, storeAuth, storeUser,
  login as apiLogin, verifyOtp as apiVerifyOtp,
  fetchMe, fetchSetupStatus, setupAdmin as apiSetupAdmin,
} from '../services/authService';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getStoredUser);
  const [token, setToken] = useState(getStoredToken);
  const [loading, setLoading] = useState(true);
  const [backendUnreachable, setBackendUnreachable] = useState(false);
  const [setupRequired, setSetupRequired] = useState(false);

  // On mount: check whether the platform needs initial setup, then validate
  // any stored token by fetching /auth/me.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const { setup_required } = await fetchSetupStatus();
        if (cancelled) return;
        setSetupRequired(setup_required);
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
    if (result.otpRequired) {
      setBackendUnreachable(false);
      return result;
    }
    setToken(result.token);
    setUser(result.user);
    setBackendUnreachable(false);
    window.dispatchEvent(new CustomEvent('aida:auth-loaded'));
    return result;
  }, []);

  const verifyOtp = useCallback(async (challengeId, code) => {
    const result = await apiVerifyOtp(challengeId, code);
    setToken(result.token);
    setUser(result.user);
    setBackendUnreachable(false);
    window.dispatchEvent(new CustomEvent('aida:auth-loaded'));
    return result;
  }, []);

  // SSO: consume an OIDC-issued access token (picked up from the /sso hash).
  const ssoLogin = useCallback(async (rawToken) => {
    storeAuth(rawToken, null);
    const freshUser = await fetchMe();
    storeUser(freshUser);
    setToken(rawToken);
    setUser(freshUser);
    setBackendUnreachable(false);
    window.dispatchEvent(new CustomEvent('aida:auth-loaded'));
    return freshUser;
  }, []);

  const completeSetup = useCallback(async (username, password, email) => {
    const result = await apiSetupAdmin(username, password, email);
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
      backendUnreachable,
      login, verifyOtp, logout, refreshUser, completeSetup, ssoLogin,
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
