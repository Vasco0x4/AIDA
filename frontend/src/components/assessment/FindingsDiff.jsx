/**
 * Findings diff between two audits (E4) — recurring-audit regression view.
 *
 * Pick a baseline assessment; the current assessment's findings are compared
 * by (title, target) and grouped into New / Fixed / Persistent, with severity
 * drift flagged. Backs the Scheduler's cron engagements: each run becomes an
 * assessment, and this panel shows what changed since the previous run.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle, ArrowRight, ArrowUpRight, CheckCircle2, GitCompareArrows,
  RefreshCw, ShieldAlert, ShieldX,
} from 'lucide-react';
import { assessmentService } from '../../services/assessmentService';
import scheduleService from '../../services/scheduleService';

const sevChip = (sev) => {
  const s = String(sev || 'INFO').toUpperCase();
  const cls = {
    CRITICAL: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    HIGH: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
    MEDIUM: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
    LOW: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    INFO: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300',
  }[s] || 'bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300';
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${cls}`}>{s}</span>;
};

function FindingRow({ card, right }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 text-xs border-b border-neutral-100 dark:border-neutral-700/60 last:border-0">
      <div className="flex items-center gap-2 min-w-0 flex-1">
        {sevChip(card.severity)}
        <span className="truncate text-neutral-800 dark:text-neutral-200" title={card.title}>{card.title}</span>
        {card.target_service && (
          <span className="shrink-0 text-[10px] text-neutral-400 truncate max-w-[180px]">{card.target_service}</span>
        )}
      </div>
      {right}
    </div>
  );
}

export default function FindingsDiff({ assessment }) {
  const [others, setOthers] = useState([]);
  const [baselineId, setBaselineId] = useState('');
  const [diff, setDiff] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const list = await assessmentService.getAll(0, 200);
      // Baselines: every other assessment, newest first.
      setOthers((Array.isArray(list) ? list : []).filter((a) => a.id !== assessment.id));
    } catch (e) {
      setError('Failed to load assessments');
    }
  }, [assessment.id]);

  useEffect(() => { load(); }, [load]);

  const run = useCallback(async (bid) => {
    setBaselineId(bid);
    setDiff(null);
    setError(null);
    if (!bid) return;
    setBusy(true);
    try {
      setDiff(await scheduleService.diffFindings(assessment.id, bid));
    } catch (e) {
      setError(e.response?.data?.detail || 'Diff failed');
    } finally {
      setBusy(false);
    }
  }, [assessment.id]);

  // Preselect the previous run when the assessment came from a schedule.
  useEffect(() => {
    const prev = assessment.meta?.scheduled?.previous_assessment_id
      ?? assessment.task_meta?.scheduled?.previous_assessment_id;
    if (prev && others.length && !baselineId) {
      if (others.some((a) => a.id === prev)) run(String(prev));
    }
  }, [others, assessment.meta, assessment.task_meta, baselineId, run]);

  const baseline = useMemo(
    () => others.find((a) => String(a.id) === baselineId),
    [others, baselineId],
  );

  const summary = diff?.summary;

  return (
    <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg">
      <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700 bg-gray-50 dark:bg-neutral-900 flex flex-wrap items-center gap-3">
        <GitCompareArrows className="w-4 h-4 text-primary-500" />
        <h2 className="text-sm font-semibold text-gray-800 dark:text-neutral-100">Findings diff</h2>
        <span className="text-[11px] text-neutral-500 dark:text-neutral-400">
          what changed vs a previous audit (recurring engagements)
        </span>
        <div className="ml-auto flex items-center gap-2">
          <select
            value={baselineId}
            onChange={(e) => run(e.target.value)}
            className="text-xs px-2 py-1 border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-900 text-neutral-800 dark:text-neutral-200 max-w-[260px]"
          >
            <option value="">— pick baseline assessment —</option>
            {others.map((a) => (
              <option key={a.id} value={a.id}>
                #{a.id} {a.name || a.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="p-4">
        {error && (
          <div className="flex items-center gap-2 text-xs text-red-600 dark:text-red-400">
            <AlertCircle className="w-3.5 h-3.5" /> {error}
          </div>
        )}

        {!diff && !error && !busy && (
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Select a baseline assessment to compare findings — matched by title and target,
            grouped into <b>new</b>, <b>fixed</b> and <b>persistent</b>.
          </p>
        )}

        {busy && (
          <div className="flex items-center gap-2 text-xs text-neutral-500">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Diffing findings…
          </div>
        )}

        {diff && (
          <div className="space-y-4">
            {/* summary chips */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-neutral-500 dark:text-neutral-400">
                {baseline ? `#${baseline.id} ${baseline.name || ''}` : `#${diff.old_assessment?.id}`}
                <ArrowRight className="w-3 h-3 inline mx-1" />
                this audit
              </span>
              <span className="px-2 py-0.5 rounded-full bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 font-medium">
                {summary?.new ?? 0} new
              </span>
              <span className="px-2 py-0.5 rounded-full bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400 font-medium">
                {summary?.fixed ?? 0} fixed
              </span>
              <span className="px-2 py-0.5 rounded-full bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 font-medium">
                {summary?.persistent ?? 0} persistent
              </span>
              {summary?.severity_changed > 0 && (
                <span className="px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 font-medium">
                  {summary.severity_changed} severity changed
                </span>
              )}
            </div>

            {summary && summary.new === 0 && summary.fixed === 0 && summary.persistent === 0 && (
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                No findings on either side — nothing to compare.
              </p>
            )}

            {/* NEW */}
            {diff.new?.length > 0 && (
              <div className="rounded-lg border border-red-200 dark:border-red-900/50 overflow-hidden">
                <div className="px-3 py-1.5 bg-red-50 dark:bg-red-900/20 text-[11px] font-semibold text-red-700 dark:text-red-300 flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5" /> New ({diff.new.length}) — introduced since the baseline
                </div>
                {diff.new.map((c) => <FindingRow key={c.id} card={c} />)}
              </div>
            )}

            {/* FIXED */}
            {diff.fixed?.length > 0 && (
              <div className="rounded-lg border border-green-200 dark:border-green-900/50 overflow-hidden">
                <div className="px-3 py-1.5 bg-green-50 dark:bg-green-900/20 text-[11px] font-semibold text-green-700 dark:text-green-300 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Fixed ({diff.fixed.length}) — present in baseline, gone now
                </div>
                {diff.fixed.map((c) => <FindingRow key={c.id} card={c} />)}
              </div>
            )}

            {/* PERSISTENT */}
            {diff.persistent?.length > 0 && (
              <div className="rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
                <div className="px-3 py-1.5 bg-neutral-50 dark:bg-neutral-900 text-[11px] font-semibold text-neutral-600 dark:text-neutral-300 flex items-center gap-1.5">
                  <ShieldX className="w-3.5 h-3.5" /> Persistent ({diff.persistent.length}) — still open
                </div>
                {diff.persistent.map((p) => (
                  <FindingRow
                    key={p.new.id}
                    card={p.new}
                    right={p.severity_changed ? (
                      <span className="shrink-0 flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400">
                        {sevChip(p.old.severity)}
                        <ArrowUpRight className="w-3 h-3" />
                        {sevChip(p.new.severity)}
                      </span>
                    ) : undefined}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
