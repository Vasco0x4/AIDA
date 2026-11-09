/**
 * Subdomain Takeover — background scans (persisted), live progress, scan history,
 * per-asset operator notes, and delete. Checks each subdomain against the
 * can-i-take-over-xyz fingerprint set.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  Crosshair, Loader2, AlertTriangle, ShieldCheck, ShieldAlert, HelpCircle,
  ExternalLink, BookOpen, Trash2, StickyNote, Clock, ChevronRight,
} from 'lucide-react';
import takeoverService from '../services/takeoverService';
import { useWebSocketContext } from '../contexts/WebSocketContext';

const VERDICT = {
  VULNERABLE:     { label: 'Vulnerable',     color: '#e11d48', icon: ShieldAlert },
  EDGE_CASE:      { label: 'Edge case',      color: '#f59e0b', icon: HelpCircle },
  NOT_VULNERABLE: { label: 'Not vulnerable', color: '#0ea5e9', icon: ShieldCheck },
};
const ORDER = { VULNERABLE: 0, EDGE_CASE: 1, NOT_VULNERABLE: 2 };
const sortRes = (arr) => [...arr].sort((a, b) => (ORDER[a.verdict] ?? 9) - (ORDER[b.verdict] ?? 9));

function Badge({ verdict }) {
  const m = VERDICT[verdict] || { label: verdict, color: '#94a3b8', icon: HelpCircle };
  const Icon = m.icon;
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-md"
      style={{ background: `${m.color}1a`, color: m.color }}>
      <Icon size={12} /> {m.label}
    </span>
  );
}

function NoteCell({ result, onSave }) {
  const [val, setVal] = useState(result.note || '');
  const [dirty, setDirty] = useState(false);
  useEffect(() => { setVal(result.note || ''); setDirty(false); }, [result.id, result.note]);
  if (!result.id) return <span className="text-[10px] text-neutral-300">—</span>;
  return (
    <div className="flex items-center gap-1">
      <input
        value={val}
        onChange={(e) => { setVal(e.target.value); setDirty(true); }}
        onBlur={() => dirty && onSave(result.id, val)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.target.blur(); } }}
        placeholder="add note…"
        className="w-full text-[11px] bg-transparent border-b border-dashed border-neutral-200 dark:border-neutral-700 focus:border-sky-400 focus:outline-none text-neutral-600 dark:text-neutral-300 py-0.5"
      />
      {dirty && <StickyNote size={11} className="text-amber-400 shrink-0" />}
    </div>
  );
}

export default function Takeover() {
  const [domain, setDomain] = useState('');
  const [subsText, setSubsText] = useState('');
  const [scanning, setScanning] = useState(false);
  const [scanId, setScanId] = useState(null);
  const [progress, setProgress] = useState({ checked: 0, total: 0 });
  const [summary, setSummary] = useState({ vulnerable: 0, edge_case: 0, not_vulnerable: 0 });
  const [results, setResults] = useState([]);
  const [wildcard, setWildcard] = useState(false);
  const [error, setError] = useState(null);
  const [fps, setFps] = useState([]);
  const [showRef, setShowRef] = useState(false);
  const [history, setHistory] = useState([]);
  const { subscribe } = useWebSocketContext();
  const pollRef = useRef(null);

  const loadHistory = () => takeoverService.listScans().then(setHistory).catch(() => {});
  useEffect(() => {
    takeoverService.fingerprints().then(setFps).catch(() => {});
    loadHistory();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const applyState = (st) => {
    setProgress({ checked: st.checked || 0, total: st.total || 0 });
    setSummary(st.summary || summary);
    setWildcard(!!st.wildcard);
    if (Array.isArray(st.results)) setResults(sortRes(st.results));
    if (st.status && st.status !== 'running') finish(st.status, st.error);
  };
  const finish = (status, err) => {
    setScanning(false);
    if (err) setError(err);
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    loadHistory();
  };

  // Live progress for the active scan.
  useEffect(() => {
    if (!scanId) return;
    const unsubs = [
      subscribe('takeover_progress', (msg) => {
        const d = msg?.data || msg;
        if (d?.scan_id !== scanId) return;
        setProgress({ checked: d.checked, total: d.total });
        if (d.summary) setSummary(d.summary);
        if (d.result) setResults((prev) => sortRes([...prev, d.result]));
      }),
      subscribe('takeover_done', (msg) => {
        const d = msg?.data || msg;
        if (d?.scan_id !== scanId) return;
        // Reload from DB to get ids/notes.
        takeoverService.getScan(scanId).then(applyState).catch(() => {});
        finish(d.status, d.error);
      }),
    ];
    return () => unsubs.forEach((u) => u && u());
  }, [scanId, subscribe]);

  const runScan = async () => {
    if (!domain.trim()) { setError('Enter a domain'); return; }
    setError(null); setResults([]); setSummary({ vulnerable: 0, edge_case: 0, not_vulnerable: 0 });
    setProgress({ checked: 0, total: 0 }); setWildcard(false); setScanning(true);
    try {
      const subs = subsText.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);
      const { scan_id } = await takeoverService.startScan(domain.trim(), { subdomains: subs.length ? subs : null });
      setScanId(scan_id);
      loadHistory();
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try { applyState(await takeoverService.getScan(scan_id)); } catch { /* ignore */ }
      }, 5000);
    } catch (err) { setError(err.response?.data?.detail || err.message); setScanning(false); }
  };

  const openScan = async (id) => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    setScanId(id); setScanning(false); setError(null);
    try {
      const st = await takeoverService.getScan(id);
      setDomain(st.domain);
      applyState({ ...st, status: st.status === 'running' ? 'done' : st.status });
      if (st.status === 'running') { setScanning(true); runPolling(id); }
    } catch (e) { setError(e.message); }
  };
  const runPolling = (id) => {
    pollRef.current = setInterval(async () => {
      try { applyState(await takeoverService.getScan(id)); } catch { /* ignore */ }
    }, 5000);
  };

  const removeScan = async (id, e) => {
    e?.stopPropagation();
    if (!confirm('Delete this scan and its results?')) return;
    await takeoverService.deleteScan(id).catch(() => {});
    if (id === scanId) { setScanId(null); setResults([]); setProgress({ checked: 0, total: 0 }); }
    loadHistory();
  };
  const saveNote = async (rid, note) => {
    await takeoverService.setNote(rid, note).catch(() => {});
    setResults((prev) => prev.map((r) => (r.id === rid ? { ...r, note } : r)));
  };
  const removeResult = async (rid) => {
    await takeoverService.deleteResult(rid).catch(() => {});
    setResults((prev) => prev.filter((r) => r.id !== rid));
  };

  const field = 'w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-800 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-sky-500/60';
  const pct = progress.total ? Math.round((progress.checked / progress.total) * 100) : 0;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-2xl font-bold text-neutral-800 dark:text-neutral-100 flex items-center gap-2">
            <Crosshair size={22} className="text-rose-500" /> Subdomain Takeover
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
            Enumerate a domain's subdomains and check each against the can-i-take-over-xyz fingerprints
            {fps.length ? ` (${fps.length} services)` : ''}. Authorized targets only.
          </p>
        </div>
        <button onClick={() => setShowRef((v) => !v)} className="text-xs text-neutral-500 hover:text-sky-600 inline-flex items-center gap-1">
          <BookOpen size={14} /> Fingerprint list
        </button>
      </div>

      {showRef && (
        <div className="mb-5 rounded-xl border border-neutral-200 dark:border-neutral-700 max-h-56 overflow-y-auto text-[12px]">
          <table className="w-full">
            <thead className="sticky top-0 bg-neutral-100 dark:bg-neutral-800 text-neutral-500">
              <tr><th className="text-left px-3 py-1.5">Service</th><th className="text-left px-3 py-1.5">Status</th><th className="text-left px-3 py-1.5">Fingerprint</th></tr>
            </thead>
            <tbody>
              {fps.map((f, i) => (
                <tr key={i} className="border-t border-neutral-100 dark:border-neutral-800">
                  <td className="px-3 py-1 text-neutral-700 dark:text-neutral-200">{f.service}</td>
                  <td className="px-3 py-1"><Badge verdict={f.vulnerable ? 'VULNERABLE' : f.status === 'Edge case' ? 'EDGE_CASE' : 'NOT_VULNERABLE'} /></td>
                  <td className="px-3 py-1 text-neutral-400 font-mono truncate max-w-xs">{f.fingerprint || '(NXDOMAIN)'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
        {/* Left: form + history */}
        <div className="lg:col-span-1 space-y-4">
          <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-4 space-y-3">
            <div>
              <label className="text-[11px] font-semibold uppercase text-neutral-500">Target domain</label>
              <input className={field} value={domain} onChange={(e) => setDomain(e.target.value)}
                placeholder="example.com" onKeyDown={(e) => e.key === 'Enter' && !scanning && runScan()} />
            </div>
            <div>
              <label className="text-[11px] font-semibold uppercase text-neutral-500">Subdomains (optional)</label>
              <textarea className={field} rows={2} value={subsText} onChange={(e) => setSubsText(e.target.value)}
                placeholder="one per line — skips enumeration" />
            </div>
            <button onClick={runScan} disabled={scanning}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50 font-medium">
              {scanning ? <><Loader2 size={16} className="animate-spin" /> Scanning…</> : <><Crosshair size={16} /> Scan</>}
            </button>
            {error && <p className="text-sm text-rose-600 flex items-center gap-1"><AlertTriangle size={14} /> {error}</p>}
          </div>

          <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-3">
            <div className="text-[11px] font-semibold uppercase text-neutral-500 mb-2 flex items-center gap-1"><Clock size={12} /> Scan history</div>
            <div className="space-y-1 max-h-96 overflow-y-auto">
              {history.length === 0 && <p className="text-[12px] text-neutral-400">No scans yet.</p>}
              {history.map((s) => (
                <div key={s.scan_id} onClick={() => openScan(s.scan_id)}
                  className={`group flex items-center gap-2 rounded-lg px-2.5 py-1.5 cursor-pointer text-[12px] ${s.scan_id === scanId ? 'bg-sky-50 dark:bg-sky-900/20' : 'hover:bg-neutral-50 dark:hover:bg-neutral-700/40'}`}>
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-neutral-700 dark:text-neutral-200 truncate">{s.domain}</div>
                    <div className="text-[10px] text-neutral-400 flex items-center gap-1.5">
                      {s.status === 'running' ? <span className="text-amber-500">running…</span> : <span>{s.checked} checked</span>}
                      {s.summary.vulnerable > 0 && <span className="text-rose-500 font-semibold">{s.summary.vulnerable} vuln</span>}
                      {s.summary.edge_case > 0 && <span className="text-amber-600">{s.summary.edge_case} edge</span>}
                    </div>
                  </div>
                  <button onClick={(e) => removeScan(s.scan_id, e)} className="opacity-0 group-hover:opacity-100 text-neutral-300 hover:text-rose-500"><Trash2 size={13} /></button>
                  <ChevronRight size={13} className="text-neutral-300" />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: progress + results */}
        <div className="lg:col-span-3 space-y-4">
          {(scanning || progress.total > 0) && (
            <div>
              <div className="flex items-center justify-between text-xs text-neutral-500 mb-1">
                <span>{scanning ? 'Scanning…' : 'Done'} — {progress.checked}{progress.total ? ` / ${progress.total}` : ''} checked{domain ? ` · ${domain}` : ''}</span>
                <span className="flex items-center gap-3">
                  <span className="text-rose-600 font-semibold">{summary.vulnerable} vuln</span>
                  <span className="text-amber-600 font-semibold">{summary.edge_case} edge</span>
                  <span className="text-sky-600 font-semibold">{summary.not_vulnerable} dangling</span>
                  {wildcard && <span className="text-[11px] px-2 py-0.5 rounded bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">wildcard DNS</span>}
                  {scanId && !scanning && <button onClick={(e) => removeScan(scanId, e)} className="text-rose-400 hover:text-rose-600 inline-flex items-center gap-1"><Trash2 size={12} /> delete</button>}
                </span>
              </div>
              <div className="h-2 rounded-full bg-neutral-200 dark:bg-neutral-700 overflow-hidden">
                <div className="h-full bg-rose-500 transition-all" style={{ width: `${pct}%` }} />
              </div>
            </div>
          )}

          {results.length > 0 ? (
            <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-hidden">
              <table className="w-full text-[13px]">
                <thead className="bg-neutral-100 dark:bg-neutral-800 text-neutral-500 text-[11px] uppercase">
                  <tr>
                    <th className="text-left px-3 py-2">Subdomain</th>
                    <th className="text-left px-3 py-2">Verdict</th>
                    <th className="text-left px-3 py-2">Service</th>
                    <th className="text-left px-3 py-2 w-48">Note</th>
                    <th className="px-2 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={r.id || i} className="border-t border-neutral-100 dark:border-neutral-800 align-top group">
                      <td className="px-3 py-2 font-mono text-neutral-700 dark:text-neutral-200 break-all">{r.subdomain}
                        {r.cname_target && <div className="text-[10px] text-neutral-400">→ {r.cname_target}</div>}
                      </td>
                      <td className="px-3 py-2"><Badge verdict={r.verdict} /><div className="text-[10px] text-neutral-400 mt-0.5">{r.confidence}</div></td>
                      <td className="px-3 py-2 text-neutral-600 dark:text-neutral-300">{r.service}
                        {r.documentation && <a href={r.documentation} target="_blank" rel="noreferrer" className="ml-1 text-sky-500 inline-flex"><ExternalLink size={11} /></a>}
                        {r.evidence && <div className="text-[10px] text-neutral-400 mt-0.5 line-clamp-2">{r.evidence}</div>}
                      </td>
                      <td className="px-3 py-2"><NoteCell result={r} onSave={saveNote} /></td>
                      <td className="px-2 py-2 text-right">
                        {r.id && <button onClick={() => removeResult(r.id)} className="opacity-0 group-hover:opacity-100 text-neutral-300 hover:text-rose-500"><Trash2 size={13} /></button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (!scanning && progress.total > 0 && (
            <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 p-8 text-center text-neutral-400 text-sm">
              No takeover candidates found across {progress.total} subdomains. 🎉
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
