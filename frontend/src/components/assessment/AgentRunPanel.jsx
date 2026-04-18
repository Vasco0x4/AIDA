import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Play,
  X,
  Loader2,
  Cpu,
  Terminal,
  Activity,
  Check,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Plus,
} from '../icons';
import agentService from '../../services/agentService';

// Collapse threshold — anything longer gets a "click to expand" wrapper.
const COLLAPSE_CHAR_LIMIT = 600;

const ACTIVE_STATUSES = new Set(['queued', 'running']);

const STATUS_STYLES = {
  queued: 'bg-neutral-200 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-200',
  running: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  completed: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  stopped: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
};

function StatusChip({ status }) {
  const cls = STATUS_STYLES[status] || STATUS_STYLES.queued;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${cls}`}>
      {status === 'running' && <Loader2 className="w-3 h-3 animate-spin" />}
      {status}
    </span>
  );
}

function formatRelative(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return d.toLocaleString();
}

function formatDuration(ms) {
  if (ms == null) return '—';
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s - m * 60);
  return `${m}m ${rem}s`;
}

function MarkdownText({ text }) {
  return (
    <div className="markdown-body text-sm text-neutral-800 dark:text-neutral-200 leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ node, ...props }) => <p className="my-1" {...props} />,
          h1: ({ node, ...props }) => <h1 className="text-base font-semibold mt-3 mb-1" {...props} />,
          h2: ({ node, ...props }) => <h2 className="text-sm font-semibold mt-3 mb-1" {...props} />,
          h3: ({ node, ...props }) => <h3 className="text-sm font-semibold mt-2 mb-1" {...props} />,
          ul: ({ node, ...props }) => <ul className="list-disc pl-5 my-1 space-y-0.5" {...props} />,
          ol: ({ node, ...props }) => <ol className="list-decimal pl-5 my-1 space-y-0.5" {...props} />,
          li: ({ node, ...props }) => <li className="leading-snug" {...props} />,
          a: ({ node, ...props }) => (
            <a className="text-primary-600 dark:text-primary-400 underline" target="_blank" rel="noreferrer" {...props} />
          ),
          code: ({ node, inline, className, children, ...props }) => {
            if (inline) {
              return (
                <code
                  className="px-1 py-0.5 rounded bg-neutral-200/70 dark:bg-neutral-700/60 font-mono text-[12px]"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code className="block font-mono text-[12px] whitespace-pre-wrap" {...props}>
                {children}
              </code>
            );
          },
          pre: ({ node, ...props }) => (
            <pre
              className="my-2 px-3 py-2 rounded-md bg-neutral-900 text-neutral-100 dark:bg-black/60 overflow-x-auto text-[12px]"
              {...props}
            />
          ),
          blockquote: ({ node, ...props }) => (
            <blockquote className="border-l-2 border-neutral-300 dark:border-neutral-600 pl-3 italic my-1" {...props} />
          ),
          table: ({ node, ...props }) => (
            <div className="overflow-x-auto my-2">
              <table className="min-w-full text-[12px] border-collapse" {...props} />
            </div>
          ),
          th: ({ node, ...props }) => (
            <th className="border border-neutral-300 dark:border-neutral-600 px-2 py-1 bg-neutral-100 dark:bg-neutral-800" {...props} />
          ),
          td: ({ node, ...props }) => (
            <td className="border border-neutral-300 dark:border-neutral-700 px-2 py-1 align-top" {...props} />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

function syntaxHighlightJSON(jsonStr) {
  // Small inline colorizer — avoids pulling in a full highlighter. Good enough
  // for tool input/result JSON, which is the only thing we feed into it.
  const escaped = jsonStr
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  return escaped.replace(
    /("(?:\\.|[^"\\])*"(?:\s*:)?)|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(\btrue\b|\bfalse\b)|(\bnull\b)/g,
    (match, str, num, bool, nul) => {
      if (str) {
        const isKey = str.endsWith(':') || /"\s*:$/.test(str);
        return `<span class="${isKey
          ? 'text-sky-600 dark:text-sky-300'
          : 'text-emerald-700 dark:text-emerald-300'}">${str}</span>`;
      }
      if (num) return `<span class="text-amber-600 dark:text-amber-300">${num}</span>`;
      if (bool) return `<span class="text-purple-600 dark:text-purple-300">${bool}</span>`;
      if (nul) return `<span class="text-neutral-500">${nul}</span>`;
      return match;
    },
  );
}

function HighlightedJSON({ value }) {
  const jsonStr = useMemo(() => {
    try {
      return typeof value === 'string' ? value : JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }, [value]);
  const html = useMemo(() => syntaxHighlightJSON(jsonStr), [jsonStr]);
  return (
    <pre
      className="font-mono text-[11px] whitespace-pre-wrap break-words"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function CollapsibleBlock({ children, charLen, label = 'output' }) {
  const longByDefault = charLen > COLLAPSE_CHAR_LIMIT;
  const [open, setOpen] = useState(!longByDefault);
  if (!longByDefault) return children;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-[11px] text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200 mb-1"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <span>{open ? 'Hide' : `Show ${charLen.toLocaleString()} chars of ${label}`}</span>
      </button>
      {open && children}
    </div>
  );
}

function TranscriptEvent({ event }) {
  const type = event.type;
  if (type === 'assistant_text') {
    const len = (event.text || '').length;
    return (
      <div className="flex gap-2">
        <span className="text-primary-600 dark:text-primary-400 font-mono text-xs shrink-0 pt-0.5">ai</span>
        <div className="flex-1 min-w-0">
          <CollapsibleBlock charLen={len} label="response">
            <MarkdownText text={event.text || ''} />
          </CollapsibleBlock>
        </div>
      </div>
    );
  }
  if (type === 'tool_use') {
    const inputStr = event.input ? JSON.stringify(event.input, null, 2) : '';
    return (
      <div className="flex gap-2 text-xs">
        <span className="text-amber-600 dark:text-amber-400 shrink-0 font-mono pt-0.5">tool</span>
        <div className="flex-1 min-w-0">
          <div className="font-mono text-neutral-700 dark:text-neutral-300">{event.name}</div>
          {event.input && (
            <div className="mt-0.5">
              <CollapsibleBlock charLen={inputStr.length} label="input">
                <HighlightedJSON value={event.input} />
              </CollapsibleBlock>
            </div>
          )}
        </div>
      </div>
    );
  }
  if (type === 'tool_result') {
    const raw = event.content;
    const text = typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2);
    const looksLikeJson =
      typeof raw !== 'string' ||
      (raw.trim().startsWith('{') || raw.trim().startsWith('['));
    return (
      <div className="flex gap-2 text-xs">
        <span className={`shrink-0 pt-0.5 font-mono ${event.is_error ? 'text-red-500' : 'text-green-600 dark:text-green-400'}`}>
          ←
        </span>
        <div className="flex-1 min-w-0">
          <CollapsibleBlock charLen={(text || '').length} label="output">
            {looksLikeJson ? (
              <HighlightedJSON value={raw} />
            ) : (
              <pre className="font-mono text-[11px] whitespace-pre-wrap break-words text-neutral-600 dark:text-neutral-300">
                {text}
              </pre>
            )}
          </CollapsibleBlock>
        </div>
      </div>
    );
  }
  if (type === 'system_init') {
    return (
      <div className="text-[11px] text-neutral-500 dark:text-neutral-400 font-mono">
        session {event.session_id} · {event.model}
      </div>
    );
  }
  if (type === 'result') {
    return (
      <div className="text-[11px] text-neutral-500 dark:text-neutral-400 font-mono">
        turns={event.num_turns} · duration={formatDuration(event.duration_ms)} · cost=${(event.total_cost_usd || 0).toFixed(4)}
      </div>
    );
  }
  return (
    <pre className="text-xs text-neutral-500 dark:text-neutral-400 whitespace-pre-wrap">
      {JSON.stringify(event, null, 2)}
    </pre>
  );
}

function TranscriptList({ events }) {
  if (!events || events.length === 0) {
    return <div className="text-xs text-neutral-400 italic">No messages yet…</div>;
  }
  return (
    <div className="space-y-2">
      {events.map((ev, idx) => (
        <TranscriptEvent key={idx} event={ev} />
      ))}
    </div>
  );
}

/**
 * Scroll container that follows new content while the user is near the bottom,
 * but respects manual scroll-up (so reading earlier events isn't yanked away).
 */
function AutoScroll({ deps = [], className = '', children }) {
  const ref = useRef(null);
  const stick = useRef(true);

  const onScroll = () => {
    const el = ref.current;
    if (!el) return;
    const slack = 40; // px
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < slack;
  };

  useEffect(() => {
    const el = ref.current;
    if (!el || !stick.current) return;
    // Defer to next frame so layout has settled after new content mounts.
    const id = requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
    return () => cancelAnimationFrame(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return (
    <div ref={ref} onScroll={onScroll} className={className}>
      {children}
    </div>
  );
}

const MODEL_OPTIONS = [
  { id: '', label: 'Default (Sonnet 4.6)', hint: 'Balanced speed and depth' },
  { id: 'claude-sonnet-4-6', label: 'Sonnet 4.6', hint: 'Balanced speed and depth' },
  { id: 'claude-opus-4-7', label: 'Opus 4.7', hint: 'Deepest reasoning, slower, pricier' },
  { id: 'claude-haiku-4-5', label: 'Haiku 4.5', hint: 'Fastest, cheapest — light tasks' },
];

function StartRunModal({ onClose, onSubmit, busy }) {
  const [goal, setGoal] = useState('');
  const [model, setModel] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const trimmed = goal.trim();
    if (!trimmed) {
      setError('Goal is required');
      return;
    }
    try {
      await onSubmit({ goal: trimmed, model: model || undefined });
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Failed to start run');
    }
  };

  const hint = MODEL_OPTIONS.find((m) => m.id === model)?.hint;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 dark:bg-black/70 backdrop-blur-sm">
      <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-strong max-w-lg w-full mx-4">
        <div className="flex items-center justify-between px-5 py-3 border-b border-neutral-200 dark:border-neutral-700">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-primary-500" />
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Start AI scan</h3>
          </div>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="px-5 py-4 space-y-3">
          <div>
            <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1">Goal</label>
            <textarea
              autoFocus
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={4}
              placeholder="e.g. Enumerate services on the in-scope hosts and flag anything with known CVEs"
              className="w-full px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1">Model</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {MODEL_OPTIONS.map((m) => (
                <option key={m.id || 'default'} value={m.id}>{m.label}</option>
              ))}
            </select>
            {hint && (
              <p className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-1">{hint}</p>
            )}
          </div>
          <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
            The agent runs headlessly in the backend. You can watch its transcript live and stop it at any time.
          </p>
          {error && (
            <div className="flex items-start gap-2 px-3 py-2 rounded bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-xs">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn btn-secondary btn-sm" disabled={busy}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              <span>Start</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/**
 * AgentRunPanel — UI-initiated Claude sessions for one assessment.
 *
 * Subscribes to WS events to update the active run's status and transcript
 * in real time. Full transcripts for completed runs are lazy-loaded on expand.
 */
export default function AgentRunPanel({ assessmentId, subscribe }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [expandedTranscript, setExpandedTranscript] = useState(null);
  const [stopping, setStopping] = useState(false);

  // Live transcript buffer keyed by run_id, so the active run fills in
  // events as WS messages arrive even before we refresh the list.
  const liveTranscripts = useRef({});

  const activeRun = runs.find((r) => ACTIVE_STATUSES.has(r.status)) || null;

  const loadRuns = useCallback(async () => {
    try {
      const data = await agentService.list(assessmentId);
      setRuns(data.runs || []);
    } catch (err) {
      console.error('Failed to load agent runs', err);
    } finally {
      setLoading(false);
    }
  }, [assessmentId]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  // WebSocket subscriptions — maintain a live transcript for the active run
  // and update status rows as events land.
  useEffect(() => {
    if (!subscribe) return;

    const upsertRun = (run) => {
      if (!run || run.assessment_id !== Number(assessmentId)) return;
      setRuns((prev) => {
        const idx = prev.findIndex((r) => r.id === run.id);
        if (idx === -1) return [run, ...prev];
        const next = [...prev];
        next[idx] = { ...next[idx], ...run };
        return next;
      });
    };

    const unsubStarted = subscribe('agent_run_started', (data) => {
      liveTranscripts.current[data.run.id] = [];
      upsertRun(data.run);
    });

    const unsubMessage = subscribe('agent_run_message', (data) => {
      const buf = liveTranscripts.current[data.run_id] || [];
      liveTranscripts.current[data.run_id] = [...buf, data.message];
      // Trigger a re-render by touching runs state with a no-op reference
      // bump so the panel reflects the new transcript length.
      setRuns((prev) => prev.map((r) => (r.id === data.run_id ? { ...r } : r)));
    });

    const unsubCompleted = subscribe('agent_run_completed', (data) => {
      upsertRun(data.run);
    });

    const unsubFailed = subscribe('agent_run_failed', (data) => {
      setRuns((prev) =>
        prev.map((r) =>
          r.id === data.run_id ? { ...r, status: 'failed', error: data.error } : r
        )
      );
    });

    const unsubStopped = subscribe('agent_run_stopped', (data) => {
      setRuns((prev) =>
        prev.map((r) => (r.id === data.run_id ? { ...r, status: 'stopped' } : r))
      );
    });

    return () => {
      unsubStarted();
      unsubMessage();
      unsubCompleted();
      unsubFailed();
      unsubStopped();
    };
  }, [subscribe, assessmentId]);

  const handleStart = async ({ goal, model }) => {
    setSubmitting(true);
    try {
      const run = await agentService.create(assessmentId, { goal, model });
      liveTranscripts.current[run.id] = [];
      setRuns((prev) => [run, ...prev]);
      setShowModal(false);
    } finally {
      setSubmitting(false);
    }
  };

  const handleStop = async (runId) => {
    setStopping(true);
    try {
      await agentService.stop(runId);
    } catch (err) {
      console.error('Failed to stop run', err);
    } finally {
      setStopping(false);
    }
  };

  const toggleExpand = async (runId) => {
    if (expandedId === runId) {
      setExpandedId(null);
      setExpandedTranscript(null);
      return;
    }
    setExpandedId(runId);
    setExpandedTranscript(null);
    try {
      const full = await agentService.get(runId);
      setExpandedTranscript(full.transcript || []);
    } catch (err) {
      console.error('Failed to load transcript', err);
      setExpandedTranscript([]);
    }
  };

  return (
    <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg">
      <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700 bg-gray-50 dark:bg-neutral-900">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-primary-500" />
            <h2 className="text-sm font-semibold text-gray-800 dark:text-neutral-100">AI Scans</h2>
            <span className="text-xs text-gray-500 dark:text-neutral-400">
              {runs.length} {runs.length === 1 ? 'run' : 'runs'}
            </span>
          </div>
          <button
            onClick={() => setShowModal(true)}
            disabled={!!activeRun}
            className="btn btn-primary btn-sm"
            title={activeRun ? 'A scan is already running' : 'Start a new AI scan'}
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New scan</span>
          </button>
        </div>
      </div>

      <div className="p-4 space-y-3">
        {loading && (
          <div className="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Loading runs…
          </div>
        )}

        {!loading && activeRun && (
          <div className="border border-primary-200 dark:border-primary-800 rounded-lg overflow-hidden">
            <div className="px-3 py-2 bg-primary-50 dark:bg-primary-900/20 flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <Activity className="w-3.5 h-3.5 text-primary-500 shrink-0" />
                <StatusChip status={activeRun.status} />
                <span className="text-xs text-neutral-700 dark:text-neutral-200 truncate">
                  {activeRun.goal}
                </span>
              </div>
              <button
                onClick={() => handleStop(activeRun.id)}
                disabled={stopping}
                className="btn btn-secondary btn-sm"
                title="Stop run"
              >
                {stopping ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />}
                <span>Stop</span>
              </button>
            </div>
            <AutoScroll
              deps={[(liveTranscripts.current[activeRun.id] || []).length]}
              className="px-3 py-3 max-h-80 overflow-y-auto bg-neutral-50 dark:bg-neutral-900/40"
            >
              <TranscriptList events={liveTranscripts.current[activeRun.id] || []} />
            </AutoScroll>
          </div>
        )}

        {!loading && runs.length === 0 && (
          <div className="py-8 text-center">
            <Terminal className="w-8 h-8 mx-auto text-neutral-300 dark:text-neutral-600 mb-2" />
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              No AI scans yet. Start one to let the agent work autonomously against this assessment.
            </p>
          </div>
        )}

        {!loading && runs.filter((r) => !ACTIVE_STATUSES.has(r.status)).length > 0 && (
          <div className="border border-neutral-200 dark:border-neutral-700 rounded-lg divide-y divide-neutral-200 dark:divide-neutral-700">
            {runs
              .filter((r) => !ACTIVE_STATUSES.has(r.status))
              .map((run) => {
                const expanded = expandedId === run.id;
                return (
                  <div key={run.id}>
                    <button
                      onClick={() => toggleExpand(run.id)}
                      className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-neutral-50 dark:hover:bg-neutral-900/40"
                    >
                      {expanded ? (
                        <ChevronDown className="w-3.5 h-3.5 text-neutral-400 shrink-0" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 text-neutral-400 shrink-0" />
                      )}
                      <StatusChip status={run.status} />
                      <span className="flex-1 min-w-0 truncate text-xs text-neutral-700 dark:text-neutral-200">
                        {run.goal}
                      </span>
                      <span className="text-[11px] text-neutral-500 dark:text-neutral-400 shrink-0">
                        {formatDuration(run.duration_ms)}
                      </span>
                      <span className="text-[11px] text-neutral-500 dark:text-neutral-400 shrink-0 w-20 text-right">
                        {formatRelative(run.created_at)}
                      </span>
                    </button>
                    {expanded && (
                      <div className="px-3 py-3 bg-neutral-50 dark:bg-neutral-900/40 border-t border-neutral-200 dark:border-neutral-700">
                        {run.status === 'failed' && run.error && (
                          <div className="mb-2 flex items-start gap-2 px-2 py-1.5 rounded bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-xs">
                            <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                            <span className="font-mono break-all">{run.error}</span>
                          </div>
                        )}
                        {expandedTranscript === null ? (
                          <div className="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            Loading transcript…
                          </div>
                        ) : (
                          <AutoScroll
                            deps={[expandedTranscript.length]}
                            className="max-h-80 overflow-y-auto"
                          >
                            <TranscriptList events={expandedTranscript} />
                          </AutoScroll>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        )}
      </div>

      {showModal && (
        <StartRunModal
          onClose={() => setShowModal(false)}
          onSubmit={handleStart}
          busy={submitting}
        />
      )}
    </div>
  );
}
