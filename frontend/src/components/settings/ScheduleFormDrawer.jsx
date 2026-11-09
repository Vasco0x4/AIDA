import { Save } from 'lucide-react';
import { useEffect, useState } from 'react';
import scheduleService from '../../services/scheduleService';
import { formatScheduleTime, UTC_ZONES, timezoneLabel } from '../../utils/scheduleTime';
import Drawer from '../common/Drawer';

export const inputClass = 'mt-1 w-full rounded border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary-500';
export const labelClass = 'text-xs font-medium text-neutral-700 dark:text-neutral-300';

const CRON_PRESETS = [
  ['Daily at 03:00', '0 3 * * *'], ['Every 6 hours', '0 */6 * * *'],
  ['Weekly on Monday', '0 3 * * mon'], ['Monthly on the 1st', '0 3 1 * *'],
];

function Field({ id, label, help, children }) {
  return <div>
    <label htmlFor={id} className={labelClass}>{label}</label>
    {children}
    {help && <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{help}</p>}
  </div>;
}

export default function ScheduleFormDrawer({ editing, form, setForm, onClose, onSave,
  busy, assessments, profiles, models, error }) {
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const safe = form.scan_profile === 'safe_web_baseline';
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState('');
  useEffect(() => {
    if (!editing) return;
    let cancelled = false;
    setPreview(null); setPreviewError('');
    const timer = window.setTimeout(async () => {
      try {
        const result = await scheduleService.preview(form.cron, form.timezone);
        if (!cancelled) setPreview(result);
      } catch (error) {
        if (!cancelled) setPreviewError(error.response?.data?.detail || 'Schedule preview unavailable. Check expression, timezone and connection.');
      }
    }, 350);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [editing, form.cron, form.timezone]);
  const selectProfile = (value) => {
    const profile = profiles.find((item) => String(item.id) === value);
    setForm((current) => ({
      ...current,
      scan_profile_id: value ? Number(value) : null,
      scan_profile: profile?.kind || 'autonomous',
      rate_limit_seconds: profile?.rate_limit_seconds || current.rate_limit_seconds,
      orchestrate: profile?.kind === 'safe_web_baseline' ? false : current.orchestrate,
    }));
  };
  const selectAssessment = (value) => {
    setForm((current) => ({
      ...current,
      assessment_id: value ? Number(value) : null,
    }));
  };

  return <Drawer open={Boolean(editing)} onClose={onClose}
    title={editing?.id ? 'Edit scheduled scan' : 'New scheduled scan'} wide>
    <form onSubmit={(event) => { event.preventDefault(); onSave(); }} className="space-y-5">
      {error && <p role="alert" className="rounded-lg border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950 dark:text-rose-200">{error}</p>}
      <p className="rounded bg-neutral-50 dark:bg-neutral-900 p-3 text-sm text-neutral-600 dark:text-neutral-300">
        Each scheduled start creates a new Scan Run in the selected Assessment. Findings, evidence and run history stay together.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="schedule-name" label="Schedule name">
          <input id="schedule-name" data-initial-focus required maxLength={255} className={inputClass} value={form.name}
            onChange={(event) => update('name', event.target.value)} />
        </Field>
        <Field id="schedule-timezone" label="Timezone" help="Fixed UTC offset. No daylight-saving changes. Existing regional zones are preserved until you change them.">
          <select id="schedule-timezone" required className={inputClass} value={form.timezone}
            onChange={(event) => update('timezone', event.target.value)}>
            {!UTC_ZONES.some(zone => zone.value === form.timezone) && <option value={form.timezone}>{form.timezone} (existing timezone)</option>}
            {UTC_ZONES.map(zone => <option key={zone.value} value={zone.value}>{zone.label}</option>)}
          </select>
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="schedule-cron" label="Cron expression">
          <input id="schedule-cron" required className={`${inputClass} font-mono`} value={form.cron}
            onChange={(event) => update('cron', event.target.value)} placeholder="0 3 * * *" />
        </Field>
        <Field id="schedule-preset" label="Cron preset">
          <select id="schedule-preset" className={inputClass} value="" onChange={(event) => {
            if (event.target.value) update('cron', event.target.value);
          }}><option value="">Choose a preset…</option>{CRON_PRESETS.map(([label, cron]) =>
            <option key={cron} value={cron}>{label} ({cron})</option>)}</select>
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2 rounded-xl bg-primary-50 dark:bg-neutral-900 border border-primary-200 dark:border-primary-900 p-4" aria-live="polite">
          <p className="text-sm font-semibold">Next five runs · {timezoneLabel(form.timezone)}</p>
          {previewError ? <p className="text-sm text-rose-600 mt-2">{previewError}</p> : preview ?
            <ol className="mt-2 grid gap-1 text-sm text-neutral-600 dark:text-neutral-300">{preview.occurrences.map(value => <li key={value}>{formatScheduleTime(value, form.timezone)}</li>)}</ol>
            : <p className="mt-2 text-sm text-neutral-500">Calculating schedule…</p>}
          <p className="text-xs text-neutral-500 mt-2">Preview only. No scan is started.</p>
        </div>
        <Field id="schedule-assessment" label="Assessment" help="Required: all recurring runs reuse this Assessment.">
          <select id="schedule-assessment" required className={inputClass} value={form.assessment_id ?? ''}
            onChange={(event) => selectAssessment(event.target.value)}>
            <option value="">Select an Assessment…</option>
            {assessments.map((item) => <option key={item.id} value={item.id}>#{item.id} {item.name}</option>)}
          </select>
        </Field>
        <Field id="schedule-profile" label="Scan Profile" help="Safe baseline is GET-only; autonomous requires a configured AI model.">
          <select id="schedule-profile" className={inputClass} value={form.scan_profile_id ?? ''}
            onChange={(event) => selectProfile(event.target.value)}>
            <option value="">Autonomous (custom settings)</option>
            {profiles.filter((item) => item.enabled).map((item) =>
              <option key={item.id} value={item.id}>{item.name} — {item.kind}</option>)}
          </select>
        </Field>
      </div>
      <h3 className="aida-section-heading">Scan details</h3>
      <Field id="schedule-task-title" label="Task title">
        <input id="schedule-task-title" required maxLength={255} className={inputClass} value={form.task_title}
          onChange={(event) => update('task_title', event.target.value)} />
      </Field>
      <Field id="schedule-description" label="Description and objectives">
        <textarea id="schedule-description" rows={2} className={inputClass} value={form.description}
          onChange={(event) => update('description', event.target.value)} />
      </Field>
      <Field id="schedule-target" label="Target URL" help="Use the exact authorized origin. Redirects are denied by the safe profile.">
        <input id="schedule-target" type="url" required={safe} className={inputClass} value={form.target}
          onChange={(event) => update('target', event.target.value)} placeholder="http://127.0.0.1:3000" />
      </Field>
      <Field id="schedule-scope" label="Authorized scope"
        help="Comma/newline-separated exact hosts, URLs, IPs or CIDRs. Prefix exclusions with ! (for example !*.admin.example.com).">
        <textarea id="schedule-scope" required className={`${inputClass} font-mono`} rows={3}
          value={form.authorized_scope} onChange={(event) => update('authorized_scope', event.target.value)}
          placeholder="127.0.0.1, app.example.com, 10.0.0.0/24" />
      </Field>
      <Field id="schedule-authorization" label="Authorization reference"
        help="Policy, contract, bug-bounty scope, or ownership basis. Never schedule an unapproved target.">
        <input id="schedule-authorization" required={safe} className={inputClass} value={form.authorization_reference}
          onChange={(event) => update('authorization_reference', event.target.value)}
          placeholder="Owned isolated lab / HackerOne policy URL / change ticket" />
      </Field>
      <label className="flex items-start gap-2 text-sm text-neutral-700 dark:text-neutral-300">
        <input type="checkbox" required={safe} className="mt-1" checked={form.authorization_confirmed}
          onChange={(event) => update('authorization_confirmed', event.target.checked)} />
        <span>I confirm that I am authorized to scan only the targets in this scope.</span>
      </label>
      <h3 className="aida-section-heading">Execution settings</h3>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field id="schedule-priority" label="Priority"><select id="schedule-priority" className={inputClass}
          value={form.priority} onChange={(event) => update('priority', event.target.value)}>
          {['critical', 'high', 'medium', 'low'].map((value) => <option key={value}>{value}</option>)}
        </select></Field>
        <Field id="schedule-rate" label="Minimum seconds between requests">
          <input id="schedule-rate" type="number" min={1} max={3600} className={inputClass}
            value={form.rate_limit_seconds} onChange={(event) => update('rate_limit_seconds', Number(event.target.value))} />
        </Field>
        <Field id="schedule-budget" label="Token budget">
          <input id="schedule-budget" type="number" min={0} disabled={safe} className={inputClass}
            value={form.token_budget ?? ''} onChange={(event) => update('token_budget',
              event.target.value ? Number(event.target.value) : null)} placeholder="Platform default" />
        </Field>
      </div>
      {!safe && <>
        <Field id="schedule-model" label="AI model"><select id="schedule-model" className={inputClass}
          value={form.model_config_id ?? ''} onChange={(event) => update('model_config_id',
            event.target.value ? Number(event.target.value) : null)}><option value="">Default model</option>
          {models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.orchestrate}
          onChange={(event) => update('orchestrate', event.target.checked)} /> Orchestrate multi-phase assessment</label>
      </>}
      <div className="flex items-center justify-between border-t border-neutral-200 dark:border-neutral-700 pt-4">
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.enabled}
          onChange={(event) => update('enabled', event.target.checked)} /> Enabled</label>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} className="rounded border border-neutral-300 dark:border-neutral-600 px-3 py-2 text-sm">Cancel</button>
          <button type="submit" disabled={busy} className="flex items-center gap-2 rounded bg-primary-600 px-3 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
            <Save aria-hidden="true" className="h-4 w-4" />{editing?.id ? 'Save schedule' : 'Create schedule'}
          </button>
        </div>
      </div>
    </form>
  </Drawer>;
}
