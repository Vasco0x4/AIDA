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

export function storeUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export async function login(username, password) {
  const res = await apiClient.post('/auth/login', { username, password });
  if (res.data.otp_required) {
    return {
      otpRequired: true,
      challengeId: res.data.challenge_id,
      user: res.data.user,
    };
  }
  const { access_token, user } = res.data;
  storeAuth(access_token, user);
  return { token: access_token, user };
}

export async function verifyOtp(challengeId, code) {
  const res = await apiClient.post('/auth/otp/verify', {
    challenge_id: challengeId,
    code: code.trim(),
  });
  const { access_token, user } = res.data;
  storeAuth(access_token, user);
  return { token: access_token, user };
}

export async function fetchOtpStatus() {
  const res = await apiClient.get('/auth/otp/status');
  return res.data;
}

export async function setupOtp(password) {
  const res = await apiClient.post('/auth/otp/setup', password ? { password } : {});
  return res.data;
}

export async function enableOtp(password, code) {
  const res = await apiClient.post('/auth/otp/enable', {
    ...(password ? { password } : {}), code: code.trim(),
  });
  return res.data;
}

export async function regenerateRecoveryCodes(password, code) {
  const res = await apiClient.post('/auth/otp/recovery-codes', {
    ...(password ? { password } : {}), code: code.trim(),
  });
  return res.data;
}

export async function disableOtp(password, code) {
  const res = await apiClient.post('/auth/otp/disable', {
    ...(password ? { password } : {}), code: code.trim(),
  });
  return res.data;
}

export async function fetchSetupStatus() {
  const res = await apiClient.get('/auth/setup-status');
  return res.data; // { setup_required: bool }
}

export async function setupAdmin(username, password, email) {
  const body = { username, password };
  if (email) body.email = email;
  const res = await apiClient.post('/auth/setup', body);
  const { access_token, user } = res.data;
  storeAuth(access_token, user);
  return { token: access_token, user };
}

export async function fetchMe() {
  const res = await apiClient.get('/auth/me');
  return res.data;
}

export async function changePassword(currentPassword, newPassword) {
  const res = await apiClient.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  });
  storeUser(res.data);
  return res.data;
}
