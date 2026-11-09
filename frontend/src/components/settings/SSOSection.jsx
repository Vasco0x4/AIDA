/**
 * Settings → SSO: OIDC single sign-on configuration (admin only).
 * The client secret is write-only — leave blank to keep the stored one.
 */
import { useEffect, useState } from 'react';
import { KeyRound, Save } from 'lucide-react';
import api from '../../services/api';
import * as sso from '../../services/ssoService';

export default function SSOSection() {
  const [form, setForm] = useState({
    enabled: false, issuer: '', client_id: '', client_secret: '',
    default_role: 'viewer', redirect_base: '',
  });
  const [hasSecret, setHasSecret] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    sso.load()
      .then((cfg) => setForm((f) => ({
        ...f,
        enabled: cfg.enabled,
        issuer: cfg.issuer || '',
        client_id: cfg.client_id || '',
        default_role: cfg.default_role || 'viewer',
        redirect_base: cfg.redirect_base || '',
      })))
      .catch((e) => setError(e.response?.data?.detail || 'Failed to load SSO settings'));
  }, []);

  const save = async () => {
    setBusy(true);
    setStatus('');
    setError('');
    try {
      const cfg = await sso.save(form);
      setHasSecret(cfg.has_secret);
      setForm((f) => ({ ...f, enabled: cfg.enabled, client_secret: '' }));
      setStatus('Saved. The "Continue with SSO" button appears on the login screen when enabled.');
    } catch (e) {
      setError(e.response?.data?.detail || 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const input = 'w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 outline-none';

  return (
    <div className="space-y-4 max-w-2xl">
      <div>
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Single Sign-On (OIDC)</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Authorization-code flow with PKCE. Works with any OIDC provider (Keycloak, Entra ID,
          Google, Okta…). Users are provisioned on first login with the default role and can be
          promoted afterwards.
        </p>
      </div>

      <label className="flex items-center gap-2 text-sm font-medium text-neutral-800 dark:text-neutral-200">
        <input type="checkbox" checked={form.enabled}
               onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
               className="rounded border-neutral-300 dark:border-neutral-600" />
        Enable SSO
      </label>

      <div>
        <label className="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">Issuer URL</label>
        <input className={input} placeholder="https://sso.company.com/realms/main"
               value={form.issuer} onChange={(e) => setForm({ ...form, issuer: e.target.value })} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">Client ID</label>
          <input className={input} value={form.client_id}
                 onChange={(e) => setForm({ ...form, client_id: e.target.value })} />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">
            Client secret{' '}
            <span className="text-neutral-400 font-normal">
              (stored encrypted, blank = keep{hasSecret ? ' ✓ set' : ''})
            </span>
          </label>
          <input type="password" className={input} placeholder="••••••••"
                 value={form.client_secret} onChange={(e) => setForm({ ...form, client_secret: e.target.value })} />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">Default role for new SSO users</label>
          <select className={input} value={form.default_role}
                  onChange={(e) => setForm({ ...form, default_role: e.target.value })}>
            <option value="viewer">viewer (read-only)</option>
            <option value="auditor">auditor (operational)</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">
            Frontend base URL <span className="text-neutral-400 font-normal">(for post-login redirect)</span>
          </label>
          <input className={input} placeholder="http://localhost:5174"
                 value={form.redirect_base} onChange={(e) => setForm({ ...form, redirect_base: e.target.value })} />
        </div>
      </div>

      <div className="p-3 bg-neutral-50 dark:bg-neutral-800/60 border border-neutral-200 dark:border-neutral-700 rounded-lg text-xs text-neutral-600 dark:text-neutral-400">
        <KeyRound className="w-3.5 h-3.5 inline mr-1 -mt-0.5" />
        Redirect URI to register with your IdP:&nbsp;
        <code className="text-neutral-800 dark:text-neutral-200">
          {(api.defaults.baseURL || window.location.origin).replace(/\/api$/, '')}/api/auth/oidc/callback
        </code>
      </div>

      {error && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button onClick={save} disabled={busy}
                className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg disabled:opacity-50">
          <Save className="w-4 h-4" /> {busy ? 'Saving…' : 'Save SSO settings'}
        </button>
        {status && <span className="text-sm text-emerald-600 dark:text-emerald-400">{status}</span>}
      </div>
    </div>
  );
}
