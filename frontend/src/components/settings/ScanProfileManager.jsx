import { useCallback, useState } from 'react';
import { Plus, Save, Trash2 } from 'lucide-react';
import Drawer from '../common/Drawer';
import scanProfileService from '../../services/scanProfileService';
import { inputClass, labelClass } from './ScheduleFormDrawer';

const BLANK = { name: '', kind: 'safe_web_baseline', description: '', rate_limit_seconds: 60,
  max_pages: 8, max_response_bytes: 1000000, timeout_seconds: 5, max_concurrency: 1, enabled: true };

export default function ScanProfileManager({ profiles, onChanged, readOnly }) {
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(BLANK);
  const [message, setMessage] = useState(null);
  const close = useCallback(() => setEditing(null), []);
  const open = (profile) => {
    setForm(profile ? { ...profile } : BLANK);
    setEditing(profile || {});
  };
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const save = async () => {
    try {
      if (editing.id) await scanProfileService.update(editing.id, form);
      else await scanProfileService.create(form);
      close();
      setMessage('Scan Profile saved');
      await onChanged();
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Failed to save Scan Profile');
    }
  };
  const remove = async (profile) => {
    if (!window.confirm(`Delete Scan Profile "${profile.name}"? Existing run policy snapshots are kept.`)) return;
    try {
      await scanProfileService.remove(profile.id);
      await onChanged();
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Failed to delete Scan Profile');
    }
  };

  return <section aria-labelledby="scan-profiles-heading" className="border-t border-neutral-200 dark:border-neutral-700 pt-5">
    <div className="flex items-center justify-between gap-3">
      <div><h4 id="scan-profiles-heading" className="text-sm font-semibold">Scan Profiles</h4>
        <p className="text-xs text-neutral-500">Reusable request, page, timeout and response-size limits.</p></div>
      {!readOnly && <button type="button" onClick={() => open(null)} className="flex items-center gap-1 rounded border border-neutral-300 dark:border-neutral-600 px-2 py-1 text-xs">
        <Plus aria-hidden="true" className="h-3 w-3" /> New profile</button>}
    </div>
    {message && <p role="status" className="mt-2 text-xs text-neutral-600 dark:text-neutral-300">{message}</p>}
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {profiles.map((profile) => <article key={profile.id} className="rounded border border-neutral-200 dark:border-neutral-700 p-3 text-xs">
        <div className="flex items-start justify-between gap-2"><div><strong>{profile.name}</strong>
          <p className="text-neutral-500">{profile.kind} · {profile.rate_limit_seconds}s/request · {profile.max_pages} pages max</p></div>
          {!readOnly && <div className="flex gap-2"><button type="button" onClick={() => open(profile)} className="text-primary-600">Edit</button>
            <button type="button" onClick={() => remove(profile)} aria-label={`Delete ${profile.name}`}><Trash2 aria-hidden="true" className="h-3 w-3" /></button></div>}
        </div>
      </article>)}
    </div>
    <Drawer open={Boolean(editing)} onClose={close} title={editing?.id ? 'Edit Scan Profile' : 'New Scan Profile'}>
      <form onSubmit={(event) => { event.preventDefault(); save(); }} className="space-y-4">
        <div><label htmlFor="profile-name" className={labelClass}>Profile name</label>
          <input id="profile-name" required className={inputClass} value={form.name} onChange={(e) => update('name', e.target.value)} /></div>
        <div><label htmlFor="profile-kind" className={labelClass}>Profile kind</label>
          <select id="profile-kind" className={inputClass} value={form.kind} onChange={(e) => update('kind', e.target.value)}>
            <option value="safe_web_baseline">Safe web baseline (GET-only)</option><option value="autonomous">Autonomous</option></select></div>
        <div><label htmlFor="profile-description" className={labelClass}>Description</label>
          <textarea id="profile-description" className={inputClass} value={form.description || ''} onChange={(e) => update('description', e.target.value)} /></div>
        {[['rate_limit_seconds', 'Seconds between requests', 1, 3600], ['max_pages', 'Maximum pages', 1, 25],
          ['max_response_bytes', 'Maximum response bytes', 1024, 2000000], ['timeout_seconds', 'Request timeout seconds', 1, 15]].map(([key, label, min, max]) =>
          <div key={key}><label htmlFor={`profile-${key}`} className={labelClass}>{label}</label>
            <input id={`profile-${key}`} type="number" min={min} max={max} required className={inputClass} value={form[key]}
              onChange={(e) => update(key, Number(e.target.value))} /></div>)}
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.enabled}
          onChange={(e) => update('enabled', e.target.checked)} /> Enabled</label>
        <p className="text-xs text-neutral-500">Maximum concurrency is fixed at 1 per Assessment to prevent conflicting scans.</p>
        <button type="submit" className="flex items-center gap-2 rounded bg-primary-600 px-3 py-2 text-sm text-white">
          <Save aria-hidden="true" className="h-4 w-4" /> Save profile</button>
      </form>
    </Drawer>
  </section>;
}
