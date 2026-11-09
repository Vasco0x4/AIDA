/**
 * Login page — password and optional second-factor challenge. No public registration.
 */
import { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { User, Lock, AlertCircle, LogIn, ShieldCheck } from 'lucide-react';
import api from '../services/api';

export default function Login() {
  const { login, verifyOtp, ssoLogin, backendUnreachable } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [challengeId, setChallengeId] = useState(null);
  const [otpCode, setOtpCode] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sso, setSso] = useState({ enabled: false, provider: null });

  // OIDC SSO returns either a full token or a short-lived OTP challenge.
  useEffect(() => {
    (async () => {
      const hash = window.location.hash || '';
      const challenge = hash.match(/[ #&]challenge=([^&]+)/);
      if (challenge) {
        window.history.replaceState(null, '', window.location.pathname);
        setChallengeId(decodeURIComponent(challenge[1]));
      }
      const tok = hash.match(/[ #&]token=([^&]+)/);
      if (tok) {
        window.history.replaceState(null, '', window.location.pathname);
        try {
          await ssoLogin(decodeURIComponent(tok[1]));
          return; // AuthGate takes over on success
        } catch {
          setError('SSO sign-in failed — try username/password or contact an admin.');
        }
      }
      const err = hash.match(/[ #&]error=([^&]+)/);
      if (err) {
        window.history.replaceState(null, '', window.location.pathname);
        setError(decodeURIComponent(err[1]));
      }
      try {
        const { data } = await api.get('/auth/oidc/status');
        setSso(data);
      } catch { /* SSO status is optional chrome */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      if (challengeId) {
        await verifyOtp(challengeId, otpCode);
      } else {
        const result = await login(username, password);
        if (result.otpRequired) {
          setChallengeId(result.challengeId);
          setPassword('');
          setOtpCode('');
        }
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Authentication failed');
    } finally {
      setSubmitting(false);
    }
  };

  const cancelChallenge = () => {
    setChallengeId(null);
    setOtpCode('');
    setError('');
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-neutral-50 dark:bg-neutral-900 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <img
            src="/assets/aida-logo.png"
            alt="AIDA Logo"
            className="w-16 h-16 mx-auto mb-4 object-contain"
          />
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">AIDA</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            AI-Driven Security Assessment
          </p>
        </div>

        <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-lg border border-neutral-200 dark:border-neutral-700 p-6">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
            {challengeId ? 'Two-factor authentication' : 'Sign In'}
          </h2>

          {backendUnreachable && (
            <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
              <p className="text-sm text-amber-700 dark:text-amber-300">
                Backend unreachable. Check that the API is running.
              </p>
            </div>
          )}

          {error && (
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-2" role="alert">
              <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {challengeId ? (
              <div>
                <label htmlFor="otp-code" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  Authenticator or recovery code
                </label>
                <div className="relative">
                  <ShieldCheck className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
                  <input
                    id="otp-code"
                    type="text"
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value)}
                    required
                    minLength={6}
                    maxLength={64}
                    autoComplete="one-time-code"
                    className="w-full pl-10 pr-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                    placeholder="123456 or XXXXX-XXXXX-…"
                    autoFocus
                  />
                </div>
                <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
                  The challenge expires after 5 minutes. A recovery code can be used only once.
                </p>
              </div>
            ) : (
              <>
                <div>
                  <label htmlFor="login-username" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    Username
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
                    <input
                      id="login-username"
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      required
                      minLength={3}
                      autoComplete="username"
                      className="w-full pl-10 pr-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                      placeholder="Enter username"
                      autoFocus
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="login-password" className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
                    <input
                      id="login-password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      autoComplete="current-password"
                      className="w-full pl-10 pr-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                      placeholder="Password"
                    />
                  </div>
                </div>
              </>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full py-2.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
            >
              {submitting ? 'Please wait...' : (challengeId ? 'Verify and sign in' : 'Sign In')}
            </button>
            {challengeId && (
              <button
                type="button"
                onClick={cancelChallenge}
                className="w-full py-2 text-sm text-neutral-600 dark:text-neutral-300 hover:text-primary-600"
              >
                Back to password sign-in
              </button>
            )}
          </form>

          {!challengeId && sso.enabled && (
            <>
              <div className="my-4 flex items-center gap-3 text-xs text-neutral-400 dark:text-neutral-500">
                <span className="flex-1 h-px bg-neutral-200 dark:bg-neutral-700" />
                or
                <span className="flex-1 h-px bg-neutral-200 dark:bg-neutral-700" />
              </div>
              <a
                href={`${api.defaults.baseURL}/auth/oidc/login`}
                className="w-full py-2.5 flex items-center justify-center gap-2 border border-neutral-300 dark:border-neutral-600 hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-200 font-medium rounded-lg transition-colors"
              >
                <LogIn className="w-4 h-4" />
                Continue with SSO{sso.provider ? ` (${sso.provider})` : ''}
              </a>
            </>
          )}

          {!challengeId && (
            <div className="mt-4 text-center">
              <a
                href="https://github.com/Vasco0x4/AIDA/blob/main/Docs/RESET_PASSWORD.md"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-neutral-500 hover:text-primary-600 dark:text-neutral-400 dark:hover:text-primary-400 transition-colors"
              >
                Forgot password?
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
