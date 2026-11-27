/**
 * Initial setup wizard.
 *
 * Shown only when the platform has zero users. Lets the very first visitor
 * create the admin account with credentials of their choice. Once any user
 * exists, the backend rejects /auth/setup with 403 and this page is no longer
 * reachable.
 *
 * The UI is reachable from the network, so the backend also asks for the
 * one-time setup code printed by `aida start`. The link it prints carries the
 * code in the URL fragment (#code=...), which never reaches the server.
 */
import { useState } from 'react';
import { User, Lock, Mail, AlertCircle, ShieldCheck, KeyRound } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

function codeFromUrl() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  return params.get('code') || '';
}

export default function Setup() {
  const { completeSetup, backendUnreachable, setupCodeRequired } = useAuth();
  const [setupCode, setSetupCode] = useState(codeFromUrl);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (password !== confirm) {
      setError('Password and confirmation do not match');
      return;
    }
    if (password.length < 7) {
      setError('Password must be at least 7 characters');
      return;
    }

    setSubmitting(true);
    try {
      await completeSetup(username, password, email || undefined, setupCode.trim() || undefined);
      // Don't leave the (now used) code in the address bar.
      if (window.location.hash) {
        window.history.replaceState(null, '', window.location.pathname + window.location.search);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Setup failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-neutral-50 dark:bg-neutral-900 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <ShieldCheck className="w-12 h-12 mx-auto mb-4 text-primary-600" />
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            Welcome to AIDA
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Create the first administrator account.
          </p>
        </div>

        <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-lg border border-neutral-200 dark:border-neutral-700 p-6">
          {backendUnreachable && (
            <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg text-sm text-amber-700 dark:text-amber-300">
              Backend unreachable. Check that the API is running.
            </div>
          )}

          {error && (
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {setupCodeRequired && (
              <div>
                <Field label="Setup code" icon={<KeyRound className="w-4 h-4" />}>
                  <input
                    type="text"
                    value={setupCode}
                    onChange={(e) => setSetupCode(e.target.value)}
                    required
                    autoComplete="off"
                    spellCheck={false}
                    className="w-full pl-10 pr-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 font-mono tracking-wider uppercase focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                    placeholder="ABCD-EFGH"
                  />
                </Field>
                <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                  Shown in the terminal where you started AIDA. Lost it? Run <code>aida status</code>.
                </p>
              </div>
            )}

            <Field label="Username" icon={<User className="w-4 h-4" />}>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                minLength={3}
                autoFocus
                className="w-full pl-10 pr-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                placeholder="admin"
              />
            </Field>

            <Field label="Email (optional)" icon={<Mail className="w-4 h-4" />}>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-10 pr-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                placeholder="you@example.com"
              />
            </Field>

            <Field label="Password (min 7 characters)" icon={<Lock className="w-4 h-4" />}>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={7}
                className="w-full pl-10 pr-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
              />
            </Field>

            <Field label="Confirm password" icon={<Lock className="w-4 h-4" />}>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                minLength={7}
                className="w-full pl-10 pr-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
              />
            </Field>

            <button
              type="submit"
              disabled={submitting}
              className="w-full py-2.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
            >
              {submitting ? 'Creating…' : 'Create admin account'}
            </button>
          </form>

          <p className="mt-4 text-xs text-neutral-500 dark:text-neutral-400 text-center">
            This screen only appears once. Add more users later from the Users page.
          </p>
        </div>
      </div>
    </div>
  );
}

function Field({ label, icon, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
        {label}
      </label>
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400">{icon}</span>
        {children}
      </div>
    </div>
  );
}
