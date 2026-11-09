import { utcDate } from '../utils/utcDate';
/**
 * Kanban Board — the autonomous task board.
 *
 * Columns are the workflow stages. Drag a card to a column to move it; dropping
 * into "Queued" hands it to the autonomous agent runner. When creating a task
 * you choose which integrated AI model runs it. Live updates over WebSocket.
 */
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  Plus, Play, Pause, Trash2, AlertTriangle, Server, Cpu, X,
  Inbox, Clock, Loader2, Eye, CheckCircle2, XCircle, Target, ShieldCheck, Sparkles,
  ListTree, Activity, Terminal, Camera, BookOpen, Flag, GitBranch,
  MessageSquare, Paperclip, Send, Download, FileText, Upload, Square,
  Coins, OctagonX, RefreshCw, History, Search, CalendarClock,
} from 'lucide-react';
import Drawer from '../components/common/Drawer';
import { useAuth } from '../contexts/AuthContext';
import taskService from '../services/taskService';
import aiModelService from '../services/aiModelService';
import taskExtrasService from '../services/taskExtrasService';
import { useWebSocketContext } from '../contexts/WebSocketContext';

const COLUMN_META = {
  backlog:      { label: 'Backlog',      icon: Inbox,        accent: '#94a3b8', hint: 'Captured, not ready' },
  queued:       { label: 'Queued',       icon: Clock,        accent: '#0ea5e9', hint: 'Waiting for the agent' },
  running:      { label: 'Running',      icon: Loader2,      accent: '#f59e0b', hint: 'Set by the agent' },
  needs_review: { label: 'Needs review', icon: Eye,          accent: '#8b5cf6', hint: 'Findings to triage' },
  done:         { label: 'Done',         icon: CheckCircle2, accent: '#10b981', hint: 'Completed' },
  failed:       { label: 'Failed',       icon: XCircle,      accent: '#f43f5e', hint: 'Errored / aborted' },
};

const PRIORITY = {
  critical: { label: 'Critical', color: '#e11d48', bar: '#e11d48' },
  high:     { label: 'High',     color: '#f97316', bar: '#f97316' },
  medium:   { label: 'Medium',   color: '#0ea5e9', bar: '#0ea5e9' },
  low:      { label: 'Low',      color: '#94a3b8', bar: '#cbd5e1' },
};

function Chip({ children, color, title }) {
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-md"
      style={{ background: `${color}1a`, color }}
    >
      {children}
    </span>
  );
}

function TaskCard({ readOnly, task, modelMap, childCount, onDragStart, onDragOver, onDragEnd, onDelete, onOpen, onStop }) {
  const prio = PRIORITY[task.priority] || PRIORITY.medium;
  const findings = task.meta?.findings;
  const modelName = task.model_config_id ? (modelMap[task.model_config_id] || 'model') : 'Default AI';
  const isChild = !!task.parent_task_id;
  const isParent = childCount > 0;
  const logLen = (task.meta?.log || []).length;
  return (
    <div
      draggable={!readOnly}
      onDragStart={(e) => onDragStart(e, task)}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      tabIndex={0}
      role="group"
      aria-label={`Task: ${task.title}`}
      onKeyDown={(event) => { if (event.target === event.currentTarget && ['Enter', ' '].includes(event.key)) { event.preventDefault(); onOpen(task.id); } }}
      onClick={() => onOpen(task.id)}
      className="group relative rounded-xl bg-white dark:bg-neutral-800 border border-neutral-200/80 dark:border-neutral-700 shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all cursor-pointer overflow-hidden"
    >
      <span className="absolute left-0 top-0 bottom-0 w-1" style={{ background: prio.bar }} />
      <div className="pl-3.5 pr-2.5 py-2.5">
        <div className="flex items-start justify-between gap-2">
          <p className="text-[13px] font-semibold text-neutral-800 dark:text-neutral-100 leading-snug">
            {isChild && <span className="text-indigo-500 mr-1" title={task.phase}>↳</span>}
            {task.title}
          </p>
          <div hidden={readOnly} className={readOnly ? "hidden" : "flex items-center gap-1 shrink-0 -mr-0.5"}>
            {task.status === 'running' && (
              <button
                onClick={(e) => { e.stopPropagation(); onStop(task); }}
                className="text-amber-500 hover:text-amber-600 transition"
                title="Stop — abort the agent & kill its scans"
              >
                <Square size={13} fill="currentColor" />
              </button>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(task); }}
              className="opacity-0 group-hover:opacity-100 text-neutral-300 hover:text-rose-500 transition"
              title="Delete task"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        {task.target && (
          <div className="mt-1.5 flex items-center gap-1 text-[11px] text-neutral-500 dark:text-neutral-400 font-mono">
            <Target size={11} className="shrink-0" />
            <span className="truncate">{task.target}</span>
          </div>
        )}

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          {isParent && <Chip color="#6366f1" title="Orchestrated audit"><GitBranch size={10} /> {childCount} phases</Chip>}
          {task.source === 'schedule' && (
            <Chip color="#0891b2" title={`Triggered by the Scheduler (cron engagement${task.meta?.scheduled?.run_no ? `, run #${task.meta.scheduled.run_no}` : ''})`}>
              <Clock size={10} /> cron
            </Chip>
          )}
          {task.role && <Chip color="#8b5cf6" title={`Phase: ${task.phase}`}>{task.role}</Chip>}
          {(task.dependency_ids || []).length > 0 && (
            <Chip color="#f59e0b" title={`Runs after task(s): ${task.dependency_ids.join(', ')}`}>
              <GitBranch size={10} /> {task.dependency_ids.length} prerequisite{task.dependency_ids.length === 1 ? '' : 's'}
            </Chip>
          )}
          <Chip color={prio.color} title="Priority">{prio.label}</Chip>
          {!isParent && <Chip color="#6366f1" title="AI model"><Sparkles size={10} /> {modelName}</Chip>}
          <Chip color={task.execution_target === 'host' ? '#e11d48' : '#64748b'} title="Execution target">
            {task.execution_target === 'host' ? <><Server size={10} /> host</> : <><Cpu size={10} /> container</>}
          </Chip>
          {typeof findings === 'number' && findings > 0 && (
            <Chip color="#8b5cf6" title="Findings">{findings} finding{findings > 1 ? 's' : ''}</Chip>
          )}
          {logLen > 0 && <Chip color="#0ea5e9" title="Agent activity"><Activity size={10} /> {logLen}</Chip>}
          {task.authorized_scope
            ? <Chip color="#10b981" title="Authorized scope set"><ShieldCheck size={10} /> scoped</Chip>
            : <Chip color="#f59e0b" title="No authorized scope"><AlertTriangle size={10} /> no scope</Chip>}
        </div>

        {(() => {
          const lastMs = (task.meta?.milestones || []).slice(-1)[0];
          const line = (task.status === 'running' && lastMs) ? `${lastMs.icon} ${lastMs.text}` : task.result_summary;
          return line ? (
            <p className="mt-2 text-[11px] text-neutral-500 dark:text-neutral-400 line-clamp-2 border-t border-neutral-100 dark:border-neutral-700/60 pt-2">
              {line}
            </p>
          ) : null;
        })()}
      </div>
    </div>
  );
}

const STEP_ICON = {
  start: Play, plan_start: GitBranch, plan_done: GitBranch, subtask_created: ListTree,
  thought: Sparkles, run_shell: Terminal, shell_result: Terminal, recon: BookOpen,
  finding: Flag, screenshot: Camera, blocked: AlertTriangle, error: XCircle,
  done: CheckCircle2, plan_note: BookOpen,
};

// Mirror backend _friendly_milestone so live steps surface as progress too.
function friendlyMilestone(s) {
  switch (s.kind) {
    case 'milestone': return { icon: '•', text: s.text || '' };
    case 'finding': return { icon: '🔴', text: `Finding: ${s.title || ''} (${s.severity || ''})` };
    case 'blocked': return { icon: '⛔', text: `Blocked: ${s.out_of_scope || s.error || 'out of scope'}` };
    case 'recon': return { icon: '🔎', text: `Recon: ${s.name || ''}` };
    case 'screenshot': return { icon: '📸', text: 'Screenshot captured' };
    case 'done': return { icon: '✅', text: `Phase complete — ${s.findings ?? 0} finding(s)` };
    case 'subtask_created': return { icon: '📋', text: `Planned: ${s.role || ''} — ${s.title || ''}` };
    default: return null;
  }
}

function stepLine(s) {
  if (s.command) return s.command;
  if (s.title) return s.title;
  if (s.text) return s.text;
  if (s.url) return s.url;
  if (s.note) return s.note;
  if (s.error) return s.error;
  if (s.child_id) return `${s.role || 'agent'}: ${s.title || 'sub-task'}`;
  if (s.name) return s.name;
  if (s.returncode !== undefined) return `exit ${s.returncode}`;
  return s.kind;
}

function TaskDetailDrawer({ taskId, allTasks, liveLog, modelMap, onClose, onDelete, onStop, onRecover, onRetry, onMove, readOnly }) {
  const [comments, setComments] = useState([]);
  const [files, setFiles] = useState([]);
  const [events, setEvents] = useState([]);
  const [newComment, setNewComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  const loadExtras = useCallback(async () => {
    const [c, f, e] = await Promise.all([
      taskExtrasService.listComments(taskId).catch(() => []),
      taskExtrasService.listFiles(taskId).catch(() => []),
      taskService.listEvents(taskId).catch(() => []),
    ]);
    setComments(c); setFiles(f); setEvents(e);
  }, [taskId]);
  useEffect(() => { loadExtras(); }, [loadExtras]);

  const postComment = async () => {
    if (!newComment.trim()) return;
    setBusy(true);
    try { await taskExtrasService.addComment(taskId, newComment.trim()); setNewComment(''); await loadExtras(); }
    finally { setBusy(false); }
  };
  const uploadFiles = async (fileList) => {
    setBusy(true);
    try { for (const f of Array.from(fileList)) await taskExtrasService.uploadFile(taskId, f); await loadExtras(); }
    finally { setBusy(false); }
  };

  const task = allTasks.find((t) => t.id === taskId);
  if (!task) return null;
  const children = allTasks.filter((t) => t.parent_task_id === taskId)
    .sort((a, b) => a.order_index - b.order_index);
  const persisted = task.meta?.log || [];
  // Merge persisted + live without duplicates: the board reloads on milestone
  // events, so steps already flushed to task.meta.log are also in liveLog.
  // Multiset-dedupe by kind+line so repeated identical commands still count.
  const keyOf = (s) => `${s.kind}|${stepLine(s)}`;
  const persistedCounts = {};
  persisted.forEach((s) => { const k = keyOf(s); persistedCounts[k] = (persistedCounts[k] || 0) + 1; });
  const liveCounts = {};
  const freshLive = liveLog.filter((s) => {
    const k = keyOf(s);
    liveCounts[k] = (liveCounts[k] || 0) + 1;
    return liveCounts[k] > (persistedCounts[k] || 0);
  });
  const log = [...persisted, ...freshLive];
  // Progress = curated milestones (persisted) + any live milestone-ish steps.
  const persistedMs = task.meta?.milestones || [];
  const seenMs = new Set(persistedMs.map((m) => m.text));
  const liveMs = liveLog.map(friendlyMilestone).filter((m) => m && !seenMs.has(m.text));
  const milestones = [...persistedMs, ...liveMs];
  const modelName = task.model_config_id ? (modelMap[task.model_config_id] || 'model') : 'Default AI';
  const colMeta = COLUMN_META[task.status] || {};
  const usage = task.meta?.usage;
  const usedModels = Object.keys(usage?.by_model || {});

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-neutral-900/40" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md h-full bg-white dark:bg-neutral-900 shadow-2xl border-l border-neutral-200 dark:border-neutral-800 flex flex-col">
        <div className="flex items-start justify-between gap-2 px-5 py-4 border-b border-neutral-100 dark:border-neutral-800">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: `${colMeta.accent}22`, color: colMeta.accent }}>{colMeta.label || task.status}</span>
              {task.role && <span className="text-[11px] text-indigo-500 font-medium">{task.role}</span>}
            </div>
            <h2 className="text-base font-semibold text-neutral-800 dark:text-neutral-100 mt-1">{task.title}</h2>
          </div>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-600"><X size={18} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 text-sm">
          <div className="grid grid-cols-2 gap-2 text-[12px]">
            {task.target && <div><span className="text-neutral-400">Target</span><div className="font-mono text-neutral-700 dark:text-neutral-200 break-all">{task.target}</div></div>}
            <div><span className="text-neutral-400">Model</span><div className="text-neutral-700 dark:text-neutral-200">{modelName}</div></div>
            <div><span className="text-neutral-400">Execution</span><div className="text-neutral-700 dark:text-neutral-200">{task.execution_target}</div></div>
            <div><span className="text-neutral-400">Priority</span><div className="text-neutral-700 dark:text-neutral-200">{task.priority}</div></div>
            {usage && usage.total > 0 && (
              <div className="col-span-2 flex items-center gap-1.5 text-[11px] text-neutral-500 dark:text-neutral-400">
                <Coins size={11} className="shrink-0" />
                <span>
                  {usage.total.toLocaleString()} tokens ({(usage.prompt || 0).toLocaleString()} in + {(usage.completion || 0).toLocaleString()} out)
                  {' · '}{usage.calls || 0} call{usage.calls === 1 ? '' : 's'}
                  {task.token_budget ? <>{' · budget '}{task.token_budget.toLocaleString()}</> : null}
                  {usedModels.length > 1 && <>{' · models: '}{usedModels.join(' → ')}</>}
                </span>
              </div>
            )}
            <div className="col-span-2">
              <span className="text-neutral-400">Assessment</span>
              <div>
                {task.assessment_id
                  ? <Link to={`/assessments/${task.assessment_id}`} className="text-sky-600 dark:text-sky-400 hover:underline inline-flex items-center gap-1"><Flag size={12} /> Open assessment #{task.assessment_id} (findings go here)</Link>
                  : <span className="text-neutral-400">created when the agent starts</span>}
              </div>
            </div>
          </div>

          {!readOnly && task.status !== 'running' && <label className="block text-xs font-medium">
            Move task to
            <select aria-label="Move task to" className="input mt-2" value={task.status}
              onChange={(event) => onMove(task, event.target.value)}>
              {Object.entries(COLUMN_META).filter(([key]) => key !== 'running').map(([key, value]) =>
                <option key={key} value={key}>{value.label}</option>)}
            </select>
          </label>}
          {task.authorized_scope && (
            <div><div className="text-[11px] font-semibold text-neutral-400 uppercase mb-1">Authorized scope</div>
              <p className="text-[12px] text-neutral-600 dark:text-neutral-300 font-mono bg-neutral-50 dark:bg-neutral-800 rounded-lg p-2">{task.authorized_scope}</p></div>
          )}
          {task.description && (
            <div><div className="text-[11px] font-semibold text-neutral-400 uppercase mb-1">Description / what to look for</div>
              <p className="text-[12px] text-neutral-600 dark:text-neutral-300 whitespace-pre-wrap">{task.description}</p></div>
          )}

          {(task.dependency_ids || []).length > 0 && (
            <div><div className="text-[11px] font-semibold text-neutral-400 uppercase mb-1">Prerequisites</div>
              <p className="text-[12px] text-neutral-600 dark:text-neutral-300">Runs after task(s) {task.dependency_ids.join(', ')} reach Done. Cycles are rejected.</p></div>
          )}

          {children.length > 0 && (
            <div>
              <div className="text-[11px] font-semibold text-neutral-400 uppercase mb-1.5 flex items-center gap-1"><ListTree size={12} /> Sub-tasks (run in order)</div>
              <div className="space-y-1.5">
                {children.map((c) => {
                  const cm = COLUMN_META[c.status] || {};
                  return (
                    <div key={c.id} className="flex items-center gap-2 text-[12px] rounded-lg border border-neutral-100 dark:border-neutral-800 px-2.5 py-1.5">
                      <span className="w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold" style={{ background: `${cm.accent}22`, color: cm.accent }}>{c.order_index + 1}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-neutral-700 dark:text-neutral-200 truncate">{c.title}</div>
                        <div className="text-[10px] text-neutral-400">{c.role} · {c.status}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Progress — curated, human-readable milestones */}
          <div>
            <div className="text-[11px] font-semibold text-neutral-400 uppercase mb-1.5 flex items-center gap-1"><Activity size={12} /> Progress {milestones.length > 0 && `(${milestones.length})`}</div>
            {milestones.length === 0 ? (
              <p className="text-[12px] text-neutral-400">No updates yet. The agent posts a short status after each key step.</p>
            ) : (
              <div className="space-y-1.5">
                {milestones.map((m, i) => (
                  <div key={i} className="flex items-start gap-2 text-[12px] rounded-lg bg-neutral-50 dark:bg-neutral-800/60 px-2.5 py-1.5">
                    <span className="shrink-0">{m.icon}</span>
                    <span className="text-neutral-700 dark:text-neutral-200 leading-snug">{m.text}</span>
                  </div>
                ))}
              </div>
            )}
            {log.length > 0 && (
              <button onClick={() => setShowRaw((v) => !v)} className="mt-2 text-[11px] text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 inline-flex items-center gap-1">
                <Terminal size={11} /> {showRaw ? 'Hide' : 'Show'} raw command log ({log.length})
              </button>
            )}
            {showRaw && (
              <div className="mt-1.5 space-y-1 max-h-64 overflow-y-auto rounded-lg bg-neutral-900 dark:bg-black p-2">
                {log.map((s, i) => {
                  const Icon = STEP_ICON[s.kind] || Sparkles;
                  const color = s.kind === 'finding' ? '#a78bfa' : s.kind === 'blocked' || s.kind === 'error' ? '#fb7185' : s.kind === 'shell_result' && s.returncode ? '#fbbf24' : '#38bdf8';
                  return (
                    <div key={i} className="flex items-start gap-2 text-[10.5px]">
                      <Icon size={12} className="shrink-0 mt-0.5" style={{ color }} />
                      <div className="min-w-0">
                        <span className="text-neutral-500">{s.kind}</span>
                        <span className="text-neutral-300 ml-1.5 break-all font-mono">{stepLine(s)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div>
            <div className="text-[11px] font-semibold text-neutral-400 uppercase mb-1.5 flex items-center gap-1"><History size={12} /> Lifecycle events {events.length > 0 && `(${events.length})`}</div>
            {events.length === 0 ? <p className="text-[12px] text-neutral-400">No lifecycle events recorded.</p> : (
              <div className="space-y-1 max-h-44 overflow-y-auto">
                {events.map((event) => (
                  <div key={event.id} className="text-[11px] rounded-lg bg-neutral-50 dark:bg-neutral-800/60 px-2.5 py-1.5">
                    <span className="font-medium text-neutral-700 dark:text-neutral-200">{event.event_type}</span>
                    <span className="ml-2 text-neutral-400">{utcDate(event.created_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Context files */}
          <div>
            <div className="text-[11px] font-semibold text-neutral-400 uppercase mb-1.5 flex items-center gap-1"><Paperclip size={12} /> Context files {files.length > 0 && `(${files.length})`}</div>
            <div className="space-y-1.5">
              {files.map((f) => (
                <div key={f.id} className="flex items-center gap-2 text-[12px] rounded-lg border border-neutral-100 dark:border-neutral-800 px-2.5 py-1.5">
                  <FileText size={13} className="text-neutral-400 shrink-0" />
                  <a href={taskExtrasService.fileUrl(f.id)} target="_blank" rel="noreferrer" className="flex-1 min-w-0 truncate text-neutral-700 dark:text-neutral-200 hover:text-sky-600">{f.filename}</a>
                  {f.has_text && <span className="text-[9px] text-emerald-500" title="Text extracted for the agent">✓ text</span>}
                  <a href={taskExtrasService.fileUrl(f.id)} target="_blank" rel="noreferrer" className="text-neutral-400 hover:text-sky-600"><Download size={13} /></a>
                  <button onClick={async () => { await taskExtrasService.deleteFile(f.id); loadExtras(); }} className="text-neutral-400 hover:text-rose-500"><X size={13} /></button>
                </div>
              ))}
            </div>
            <label className="mt-1.5 flex items-center gap-2 px-3 py-2 rounded-lg border border-dashed border-neutral-300 dark:border-neutral-600 cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800 text-[11px] text-neutral-500">
              <Upload size={13} /> Attach file (txt, pdf, html, md…)
              <input type="file" disabled={readOnly} multiple className="hidden" onChange={(e) => uploadFiles(e.target.files)} />
            </label>
          </div>

          {/* Comments */}
          <div>
            <div className="text-[11px] font-semibold text-neutral-400 uppercase mb-1.5 flex items-center gap-1"><MessageSquare size={12} /> Comments {comments.length > 0 && `(${comments.length})`}</div>
            <div className="space-y-2 mb-2">
              {comments.map((c) => (
                <div key={c.id} className="group text-[12px] rounded-lg bg-neutral-50 dark:bg-neutral-800 px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-neutral-500">{c.author === 'agent' ? '🤖 agent' : c.author}</span>
                    <button disabled={readOnly} onClick={async () => { await taskExtrasService.deleteComment(c.id); loadExtras(); }} className="opacity-0 group-hover:opacity-100 text-neutral-400 hover:text-rose-500"><X size={11} /></button>
                  </div>
                  <p className="text-neutral-700 dark:text-neutral-200 whitespace-pre-wrap mt-0.5">{c.body}</p>
                </div>
              ))}
              {comments.length === 0 && <p className="text-[11px] text-neutral-400">No comments. Add instructions/hints the agent will read.</p>}
            </div>
            <div className="flex items-end gap-2">
              <textarea value={newComment} onChange={(e) => setNewComment(e.target.value)} rows={2} placeholder="Add a comment / instruction…"
                className="flex-1 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-2.5 py-1.5 text-[12px] text-neutral-800 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-sky-500/50" />
              <button onClick={postComment} disabled={readOnly || busy || !newComment.trim()} className="px-2.5 py-2 rounded-lg bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-40"><Send size={14} /></button>
            </div>
          </div>

          {task.result_summary && (
            <div><div className="text-[11px] font-semibold text-neutral-400 uppercase mb-1">Summary</div>
              <p className="text-[12px] text-neutral-600 dark:text-neutral-300 whitespace-pre-wrap">{task.result_summary}</p></div>
          )}
        </div>

        <div className={readOnly ? "hidden" : "px-5 py-3 border-t border-neutral-100 dark:border-neutral-800 flex justify-between items-center gap-2"}>
          <div className="flex items-center gap-3">
            {task.status === 'running' && <>
              <button onClick={() => { onStop(task); onClose(); }} className="text-[12px] text-amber-600 hover:text-amber-700 inline-flex items-center gap-1"><Square size={12} fill="currentColor" /> Stop agent</button>
              <button onClick={() => { onRecover(task); onClose(); }} className="text-[12px] text-sky-600 hover:text-sky-700 inline-flex items-center gap-1"><RefreshCw size={12} /> Recover</button>
            </>}
            {['failed', 'needs_review', 'done'].includes(task.status) && (
              <button onClick={() => { onRetry(task); onClose(); }} className="text-[12px] text-sky-600 hover:text-sky-700 inline-flex items-center gap-1"><RefreshCw size={12} /> Retry</button>
            )}
          </div>
          <button onClick={() => { onDelete(task); onClose(); }} className="text-[12px] text-rose-500 hover:text-rose-600 inline-flex items-center gap-1"><Trash2 size={13} /> Delete task</button>
        </div>
      </div>
    </div>
  );
}

export function NewTaskModal({ models, onClose, onCreate }) {
  const [form, setForm] = useState({
    title: '', target: '', authorized_scope: '', description: '',
    priority: 'medium', execution_target: 'container', status: 'backlog',
    model_config_id: '', token_budget: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [files, setFiles] = useState([]);
  const createdTask = useRef(null);
  const uploadedCount = useRef(0);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!form.title.trim()) { setError('Title is required'); return; }
    if (!form.authorized_scope.trim()) { setError('Authorized scope is required — the agent refuses to act without it'); return; }
    setSaving(true);
    try {
      const created = createdTask.current || await onCreate({
        ...form,
        status: 'backlog',
        model_config_id: form.model_config_id ? parseInt(form.model_config_id, 10) : null,
        token_budget: form.token_budget ? parseInt(form.token_budget, 10) : null,
        source: 'ui',
      });
      createdTask.current = created;
      // Context must be complete before the runner can claim the task.
      while (created?.id && uploadedCount.current < files.length) {
        await taskExtrasService.uploadFile(created.id, files[uploadedCount.current]);
        uploadedCount.current += 1;
      }
      if (form.status === 'queued') await taskService.moveTask(created.id, 'queued', 0, created.version);
      onClose();
    } catch (err) {
      setError(`${createdTask.current ? 'Task saved in Backlog. Retry to finish attaching context and queue it. ' : ''}${err.response?.data?.detail || err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const field = 'w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-800 dark:text-neutral-100 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-sky-500/60 focus:border-sky-500';
  const label = 'text-[11px] font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400';

  return (
    <Drawer open onClose={onClose} title="New assessment task">
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
        className="w-full max-w-lg rounded-2xl bg-white dark:bg-neutral-800 shadow-2xl border border-neutral-200 dark:border-neutral-700 overflow-hidden max-h-[92vh] flex flex-col"
      >
        <fieldset disabled={saving || Boolean(createdTask.current)} className="space-y-4 overflow-y-auto">
          <div>
            <label htmlFor="task-title" className={label}>Title</label>
            <input data-initial-focus className={field} id="task-title" value={form.title} onChange={set('title')} placeholder="Test HackerOne program — example.com" autoFocus />
          </div>
          <div>
            <label htmlFor="task-target" className={label}>Target</label>
            <input className={field} id="task-target" value={form.target} onChange={set('target')} placeholder="https://example.com" />
          </div>
          <div>
            <label htmlFor="task-scope" className={label}>Authorized scope <span className="text-rose-500">*</span></label>
            <textarea className={field} rows={2} id="task-scope" value={form.authorized_scope} onChange={set('authorized_scope')} placeholder="*.example.com, 10.0.0.0/24, exclude admin.example.com" />
            <p className="text-[10px] text-neutral-400 mt-1 flex items-center gap-1"><ShieldCheck size={11} /> The agent refuses to touch anything outside this.</p>
          </div>
          <div>
            <label className={label}>Description — what to look for / instructions</label>
            <textarea className={field} rows={4} value={form.description} onChange={set('description')} placeholder={"e.g. Full web app security audit. Focus on: XSS, SQLi, auth/access-control (IDOR), SSRF. It's a Django + React app behind Cloudflare. Skip DoS."} />
            <p className="text-[10px] text-neutral-400 mt-1 flex items-center gap-1"><GitBranch size={11} /> The planner reads this and breaks the audit into ordered sub-tasks (recon → … → report), one per specialized agent.</p>
          </div>

          {/* Context file attachments */}
          <div>
            <label className={label}>Attach context files (txt, pdf, html, md…)</label>
            <label className="mt-1 flex items-center gap-2 px-3 py-2 rounded-lg border border-dashed border-neutral-300 dark:border-neutral-600 cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800 text-[12px] text-neutral-500">
              <Upload size={14} /> Choose files
              <input type="file" multiple className="hidden" onChange={(e) => setFiles([...files, ...Array.from(e.target.files)])} />
            </label>
            {files.length > 0 && (
              <div className="mt-1.5 space-y-1">
                {files.map((f, i) => (
                  <div key={i} className="flex items-center justify-between text-[11px] text-neutral-600 dark:text-neutral-300 bg-neutral-50 dark:bg-neutral-800 rounded px-2 py-1">
                    <span className="truncate flex items-center gap-1"><FileText size={11} /> {f.name}</span>
                    <button type="button" onClick={() => setFiles(files.filter((_, j) => j !== i))} className="text-neutral-400 hover:text-rose-500"><X size={12} /></button>
                  </div>
                ))}
              </div>
            )}
            <p className="text-[10px] text-neutral-400 mt-1">The agent reads these (text extracted) as context while working.</p>
          </div>

          {/* AI model selection */}
          <div>
            <label htmlFor="task-model_config_id" className={label}>AI model</label>
            <div className="relative">
              <Sparkles size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-indigo-400 pointer-events-none" />
              <select className={`${field} pl-9`} id="task-model_config_id" value={form.model_config_id} onChange={set('model_config_id')}>
                <option value="">Default model{models.find((m) => m.is_default) ? ` (${models.find((m) => m.is_default).name})` : ''}</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id} disabled={!m.has_api_key}>
                    {m.name} · {m.model}{m.has_api_key ? '' : ' (no key)'}
                  </option>
                ))}
              </select>
            </div>
            {models.length === 0 && (
              <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-1">No models yet — add one in Settings → AI Models.</p>
            )}
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label htmlFor="task-priority" className={label}>Priority</label>
              <select className={field} id="task-priority" value={form.priority} onChange={set('priority')}>
                <option value="low">Low</option><option value="medium">Medium</option>
                <option value="high">High</option><option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label htmlFor="task-execution_target" className={label}>Execution</label>
              <select className={field} id="task-execution_target" value={form.execution_target} onChange={set('execution_target')}>
                <option value="container">Container</option>
                <option value="host">Host (opt-in)</option>
              </select>
            </div>
            <div>
              <label htmlFor="task-status" className={label}>Start in</label>
              <select className={field} id="task-status" value={form.status} onChange={set('status')}>
                <option value="queued">Queued</option>
                <option value="backlog">Backlog</option>
              </select>
            </div>
            <div>
              <label htmlFor="task-token_budget" className={label}>Token budget</label>
              <input className={field} type="number" min="0" step="1000"
                id="task-token_budget" value={form.token_budget} onChange={set('token_budget')}
                placeholder="platform default" />
            </div>
          </div>
          <p className="text-[11px] text-neutral-400 -mt-1">
            Token budget: max prompt+completion tokens for this task. Empty / 0 = use the platform default (Settings → Agents).
          </p>

          {form.execution_target === 'host' && (
            <p className="text-[11px] text-rose-600 dark:text-rose-400 flex items-center gap-1.5 bg-rose-50 dark:bg-rose-900/20 rounded-lg px-3 py-2">
              <AlertTriangle size={13} className="shrink-0" /> Host execution runs outside the sandbox — only on systems you're authorized to test.
            </p>
          )}
          {error && <p className="text-sm text-rose-600 flex items-center gap-1.5"><AlertTriangle size={14} /> {error}</p>}
        </fieldset>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-neutral-100 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800/50">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700">Cancel</button>
          <button type="submit" disabled={saving} className="px-5 py-2 text-sm font-medium rounded-lg bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-50 shadow-sm">
            {saving ? 'Saving…' : createdTask.current ? 'Retry remaining steps' : 'Create task'}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

export default function Board() {
  const [columns, setColumns] = useState([]);
  const [models, setModels] = useState([]);
  const [modelMap, setModelMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [runner, setRunner] = useState(null);
  const [error, setError] = useState(null);
  const [runnerBusy, setRunnerBusy] = useState(false);
  const [query, setQuery] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [hideCompleted, setHideCompleted] = useState(false);
  const { user } = useAuth();
  const readOnly = user?.role === 'viewer';
  const canManageRunner = user?.role === 'admin';
  const refreshTimer = useRef(null);
  const loadGeneration = useRef(0);
  const [dropAt, setDropAt] = useState(null); // insertion target { col, index }
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [liveLog, setLiveLog] = useState([]);
  const { subscribe } = useWebSocketContext();

  const openTask = (id) => { setSelectedTaskId(id); setLiveLog([]); };

  const load = useCallback(async () => {
    const generation = ++loadGeneration.current;
    try {
      const [board, runnerState] = await Promise.all([taskService.getBoard(), taskService.getRunner()]);
      if (generation !== loadGeneration.current) return;
      setColumns(board.columns); setRunner(runnerState); setError(null);
    } catch (err) {
      if (generation !== loadGeneration.current) return;
      setRunner(null);
      setError(err.response?.data?.detail || 'Unable to refresh the board. Check the connection and try again.');
    } finally { if (generation === loadGeneration.current) setLoading(false); }
  }, []);
  useEffect(() => {
    load();
    if (canManageRunner) aiModelService.list().then((list) => {
      setModels(list); setModelMap(Object.fromEntries(list.map((m) => [m.id, m.name])));
    }).catch(() => setError('AI model configuration is unavailable. Refresh before creating a task.'));
    const interval = window.setInterval(load, 30000);
    return () => { window.clearInterval(interval); window.clearTimeout(refreshTimer.current); loadGeneration.current += 1; };
  }, [load, canManageRunner]);
  const scheduleRefresh = useCallback(() => {
    if (refreshTimer.current) return;
    refreshTimer.current = window.setTimeout(() => { refreshTimer.current = null; load(); }, 250);
  }, [load]);

  useEffect(() => {
    const events = ['task_created', 'task_updated', 'task_deleted', 'task_moved'];
    const unsubs = events.map((ev) => subscribe(ev, scheduleRefresh));
    // Refresh the board on milestone-worthy agent steps (not the raw firehose),
    // so cards show live status without reloading on every command.
    const MS_KINDS = ['milestone', 'finding', 'done', 'subtask_created', 'blocked'];
    unsubs.push(subscribe('agent_step', (msg) => {
      const d = msg?.data || msg;
      if (d && MS_KINDS.includes(d.kind)) scheduleRefresh();
    }));
    return () => unsubs.forEach((u) => u && u());
  }, [subscribe, scheduleRefresh]);

  // Live agent step stream for the open task, plus a light board refresh.
  useEffect(() => {
    const unsub = subscribe('agent_step', (msg) => {
      const d = msg?.data || msg;
      if (selectedTaskId && d?.task_id === selectedTaskId) {
        setLiveLog((prev) => [...prev, d].slice(-100));
      }
    });
    return () => unsub && unsub();
  }, [subscribe, selectedTaskId]);

  const onDragStart = (e, task) => {
    e.dataTransfer.setData('text/plain', String(task.id));
    e.dataTransfer.effectAllowed = 'move';
  };
  // Hovering a card: insert before/after it depending on the pointer's half.
  const onCardDragOver = (e, colKey, index) => {
    e.preventDefault();
    e.stopPropagation();
    const rect = e.currentTarget.getBoundingClientRect();
    const idx = index + (e.clientY > rect.top + rect.height / 2 ? 1 : 0);
    setDropAt((prev) => (prev && prev.col === colKey && prev.index === idx
      ? prev : { col: colKey, index: idx }));
  };
  const onDrop = async (e, colKey) => {
    e.preventDefault();
    if (readOnly || query || priorityFilter !== 'all' || sourceFilter !== 'all') return;
    const id = parseInt(e.dataTransfer.getData('text/plain'), 10);
    const target = dropAt && dropAt.col === colKey ? dropAt : null;
    setDropAt(null);
    if (!id) return;
    // "Running" is set by the agent runner itself — a manual drop there would
    // strand the task (nothing would execute it). Re-route to Queued.
    let status = colKey;
    let index = target ? target.index : null;
    if (colKey === 'running') {
      status = 'queued';
      index = null;
      alert('The Running column is set by the agent itself. The task was moved to Queued instead — the runner picks it up within seconds.');
    }
    if (index == null) {
      const col = columns.find((c) => c.key === status);
      index = col ? col.tasks.length : 0;
    }
    // Same-column reorder: insertion index counts the dragged card itself.
    const srcCol = columns.find((c) => c.tasks.some((t) => t.id === id));
    if (srcCol && srcCol.key === status) {
      const srcIdx = srcCol.tasks.findIndex((t) => t.id === id);
      if (srcIdx !== -1) {
        if (index === srcIdx || index === srcIdx + 1) return; // no-op
        if (index > srcIdx) index -= 1;
      }
    }
    const dragged = columns.flatMap((c) => c.tasks).find((t) => t.id === id);
    await moveTask(dragged, status, index);
  };
  const createTask = async (payload) => { const t = await taskService.createTask(payload); load(); return t; };
  const deleteTask = async (task) => {
    const kids = allTasks.filter((t) => t.parent_task_id === task.id).length;
    const msg = kids
      ? `Delete "${task.title}"?\n\nIts ${kids} sub-task(s) are deleted too. This cannot be undone.`
      : `Delete "${task.title}"?\n\nThis cannot be undone.`;
    if (!confirm(msg)) return;
    try { await taskService.deleteTask(task.id); await load(); }
    catch (err) { setError(err.response?.data?.detail || 'Could not delete task'); }
  };
  const stopTask = async (task) => {
    if (!confirm(`Stop "${task.title}"? This aborts the agent and kills its running scans.`)) return;
    try { await taskService.stopTask(task.id); await load(); }
    catch (err) { setError(err.response?.data?.detail || 'Could not stop task'); }
  };
  const recoverTask = async (task) => {
    if (!confirm(`Recover "${task.title}"? This fences the current worker and returns the task to Queued.`)) return;
    await taskService.recoverTask(task.id).catch((err) => alert(err.response?.data?.detail || 'Recovery failed'));
    load();
  };
  const retryTask = async (task) => {
    if (!confirm(`Retry "${task.title}"? It will return to Queued with a fresh retry budget.`)) return;
    await taskService.retryTask(task.id).catch((err) => alert(err.response?.data?.detail || 'Retry failed'));
    load();
  };
  const moveTask = async (task, status, position = 0) => {
    if (!task || readOnly) return;
    try { await taskService.moveTask(task.id, status, position, task.version); await load(); }
    catch (err) {
      await load();
      setError(err.response?.status === 409 ? 'This task changed elsewhere. Review its current state and try again.' : (err.response?.data?.detail || 'Could not move task'));
    }
  };
  const toggleRunner = async () => {
    if (!runner || runnerBusy) return;
    setRunnerBusy(true);
    try { await taskService.setRunner(!runner?.enabled); await load(); }
    catch (err) { setError(err.response?.data?.detail || 'Runner state could not be changed'); }
    finally { setRunnerBusy(false); }
  };
  const killAgents = async () => {
    const n = runner?.active || 0;
    if (!confirm(`Kill ${n} running agent${n === 1 ? '' : 's'} NOW?\n\nEvery running task is aborted and marked failed. This cannot be undone.`)) return;
    try { await taskService.killRunner(); await load(); }
    catch (err) { setError(err.response?.data?.detail || 'Could not stop agents'); }
  };

  const totalTasks = columns.reduce((n, c) => n + c.tasks.length, 0);
  const allTasks = columns.flatMap((c) => c.tasks);
  const childCount = {};
  allTasks.forEach((t) => { if (t.parent_task_id) childCount[t.parent_task_id] = (childCount[t.parent_task_id] || 0) + 1; });

  return (
    <div className="aida-board flex flex-col gap-5 min-w-0">
      <div className="aida-page-header flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-primary-600 dark:text-primary-400 mb-2">Agent workspace</p>
          <h1 className="text-2xl font-bold text-neutral-800 dark:text-neutral-100">Task Board</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
            {totalTasks} task{totalTasks !== 1 ? 's' : ''} · drag a card to <span className="font-medium text-sky-600 dark:text-sky-400">Queued</span> to hand it to the agent.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Link to="/schedules" className="btn btn-secondary"><CalendarClock size={16} /> Scheduler</Link>
          <button onClick={load} className="btn btn-secondary" aria-label="Refresh board"><RefreshCw size={16} /></button>
          <button
            disabled={!canManageRunner || !runner || runnerBusy}
            onClick={toggleRunner}
            className={`inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium rounded-lg border transition ${
              runner?.enabled
                ? 'border-emerald-300 dark:border-emerald-800 text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20'
                : 'border-neutral-300 dark:border-neutral-600 text-neutral-500 bg-white dark:bg-neutral-800'
            }`}
          >
            {runner?.enabled ? <Play size={15} /> : <Pause size={15} />}
            {!runner ? 'Runner unavailable' : runnerBusy ? 'Updating…' : runner.enabled ? 'Pause runner' : 'Resume runner'}
          </button>
          {canManageRunner && runner?.active > 0 && (
            <button
              onClick={killAgents}
              title="Global kill switch: abort every running agent immediately"
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-rose-300 dark:border-rose-800 text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/20 hover:bg-rose-100 dark:hover:bg-rose-900/40 transition"
            >
              <OctagonX size={15} /> Stop {runner?.active} agent{runner?.active === 1 ? '' : 's'}
            </button>
          )}
          <button
            disabled={readOnly}
            onClick={() => setShowModal(true)}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-sky-600 text-white hover:bg-sky-700 shadow-sm"
          >
            <Plus size={16} /> New task
          </button>
        </div>
      </div>

      {error && <div role="alert" className="rounded-xl border border-rose-300 bg-rose-50 dark:bg-rose-950/30 p-4 text-sm text-rose-700 dark:text-rose-300">{error}</div>}
      {runner && !runner.enabled && <div className="rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/20 p-4 text-sm text-amber-800 dark:text-amber-200">
        <Pause size={16} className="inline mr-2" />Runner is paused. Queued tasks, including scheduled scans, wait until it is resumed. Pausing does not stop agents that are already running.
      </div>}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        {[['All tasks', totalTasks], ['In progress', allTasks.filter(t => t.status === 'running').length], ['Needs attention', allTasks.filter(t => ['failed', 'needs_review'].includes(t.status)).length], ['Completed', allTasks.filter(t => t.status === 'done').length]].map(([label, count]) =>
          <div key={label} className="rounded-xl border bg-white dark:bg-neutral-800/60 px-5 py-4 shadow-sm"><p className="text-xs text-neutral-500 dark:text-neutral-400">{label}</p><p className="text-2xl font-semibold mt-1 tabular-nums">{count}</p></div>)}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="relative flex-1 min-w-[200px]"><Search size={16} className="absolute left-3 top-3 text-neutral-400" /><input aria-label="Search tasks" className="input pl-9" placeholder="Search title, target or task ID…" value={query} onChange={e => setQuery(e.target.value)} /></label>
        <select aria-label="Filter priority" className="input w-auto" value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}><option value="all">All priorities</option>{Object.entries(PRIORITY).map(([key, val]) => <option key={key} value={key}>{val.label}</option>)}</select>
        <select aria-label="Filter source" className="input w-auto" value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}><option value="all">All sources</option><option value="schedule">Scheduled scans</option><option value="manual">Other tasks</option></select>
        <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={hideCompleted} onChange={e => setHideCompleted(e.target.checked)} />Hide completed</label>
      </div>
      {(query || priorityFilter !== 'all' || sourceFilter !== 'all') && <p className="text-xs text-neutral-500">Filtered view: open a task to change its status. Clear filters to reorder by dragging.</p>}
      {!loading && totalTasks === 0 && !error && <div className="rounded-xl border border-dashed p-5 flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Plan your first assessment</h2><p className="text-sm text-neutral-500 mt-1">Create a task with a target and scope, review it in Backlog, then queue it for an agent.</p></div><Link to="/schedules" className="text-sm text-primary-600">Set up recurring scans →</Link></div>}
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-neutral-400">
          <Loader2 className="animate-spin mr-2" size={18} /> Loading board…
        </div>
      ) : (
        <div className="flex-1 min-w-0 overflow-x-auto pb-3">
          <div className="aida-board-columns">
            {columns.filter(col => !hideCompleted || col.key !== 'done').map((originalCol) => {
              const col = { ...originalCol, tasks: originalCol.tasks.filter(task =>
                (!query || `${task.title} ${task.target || ''} ${task.id}`.toLowerCase().includes(query.toLowerCase())) &&
                (priorityFilter === 'all' || task.priority === priorityFilter) &&
                (sourceFilter === 'all' || (sourceFilter === 'schedule' ? task.source === 'schedule' : task.source !== 'schedule'))) };
              const meta = COLUMN_META[col.key] || { label: col.key, icon: Inbox, accent: '#94a3b8', hint: '' };
              const Icon = meta.icon;
              const active = dropAt && dropAt.col === col.key;
              return (
                <div
                  key={col.key}
                  onDragOver={(e) => {
                    e.preventDefault();
                    const n = col.tasks.length;
                    setDropAt((prev) => (prev && prev.col === col.key && prev.index === n
                      ? prev : { col: col.key, index: n }));
                  }}
                  onDragLeave={() => setDropAt((p) => (p && p.col === col.key ? null : p))}
                  onDrop={(e) => onDrop(e, col.key)}
                  style={{ borderTop: `3px solid ${meta.accent}` }}
                  className={`min-w-0 flex flex-col rounded-xl border transition-colors ${
                    active
                      ? 'border-sky-400 bg-sky-50/70 dark:bg-sky-900/10'
                      : 'border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800/40'
                  }`}
                >
                  <div className="flex items-center justify-between px-3.5 py-3">
                    <div className="flex items-center gap-2">
                      <span className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: `${meta.accent}22`, color: meta.accent }}>
                        <Icon size={15} className={col.key === 'running' && col.tasks.length > 0 ? 'animate-spin' : ''} />
                      </span>
                      <div>
                        <div className="text-[13px] font-semibold text-neutral-700 dark:text-neutral-200 leading-none">{meta.label}</div>
                        <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{meta.hint}</div>
                      </div>
                    </div>
                    <span className="text-xs font-semibold text-neutral-500 dark:text-neutral-400 bg-white dark:bg-neutral-800 rounded-full px-2 py-0.5 min-w-[24px] text-center">{col.tasks.length}</span>
                  </div>
                  <div className="px-2.5 pb-2.5 space-y-2.5 overflow-y-auto flex-1 min-h-[140px] max-h-[calc(100vh-380px)]">
                    {col.tasks.map((task, i) => (
                      <React.Fragment key={task.id}>
                        {dropAt && dropAt.col === col.key && dropAt.index === i && (
                          <div className="h-1 rounded-full bg-sky-500 shadow-[0_0_6px_rgba(14,165,233,0.9)]" />
                        )}
                        <TaskCard readOnly={readOnly} task={task} modelMap={modelMap}
                          childCount={childCount[task.id] || 0}
                          onDragStart={onDragStart}
                          onDragOver={(e) => onCardDragOver(e, col.key, i)}
                          onDragEnd={() => setDropAt(null)}
                          onDelete={deleteTask} onOpen={openTask} onStop={stopTask} />
                      </React.Fragment>
                    ))}
                    {dropAt && dropAt.col === col.key && dropAt.index === col.tasks.length && (
                      <div className="h-1 rounded-full bg-sky-500 shadow-[0_0_6px_rgba(14,165,233,0.9)]" />
                    )}
                    {col.tasks.length === 0 && (
                      <div className="h-24 flex items-center justify-center text-[11px] text-neutral-500 dark:text-neutral-400 border border-dashed border-neutral-200 dark:border-neutral-800 rounded-xl">
                        {col.key === 'backlog' ? 'Ideas and planned work' : col.key === 'queued' ? 'Ready for an agent' : col.key === 'running' ? 'Agent activity appears here' : col.key === 'needs_review' ? 'Review findings here' : col.key === 'done' ? 'Completed work' : 'Errors and interrupted tasks'}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {showModal && <NewTaskModal models={models} onClose={() => { setShowModal(false); load(); }} onCreate={createTask} />}
      {selectedTaskId && (
        <TaskDetailDrawer
          taskId={selectedTaskId}
          allTasks={allTasks}
          liveLog={liveLog}
          modelMap={modelMap}
          onClose={() => setSelectedTaskId(null)}
          onDelete={deleteTask}
          onStop={stopTask}
          onRecover={recoverTask}
          onRetry={retryTask}
          onMove={moveTask}
          readOnly={readOnly}
        />
      )}
    </div>
  );
}
