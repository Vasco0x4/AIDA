const GROUPS = [
  ['new', 'New', 'First observed in this run', 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300'],
  ['recurring', 'Recurring', 'Observed in an earlier run and this run', 'bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300'],
  ['remediated', 'Remediated', 'Observed previously but not in this completed run', 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300'],
  ['reopened', 'Reopened', 'Previously remediated and observed again', 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300'],
];

export function DiffSummary({ summary = {} }) {
  return <div className="flex flex-wrap gap-2" aria-label="Finding change summary">
    {GROUPS.map(([key, label, , classes]) => <span key={key} className={`rounded-full px-2 py-1 text-xs font-medium ${classes}`}>
      {summary[key] || 0} {label.toLowerCase()}</span>)}
  </div>;
}

export default function FindingDelta({ diff, loading }) {
  if (loading) return <p role="status" className="text-sm text-neutral-500">Loading finding changes…</p>;
  if (!diff) return <p className="text-sm text-neutral-500">The run diff is not final yet. No change counts are assumed.</p>;
  return <div className="space-y-4">
    <DiffSummary summary={diff.summary} />
    {diff.partial && <p role="alert" className="rounded bg-amber-50 p-2 text-xs text-amber-800">Partial run: failed requests are not treated as remediation.</p>}
    {GROUPS.map(([key, label, explanation, classes]) => {
      const items = diff[key] || [];
      if (!items.length) return null;
      return <section key={key} aria-labelledby={`delta-${key}`} className="overflow-hidden rounded border border-neutral-200 dark:border-neutral-700">
        <header className={`px-3 py-2 ${classes}`}><h4 id={`delta-${key}`} className="text-xs font-semibold">{label} ({items.length})</h4>
          <p className="text-xs">{explanation}</p></header>
        <ul>{items.map((item) => <li key={item.fingerprint || item.card_id} className="flex flex-wrap items-center gap-2 border-t border-neutral-100 dark:border-neutral-700 px-3 py-2 text-sm">
          <span className="rounded bg-neutral-100 dark:bg-neutral-700 px-1.5 py-0.5 text-xs font-semibold">{item.severity || 'INFO'}</span>
          <span>{item.title}</span><span className="text-xs text-neutral-500">{item.target_service}</span>
          {item.card_id && <span className="ml-auto text-xs text-neutral-400">Card #{item.card_id}</span>}
        </li>)}</ul>
      </section>;
    })}
  </div>;
}
