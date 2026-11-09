/**
 * Settings → AI Models tab.
 *
 * Manage model backends (OpenRouter / Kimi / GLM / OpenAI / DeepSeek / custom):
 * add, edit, set default, test connectivity, delete. API keys are write-only —
 * the server returns only a masked hint, never the key.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Cpu, Plus, Star, Trash2, Zap, Check, X, Loader2, AlertTriangle } from 'lucide-react';
import aiModelService from '../../services/aiModelService';

const EMPTY = { name: '', provider: 'openrouter', model: '', base_url: '', api_key: '', is_default: false, enabled: true };

export default function AIModelsSection() {
  const [presets, setPresets] = useState([]);
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(EMPTY);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [testing, setTesting] = useState({});   // id -> bool
  const [testResult, setTestResult] = useState({}); // id -> {ok,message,latency_ms}

  const load = useCallback(async () => {
    try {
      const [p, m] = await Promise.all([aiModelService.getPresets(), aiModelService.list()]);
      setPresets(p);
      setModels(m);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const presetFor = (key) => presets.find((p) => p.key === key);

  const onProviderChange = (key) => {
    const p = presetFor(key);
    setForm((f) => ({
      ...f,
      provider: key,
      base_url: p && p.base_url ? p.base_url : '',
      model: f.model || (p ? p.example_model : ''),
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!form.name.trim() || !form.model.trim()) { setError('Name and model are required'); return; }
    setSaving(true);
    try {
      await aiModelService.create(form);
      setForm(EMPTY);
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setSaving(false);
    }
  };

  const setDefault = async (m) => { await aiModelService.update(m.id, { is_default: true }); load(); };
  const remove = async (m) => { if (confirm(`Delete "${m.name}"?`)) { await aiModelService.remove(m.id); load(); } };

  const runTest = async (m) => {
    setTesting((t) => ({ ...t, [m.id]: true }));
    setTestResult((r) => ({ ...r, [m.id]: undefined }));
    try {
      const res = await aiModelService.test(m.id);
      setTestResult((r) => ({ ...r, [m.id]: res }));
    } catch (err) {
      setTestResult((r) => ({ ...r, [m.id]: { ok: false, message: err.response?.data?.detail || err.message } }));
    } finally {
      setTesting((t) => ({ ...t, [m.id]: false }));
    }
  };

  const field = 'w-full rounded-md border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-800 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-sky-500';

  if (loading) return <div className="text-neutral-400 py-8">Loading models…</div>;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-neutral-800 dark:text-neutral-100 flex items-center gap-2">
            <Cpu size={18} /> AI Models
          </h2>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Model backends the autonomous agent uses. The default runs tasks with no explicit model.</p>
        </div>
        <button onClick={() => { setForm(EMPTY); setShowForm((s) => !s); }} className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-md bg-sky-600 text-white hover:bg-sky-700">
          <Plus size={16} /> Add model
        </button>
      </div>

      {showForm && (
        <form onSubmit={submit} className="rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 space-y-3 bg-neutral-50 dark:bg-neutral-900/40">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-neutral-600 dark:text-neutral-300">Label *</label>
              <input className={field} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="OpenRouter-Kimi" />
            </div>
            <div>
              <label className="text-xs font-medium text-neutral-600 dark:text-neutral-300">Provider</label>
              <select className={field} value={form.provider} onChange={(e) => onProviderChange(e.target.value)}>
                {presets.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-neutral-600 dark:text-neutral-300">Model id *</label>
              <input className={field} value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} placeholder={presetFor(form.provider)?.example_model || 'model-id'} />
            </div>
            <div>
              <label className="text-xs font-medium text-neutral-600 dark:text-neutral-300">Base URL {form.provider === 'custom' ? '*' : '(preset)'}</label>
              <input className={field} value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://…/v1" />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-neutral-600 dark:text-neutral-300">API key</label>
            <input type="password" className={field} value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} placeholder="sk-…" autoComplete="new-password" />
            <p className="text-[10px] text-neutral-400 mt-0.5">Stored encrypted at rest. Never shown again.</p>
          </div>
          <label className="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-300">
            <input type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} />
            Set as default
          </label>
          {error && <p className="text-sm text-rose-600 inline-flex items-center gap-1"><AlertTriangle size={14} /> {error}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowForm(false)} className="px-3 py-2 text-sm rounded-md border border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm rounded-md bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-50">{saving ? 'Saving…' : 'Save'}</button>
          </div>
        </form>
      )}

      <div className="space-y-2">
        {models.length === 0 && <p className="text-sm text-neutral-400 py-4">No models configured yet. Add one to enable autonomous runs.</p>}
        {models.map((m) => {
          const res = testResult[m.id];
          return (
            <div key={m.id} className="rounded-lg border border-neutral-200 dark:border-neutral-700 p-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-neutral-800 dark:text-neutral-100 truncate">{m.name}</span>
                  {m.is_default && <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 inline-flex items-center gap-1"><Star size={10} /> default</span>}
                  {!m.has_api_key && <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">no key</span>}
                </div>
                <p className="text-xs text-neutral-500 dark:text-neutral-400 font-mono truncate">{m.provider} · {m.model} · {m.base_url} · key {m.api_key_masked || '—'}</p>
                {res && (
                  <p className={`text-xs mt-1 inline-flex items-center gap-1 ${res.ok ? 'text-emerald-600' : 'text-rose-600'}`}>
                    {res.ok ? <Check size={12} /> : <X size={12} />} {res.message}{res.latency_ms ? ` (${res.latency_ms}ms)` : ''}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <button onClick={() => runTest(m)} disabled={testing[m.id]} className="p-2 rounded-md text-neutral-500 hover:text-sky-600 hover:bg-neutral-100 dark:hover:bg-neutral-800" title="Test connection">
                  {testing[m.id] ? <Loader2 size={15} className="animate-spin" /> : <Zap size={15} />}
                </button>
                {!m.is_default && (
                  <button onClick={() => setDefault(m)} className="p-2 rounded-md text-neutral-500 hover:text-amber-500 hover:bg-neutral-100 dark:hover:bg-neutral-800" title="Set default"><Star size={15} /></button>
                )}
                <button onClick={() => remove(m)} className="p-2 rounded-md text-neutral-500 hover:text-rose-500 hover:bg-neutral-100 dark:hover:bg-neutral-800" title="Delete"><Trash2 size={15} /></button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
