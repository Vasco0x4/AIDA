/**
 * Settings → Knowledge base. Shows what the agent knows (skills, bug-bounty
 * reports, CVEs, playbooks), lets you sync bug-bounty writeups + ingest CVEs,
 * and preview-search the base.
 */
import React, { useEffect, useState } from 'react';
import { BookOpen, RefreshCw, Search, Download, Upload, HardDriveDownload, ExternalLink, Loader2, CheckCircle2 } from 'lucide-react';
import knowledgeService from '../../services/knowledgeService';

const SOURCE_META = {
  skill:     { label: 'Skills',             color: '#6366f1' },
  bugbounty: { label: 'Writeups',           color: '#e11d48' },
  h1report:  { label: 'HackerOne reports',  color: '#8b5cf6' },
  nvd:       { label: 'CVEs (NVD)',         color: '#f59e0b' },
  playbook:  { label: 'Playbooks',          color: '#10b981' },
};

export default function KnowledgeSection() {
  const [stats, setStats] = useState(null);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [nvdKw, setNvdKw] = useState('');

  const loadStats = () => knowledgeService.stats().then(setStats).catch(() => {});
  useEffect(() => { loadStats(); }, []);

  const syncBugbounty = async () => {
    setBusy('bugbounty'); setMsg(null);
    try {
      const r = await knowledgeService.ingestBugbounty();
      setMsg(`Synced bug-bounty reports: +${r.added} new, ${r.updated} updated.`);
      loadStats();
    } catch (e) {
      setMsg('Sync failed: ' + (e.response?.data?.detail || e.message));
    } finally { setBusy(null); }
  };

  const ingestNvd = async () => {
    if (!nvdKw.trim()) return;
    setBusy('nvd'); setMsg(null);
    try {
      const r = await knowledgeService.ingestNvd(nvdKw.trim());
      setMsg(`Ingested ${r.ingested} CVEs for "${nvdKw}".`);
      setNvdKw(''); loadStats();
    } catch (e) {
      setMsg('CVE ingest failed: ' + (e.response?.data?.detail || e.message));
    } finally { setBusy(null); }
  };

  const runSearch = async () => {
    if (!q.trim()) return;
    setSearching(true);
    try { setResults(await knowledgeService.search(q.trim(), { limit: 15 })); }
    finally { setSearching(false); }
  };

  const exportKb = async () => {
    setBusy('export'); setMsg(null);
    try {
      const blob = await knowledgeService.exportBlob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'aida_knowledge_all.jsonl.gz';
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
      setMsg('Exported the knowledge base (compact .jsonl.gz).');
    } catch (e) { setMsg('Export failed: ' + (e.response?.data?.detail || e.message)); }
    finally { setBusy(null); }
  };

  const importKb = async (file) => {
    if (!file) return;
    setBusy('import'); setMsg(null);
    try {
      const r = await knowledgeService.importFile(file);
      setMsg(`Imported: +${r.added} new, ${r.updated} updated.`);
      loadStats();
    } catch (e) { setMsg('Import failed: ' + (e.response?.data?.detail || e.message)); }
    finally { setBusy(null); }
  };

  const field = 'rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-800 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-sky-500/60';

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-neutral-800 dark:text-neutral-100 flex items-center gap-2">
          <BookOpen size={18} /> Knowledge base
        </h2>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">What the autonomous agent consults — methodology skills, real disclosed bug-bounty reports, CVEs. It grounds the agent in what actually worked instead of guessing.</p>
      </div>

      {/* Source counts */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {Object.entries(SOURCE_META).map(([key, m]) => (
          <div key={key} className="rounded-xl border border-neutral-200 dark:border-neutral-700 p-3">
            <div className="text-2xl font-bold" style={{ color: m.color }}>{stats?.by_source?.[key] ?? '—'}</div>
            <div className="text-[12px] text-neutral-500 dark:text-neutral-400">{m.label}</div>
          </div>
        ))}
      </div>

      {msg && (
        <div className="text-[13px] rounded-lg bg-neutral-50 dark:bg-neutral-800 px-3 py-2 text-neutral-600 dark:text-neutral-300 flex items-center gap-2">
          <CheckCircle2 size={14} className="text-emerald-500" /> {msg}
        </div>
      )}

      {/* Sync controls */}
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={syncBugbounty} disabled={busy}
          className="inline-flex items-center gap-2 px-3.5 py-2 text-sm rounded-lg bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50">
          {busy === 'bugbounty' ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          Sync bug-bounty reports
        </button>
        <div className="flex items-center gap-2">
          <input className={field} value={nvdKw} onChange={(e) => setNvdKw(e.target.value)}
            placeholder="CVE keyword, e.g. grafana" onKeyDown={(e) => e.key === 'Enter' && ingestNvd()} />
          <button onClick={ingestNvd} disabled={busy} className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300 disabled:opacity-50">
            {busy === 'nvd' ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} Ingest CVEs
          </button>
        </div>
        <div className="w-px h-6 bg-neutral-200 dark:bg-neutral-700 hidden md:block" />
        <button onClick={exportKb} disabled={busy} className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300 disabled:opacity-50" title="Download the whole KB as a compact .jsonl.gz">
          {busy === 'export' ? <Loader2 size={14} className="animate-spin" /> : <HardDriveDownload size={14} />} Export
        </button>
        <label className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300 cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800">
          {busy === 'import' ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} Import
          <input type="file" accept=".gz,.jsonl,.json" className="hidden" onChange={(e) => importKb(e.target.files?.[0])} />
        </label>
      </div>

      {/* Preview search */}
      <div>
        <label className="text-[11px] font-semibold uppercase text-neutral-500">Search the knowledge base</label>
        <div className="flex items-center gap-2 mt-1">
          <input className={`${field} flex-1`} value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. SSRF cloud metadata, OAuth account takeover, IDOR…" onKeyDown={(e) => e.key === 'Enter' && runSearch()} />
          <button onClick={runSearch} disabled={searching} className="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg bg-sky-600 text-white hover:bg-sky-700">
            {searching ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />} Search
          </button>
        </div>
        {results.length > 0 && (
          <div className="mt-2 space-y-1.5 max-h-80 overflow-y-auto">
            {results.map((r, i) => (
              <div key={i} className="rounded-lg border border-neutral-100 dark:border-neutral-800 px-3 py-2 text-[12px]">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded" style={{ background: `${(SOURCE_META[r.source]?.color || '#94a3b8')}1a`, color: SOURCE_META[r.source]?.color || '#94a3b8' }}>{SOURCE_META[r.source]?.label || r.source}</span>
                  <span className="text-neutral-700 dark:text-neutral-200 font-medium">{r.title}</span>
                </div>
                {r.description && <div className="text-neutral-500 dark:text-neutral-400 mt-0.5 line-clamp-2">{r.description}</div>}
                {r.references?.[0] && <a href={r.references[0]} target="_blank" rel="noreferrer" className="text-sky-500 inline-flex items-center gap-1 mt-0.5">{r.references[0].slice(0, 70)} <ExternalLink size={10} /></a>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
