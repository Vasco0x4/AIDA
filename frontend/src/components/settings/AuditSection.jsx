import { utcDate } from '../../utils/utcDate';
/**
 * Settings → Audit: the platform's security audit trail (who did what, when,
 * from where). Admin-only surface (backend enforces it too).
 */
import { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, RefreshCw, Search, XCircle } from 'lucide-react';
import api from '../../services/api';

const ROWS = [
  { id: '', label: 'All actions' },
  { id: 'auth.', label: 'Auth / SSO' },
  { id: 'rbac.', label: 'Access denials' },
  { id: 'task.', label: 'Tasks' },
  { id: 'user.', label: 'User management' },
  { id: 'model.', label: 'AI models' },
  { id: 'api_key.', label: 'API keys' },
  { id: 'command.', label: 'Command approvals' },
  { id: 'knowledge.', label: 'Knowledge' },
  { id: 'runner.', label: 'Agent runner' },
];

export default function AuditSection() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [action, setAction] = useState('');
  const [success, setSuccess] = useState('');
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pageSize = 50;

  const load = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const params = { limit: pageSize, offset: page * pageSize };
      if (action) params.action = action;
      if (success !== '') params.success = success === 'ok';
      const { data } = await api.get('/audit', { params });
      setItems(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to load audit trail');
    } finally {
      setBusy(false);
    }
  }, [action, success, page]);

  useEffect(() => { load(); }, [load]);

  const fmt = (iso) => utcDate(iso).toLocaleString();

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Audit Trail</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Security-relevant actions across the platform ({total} events).
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
          <select value={action} onChange={(e) => { setAction(e.target.value); setPage(0); }}
                  className="pl-8 pr-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100">
            {ROWS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
        </div>
        <select value={success} onChange={(e) => { setSuccess(e.target.value); setPage(0); }}
                className="px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100">
          <option value="">Success &amp; failure</option>
          <option value="ok">Success only</option>
          <option value="fail">Failures only</option>
        </select>
        <button onClick={load} disabled={busy}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-200 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-700">
        <table className="min-w-full text-sm">
          <thead className="bg-neutral-50 dark:bg-neutral-800">
            <tr className="text-left text-neutral-600 dark:text-neutral-300">
              <th className="px-3 py-2 font-medium">Time</th>
              <th className="px-3 py-2 font-medium">Actor</th>
              <th className="px-3 py-2 font-medium">Action</th>
              <th className="px-3 py-2 font-medium">Resource</th>
              <th className="px-3 py-2 font-medium">IP</th>
              <th className="px-3 py-2 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {items.map((it) => (
              <tr key={it.id} className="text-neutral-800 dark:text-neutral-200 align-top">
                <td className="px-3 py-2 whitespace-nowrap text-neutral-500 dark:text-neutral-400">{fmt(it.created_at)}</td>
                <td className="px-3 py-2 whitespace-nowrap">{it.actor_username || '—'}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <span className="inline-flex items-center gap-1.5">
                    {it.success
                      ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      : <XCircle className="w-3.5 h-3.5 text-red-500" />}
                    {it.action}
                  </span>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">{it.resource_type ? `${it.resource_type} ${it.resource_id ?? ''}` : '—'}</td>
                <td className="px-3 py-2 whitespace-nowrap text-neutral-500 dark:text-neutral-400">{it.ip || '—'}</td>
                <td className="px-3 py-2 max-w-md break-words text-xs text-neutral-500 dark:text-neutral-400">
                  {Object.keys(it.detail || {}).length ? JSON.stringify(it.detail) : '—'}
                </td>
              </tr>
            ))}
            {items.length === 0 && !busy && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-neutral-400">No audit events</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-neutral-500 dark:text-neutral-400">
          Page {page + 1} · showing {items.length} of {total}
        </span>
        <div className="flex gap-2">
          <button disabled={page === 0 || busy} onClick={() => setPage((p) => p - 1)}
                  className="px-3 py-1.5 border border-neutral-300 dark:border-neutral-600 rounded-lg disabled:opacity-40 hover:bg-neutral-50 dark:hover:bg-neutral-700">
            Previous
          </button>
          <button disabled={(page + 1) * pageSize >= total || busy} onClick={() => setPage((p) => p + 1)}
                  className="px-3 py-1.5 border border-neutral-300 dark:border-neutral-600 rounded-lg disabled:opacity-40 hover:bg-neutral-50 dark:hover:bg-neutral-700">
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
