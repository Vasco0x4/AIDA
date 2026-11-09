import { utcDate } from '../../utils/utcDate';
import { useEffect, useState } from 'react';
import {
  Key,
  Copy,
  Trash2,
  Plus,
  Shield,
  AlertTriangle,
  CheckCircle,
  AlertCircle,
  Save,
} from '../icons';
import {
  listApiKeys,
  createApiKey,
  revokeApiKey,
  getMcpSetting,
  updateMcpSetting,
} from '../../services/apiKeyService';
import {
  MCP_CLIENT_ADAPTERS,
  buildClientSnippet,
  getMcpClientAdapter,
  resolveMcpUrl,
} from '../../services/mcpClients';

const POLICY_OPTIONS = [
  { value: 'localhost', label: 'Localhost only' },
  { value: 'lan', label: 'LAN (private + loopback)' },
  { value: 'any', label: 'Any (requires TLS in front)' },
];

function formatDate(iso) {
  if (!iso) return '—';
  try {
    return utcDate(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function McpAccessSection() {
  const [enabled, setEnabled] = useState(false);
  const [policy, setPolicy] = useState('localhost');
  const [savedPolicy, setSavedPolicy] = useState('localhost');
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [creating, setCreating] = useState(false);

  const [revealedKey, setRevealedKey] = useState(null);
  const [clientTab, setClientTab] = useState('claude-code');

  useEffect(() => {
    loadAll();
  }, []);

  const showMessage = (type, text) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  async function loadAll() {
    setLoading(true);
    try {
      const [enabledSetting, policySetting, list] = await Promise.all([
        getMcpSetting('mcp_http_enabled'),
        getMcpSetting('mcp_http_network_policy'),
        listApiKeys(),
      ]);
      setEnabled(enabledSetting.value === 'true');
      setPolicy(policySetting.value);
      setSavedPolicy(policySetting.value);
      setKeys(list);
    } catch (err) {
      showMessage('error', err.response?.data?.detail || 'Failed to load MCP settings');
    } finally {
      setLoading(false);
    }
  }

  async function toggleEnabled(next) {
    setBusy(true);
    try {
      await updateMcpSetting('mcp_http_enabled', next ? 'true' : 'false');
      setEnabled(next);
      showMessage('success', `HTTP MCP ${next ? 'enabled' : 'disabled'}`);
    } catch (err) {
      showMessage('error', err.response?.data?.detail || 'Failed to update setting');
    } finally {
      setBusy(false);
    }
  }

  async function savePolicy() {
    setBusy(true);
    try {
      await updateMcpSetting('mcp_http_network_policy', policy);
      setSavedPolicy(policy);
      showMessage('success', 'Network policy saved');
    } catch (err) {
      showMessage('error', err.response?.data?.detail || 'Failed to save policy');
    } finally {
      setBusy(false);
    }
  }

  async function handleCreate() {
    const trimmed = newKeyName.trim();
    if (!trimmed) return;
    setCreating(true);
    try {
      const created = await createApiKey(trimmed);
      setRevealedKey(created);
      setShowCreateModal(false);
      setNewKeyName('');
      const list = await listApiKeys();
      setKeys(list);
    } catch (err) {
      showMessage('error', err.response?.data?.detail || 'Failed to create key');
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(id) {
    if (!window.confirm('Revoke this API key? Any client using it will stop working.')) return;
    try {
      await revokeApiKey(id);
      const list = await listApiKeys();
      setKeys(list);
      showMessage('success', 'Key revoked');
    } catch (err) {
      showMessage('error', err.response?.data?.detail || 'Failed to revoke key');
    }
  }

  function copyText(text) {
    navigator.clipboard.writeText(text).then(
      () => showMessage('success', 'Copied to clipboard'),
      () => showMessage('error', 'Clipboard copy failed')
    );
  }

  function mcpUrl() {
    return resolveMcpUrl(savedPolicy, {
      configuredUrl: import.meta.env.VITE_MCP_URL || '',
      port: import.meta.env.VITE_MCP_PORT || '8000',
    });
  }

  function clientSnippet(key) {
    return buildClientSnippet(clientTab, mcpUrl(), key.full_key);
  }

  const policyDirty = policy !== savedPolicy;
  const needsBindWarning = policy !== 'localhost';

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-1 flex items-center gap-2">
          <Shield className="w-4 h-4" /> MCP HTTP Access
        </h2>
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-4">
          Expose the MCP server over HTTP so remote AI clients can connect with a Bearer token.
          Disabled by default.
        </p>
      </div>

      {message && (
        <div
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${
            message.type === 'success'
              ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
              : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
          }`}
        >
          {message.type === 'success' ? (
            <CheckCircle className="w-3 h-3" />
          ) : (
            <AlertCircle className="w-3 h-3" />
          )}
          <span>{message.text}</span>
        </div>
      )}

      {/* Enable toggle + endpoint info */}
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
              Enable HTTP MCP transport
            </h3>
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              Endpoint: <code className="font-mono">{mcpUrl()}</code>
            </p>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={enabled}
              disabled={loading || busy}
              onChange={(e) => toggleEnabled(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-9 h-5 bg-neutral-200 peer-focus:outline-none rounded-full peer dark:bg-neutral-700 peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary-600" />
          </label>
        </div>
      </div>

      {/* Network policy */}
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
            Network policy
          </h3>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Which clients are accepted by <code className="font-mono">/mcp</code>.
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <select
            value={policy}
            onChange={(e) => setPolicy(e.target.value)}
            className="text-xs px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100"
          >
            {POLICY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <button
            onClick={savePolicy}
            disabled={!policyDirty || busy}
            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors flex items-center gap-1 disabled:opacity-50"
          >
            <Save className="w-3 h-3" /> Save
          </button>
        </div>
        {needsBindWarning && (
          <div className="flex gap-2 items-start text-xs px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span>
              To actually receive LAN/public traffic, set{' '}
              <code className="font-mono">BACKEND_BIND_HOST=0.0.0.0</code> in your{' '}
              <code className="font-mono">.env</code> and restart the backend. The application-level
              policy above is enforced regardless.
            </span>
          </div>
        )}
      </div>

      {/* Keys table */}
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <Key className="w-4 h-4" /> API keys
          </h3>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors flex items-center gap-1"
          >
            <Plus className="w-3 h-3" /> Create key
          </button>
        </div>

        {loading ? (
          <div className="text-xs text-neutral-500">Loading…</div>
        ) : keys.length === 0 ? (
          <div className="text-xs text-neutral-500">
            No keys yet. Create one to let an HTTP MCP client connect.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] font-semibold text-neutral-500 uppercase border-b border-neutral-200 dark:border-neutral-700">
                  <th className="py-2">Name</th>
                  <th className="py-2">Prefix</th>
                  <th className="py-2">Created</th>
                  <th className="py-2">Last used</th>
                  <th className="py-2">Status</th>
                  <th className="py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 dark:divide-neutral-700">
                {keys.map((k) => (
                  <tr key={k.id}>
                    <td className="py-2 text-neutral-900 dark:text-neutral-100">{k.name}</td>
                    <td className="py-2 font-mono text-neutral-600 dark:text-neutral-400">
                      {k.key_prefix}…
                    </td>
                    <td className="py-2 text-neutral-500">{formatDate(k.created_at)}</td>
                    <td className="py-2 text-neutral-500">{formatDate(k.last_used_at)}</td>
                    <td className="py-2">
                      {k.revoked_at ? (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400">
                          Revoked
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400">
                          Active
                        </span>
                      )}
                    </td>
                    <td className="py-2 text-right">
                      {!k.revoked_at && (
                        <button
                          onClick={() => handleRevoke(k.id)}
                          className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-md text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                        >
                          <Trash2 className="w-3 h-3" /> Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create-key modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl p-6 w-full max-w-md">
            <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-2">
              New API key
            </h3>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-4">
              Pick a memorable name, e.g. <em>Claude Code — laptop</em>.
            </p>
            <input
              autoFocus
              type="text"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="Key name"
              className="w-full text-sm px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newKeyName.trim()) handleCreate();
              }}
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  setNewKeyName('');
                }}
                className="px-3 py-1.5 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={creating || !newKeyName.trim()}
                className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white disabled:opacity-50"
              >
                {creating ? 'Creating…' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reveal-key modal */}
      {revealedKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl p-6 w-full max-w-2xl space-y-4">
            <div>
              <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
                Key created
              </h3>
              <p className="text-xs text-amber-700 dark:text-amber-400 mt-1 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" /> Save it now — you won't see it again.
              </p>
            </div>

            <div className="bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-md p-3 flex items-center justify-between gap-2">
              <code className="text-xs font-mono break-all text-neutral-900 dark:text-neutral-100">
                {revealedKey.full_key}
              </code>
              <button
                onClick={() => copyText(revealedKey.full_key)}
                className="shrink-0 p-1.5 rounded hover:bg-neutral-200 dark:hover:bg-neutral-700"
                title="Copy"
              >
                <Copy className="w-3.5 h-3.5" />
              </button>
            </div>

            <div>
              <div className="flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-700 mb-2">
                {MCP_CLIENT_ADAPTERS.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setClientTab(t.id)}
                    className={`px-3 py-1.5 text-xs border-b-2 ${
                      clientTab === t.id
                        ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                        : 'border-transparent text-neutral-500'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-2">
                {getMcpClientAdapter(clientTab).description}
              </p>
              <div className="bg-neutral-900 text-neutral-100 rounded-md p-3 relative">
                <pre className="text-[11px] font-mono whitespace-pre-wrap break-all">
                  {clientSnippet(revealedKey)}
                </pre>
                <button
                  onClick={() => copyText(clientSnippet(revealedKey))}
                  className="absolute top-2 right-2 p-1.5 rounded bg-neutral-800 hover:bg-neutral-700"
                  title="Copy snippet"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setRevealedKey(null)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default McpAccessSection;
