/**
 * Settings → Agents (E3): the autonomous agent pool's reliability controls.
 *
 * Concurrency, per-target rate limit, default token budget, model fallback
 * chain, runner pause/resume and the GLOBAL KILL SWITCH. Admin-only surface
 * (the backend enforces it too).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle, CheckCircle, ChevronDown, ChevronUp, Gauge, OctagonX,
  Play, Pause, RefreshCw, Save, Target, Trash2,
} from 'lucide-react';
import taskService from '../../services/taskService';
import aiModelService from '../../services/aiModelService';

const EMPTY = {
  max_concurrency: 2, target_min_interval: 60, max_steps: 500, token_budget: 0,
  fallback_chain: [], goal_mode: true, max_auto_continuations: 2,
  goal_judge_max_cont: 3,
};

export default function AgentOpsSection() {
  const [status, setStatus] = useState(null);   // { enabled, active, config }
  const [form, setForm] = useState(EMPTY);
  const [models, setModels] = useState([]);
  const [busy, setBusy] = useState(false);
  const [killing, setKilling] = useState(false);
  const [message, setMessage] = useState(null);
  // Last manual (non-unlimited) goal limits — restored when "no limits" is
  // switched back off, so toggling it never clobbers custom values.
  const limitsBackup = useRef({ auto: 2, judge: 3 });

  const toggleNoLimits = (on) => {
    if (on) {
      limitsBackup.current = {
        auto: form.max_auto_continuations >= 0 ? form.max_auto_continuations : 2,
        judge: form.goal_judge_max_cont >= 0 ? form.goal_judge_max_cont : 3,
      };
      setForm({ ...form, max_auto_continuations: -1, goal_judge_max_cont: -1 });
    } else {
      setForm({ ...form, ...limitsBackup.current });
    }
  };

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [runner, modelList] = await Promise.all([
        taskService.getRunner(),
        aiModelService.list().catch(() => []),
      ]);
      setStatus(runner);
      setForm(runner.config || EMPTY);
      setModels(modelList);
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || 'Failed to load agent pool state' });
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const flash = (type, text, ms = 4000) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), ms);
  };

  const save = async () => {
    if (form.max_concurrency < 1 || form.max_concurrency > 8) {
      flash('error', 'Max concurrent agents must be between 1 and 8');
      return;
    }
    if (form.target_min_interval < 0 || form.token_budget < 0) {
      flash('error', 'Intervals and budgets cannot be negative');
      return;
    }
    if (!form.max_steps || form.max_steps < 1 || form.max_steps > 1000000) {
      flash('error', 'Max steps must be between 1 and 1000000');
      return;
    }
    if (form.max_auto_continuations < -1 || form.max_auto_continuations > 10
        || form.goal_judge_max_cont < -1 || form.goal_judge_max_cont > 10) {
      flash('error', 'Goal-mode limits must be between -1 (unlimited) and 10');
      return;
    }
    setBusy(true);
    try {
      const cfg = await taskService.setRunnerConfig(form);
      setForm(cfg);
      flash('success', 'Agent pool config saved — applies immediately');
    } catch (e) {
      flash('error', e.response?.data?.detail || 'Failed to save config');
    } finally {
      setBusy(false);
    }
  };

  const toggleRunner = async () => {
    setBusy(true);
    try {
      await taskService.setRunner(!status.enabled);
      await load();
      flash('success', !status.enabled ? 'Runner resumed' : 'Runner paused — queued tasks wait');
    } catch (e) {
      flash('error', e.response?.data?.detail || 'Failed to toggle runner');
    } finally {
      setBusy(false);
    }
  };

  const kill = async () => {
    const n = status.active || 0;
    if (!confirm(`GLOBAL KILL SWITCH\n\nAbort ${n} running agent${n === 1 ? '' : 's'} NOW and mark their tasks failed? This cannot be undone.`)) return;
    setKilling(true);
    try {
      const res = await taskService.killRunner();
      flash('success', `Killed ${res.killed} agent${res.killed === 1 ? '' : 's'}.`);
      await load();
    } catch (e) {
      flash('error', e.response?.data?.detail || 'Kill switch failed');
    } finally {
      setKilling(false);
    }
  };

  // Fallback chain manipulation
  const addToChain = (id) => {
    if (!id || form.fallback_chain.includes(id)) return;
    setForm({ ...form, fallback_chain: [...form.fallback_chain, id] });
  };
  const moveInChain = (idx, dir) => {
    const chain = [...form.fallback_chain];
    const j = idx + dir;
    if (j < 0 || j >= chain.length) return;
    [chain[idx], chain[j]] = [chain[j], chain[idx]];
    setForm({ ...form, fallback_chain: chain });
  };
  const removeFromChain = (idx) => {
    setForm({ ...form, fallback_chain: form.fallback_chain.filter((_, i) => i !== idx) });
  };

  const modelById = Object.fromEntries(models.map((m) => [m.id, m]));
  const available = models.filter((m) => !form.fallback_chain.includes(m.id));
  const dirty = status && JSON.stringify(form) !== JSON.stringify(status.config);

  const input = 'w-24 px-2 py-1.5 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded text-sm focus:outline-none focus:ring-2 focus:ring-primary-500';

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Agent Pool</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Reliability controls for the autonomous agent runner (E3).
        </p>
      </div>

      {message && (
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${message.type === 'success'
          ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
          : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'}`}>
          {message.type === 'success' ? <CheckCircle className="w-3.5 h-3.5 shrink-0" /> : <AlertCircle className="w-3.5 h-3.5 shrink-0" />}
          <span>{message.text}</span>
        </div>
      )}

      {/* Runner state + kill switch */}
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Gauge className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
            <div>
              <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                Runner {status ? (status.enabled ? 'active' : 'paused') : '…'}
                {status && status.active > 0 && (
                  <span className="ml-2 text-xs text-amber-600 dark:text-amber-400">
                    {status.active} agent{status.active === 1 ? '' : 's'} in flight
                  </span>
                )}
              </div>
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                {status?.enabled
                  ? 'The pool picks up queued tasks within seconds.'
                  : 'Paused — queued tasks wait until the runner is resumed.'}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={load} disabled={busy}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-200 disabled:opacity-50">
              <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} /> Refresh
            </button>
            <button onClick={toggleRunner} disabled={busy || !status}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50">
              {status?.enabled ? <><Pause className="w-4 h-4" /> Pause</> : <><Play className="w-4 h-4" /> Resume</>}
            </button>
            <button onClick={kill} disabled={killing || !status || status.active === 0}
              title="Cancel every running agent and mark its task failed"
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg border border-rose-300 dark:border-rose-800 text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/20 hover:bg-rose-100 dark:hover:bg-rose-900/40 disabled:opacity-40">
              <OctagonX className="w-4 h-4" /> Kill switch{killing ? '…' : ''}
            </button>
          </div>
        </div>
      </div>

      {/* Reliability config */}
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 space-y-4">
        <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Reliability</div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Max concurrent agents</label>
            <div className="flex items-center gap-2 mt-1">
              <input type="number" min="1" max="8" value={form.max_concurrency}
                onChange={(e) => setForm({ ...form, max_concurrency: parseInt(e.target.value) || 1 })}
                className={input} />
              <span className="text-xs text-neutral-500">of 8 workers</span>
            </div>
            <p className="text-[11px] text-neutral-400 mt-1">How many tasks execute simultaneously.</p>
          </div>
          <div>
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Per-target interval</label>
            <div className="flex items-center gap-2 mt-1">
              <input type="number" min="0" step="10" value={form.target_min_interval}
                onChange={(e) => setForm({ ...form, target_min_interval: Math.max(0, parseInt(e.target.value) || 0) })}
                className={input} />
              <span className="text-xs text-neutral-500">seconds</span>
            </div>
            <p className="text-[11px] text-neutral-400 mt-1">Min wait between two agents starting on the same target.</p>
          </div>
          <div>
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Max steps per task</label>
            <div className="flex items-center gap-2 mt-1">
              <input type="number" min="1" max="1000000" value={form.max_steps}
                onChange={(e) => setForm({ ...form, max_steps: Math.max(1, parseInt(e.target.value) || 1) })}
                className={input} />
              <span className="text-xs text-neutral-500">steps</span>
            </div>
            <p className="text-[11px] text-neutral-400 mt-1">Runaway backstop only — agents run until they finish. Raise it to run goal-mode engagements with effectively no cap. With goal mode on, a capped task auto-continues up to the limit below.</p>
          </div>
          <div>
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Default token budget</label>
            <div className="flex items-center gap-2 mt-1">
              <input type="number" min="0" step="1000" value={form.token_budget}
                onChange={(e) => setForm({ ...form, token_budget: Math.max(0, parseInt(e.target.value) || 0) })}
                className={input} />
              <span className="text-xs text-neutral-500">tokens</span>
            </div>
            <p className="text-[11px] text-neutral-400 mt-1">Per task, prompt+completion. 0 = unlimited. Tasks can override it.</p>
          </div>
        </div>

        {/* Goal mode (Ralph loop) */}
        <div className="pt-3 border-t border-neutral-200 dark:border-neutral-700">
          <div className="flex items-start gap-3">
            <div className="flex items-center gap-2 mt-0.5">
              <Target className="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
              <label className="flex items-center gap-2 text-sm font-medium text-neutral-900 dark:text-neutral-100 cursor-pointer">
                <input type="checkbox" checked={!!form.goal_mode}
                  onChange={(e) => setForm({ ...form, goal_mode: e.target.checked })}
                  className="w-4 h-4 accent-primary-600" />
                Goal mode — run until the objective is met
              </label>
            </div>
          </div>
          <p className="text-[11px] text-neutral-400 mt-1 mb-3">
            An LLM judge reviews every stop attempt (plain text or a premature finish()): if the
            task objective isn't met, the agent is told to continue. Capped runs auto-continue from
            their checkpoint.
          </p>
          <label className={`flex items-center gap-2 mb-3 text-xs font-medium cursor-pointer ${form.goal_mode ? 'text-neutral-900 dark:text-neutral-100' : 'text-neutral-400 pointer-events-none'}`}>
            <input type="checkbox"
              checked={form.max_auto_continuations === -1 && form.goal_judge_max_cont === -1}
              onChange={(e) => toggleNoLimits(e.target.checked)}
              disabled={!form.goal_mode} className="w-4 h-4 accent-primary-600" />
            No limits — stop ONLY when the goal is ready
          </label>
          <div className={`grid sm:grid-cols-2 gap-4 ${form.goal_mode && form.max_auto_continuations !== -1 ? '' : 'opacity-50 pointer-events-none'}`}>
            <div>
              <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Auto-continuations past step cap</label>
              <div className="flex items-center gap-2 mt-1">
                <input type="number" min="0" max="10" value={form.max_auto_continuations < 0 ? '∞' : form.max_auto_continuations}
                  onChange={(e) => setForm({ ...form, max_auto_continuations: Math.max(0, parseInt(e.target.value) || 0) })}
                  disabled={!form.goal_mode} className={input} />
                <span className="text-xs text-neutral-500">of 10</span>
              </div>
              <p className="text-[11px] text-neutral-400 mt-1">Automatic requeues when the step cap is hit before the objective is met. 0 = park in needs_review immediately.</p>
            </div>
            <div>
              <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Goal-review nudges per stop</label>
              <div className="flex items-center gap-2 mt-1">
                <input type="number" min="0" max="10" value={form.goal_judge_max_cont < 0 ? '∞' : form.goal_judge_max_cont}
                  onChange={(e) => setForm({ ...form, goal_judge_max_cont: Math.max(0, parseInt(e.target.value) || 0) })}
                  disabled={!form.goal_mode || form.goal_judge_max_cont < 0} className={input} />
                <span className="text-xs text-neutral-500">of 10</span>
              </div>
              <p className="text-[11px] text-neutral-400 mt-1">How many times a rejected stop is pushed back before it is accepted (resets after real work).</p>
            </div>
          </div>
        </div>

        {/* Model fallback chain */}
        <div className="pt-3 border-t border-neutral-200 dark:border-neutral-700">
          <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Model fallback chain</label>
          <p className="text-[11px] text-neutral-400 mt-0.5 mb-2">
            Tried in order when a task's primary model fails. The task's own model runs first.
          </p>
          {form.fallback_chain.length > 0 && (
            <div className="space-y-1.5 mb-2">
              {form.fallback_chain.map((id, idx) => {
                const m = modelById[id];
                return (
                  <div key={id} className="flex items-center gap-2 text-xs rounded-lg border border-neutral-200 dark:border-neutral-700 px-2.5 py-1.5">
                    <span className="w-5 h-5 rounded-md bg-neutral-100 dark:bg-neutral-700 flex items-center justify-center text-[10px] font-bold text-neutral-500">{idx + 1}</span>
                    <span className="flex-1 min-w-0 truncate text-neutral-700 dark:text-neutral-200">
                      {m ? `${m.name} (${m.provider})` : `model #${id}`}
                    </span>
                    <button onClick={() => moveInChain(idx, -1)} disabled={idx === 0}
                      className="text-neutral-400 hover:text-neutral-600 disabled:opacity-30"><ChevronUp className="w-3.5 h-3.5" /></button>
                    <button onClick={() => moveInChain(idx, 1)} disabled={idx === form.fallback_chain.length - 1}
                      className="text-neutral-400 hover:text-neutral-600 disabled:opacity-30"><ChevronDown className="w-3.5 h-3.5" /></button>
                    <button onClick={() => removeFromChain(idx)} className="text-neutral-400 hover:text-rose-500"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                );
              })}
            </div>
          )}
          <select value="" onChange={(e) => addToChain(parseInt(e.target.value, 10))}
            className="px-2.5 py-1.5 text-xs border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100">
            <option value="">+ Add fallback model…</option>
            {available.map((m) => <option key={m.id} value={m.id}>{m.name} ({m.provider})</option>)}
          </select>
          {available.length === 0 && models.length > 0 && (
            <span className="ml-2 text-[11px] text-neutral-400">all models already in the chain</span>
          )}
        </div>

        <div className="flex items-center justify-between pt-3 border-t border-neutral-200 dark:border-neutral-700">
          <p className="text-xs text-neutral-500 dark:text-neutral-400">Applies immediately — no restart needed.</p>
          <button onClick={save} disabled={busy || !dirty}
            className="flex items-center gap-1 px-3 py-1.5 bg-primary-600 text-white rounded text-xs font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed">
            {busy ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            {busy ? 'Saving…' : 'Save config'}
          </button>
        </div>
      </div>
    </div>
  );
}
