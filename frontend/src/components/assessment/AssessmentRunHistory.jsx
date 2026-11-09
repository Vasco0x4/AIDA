import { utcDate } from '../../utils/utcDate';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import scanRunService from '../../services/scanRunService';
import { DiffSummary } from '../runs/FindingDelta';

export default function AssessmentRunHistory({ assessmentId }) {
  const [runs, setRuns] = useState([]);
  const [selected, setSelected] = useState(null);
  const [diff, setDiff] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const list = await scanRunService.forAssessment(assessmentId, { limit: 50 });
      setRuns(list); setSelected((current) => current || list[0]?.id || null);
    } catch (err) { setError(err.response?.data?.detail || 'Failed to load Scan Runs'); }
    finally { setLoading(false); }
  }, [assessmentId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!selected) { setDiff(null); return; }
    let active = true;
    scanRunService.diff(selected).then((value) => { if (active) setDiff(value); })
      .catch(() => { if (active) setDiff(null); });
    return () => { active = false; };
  }, [selected]);

  return <section aria-labelledby="assessment-runs-heading" className="rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800">
    <div className="flex flex-wrap items-center gap-3 border-b border-neutral-200 dark:border-neutral-700 p-4">
      <div className="flex-1"><h2 id="assessment-runs-heading" className="font-semibold">Scan Run history</h2>
        <p className="text-xs text-neutral-500">Runs and finding deltas within this Assessment.</p></div>
      <button type="button" onClick={load} aria-label="Refresh Scan Runs" className="rounded p-2"><RefreshCw aria-hidden="true" className="h-4 w-4" /></button>
    </div>
    <div className="p-4">
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {loading ? <p role="status" className="text-sm text-neutral-500">Loading Scan Runs…</p> : runs.length === 0 ? <p className="text-sm text-neutral-500">No Scan Runs yet.</p> : <>
        <div className="flex flex-wrap items-center gap-3"><label htmlFor="assessment-run-select" className="text-xs font-medium">Run</label>
          <select id="assessment-run-select" value={selected || ''} onChange={(event) => setSelected(Number(event.target.value))}
            className="rounded border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-2 py-1 text-sm">
            {runs.map((run) => <option key={run.id} value={run.id}>#{run.id} — {run.status} — {utcDate(run.created_at).toLocaleString()}</option>)}
          </select>
          {selected && <Link to={`/runs/${selected}`} className="text-sm text-primary-600 hover:underline">Open run details</Link>}
          <DiffSummary summary={diff?.summary} />
        </div>
      </>}
    </div>
  </section>;
}
