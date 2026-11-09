import { utcDate } from '../utils/utcDate';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Code2, GitBranch, ShieldCheck, FileSearch, Plus, RefreshCw, Download, ArrowRight } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import service from '../services/appsecService';
import aiModelService from '../services/aiModelService';

const active = status => ['queued', 'running'].includes(status);
const field = 'w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 p-2.5 text-sm';
const muted = 'text-sm text-neutral-600 dark:text-neutral-300';
function message(error) { return typeof error.response?.data?.detail === 'string' ? error.response.data.detail : 'Request failed. Check your connection and try again.'; }
function Badge({ children }) {
  const tone = { critical: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200', high: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200', medium: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200', completed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200', failed: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200', partial: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200' }[children] || 'bg-neutral-100 dark:bg-neutral-700';
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${tone}`}>{String(children).replaceAll('_', ' ')}</span>;
}

export default function AppSec() {
  const { user } = useAuth();
  const readOnly = user?.role === 'viewer';
  const admin = user?.role === 'admin';
  const [params, setParams] = useSearchParams();
  const projectId = params.get('project');
  const scanId = params.get('scan');
  const [projects, setProjects] = useState([]);
  const [scans, setScans] = useState([]);
  const [scan, setScan] = useState(null);
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [preparing, setPreparing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [repository, setRepository] = useState('');
  const [ref, setRef] = useState('main');
  const [source, setSource] = useState('repository');
  const [file, setFile] = useState(null);
  const [commit, setCommit] = useState('');
  const [model, setModel] = useState('');
  const [consent, setConsent] = useState(false);
  const [tab, setTab] = useState('findings');
  const [filter, setFilter] = useState('all');
  const [tick, setTick] = useState(0);
  const project = projects.find(p => String(p.id) === projectId);

  useEffect(() => { setRef(project?.default_branch || 'main'); }, [project?.id, project?.default_branch]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    service.projects().then(rows => { if (alive) { setProjects(rows); setError(null); } })
      .catch(err => { if (alive) setError(message(err)); }).finally(() => { if (alive) setLoading(false); });
    if (admin) aiModelService.list().then(rows => { if (alive) setModels(rows.filter(m => m.enabled)); }).catch(() => {});
    return () => { alive = false; };
  }, [admin, tick]);

  useEffect(() => {
    if (!projectId && projects.length) setParams({ project: String(projects[0].id) }, { replace: true });
  }, [projects, projectId, setParams]);

  useEffect(() => {
    setPreparing(false); setScans([]); setScan(null); setError(null); setNotice(null); setFilter('all');
    setSource('repository'); setFile(null); setCommit(''); setModel(''); setConsent(false);
  }, [projectId]);

  useEffect(() => {
    let alive = true, timer;
    setScan(null);
    if (!projectId) return;
    async function refresh() {
      let repeat = true;
      try {
        const rows = await service.scans(projectId);
        if (!alive) return;
        setScans(rows);
        if (!scanId && rows.length) {
          setParams({ project: projectId, scan: String(rows[0].id) }, { replace: true });
          return;
        }
        if (scanId) {
          if (!rows.some(r => String(r.id) === scanId)) throw new Error('Scan outside project');
          const detail = await service.scan(scanId);
          if (!alive) return;
          setScan(detail);
          if (!active(detail.status)) setNotice(previous => previous?.startsWith('Scan queued.') ? null : previous);
        }
        setError(null);
        repeat = rows.some(r => active(r.status));
      } catch (err) { if (alive) setError(message(err)); }
      finally { if (alive && repeat) timer = setTimeout(refresh, 5000); }
    }
    refresh();
    return () => { alive = false; clearTimeout(timer); };
  }, [projectId, scanId, tick, setParams]);

  async function perform(fn) {
    setBusy(true); setError(null); setNotice(null);
    try { await fn(); } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }
  async function create(event) {
    event.preventDefault();
    await perform(async () => {
      const row = await service.create({ name: name.trim(), repository_url: repository.trim() });
      setProjects(rows => [row, ...rows]); setParams({ project: String(row.id) });
      setCreating(false); setName(''); setRepository('');
    });
  }
  async function start(event) {
    event.preventDefault();
    const upload = source === 'upload' || !project.repository_url;
    if (upload && (!file || !/^[a-fA-F0-9]{40}$/.test(commit))) { setError('Choose a ZIP and enter the full 40-character commit SHA.'); return; }
    if (file && file.size > 10 * 1024 * 1024) { setError('ZIP exceeds 10 MiB. Submit a smaller snapshot.'); return; }
    await perform(async () => {
      const options = { model_config_id: model ? Number(model) : null, allow_source_to_model: Boolean(model && consent) };
      const row = upload ? await service.upload(project.id, file, { commit, ...options })
        : await service.start(project.id, { ref, ...options });
      setParams({ project: projectId, scan: String(row.id) });
      setPreparing(false);
      setNotice('Scan queued. Progress updates automatically. You can leave this page.');
    });
  }
  async function report(format) {
    await perform(async () => {
      const blob = await service.report(scan.id, format), url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = `appsec-${scan.id}.${format}`;
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
    });
  }
  const summary = scan?.summary || {};
  const findings = scan?.findings || [];
  const visible = findings.filter(f => filter === 'all' || f.category === filter);
  const pending = scans.some(s => active(s.status));

  return <div className="mx-auto max-w-7xl space-y-5">
    <header className="aida-page-header flex flex-wrap items-start justify-between gap-4">
      <div><p className="aida-eyebrow">Secure your source</p><h1 className="text-2xl font-bold flex items-center gap-3"><Code2 className="text-primary-500" />Application Security</h1>
        <p className={`${muted} mt-2`}>Review code, spot exposed credentials and track fixes — one commit at a time.</p></div>
      <div className="flex flex-wrap gap-2"><Link className="btn btn-primary" to="/appsec/integrations"><GitBranch size={16} />Git integrations</Link><Link className="btn btn-secondary" to="/guide?doc=appsec">AppSec guide <ArrowRight size={15} /></Link></div>
    </header>
    {!scans.length && <div className="grid gap-3 sm:grid-cols-3">
      {[['Source review', 'Python AST and JavaScript / TypeScript baseline rules', Code2], ['Secret detection', 'Credential patterns with masked results', ShieldCheck], ['Dependency inventory', 'npm and Python manifests · CVEs not checked', FileSearch]].map(([title, detail, Icon]) =>
        <div key={title} className="card flex items-start gap-3"><Icon className="mt-0.5 h-5 w-5 shrink-0 text-primary-500" /><div><h2 className="font-semibold text-sm">{title}</h2><p className={`${muted} mt-1`}>{detail}</p></div></div>)}
    </div>}
    {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 dark:bg-red-950/40 p-4 text-sm text-red-700 dark:text-red-200">{error} <button className="underline ml-2" onClick={() => setTick(v => v + 1)}>Refresh data</button></div>}
    {notice && <p role="status" className="rounded-xl bg-primary-50 dark:bg-primary-950 p-4 text-sm">{notice}</p>}
    <section className="card space-y-4" aria-label="AppSec projects">
      <div className="flex flex-wrap items-end justify-between gap-3"><label className="flex-1 min-w-0 max-w-xl text-sm font-medium">Project
        <select className={`${field} mt-1`} value={projectId || ''} onChange={e => setParams({ project: e.target.value })}>
          <option value="" disabled>{loading ? 'Loading projects…' : 'Select a project'}</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select></label><div className="flex gap-2"><button className="btn btn-secondary" aria-label="Refresh AppSec" onClick={() => setTick(v => v + 1)}><RefreshCw size={16} /></button>
        {!readOnly && project && scans.length > 0 && <button className="btn btn-primary" onClick={() => setPreparing(!preparing)}><FileSearch size={16} />{preparing ? 'Close scan form' : 'New scan'}</button>}
        {!readOnly && <button className="btn btn-secondary" onClick={() => setCreating(!creating)}><Plus size={16} />{creating ? 'Close form' : 'New project'}</button>}</div></div>
      {creating && !readOnly && <form onSubmit={create} className="rounded-xl border border-neutral-200 dark:border-neutral-700 p-4 space-y-3">
        <h2 className="font-semibold">Connect a code project</h2><div className="grid gap-3 md:grid-cols-2">
          <label className="text-sm">Project name<input className={`${field} mt-1`} required maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>
          <label className="text-sm">Public repository URL (optional)<input type="url" className={`${field} mt-1`} placeholder="https://github.com/owner/repository" value={repository} onChange={e => setRepository(e.target.value)} /></label>
        </div><p className={muted}>Connect a public GitHub.com or GitLab.com repository. For private or self-hosted repositories, leave the URL empty and upload a ZIP snapshot.</p>
        <button className="btn btn-primary" disabled={busy || !name.trim()}>Create project</button>
      </form>}
      {!loading && !projects.length && !creating && <div className="py-7 text-center"><GitBranch className="mx-auto mb-3 text-primary-500" /><h2 className="text-lg font-semibold">Your code review workspace</h2><p className={`${muted} mt-2`}>{readOnly ? 'No projects yet. An auditor or administrator can add one.' : 'Create a project, choose a source snapshot and start your first review.'}</p></div>}
      {readOnly && <p className={muted}>Read-only access. You can inspect scans and download reports.</p>}
      {project && <p className={`${muted} break-all`}>{project.repository_url || 'ZIP snapshot project · private and self-hosted repositories supported through upload'}</p>}
    </section>
    {project && !readOnly && (!scans.length || preparing) && <form onSubmit={start} className="card space-y-4">
      <div><h2 className="text-lg font-semibold">Start a source review</h2><p className={`${muted} mt-1`}>Source files are inspected as text. Repository code, install scripts and tests are never executed.</p></div>
      <div className="grid gap-4 md:grid-cols-2"><label className="text-sm">Source
        <select className={`${field} mt-1`} value={project.repository_url ? source : 'upload'} onChange={e => setSource(e.target.value)}>
          {project.repository_url && <option value="repository">{project.git_connection_id ? 'Connected Git repository' : 'Fetch public repository'}</option>}<option value="upload">Upload ZIP snapshot</option>
        </select></label>
        {source === 'repository' && project.repository_url ? <label className="text-sm">Branch, tag or commit<input required className={`${field} mt-1`} value={ref} onChange={e => setRef(e.target.value)} maxLength={160} /></label>
          : <label className="text-sm">Full commit SHA<input required className={`${field} mt-1 font-mono`} value={commit} onChange={e => setCommit(e.target.value.trim())} pattern="[a-fA-F0-9]{40}" placeholder="40-character Git commit hash" /></label>}
      </div>
      {(source === 'upload' || !project.repository_url) && <div className="rounded-xl border border-dashed border-neutral-300 dark:border-neutral-600 p-4"><label className="block text-sm font-medium">Source ZIP<input className="mt-2 block w-full text-sm" type="file" accept=".zip,application/zip" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
        <p className={`${muted} mt-3`}>Create with <code>git archive --format=zip HEAD -o source.zip</code>. Use <code>git rev-parse HEAD</code> for the commit. Maximum 10 MiB ZIP / 20 MiB unpacked. Uploaded commit identity is supplied by you.</p></div>}
      {admin && <div className="rounded-xl bg-neutral-50 dark:bg-neutral-900/60 p-4 space-y-3"><label className="block text-sm font-medium">AI Review (optional)
        <select className={`${field} mt-1`} value={model} onChange={e => { setModel(e.target.value); setConsent(false); }}><option value="">Local baseline only · no AI transfer</option>{models.map(m => <option value={m.id} key={m.id}>{m.name} · {m.model}</option>)}</select></label>
        {model && <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} required /><span>I authorize sending up to 20 code files / 40,000 characters to the selected model provider. Recognized secret patterns are masked; masking cannot guarantee removal of all sensitive data. AI findings require human review.</span></label>}
      </div>}
      <div className="flex flex-wrap items-center gap-3"><button className="btn btn-primary" disabled={busy || pending || Boolean(model && !consent) || (source === 'repository' && project.git_allowed === false)}><FileSearch size={16} />{busy ? 'Working…' : 'Start review'}</button><p className={muted}>{source === 'repository' && project.git_allowed === false ? 'Git access is disabled. Ask an administrator to allow this repository in Git integrations.' : pending ? 'A scan is already active for this project.' : 'Runs independently of the pentest runner. No network testing of the application.'}</p></div>
    </form>}
    {project && <div className="grid gap-5 lg:grid-cols-[230px_1fr]">
      <aside className="card self-start"><h2 className="font-semibold">Scan history</h2><p className={`${muted} mt-1 mb-4`}>Latest 100 scans</p>
        {!scans.length ? <p className={muted}>No scans recorded yet.</p> : <nav aria-label="AppSec scan history" className="space-y-2 max-h-[70vh] overflow-y-auto">{scans.map(s => <button key={s.id} onClick={() => setParams({ project: projectId, scan: String(s.id) })} className={`w-full text-left rounded-xl border p-3 ${String(s.id) === scanId ? 'border-primary-500 bg-primary-50 dark:bg-primary-950' : 'border-neutral-200 dark:border-neutral-700'}`}>
          <div className="flex flex-wrap justify-between gap-2"><strong className="text-sm">Scan #{s.id}</strong><Badge>{s.status}</Badge></div><p className="mt-2 text-xs break-all font-mono">{s.commit_sha?.slice(0, 12) || s.requested_ref}</p><p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{utcDate(s.created_at + (s.created_at?.endsWith('Z') ? '' : 'Z')).toLocaleString()}</p>
        </button>)}</nav>}
      </aside>
      <section className="min-w-0 space-y-4" aria-label="AppSec results">
        {!scan ? <div className="card"><h2 className="font-semibold">Results live here</h2><p className={`${muted} mt-2`}>Select a scan to inspect its findings, coverage and dependency inventory.</p></div> : <>
          <div className="card space-y-3"><div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-lg font-semibold">Scan #{scan.id} <Badge>{scan.status}</Badge></h2><p className={`${muted} mt-2 break-all font-mono`}>{scan.commit_sha || scan.requested_ref}</p></div>
            {active(scan.status) && !readOnly && <button className="btn btn-secondary" disabled={busy} onClick={() => perform(async () => { await service.cancel(scan.id); setTick(t => t + 1); })}>Cancel scan</button>}
            {['completed', 'partial'].includes(scan.status) && <div className="flex flex-wrap gap-2">{['json', 'html', 'sarif'].map(f => <button className="btn btn-secondary" key={f} disabled={busy} onClick={() => report(f)}><Download size={14} />{f.toUpperCase()}</button>)}</div>}</div>
            {active(scan.status) && <p role="status" className={muted}>Analysis in progress. Updates every 5 seconds. Cancellation discards results; an in-flight provider request may still finish.</p>}
            {scan.error && <p role="alert" className="text-sm text-red-600 dark:text-red-300">{scan.error}</p>}
            {['completed', 'partial'].includes(scan.status) && <><div className="flex flex-wrap gap-2"><Badge>{`${findings.length} findings`}</Badge><Badge>{`${summary.new_findings || 0} new vs baseline`}</Badge><Badge>{`${summary.text_files || 0} text files`}</Badge></div><p className={muted}>Findings are review candidates, not confirmed exploits. A completed scan does not prove the code is secure.</p></>}
          </div>
          {['completed', 'partial'].includes(scan.status) && <><nav aria-label="AppSec result sections" className="flex flex-wrap gap-2">{['findings', 'dependencies', 'coverage'].map(t => <button key={t} className={`btn ${tab === t ? 'btn-primary' : 'btn-secondary'}`} aria-pressed={tab === t} onClick={() => setTab(t)}>{t[0].toUpperCase() + t.slice(1)}</button>)}</nav>
          {tab === 'findings' && <div className="space-y-3"><label className="block text-sm">Filter findings<select className={`${field} mt-1 max-w-xs`} value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All categories</option><option value="code">Source rules</option><option value="secrets">Secrets</option><option value="ai">AI review</option></select></label>
            {!visible.length && <p className={`card ${muted}`}>No findings in this view. Check Coverage for skipped files and analysis limits.</p>}
            {visible.map(f => <article key={f.id} className="card space-y-3"><div className="flex flex-wrap items-center gap-2"><Badge>{f.severity}</Badge><Badge>{f.category}</Badge><h3 className="font-semibold">{f.title}</h3></div><p className="text-sm font-mono break-all text-primary-700 dark:text-primary-300">{f.path}:{f.line}</p><p className={muted}>{f.description}</p><div className="rounded-xl bg-neutral-50 dark:bg-neutral-900/60 p-3"><h4 className="text-xs font-semibold uppercase tracking-wide mb-1">Recommended fix</h4><p className={muted}>{f.recommendation}</p></div>
              <div className="flex flex-wrap gap-3 items-center"><span className="text-xs text-neutral-500 dark:text-neutral-400">Confidence: {f.confidence} · {f.rule_id}</span>
                {readOnly ? <Badge>{f.status}</Badge> : <label className="text-sm">Review status<select aria-label={`Review status for finding ${f.id}`} className={`${field} mt-1`} value={f.status} disabled={busy} onChange={e => { const status = e.target.value; perform(async () => { const updated = await service.triage(f.id, status); setScan(current => ({ ...current, findings: current.findings.map(x => x.id === f.id ? updated : x) })); }); }}>{['open', 'confirmed', 'false_positive', 'accepted_risk'].map(s => <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>)}</select></label>}
                {f.task_id ? <Link className="btn btn-secondary" to="/board">Task #{f.task_id} on Kanban</Link> : !readOnly && <button className="btn btn-secondary" disabled={busy} onClick={() => perform(async () => { const result = await service.task(f.id); setScan(current => ({ ...current, findings: current.findings.map(x => x.id === f.id ? { ...x, task_id: result.task_id } : x) })); setNotice(`Task #${result.task_id} created in Backlog. It will not run automatically.`); })}>Create fix task</button>}
              </div></article>)}
          </div>}
          {tab === 'dependencies' && <div className="card"><h3 className="font-semibold">Dependency inventory</h3><p className={`${muted} mt-2`}>Declared and locked packages from supported manifests. Versions have not been matched against vulnerability advisories.</p><div className="overflow-x-auto mt-4"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Package</th><th className="p-2">Version / constraint</th><th className="p-2">Source</th></tr></thead><tbody>{(summary.dependencies || []).map((d, i) => <tr key={i} className="border-t border-neutral-200 dark:border-neutral-700"><td className="p-2 break-all">{d.name}<span className="block text-xs">{d.ecosystem} · {d.kind}</span></td><td className="p-2 break-all">{d.version}</td><td className="p-2 break-all">{d.path}</td></tr>)}</tbody></table></div>{!summary.dependencies?.length && <p className={`${muted} mt-4`}>No packages found in supported manifests.</p>}</div>}
          {tab === 'coverage' && <div className="card space-y-3"><h3 className="font-semibold">What was checked</h3><p className={muted}>Engine: {summary.engine_version} · {summary.python_files || 0} Python files · {summary.javascript_files || 0} JavaScript / TypeScript files. Secret patterns checked across {summary.text_files || 0} text files.</p><p className={muted}>AI: {summary.ai?.status?.replaceAll('_', ' ')}{summary.ai?.files_selected != null && ` · ${summary.ai.files_selected} files selected`}. {summary.ai?.scope}</p><p className={muted}>Commit identity: {summary.commit_provenance?.replaceAll('_', ' ')}. ZIP uploads are not verified against the Git provider.</p><p className={`${muted} break-all`}>Archive SHA-256: {scan.archive_sha256}</p><p className={muted}>Comparison: {summary.baseline_scan_id ? `scan #${summary.baseline_scan_id}` : 'no previous completed scan'}. Fingerprints use rule, path and line; moving code may appear as a new finding.</p><p className={muted}>Skipped: {Object.entries(summary.skipped || {}).map(([reason, count]) => `${count} ${reason}`).join(', ') || 'none'}.</p><p className={muted}>Baseline rules do not provide full data-flow analysis. Other languages receive secret checks only unless selected for AI review. No dependency CVE lookup or dynamic execution.</p>{summary.warnings?.map((w, i) => <p key={i} role="alert" className="text-sm text-amber-700 dark:text-amber-300">{w}</p>)}</div>}
          </>}
        </>}
      </section>
    </div>}
  </div>;
}
