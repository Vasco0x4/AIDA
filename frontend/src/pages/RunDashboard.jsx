import { utcDate } from '../utils/utcDate';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Download, Pause, Play, RefreshCw, RotateCcw, Square } from 'lucide-react';
import scanRunService from '../services/scanRunService';
import { useAuth } from '../contexts/AuthContext';
import FindingDelta from '../components/runs/FindingDelta';
import RunEvents from '../components/runs/RunEvents';

const TERMINAL = new Set(['done', 'failed', 'needs_review']);

function Status({ run }) {
  return <span className={`rounded-full px-2 py-1 text-xs font-semibold ${run.status === 'failed' ? 'bg-red-100 text-red-700' : run.status === 'done' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'}`}>
    {run.meta?.paused ? 'paused' : run.status.replaceAll('_', ' ')}</span>;
}

export default function RunDashboard() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const readOnly = user?.role === 'viewer';
  const [runs, setRuns] = useState([]);
  const [run, setRun] = useState(null);
  const [findings, setFindings] = useState([]);
  const [diff, setDiff] = useState(null);
  const [loading, setLoading] = useState(Boolean(id));
  const [listLoading, setListLoading] = useState(true);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [action, setAction] = useState(null);
  const generation = useRef(0);
  const selectedIdRef = useRef(id);
  selectedIdRef.current = id;
  const previousId = useRef(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [updatedAt, setUpdatedAt] = useState(null);

  const loadRuns = useCallback(async () => {
    setListLoading(true);
    try {
      const list = await scanRunService.list({ limit: 100 });
      setRuns(list);
      if (!id && list.length) navigate(`/runs/${list[0].id}`, { replace: true });
    } catch (err) { setError(err.response?.data?.detail || 'Failed to load Scan Runs'); }
    finally { setListLoading(false); }
  }, [id, navigate]);
  useEffect(() => { loadRuns(); }, [loadRuns]);

  useEffect(() => {
    const current = ++generation.current;
    let timer;
    if (!id) { setRun(null); setFindings([]); setDiff(null); setLoading(false); setUpdatedAt(null); return; }
    if (previousId.current !== id) {
      setRun(null); setFindings([]); setDiff(null); setMessage(null); setUpdatedAt(null);
      previousId.current = id;
    }
    setLoading(true); setError(null);
    const refresh = async () => {
      if (generation.current !== current) return;
      let repeat = true;
      try {
        const [selected, evidence, delta] = await Promise.all([
          scanRunService.get(id), scanRunService.findings(id, { limit: 500 }),
          scanRunService.diff(id).catch(err => err.response?.status === 409 ? null : Promise.reject(err)),
        ]);
        if (generation.current !== current) return;
        setRun(selected); setFindings(evidence); setDiff(delta); setError(null); setUpdatedAt(utcDate());
        setRuns(previous => previous.map(item => item.id === selected.id ? selected : item));
        repeat = !TERMINAL.has(selected.status);
      } catch {
        if (generation.current !== current) return;
        setError('Live update unavailable. Displayed results may be outdated. Retrying automatically.');
      } finally {
        if (generation.current === current) {
          setLoading(false);
          if (repeat) timer = window.setTimeout(refresh, 10000);
        }
      }
    };
    refresh();
    return () => { generation.current += 1; window.clearTimeout(timer); };
  }, [id, refreshTick]);

  const mutate = async (name) => {
    const selectedId = Number(id);
    generation.current += 1;
    setAction(name); setError(null); setMessage(null);
    try {
      const updated = await scanRunService[name](selectedId);
      if (Number(selectedIdRef.current) !== selectedId) return;
      setRun(updated);
      setMessage(`${name} requested for Scan Run #${selectedId}; current status: ${updated.meta?.paused ? 'paused' : updated.status}.`);
      await loadRuns();
    } catch (err) { setError(err.response?.data?.detail || `Failed to ${name} Scan Run`); }
    finally { setAction(null); setRefreshTick(value => value + 1); }
  };
  const exportReport = async () => {
    setAction('report'); setError(null);
    try {
      const blob = await scanRunService.report(Number(id), 'html');
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = `scan-run-${id}.html`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) { setError(err.response?.data?.detail || 'Report export failed'); }
    finally { setAction(null); }
  };

  const paused = Boolean(run?.meta?.paused);
  return <div className="space-y-5">
    <div className="aida-page-header flex flex-wrap items-center justify-between gap-3"><div><p className="aida-eyebrow">Execution history</p>
      <h1 className="text-2xl font-semibold">Scan Runs</h1>
      <p className="text-sm text-neutral-500">Each scan run records one execution: its status, findings, evidence and changes since the previous scan.</p>
      {readOnly && <p className="text-xs text-neutral-500">Read-only: viewer role cannot control runs.</p>}</div>
      <Link to="/schedules" className="text-sm text-primary-600 hover:underline">Manage schedules</Link></div>
    {id && <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-500 dark:text-neutral-400" role="status"><span>{updatedAt ? `Updated ${updatedAt.toLocaleTimeString()} · ${TERMINAL.has(run?.status) ? 'Run finished' : 'Refreshes every 10 seconds'}` : 'Waiting for run data…'}</span><button className="btn btn-secondary" disabled={loading || Boolean(action)} onClick={() => setRefreshTick(value => value + 1)}>Refresh run</button></div>}
    {error && <div role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">{error}</div>}
    {message && <div role="status" className="rounded bg-blue-50 p-3 text-sm text-blue-700 dark:bg-blue-900/20 dark:text-blue-300">{message}</div>}
    <div className="grid gap-5 xl:grid-cols-[280px_1fr]">
      <aside aria-label="Scan Run list" className="rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-3">
        <div className="flex items-center justify-between"><h2 className="text-sm font-semibold">Recent runs</h2>
          <button type="button" onClick={loadRuns} aria-label="Refresh Scan Runs"><RefreshCw aria-hidden="true" className="h-4 w-4" /></button></div>
        {listLoading ? <p role="status" className="mt-3 text-xs text-neutral-500">Loading runs…</p> : runs.length === 0 ? <p className="mt-3 text-xs text-neutral-500">No runs yet.</p> :
          <nav className="mt-2 max-h-[70vh] space-y-1 overflow-y-auto">{runs.map((item) => <Link key={item.id} to={`/runs/${item.id}`}
            className={`block rounded p-2 text-xs ${Number(id) === item.id ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-300' : 'hover:bg-neutral-50 dark:hover:bg-neutral-700'}`}>
            <strong>#{item.id} {item.title}</strong><span className="mt-1 block text-neutral-500">{item.meta?.paused ? 'paused' : item.status} · Assessment #{item.assessment_id}</span>
          </Link>)}</nav>}
      </aside>
      <main className="min-w-0 space-y-5">
        {loading ? <p role="status" className="rounded border border-neutral-200 dark:border-neutral-700 p-6 text-sm text-neutral-500">Loading Scan Run…</p> : !run ? <section className="aida-page-header"><h2 className="text-lg font-semibold">{runs.length ? 'Choose a run to inspect' : 'Your scan history starts here'}</h2><p className="aida-description">{runs.length ? 'Select an execution from Recent runs to review findings and evidence.' : 'No scan executions are recorded yet. Configure a scan in Scheduler, or use Task Board for general agent tasks.'}</p><Link to="/schedules" className="btn btn-primary mt-4">Open Scheduler</Link></section> : <>
          <section className="rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">#{run.id} {run.title}</h2><Status run={run} /></div>
              <p className="mt-1 break-all text-sm text-neutral-500">{run.target || 'No target recorded'}</p>
              <Link to={`/assessments/${run.assessment_id}`} className="mt-2 inline-block text-sm text-primary-600 hover:underline">Open Assessment #{run.assessment_id}</Link>
              {run.result_summary && <p className="mt-3 text-sm">{run.result_summary}</p>}</div>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={exportReport} disabled={Boolean(action)} className="flex items-center gap-1 rounded border border-neutral-300 dark:border-neutral-600 px-2 py-1 text-xs"><Download aria-hidden="true" className="h-3 w-3" /> Export HTML</button>
                {!readOnly && paused && <button type="button" onClick={() => mutate('resume')} disabled={Boolean(action)} className="flex items-center gap-1 rounded bg-primary-600 px-2 py-1 text-xs text-white"><Play aria-hidden="true" className="h-3 w-3" /> Resume run</button>}
                {!readOnly && !paused && ['queued', 'running'].includes(run.status) && <>
                  <button type="button" onClick={() => mutate('pause')} disabled={Boolean(action)} className="flex items-center gap-1 rounded border border-neutral-300 dark:border-neutral-600 px-2 py-1 text-xs"><Pause aria-hidden="true" className="h-3 w-3" /> Pause run</button>
                  <button type="button" onClick={() => { if (window.confirm('Cancel this Scan Run? Its evidence is retained.')) mutate('cancel'); }} disabled={Boolean(action)} className="flex items-center gap-1 rounded border border-red-300 px-2 py-1 text-xs text-red-600"><Square aria-hidden="true" className="h-3 w-3" /> Cancel run</button>
                </>}
                {!readOnly && TERMINAL.has(run.status) && <button type="button" onClick={() => mutate('retry')} disabled={Boolean(action)} className="flex items-center gap-1 rounded border border-neutral-300 dark:border-neutral-600 px-2 py-1 text-xs"><RotateCcw aria-hidden="true" className="h-3 w-3" /> Retry run</button>}
              </div></div>
          </section>
          <section aria-labelledby="run-delta-heading" className="rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-4">
            <h3 id="run-delta-heading" className="mb-3 font-semibold">Finding changes</h3><FindingDelta diff={diff} loading={false} />
          </section>
          <section aria-labelledby="run-evidence-heading" className="rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-4">
            <h3 id="run-evidence-heading" className="font-semibold">Finding evidence ({findings.length})</h3>
            {findings.length === 0 ? <p className="mt-3 text-sm text-neutral-500">No finding snapshots recorded.</p> : <div className="mt-3 space-y-3">{findings.map((finding) => <article key={finding.id} className="rounded border border-neutral-200 dark:border-neutral-700 p-3">
              <div className="flex flex-wrap items-center gap-2"><span className="rounded bg-neutral-100 dark:bg-neutral-700 px-1.5 py-0.5 text-xs font-semibold">{finding.severity}</span>
                <h4 className="font-medium">{finding.title}</h4><span className="text-xs text-neutral-500">{finding.lifecycle_status}</span></div>
              <p className="mt-1 break-all text-xs text-neutral-500">{finding.target_service}</p>
              {finding.technical_analysis && <p className="mt-2 text-sm">{finding.technical_analysis}</p>}
              {finding.proof && <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-50 dark:bg-neutral-900 p-2 text-xs">{finding.proof}</pre>}
            </article>)}</div>}
          </section>
          <RunEvents key={run.id} runId={run.id} refreshToken={updatedAt?.getTime()} />
        </>}
      </main>
    </div>
  </div>;
}
