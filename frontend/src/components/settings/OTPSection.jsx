/** Self-service optional TOTP enrollment and recovery for the signed-in user. */
import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, CheckCircle, Copy, KeyRound, RefreshCw, ShieldCheck, ShieldOff } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import {
  disableOtp, enableOtp, fetchMe, fetchOtpStatus, regenerateRecoveryCodes, setupOtp,
} from '../../services/authService';

const inputClass = 'w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 outline-none';

export default function OTPSection() {
  const { user, refreshUser } = useAuth();
  const [otpStatus, setOtpStatus] = useState({ enabled: false, recovery_codes_remaining: 0 });
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState(null);
  const [setup, setSetup] = useState(null);
  const [recoveryCodes, setRecoveryCodes] = useState([]);
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const isLocal = user?.auth_provider !== 'oidc';

  const loadStatus = useCallback(async () => {
    try {
      setOtpStatus(await fetchOtpStatus());
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load OTP status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const resetForm = () => {
    setMode(null);
    setSetup(null);
    setPassword('');
    setCode('');
    setError('');
  };

  const copyText = async (text, message) => {
    try {
      await navigator.clipboard.writeText(text);
      setNotice(message);
    } catch {
      setError('Clipboard copy failed; select and copy the value manually.');
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (mode === 'setup' && !setup) {
        setSetup(await setupOtp(password));
        setCode('');
      } else if (mode === 'setup') {
        const result = await enableOtp(password, code);
        setRecoveryCodes(result.recovery_codes);
        refreshUser(await fetchMe());
        await loadStatus();
        resetForm();
        setNotice('Two-factor authentication is enabled. Save these recovery codes now.');
      } else if (mode === 'regenerate') {
        const result = await regenerateRecoveryCodes(password, code);
        setRecoveryCodes(result.recovery_codes);
        await loadStatus();
        resetForm();
        setNotice('Recovery codes regenerated. Previous codes no longer work.');
      } else if (mode === 'disable') {
        await disableOtp(password, code);
        refreshUser(await fetchMe());
        await loadStatus();
        resetForm();
        setRecoveryCodes([]);
        setNotice('Two-factor authentication is disabled for your account.');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'OTP operation failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5 max-w-3xl">
      <div>
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5" /> Two-factor authentication (TOTP)
        </h2>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          Optional per-account protection compatible with authenticator apps using RFC 6238.
          Password and SSO sign-in both require a second factor after enrollment.
        </p>
      </div>

      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
            {loading ? 'Checking status…' : (otpStatus.enabled ? 'Enabled for your account' : 'Not enabled')}
          </p>
          {otpStatus.enabled && (
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              {otpStatus.recovery_codes_remaining} unused recovery codes remain.
            </p>
          )}
        </div>
        {!loading && !mode && (
          <div className="flex flex-wrap gap-2">
            {!otpStatus.enabled ? (
              <button onClick={() => { resetForm(); setMode('setup'); }} className="px-3 py-2 text-sm rounded-lg bg-primary-600 hover:bg-primary-700 text-white">
                Set up authenticator
              </button>
            ) : (
              <>
                <button onClick={() => { resetForm(); setMode('regenerate'); }} className="px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-200 flex items-center gap-2">
                  <RefreshCw className="w-4 h-4" /> New recovery codes
                </button>
                <button onClick={() => { resetForm(); setMode('disable'); }} className="px-3 py-2 text-sm rounded-lg border border-red-300 text-red-700 dark:border-red-800 dark:text-red-300 flex items-center gap-2">
                  <ShieldOff className="w-4 h-4" /> Disable
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {notice && (
        <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg text-sm text-green-700 dark:text-green-300 flex gap-2" role="status">
          <CheckCircle className="w-4 h-4 shrink-0" /> {notice}
        </div>
      )}
      {error && !mode && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg text-sm text-red-700 dark:text-red-300 flex gap-2" role="alert">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {mode && (
        <form onSubmit={handleSubmit} className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-5 space-y-4">
          <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
            {mode === 'setup' ? (setup ? 'Confirm authenticator' : 'Reauthenticate to set up OTP') :
              (mode === 'regenerate' ? 'Regenerate recovery codes' : 'Disable two-factor authentication')}
          </h3>
          {mode !== 'setup' && (
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Enter your {isLocal ? 'current password and ' : ''}authenticator code or an unused recovery code.
            </p>
          )}
          {isLocal && (
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Current password
              <input type="password" required autoComplete="current-password" value={password}
                     onChange={(e) => setPassword(e.target.value)} className={`${inputClass} mt-1`} />
            </label>
          )}
          {!isLocal && (
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              Your verified OIDC session is used for reauthentication.
            </p>
          )}

          {mode === 'setup' && setup && (
            <>
              <div className="grid sm:grid-cols-[220px_1fr] gap-5 items-start">
                <div className="bg-white p-3 rounded-lg border border-neutral-200 w-fit [&_svg]:w-48 [&_svg]:h-48"
                     dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
                <div className="space-y-3 min-w-0">
                  <p className="text-sm text-neutral-600 dark:text-neutral-300">
                    Scan the QR code with your authenticator, or enter the manual key. Then confirm the six-digit code.
                  </p>
                  <div>
                    <span className="block text-xs font-medium text-neutral-500 mb-1">Manual setup key</span>
                    <code className="block break-all text-sm p-2 rounded bg-neutral-100 dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100">{setup.secret}</code>
                  </div>
                  <button type="button" onClick={() => copyText(setup.otpauth_uri, 'otpauth URI copied.')}
                          className="text-xs text-primary-600 dark:text-primary-400 flex items-center gap-1">
                    <Copy className="w-3 h-3" /> Copy otpauth URI
                  </button>
                </div>
              </div>
            </>
          )}

          {(mode !== 'setup' || setup) && (
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Authenticator or recovery code
              <input type="text" required minLength={6} maxLength={64} autoComplete="one-time-code"
                     value={code} onChange={(e) => setCode(e.target.value)} className={`${inputClass} mt-1`}
                     placeholder="123456 or XXXXX-XXXXX-…" autoFocus />
            </label>
          )}

          {error && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg text-sm text-red-700 dark:text-red-300 flex gap-2" role="alert">
              <AlertCircle className="w-4 h-4 shrink-0" /> {error}
            </div>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={resetForm} className="px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600">Cancel</button>
            <button type="submit" disabled={busy} className="px-4 py-2 text-sm rounded-lg bg-primary-600 hover:bg-primary-700 text-white disabled:opacity-50">
              {busy ? 'Please wait…' : (mode === 'setup' ? (setup ? 'Enable OTP' : 'Generate QR code') :
                (mode === 'regenerate' ? 'Regenerate codes' : 'Disable OTP'))}
            </button>
          </div>
        </form>
      )}

      {recoveryCodes.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-5 space-y-4">
          <div>
            <h3 className="text-base font-semibold text-amber-900 dark:text-amber-100 flex items-center gap-2">
              <KeyRound className="w-5 h-5" /> Save your recovery codes
            </h3>
            <p className="text-sm text-amber-800 dark:text-amber-200 mt-1">
              They are shown only once. Each code authorizes one sign-in if your authenticator is unavailable.
            </p>
          </div>
          <div className="grid sm:grid-cols-2 gap-2">
            {recoveryCodes.map((recoveryCode) => (
              <code key={recoveryCode} className="px-3 py-2 rounded bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 select-all">
                {recoveryCode}
              </code>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={() => copyText(recoveryCodes.join('\n'), 'Recovery codes copied.')}
                    className="px-3 py-2 text-sm rounded-lg bg-primary-600 text-white flex items-center gap-2">
              <Copy className="w-4 h-4" /> Copy all codes
            </button>
            <button onClick={() => setRecoveryCodes([])} className="px-3 py-2 text-sm rounded-lg border border-amber-300 dark:border-amber-700">
              I saved them
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
