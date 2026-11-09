/**
 * Users management page (admin only).
 */
import { useEffect, useState } from 'react';
import { Plus, Trash2, KeyRound, Power, PowerOff, ShieldOff } from 'lucide-react';
import {
  listUsers, createUser, updateUser, resetUserPassword, resetUserOtp, deleteUser,
} from '../services/userService';
import { useAuth } from '../contexts/AuthContext';

const ROLE_STYLES = {
  admin: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
  auditor: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  viewer: 'bg-neutral-100 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300',
};

export default function Users() {
  const { user: currentUser, refreshUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [resetTarget, setResetTarget] = useState(null);

  const reload = async () => {
    try {
      setLoading(true);
      setError('');
      setUsers(await listUsers());
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { reload(); }, []);

  const handleToggleActive = async (u) => {
    try {
      await updateUser(u.id, { is_active: !u.is_active });
      reload();
    } catch (err) {
      setError(err.response?.data?.detail || 'Update failed');
    }
  };

  const handleRoleChange = async (u, role) => {
    if (role === u.role) return;
    try {
      await updateUser(u.id, { role });
      reload();
    } catch (err) {
      setError(err.response?.data?.detail || 'Update failed');
      reload();
    }
  };

  const handleResetOtp = async (u) => {
    if (!confirm(`Reset two-factor authentication for "${u.username}"? This invalidates all recovery codes and pending challenges.`)) return;
    try {
      const updated = await resetUserOtp(u.id);
      if (u.id === currentUser?.id) refreshUser(updated);
      reload();
    } catch (err) {
      setError(err.response?.data?.detail || 'OTP reset failed');
    }
  };

  const handleDelete = async (u) => {
    if (!confirm(`Delete user "${u.username}"?`)) return;
    try {
      await deleteUser(u.id);
      reload();
    } catch (err) {
      setError(err.response?.data?.detail || 'Delete failed');
    }
  };

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">Users</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Manage accounts and permissions.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" /> New user
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-sm border border-neutral-200 dark:border-neutral-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 dark:bg-neutral-900/50 text-neutral-600 dark:text-neutral-400">
            <tr>
              <th className="text-left px-4 py-3">Username</th>
              <th className="text-left px-4 py-3">Email</th>
              <th className="text-left px-4 py-3">Role</th>
              <th className="text-left px-4 py-3">Status</th>
              <th className="text-right px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan="5" className="text-center py-8 text-neutral-500">Loading…</td></tr>
            )}
            {!loading && users.map((u) => {
              const isSelf = u.id === currentUser?.id;
              return (
                <tr key={u.id} className="border-t border-neutral-100 dark:border-neutral-700">
                  <td className="px-4 py-3 font-medium text-neutral-900 dark:text-neutral-100">
                    {u.username}{isSelf && <span className="ml-2 text-xs text-neutral-400">(you)</span>}
                  </td>
                  <td className="px-4 py-3 text-neutral-600 dark:text-neutral-400">{u.email || '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <select
                        value={u.role}
                        disabled={isSelf}
                        onChange={(e) => handleRoleChange(u, e.target.value)}
                        title={isSelf ? 'You cannot change your own role' : 'Change role'}
                        className={`px-2 py-1 border rounded text-xs font-medium bg-transparent focus:ring-2 focus:ring-primary-500 outline-none ${ROLE_STYLES[u.role] || ROLE_STYLES.viewer} border-neutral-300 dark:border-neutral-600 disabled:opacity-60`}
                      >
                        <option value="viewer">viewer · read-only</option>
                        <option value="auditor">auditor · operate</option>
                        <option value="admin">admin · full control</option>
                      </select>
                      {u.must_change_password && (
                        <span className="text-xs text-amber-600">must reset</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded text-xs ${u.is_active ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'}`}>
                        {u.is_active ? 'active' : 'disabled'}
                      </span>
                      {u.otp_enabled && (
                        <span className="px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">OTP on</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex gap-1">
                      <IconBtn onClick={() => handleToggleActive(u)} title={u.is_active ? 'Disable' : 'Enable'}>
                        {u.is_active ? <PowerOff className="w-4 h-4" /> : <Power className="w-4 h-4" />}
                      </IconBtn>
                      {u.otp_enabled && (
                        <IconBtn onClick={() => handleResetOtp(u)} title="Reset OTP and recovery codes">
                          <ShieldOff className="w-4 h-4" />
                        </IconBtn>
                      )}
                      <IconBtn onClick={() => setResetTarget(u)} title="Reset password">
                        <KeyRound className="w-4 h-4" />
                      </IconBtn>
                      <IconBtn onClick={() => handleDelete(u)} title="Delete" disabled={isSelf} danger>
                        <Trash2 className="w-4 h-4" />
                      </IconBtn>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); reload(); }}
        />
      )}
      {resetTarget && (
        <ResetPasswordModal
          user={resetTarget}
          onClose={() => setResetTarget(null)}
          onDone={() => { setResetTarget(null); reload(); }}
        />
      )}
    </div>
  );
}

function IconBtn({ onClick, children, title, danger, disabled }) {
  return (
    <button
      onClick={onClick}
      title={title}
      disabled={disabled}
      className={`p-2 rounded hover:bg-neutral-100 dark:hover:bg-neutral-700 disabled:opacity-30 disabled:cursor-not-allowed ${danger ? 'text-red-600 hover:text-red-700' : 'text-neutral-500 hover:text-neutral-700 dark:text-neutral-400'}`}
    >
      {children}
    </button>
  );
}

function CreateUserModal({ onClose, onCreated }) {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('auditor');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await createUser({ username, password, email: email || undefined, role });
      onCreated();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create user');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell title="Create user" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        {error && <div className="p-2 text-sm bg-red-50 text-red-700 rounded">{error}</div>}
        <Field label="Username">
          <input value={username} onChange={(e) => setUsername(e.target.value)} required minLength={3} className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 outline-none" />
        </Field>
        <Field label="Email (optional)">
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 outline-none" />
        </Field>
        <Field label="Initial password (min 7 chars)">
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={7} className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 outline-none" />
        </Field>
        <Field label="Role">
          <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 outline-none">
            <option value="viewer">viewer · read-only</option>
            <option value="auditor">auditor · operate</option>
            <option value="admin">admin · full control</option>
          </select>
        </Field>
        <p className="text-xs text-neutral-500">User will be required to change this password on first login.</p>
        <div className="flex gap-2 justify-end pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm rounded border border-neutral-300 dark:border-neutral-600">Cancel</button>
          <button type="submit" disabled={submitting} className="px-3 py-2 text-sm rounded bg-primary-600 hover:bg-primary-700 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
            {submitting ? 'Creating…' : 'Create'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

function ResetPasswordModal({ user, onClose, onDone }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await resetUserPassword(user.id, password);
      onDone();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to reset password');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell title={`Reset password — ${user.username}`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        {error && <div className="p-2 text-sm bg-red-50 text-red-700 rounded">{error}</div>}
        <Field label="New password (min 7 chars)">
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={7} className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary-500 outline-none" autoFocus />
        </Field>
        <p className="text-xs text-neutral-500">User will be required to change it on next login.</p>
        <div className="flex gap-2 justify-end pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm rounded border border-neutral-300 dark:border-neutral-600">Cancel</button>
          <button type="submit" disabled={submitting} className="px-3 py-2 text-sm rounded bg-primary-600 hover:bg-primary-700 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
            {submitting ? 'Saving…' : 'Reset'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

function ModalShell({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="bg-white dark:bg-neutral-800 rounded-xl shadow-xl border border-neutral-200 dark:border-neutral-700 w-full max-w-md p-5">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{label}</span>
      {children}
    </label>
  );
}
