import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, CalendarClock, CheckCircle, Clock, Play, Plus, RefreshCw, Trash2 } from 'lucide-react';
import scheduleService from '../../services/scheduleService';
import scanProfileService from '../../services/scanProfileService';
import aiModelService from '../../services/aiModelService';
import { assessmentService } from '../../services/assessmentService';
import { useAuth } from '../../contexts/AuthContext';
import ScheduleFormDrawer from './ScheduleFormDrawer';
import ScanProfileManager from './ScanProfileManager';
import { formatScheduleTime, timezoneLabel } from '../../utils/scheduleTime';

const BLANK = {
  name: '', cron: '0 3 * * *', timezone: 'UTC', task_title: '', description: '', target: '',
  authorized_scope: '', priority: 'medium', model_config_id: null, orchestrate: false,
  token_budget: null, enabled: true, assessment_id: null, scan_profile_id: null,
  scan_profile: 'autonomous', rate_limit_seconds: 60, max_concurrency: 1,
  authorization_reference: '', authorization_confirmed: false,
};

const fmt = formatScheduleTime;

export default function SchedulesSection() {
  const { user } = useAuth();
  const readOnly = user?.role === 'viewer';
  const [rows, setRows] = useState([]);
  const [models, setModels] = useState([]);
  const [assessments, setAssessments] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const profileDetails = useRef(null);
  const [loadError, setLoadError] = useState(null);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState(null);
  const [formError, setFormError] = useState(null);
  const [pendingIds, setPendingIds] = useState(new Set());
  const actionLocks = useRef(new Set());
  const withRowLock = async (id, operation) => {
    if (actionLocks.current.has(id)) return;
    actionLocks.current.add(id); setPendingIds(new Set(actionLocks.current));
    try { await operation(); } finally { actionLocks.current.delete(id); setPendingIds(new Set(actionLocks.current)); }
  };
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(BLANK);
  const flashTimer = useRef(null);

  const flash = useCallback((type, text) => {
    window.clearTimeout(flashTimer.current);
    setMessage({ type, text });
    flashTimer.current = window.setTimeout(() => setMessage(null), 5000);
  }, []);
  useEffect(() => () => window.clearTimeout(flashTimer.current), []);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [list, modelList, assessmentList, profileList] = await Promise.all([
        scheduleService.list(), user?.role === 'admin' ? aiModelService.list() : Promise.resolve([]),
        assessmentService.getAll(0, 200), scanProfileService.list(),
      ]);
      setLoadError(null);
      setRows(list); setModels(modelList); setAssessments(assessmentList); setProfiles(profileList);
    } catch (error) {
      setLoadError('Scheduler data could not be loaded. Use Refresh to try again.');
    } finally { setBusy(false); }
  }, [user?.role]);
  useEffect(() => { load(); }, [load]);

  const close = useCallback(() => setEditing(null), []);
  const openCreate = () => { setFormError(null); setForm({ ...BLANK }); setEditing({}); };
  const openEdit = (row) => {
    setFormError(null);
    setForm({ ...BLANK, ...row, description: row.description || '', target: row.target || '',
      authorized_scope: row.authorized_scope || '', authorization_reference: row.authorization_reference || '' });
    setEditing({ id: row.id });
  };
  const save = async () => {
    if (rows.some((row) => row.id !== editing?.id && row.name.toLowerCase() === form.name.trim().toLowerCase())) {
      setFormError('A schedule with this name already exists'); return;
    }
    setBusy(true); setFormError(null);
    const payload = { ...form, name: form.name.trim(), task_title: form.task_title.trim() };
    if (payload.scan_profile === 'safe_web_baseline') {
      payload.orchestrate = false; payload.model_config_id = null; payload.token_budget = null;
    }
    try {
      if (editing?.id) await scheduleService.update(editing.id, payload);
      else await scheduleService.create(payload);
      flash('success', `Schedule ${editing?.id ? 'updated' : 'created'}`);
      close(); await load();
    } catch (error) {
      const detail = error.response?.data?.detail;
      setFormError(typeof detail === 'string' ? detail : 'Failed to save schedule. Review the fields and try again.');
    } finally { setBusy(false); }
  };
  const toggle = async (row) => {
    try { await scheduleService.update(row.id, { enabled: !row.enabled }); await load(); }
    catch (error) { flash('error', error.response?.data?.detail || 'Failed to update schedule'); }
  };
  const runNow = async (row) => {
    try {
      const task = await scheduleService.runNow(row.id);
      flash('success', `Scan Run #${task.id} queued — open it to watch actual progress.`);
      await load();
    } catch (error) {
      flash('error', error.response?.status === 409 ? 'A run for this Assessment is still active.'
        : (error.response?.data?.detail || 'Run now failed'));
    }
  };
  const remove = async (row) => {
    if (!window.confirm(`Delete schedule "${row.name}"? Existing Scan Runs and evidence are kept.`)) return;
    try { await scheduleService.remove(row.id); await load(); }
    catch (error) { flash('error', error.response?.data?.detail || 'Failed to delete schedule'); }
  };

  return <div className="space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h3 className="text-lg font-semibold">Scheduler</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Recurring Scan Runs inside one Assessment, with explicit scope and authorization.</p>
        {readOnly && <p className="mt-1 text-xs text-neutral-500">Read-only: your viewer role cannot change schedules or profiles.</p>}</div>
      <div className="flex gap-2"><button type="button" onClick={load} disabled={busy} className="flex items-center gap-1 rounded border border-neutral-300 dark:border-neutral-600 px-3 py-2 text-sm">
        <RefreshCw aria-hidden="true" className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} /> Refresh</button>
        {!readOnly && <button type="button" onClick={openCreate} disabled={busy || Boolean(loadError) || !assessments.length} className="flex items-center gap-1 rounded bg-primary-600 px-3 py-2 text-sm text-white">
          <Plus aria-hidden="true" className="h-4 w-4" /> New schedule</button>}</div>
    </div>
    {message && <div role={message.type === 'error' ? 'alert' : 'status'} className={`flex items-center gap-2 rounded p-3 text-sm ${message.type === 'error' ? 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300' : 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300'}`}>
      {message.type === 'error' ? <AlertCircle aria-hidden="true" className="h-4 w-4" /> : <CheckCircle aria-hidden="true" className="h-4 w-4" />}{message.text}</div>}
    {loadError && <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">{loadError}</p>}
    {!busy && !loadError && rows.length === 0 && <section className="aida-page-header">
      <p className="aida-eyebrow">First scheduled scan</p><h4 className="text-xl font-semibold">Set up your first schedule</h4>
      <ol className="mt-5 grid gap-4 md:grid-cols-3">
        <li className="rounded-xl border border-neutral-200 dark:border-neutral-700 p-4"><strong>1. Choose an Assessment</strong><p className="mt-2 text-sm text-neutral-500">{assessments.length ? `${assessments.length} available. Each schedule keeps its runs and findings inside one Assessment.` : 'Create an Assessment before adding a schedule.'}</p><Link className="mt-3 inline-block text-sm text-primary-600" to="/assessments">Open Assessments →</Link></li>
        <li className="rounded-xl border border-neutral-200 dark:border-neutral-700 p-4"><strong>2. Choose scan settings</strong><p className="mt-2 text-sm text-neutral-500">Use custom settings in the schedule, or save a reusable scan profile. Profiles are optional.</p><button className="mt-3 text-sm text-primary-600" onClick={() => { profileDetails.current.open = true; profileDetails.current.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}>View scan profiles →</button></li>
        <li className="rounded-xl border border-neutral-200 dark:border-neutral-700 p-4"><strong>3. Set time and scope</strong><p className="mt-2 text-sm text-neutral-500">Select New schedule above. Review the UTC offset, next run times and authorized scope before enabling it.</p><Link className="mt-3 inline-block text-sm text-primary-600" to="/getting-started">Check runner readiness →</Link></li>
      </ol>
    </section>}
    <div className="space-y-3">{rows.map((row) => <article key={row.id} className="rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-4">
      <div className="flex flex-wrap items-start gap-3">
        <CalendarClock aria-hidden="true" className={`mt-1 h-5 w-5 ${row.enabled ? 'text-primary-500' : 'text-neutral-400'}`} />
        <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><strong>{row.name}</strong>
          <code className="rounded bg-neutral-100 dark:bg-neutral-700 px-1.5 py-0.5 text-xs">{row.cron} · {timezoneLabel(row.timezone)}</code>
          {!row.enabled && <span className="text-xs text-amber-600">schedule paused</span>}</div>
          <p className="mt-1 text-xs text-neutral-500">Assessment #{row.assessment_id || 'legacy'} · {row.scan_profile} · {row.run_count} runs</p>
          <p className="mt-1 text-xs text-neutral-500"><Clock aria-hidden="true" className="inline h-3 w-3" /> Next {fmt(row.next_run_at, row.timezone)} · Last {fmt(row.last_run_at, row.timezone)} · {timezoneLabel(row.timezone)}</p>
          {row.last_task_id && <Link to={`/runs/${row.last_task_id}`} className="mt-2 inline-block text-xs text-primary-600 hover:underline">View run #{row.last_task_id} ({row.last_task_status || 'unknown'})</Link>}
          {row.last_error && <p role="alert" className="mt-2 text-xs text-red-600">{row.last_error}</p>}</div>
        {!readOnly && <div className="flex flex-wrap gap-2">
          <button type="button" disabled={pendingIds.has(row.id)} onClick={() => withRowLock(row.id, () => runNow(row))} aria-label={`Run ${row.name} now`} className="rounded border border-neutral-300 dark:border-neutral-600 p-2"><Play aria-hidden="true" className="h-4 w-4" /></button>
          <button type="button" disabled={pendingIds.has(row.id)} onClick={() => withRowLock(row.id, () => toggle(row))} className="rounded border border-neutral-300 dark:border-neutral-600 px-2 py-1 text-xs">{row.enabled ? 'Pause schedule' : 'Enable schedule'}</button>
          <button type="button" onClick={() => openEdit(row)} className="rounded px-2 py-1 text-xs text-primary-600">Edit</button>
          <button type="button" disabled={pendingIds.has(row.id)} onClick={() => withRowLock(row.id, () => remove(row))} aria-label={`Delete ${row.name}`} className="rounded p-2 text-neutral-400 hover:text-red-600"><Trash2 aria-hidden="true" className="h-4 w-4" /></button>
        </div>}
      </div>
    </article>)}</div>
    <ScheduleFormDrawer editing={editing} form={form} setForm={setForm} onClose={close} onSave={save}
      busy={busy} assessments={assessments} profiles={profiles} models={models} error={formError} />
    <details ref={profileDetails} className="rounded-xl border p-4"><summary className="cursor-pointer font-medium">Scan profiles · {profiles.length} available</summary><div className="mt-4"><ScanProfileManager profiles={profiles} onChanged={load} readOnly={readOnly} /></div></details>
  </div>;
}
