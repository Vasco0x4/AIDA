/**
 * User management API service (admin only).
 */
import apiClient from './api';

export async function listUsers() {
  const res = await apiClient.get('/users');
  return res.data;
}

export async function createUser({ username, password, email, role }) {
  const body = { username, password, role: role || 'user' };
  if (email) body.email = email;
  const res = await apiClient.post('/users', body);
  return res.data;
}

export async function updateUser(id, patch) {
  const res = await apiClient.patch(`/users/${id}`, patch);
  return res.data;
}

export async function resetUserPassword(id, newPassword) {
  const res = await apiClient.post(`/users/${id}/reset-password`, {
    new_password: newPassword,
  });
  return res.data;
}

export async function resetUserOtp(id) {
  const res = await apiClient.post(`/users/${id}/reset-otp`);
  return res.data;
}

export async function deleteUser(id) {
  await apiClient.delete(`/users/${id}`);
}
