/**
 * Settings → Reports (E4): report branding + compliance frameworks.
 *
 * Branding (org name, tagline, classification banner, primary color, logo)
 * is applied to every generated PDF report's cover and footer. The compliance
 * block documents the OWASP / PCI DSS / NIST CSF mapping available as a
 * report appendix template. Writes are admin-only (enforced by the backend).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle, CheckCircle, FileText, Image as ImageIcon, RefreshCw, Save,
  ShieldCheck, Trash2, Upload,
} from 'lucide-react';
import apiClient from '../../services/api';

const input = 'w-full px-2.5 py-1.5 border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded text-sm focus:outline-none focus:ring-2 focus:ring-primary-500';

const FRAMEWORKS = [
  { key: 'owasp', name: 'OWASP Top 10 (2021)', hint: 'A01–A10 category mapping of findings' },
  { key: 'pci', name: 'PCI DSS v4.0', hint: 'requirement-level mapping for cardholder-data environments' },
  { key: 'nist', name: 'NIST CSF 2.0', hint: 'function/category mapping (GV/ID/PR/DE/RS/RC)' },
];

export default function ReportBrandingSection() {
  const [branding, setBranding] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const { data } = await apiClient.get('/branding');
      setBranding(data);
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || 'Failed to load branding' });
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const flash = (type, text, ms = 4000) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), ms);
  };

  const set = (k, v) => setBranding((b) => ({ ...b, [k]: v }));

  const save = async () => {
    setBusy(true);
    try {
      const { data } = await apiClient.put('/branding', {
        organization: branding.organization,
        tagline: branding.tagline,
        classification: branding.classification,
        primary_color: branding.primary_color,
      });
      setBranding(data);
      flash('success', 'Branding saved — applied to new reports');
    } catch (e) {
      flash('error', e.response?.data?.detail || 'Failed to save branding');
    } finally {
      setBusy(false);
    }
  };

  const uploadLogo = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await apiClient.post('/branding/logo', fd);
      setBranding(data);
      flash('success', 'Logo uploaded');
    } catch (e) {
      flash('error', e.response?.data?.detail || 'Logo upload failed');
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const clearLogo = async () => {
    setBusy(true);
    try {
      const { data } = await apiClient.delete('/branding/logo');
      setBranding(data);
    } catch (e) {
      flash('error', e.response?.data?.detail || 'Failed to clear logo');
    } finally {
      setBusy(false);
    }
  };

  if (!branding) return <div className="text-sm text-neutral-500">Loading…</div>;

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Report branding</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Your organization's identity on every generated PDF report (admin only).
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

      {/* Cover preview */}
      <div className="rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
        <div className="h-2" style={{ background: branding.primary_color }} />
        <div className="bg-neutral-50 dark:bg-neutral-900 p-5 flex items-center gap-4">
          {branding.logo_data_uri
            ? <img src={branding.logo_data_uri} alt="logo" className="h-10 w-auto max-w-[120px] object-contain" />
            : <ImageIcon className="w-8 h-8 text-neutral-300" />}
          <div className="min-w-0">
            <div className="text-lg font-semibold text-neutral-900 dark:text-neutral-100 truncate">{branding.organization || 'AIDA'}</div>
            <div className="text-xs text-neutral-500 dark:text-neutral-400 truncate">{branding.tagline}</div>
          </div>
          <span className="ml-auto shrink-0 text-[10px] font-bold tracking-widest px-2 py-1 rounded border"
            style={{ color: branding.primary_color, borderColor: branding.primary_color }}>
            {String(branding.classification || 'CONFIDENTIAL').toUpperCase()}
          </span>
        </div>
      </div>

      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 space-y-4">
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Organization</label>
            <input className={`${input} mt-1`} value={branding.organization}
              onChange={(e) => set('organization', e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Tagline</label>
            <input className={`${input} mt-1`} value={branding.tagline}
              onChange={(e) => set('tagline', e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Classification banner</label>
            <input className={`${input} mt-1`} value={branding.classification}
              onChange={(e) => set('classification', e.target.value)} />
            <p className="text-[11px] text-neutral-400 mt-1">e.g. Confidential, Strictly Confidential, Internal</p>
          </div>
          <div>
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Primary color</label>
            <div className="flex items-center gap-2 mt-1">
              <input type="color" value={branding.primary_color}
                onChange={(e) => set('primary_color', e.target.value)}
                className="h-9 w-12 rounded border border-neutral-300 dark:border-neutral-600 bg-transparent cursor-pointer" />
              <input className={`${input} flex-1`} value={branding.primary_color}
                onChange={(e) => set('primary_color', e.target.value)} />
            </div>
          </div>
        </div>

        <div className="pt-3 border-t border-neutral-200 dark:border-neutral-700 flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-[220px]">
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Logo (PNG / JPEG / SVG, ≤300KB)</label>
            <div className="flex items-center gap-2 mt-1">
              <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/svg+xml"
                onChange={(e) => uploadLogo(e.target.files?.[0])}
                className="hidden" id="branding-logo-input" />
              <button onClick={() => fileRef.current?.click()} disabled={busy}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-200 disabled:opacity-50">
                <Upload className="w-3.5 h-3.5" /> {branding.logo_data_uri ? 'Replace logo' : 'Upload logo'}
              </button>
              {branding.logo_data_uri && (
                <button onClick={clearLogo} disabled={busy}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-rose-300 dark:border-rose-800 text-rose-600 dark:text-rose-400 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-900/20 disabled:opacity-50">
                  <Trash2 className="w-3.5 h-3.5" /> Remove
                </button>
              )}
            </div>
          </div>
          <button onClick={save} disabled={busy}
            className="flex items-center gap-1 px-3 py-1.5 bg-primary-600 text-white rounded text-xs font-medium hover:bg-primary-700 disabled:opacity-50">
            {busy ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            {busy ? 'Saving…' : 'Save branding'}
          </button>
        </div>
      </div>

      {/* Compliance report templates */}
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 space-y-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-primary-500" />
          <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Compliance report templates</div>
        </div>
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          Append a framework mapping of the assessment's findings to a PDF report —
          pass <code className="px-1 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700">?template=</code>
          {' '}to the report download, or pick a template in the assessment's PDF menu.
          Mapping is automatic from finding content and can be overridden per finding.
        </p>
        <div className="grid sm:grid-cols-3 gap-3">
          {FRAMEWORKS.map((f) => (
            <div key={f.key} className="rounded-lg border border-neutral-200 dark:border-neutral-700 p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-neutral-800 dark:text-neutral-200">
                <FileText className="w-3.5 h-3.5 text-primary-500" /> {f.name}
              </div>
              <div className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-1">{f.hint}</div>
              <code className="text-[10px] text-neutral-400 mt-2 block">template={f.key}</code>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
