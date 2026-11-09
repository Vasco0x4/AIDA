import { utcDate } from '../../utils/utcDate';
import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import scanRunService from '../../services/scanRunService';

export default function RunEvents({ runId, refreshToken }) {
  const generation = useRef(0);
  const historyInitialized = useRef(false);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [error, setError] = useState(null);
  const [hasEarlier, setHasEarlier] = useState(false);

  const load = useCallback(async () => {
    const current = ++generation.current;
    setError(null);
    try {
      const page = await scanRunService.events(runId, { limit: 100 });
      if (current !== generation.current) return;
      setEvents(previous => Array.from(new Map([...previous, ...page].map(event => [event.id, event])).values()).sort((a, b) => a.id - b.id));
      if (!historyInitialized.current) { setHasEarlier(page.length === 100); historyInitialized.current = true; }
    } catch (err) { if (current === generation.current) setError(err.response?.data?.detail || 'Failed to load run events'); }
    finally { if (current === generation.current) setLoading(false); }
  }, [runId]);
  useEffect(() => { load(); return () => { generation.current += 1; }; }, [load, refreshToken]);

  const earlier = async () => {
    if (!events.length) return;
    setLoadingEarlier(true); setError(null);
    try {
      const beforeId = events[0].id;
      const page = await scanRunService.events(runId, { beforeId, limit: 100 });
      setEvents(previous => Array.from(new Map([...page, ...previous].map(event => [event.id, event])).values()).sort((a, b) => a.id - b.id));
      setHasEarlier(page.length === 100);
    } catch (err) { setError(err.response?.data?.detail || 'Failed to load earlier events'); }
    finally { setLoadingEarlier(false); }
  };

  return <section aria-labelledby="run-events-heading" className="rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-4">
    <div className="flex items-center justify-between"><h3 id="run-events-heading" className="font-semibold">Run events</h3>
      <button type="button" onClick={load} className="rounded p-2 text-neutral-500" aria-label="Refresh events"><RefreshCw aria-hidden="true" className="h-4 w-4" /></button></div>
    {error && <p role="alert" className="mt-2 text-sm text-red-600">{error}</p>}
    {loading ? <p role="status" className="mt-3 text-sm text-neutral-500">Loading events…</p> : <>
      {hasEarlier && <button type="button" onClick={earlier} disabled={loadingEarlier}
        className="mt-2 text-xs text-primary-600 hover:underline disabled:opacity-50">{loadingEarlier ? 'Loading…' : 'Load earlier events'}</button>}
      {events.length === 0 ? <p className="mt-3 text-sm text-neutral-500">No events recorded.</p> :
        <ol aria-label="Run events" className="mt-3 space-y-3">{events.map((event) => <li key={event.id} className="border-l-2 border-neutral-200 dark:border-neutral-600 pl-3">
          <div className="flex flex-wrap items-center gap-2"><strong className="text-xs">{event.event_type}</strong>
            <time className="text-xs text-neutral-500" dateTime={event.created_at}>{utcDate(event.created_at).toLocaleString()}</time></div>
          {event.payload && Object.keys(event.payload).length > 0 && <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-50 dark:bg-neutral-900 p-2 text-xs text-neutral-600 dark:text-neutral-300">{JSON.stringify(event.payload, null, 2)}</pre>}
        </li>)}</ol>}
    </>}
  </section>;
}
