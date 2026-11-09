/**
 * SSO (OIDC) settings persistence via the dedicated admin endpoint.
 * The client secret is write-only — it never comes back, just `has_secret`.
 */
import api from './api';

export async function load() {
  const { data } = await api.get('/sso/config');
  return data;
}

export async function save({ enabled, issuer, client_id, client_secret, default_role, redirect_base }) {
  const { data } = await api.post('/sso/config', {
    enabled, issuer, client_id, client_secret, default_role, redirect_base,
  });
  return data;
}
