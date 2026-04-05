/**
 * Authentication API service
 */
import apiClient from './api';

const TOKEN_KEY = 'aida_token';
const USER_KEY = 'aida_user';

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser() {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export function storeAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export async function login(username, password) {
  const res = await apiClient.post('/auth/login', { username, password });
  const { access_token, user } = res.data;
  storeAuth(access_token, user);
  return { token: access_token, user };
}

export async function register(username, password, email) {
  const body = { username, password };
  if (email) body.email = email;
  const res = await apiClient.post('/auth/register', body);
  const { access_token, user } = res.data;
  storeAuth(access_token, user);
  return { token: access_token, user };
}

export async function fetchMe() {
  const res = await apiClient.get('/auth/me');
  return res.data;
}

export async function fetchAuthStatus() {
  const res = await apiClient.get('/auth/status');
  return res.data;
}
