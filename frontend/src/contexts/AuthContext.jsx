/**
 * Authentication Context
 * Manages JWT auth state, auto-login, and logout
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  getStoredToken, getStoredUser, clearAuth,
  login as apiLogin, register as apiRegister,
  fetchAuthStatus,
} from '../services/authService';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getStoredUser);
  const [token, setToken] = useState(getStoredToken);
  const [authRequired, setAuthRequired] = useState(null); // null = loading
  const [loading, setLoading] = useState(true);

  // Check if auth is required (any users exist in DB)
  useEffect(() => {
    fetchAuthStatus()
      .then(({ auth_required }) => {
        setAuthRequired(auth_required);
        // If no auth required (no users), auto-pass
        if (!auth_required) {
          setLoading(false);
          return;
        }
        // If auth required but we have token, validate it
        if (auth_required && token) {
          setLoading(false);
        } else {
          setLoading(false);
        }
      })
      .catch(() => {
        // Backend unreachable — skip auth
        setAuthRequired(false);
        setLoading(false);
      });
  }, [token]);

  const login = useCallback(async (username, password) => {
    const result = await apiLogin(username, password);
    setToken(result.token);
    setUser(result.user);
    setAuthRequired(true);
    return result;
  }, []);

  const registerUser = useCallback(async (username, password, email) => {
    const result = await apiRegister(username, password, email);
    setToken(result.token);
    setUser(result.user);
    setAuthRequired(true);
    return result;
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setToken(null);
    setUser(null);
  }, []);

  const isAuthenticated = !authRequired || !!token;

  return (
    <AuthContext.Provider value={{
      user, token, loading,
      authRequired,
      isAuthenticated,
      login, register: registerUser, logout,
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
