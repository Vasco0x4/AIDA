import { utcDate } from '../utils/utcDate';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2, CircleHelp, Cpu, Database, RefreshCw, Server, ShieldCheck } from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../contexts/AuthContext';

export default function GettingStarted() {
  const { user } = useAuth();
  const admin = user?.role === 'admin';
  const [checks, setChecks] = useState({});
  const [busy, setBusy] = useState(true);
  const [checkedAt, setCheckedAt] = useState(null);
  const generation = useRef(0);
  const refresh = useCallback(async () => {
    const current = ++generation.current;
    setBusy(true);
    const keys = ['system', 'runner', ...(admin ? ['models'] : [])];
    const paths = ['/system/status', '/tasks/runner', ...(admin ? ['/ai-models'] : [])];
    const results = await Promise.allSettled(paths.map(path => api.get(path, { timeout: 10000 })));
    if (current !== generation.current) return;
    setChecks(Object.fromEntries(keys.map((key, index) => [key, results[index].status === 'fulfilled' ? results[index].value.data : null])));
    setCheckedAt(utcDate());
    setBusy(false);
  }, [admin]);
  useEffect(() => { refresh(); return () => { generation.current += 1; }; }, [refresh]);
  const system = checks.system;
  const models = checks.models?.filter(model => model.enabled) || [];
  const cards = [
    { title: 'Application & database', icon: Database, ok: system ? system.backend?.status === 'connected' && system.database?.connected : null,
      detail: system ? 'AIDA API and assessment storage.' : 'Status could not be verified. Refresh or check Settings.', to: '/settings?tab=general' },
    { title: 'Execution container', icon: Server, ok: system ? Boolean(system.exegol?.running) : null,
      detail: system?.exegol?.running ? `Running: ${system.exegol.container}` : 'A running execution container is needed for container-based tasks.', to: '/settings?tab=general' },
    { title: 'AI configuration', icon: Cpu, ok: admin && checks.models ? models.length > 0 : null,
      detail: !admin ? 'Ask an administrator to verify the model configuration.' : checks.models ? `${models.length} enabled model${models.length === 1 ? '' : 's'}. Test credentials in AI Models before scanning.` : 'Model configuration could not be loaded.', to: admin ? '/settings?tab=ai_models' : '/guide' },
  ];
  return <div className="max-w-6xl mx-auto space-y-6">
    <header className="aida-page-header flex flex-wrap items-start justify-between gap-4">
      <div className="max-w-2xl"><p className="aida-eyebrow">Your first assessment</p><h1 className="text-3xl font-bold tracking-tight">A clear path from setup to results.</h1><p className="aida-description">Check your workspace, define the scope, then hand a reviewed task to an agent. You stay in control of when execution starts.</p></div>
      <Link className="btn btn-secondary" to="/guide">Read the guide <ArrowRight size={16} /></Link>
    </header>
    <section aria-labelledby="readiness-title" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 id="readiness-title" className="text-lg font-semibold">Workspace checks</h2><p className="text-xs text-neutral-500 dark:text-neutral-400" role="status">{busy ? 'Checking current status…' : `Checked at ${checkedAt?.toLocaleTimeString()}. Configuration checks do not run a scan or test AI credentials.`}</p></div><button className="btn btn-secondary" disabled={busy} onClick={refresh}><RefreshCw size={16} className={busy ? 'animate-spin' : ''} />Refresh checks</button></div>
      <div className="grid md:grid-cols-3 gap-4">{cards.map(({title, icon: Icon, ok, detail, to}) => <article key={title} className="aida-check-card">
        <div className="flex items-center justify-between gap-2"><Icon size={20} className="text-primary-600 dark:text-primary-400" /><span className={`aida-status ${busy || ok === null ? 'aida-status-neutral' : ok ? 'aida-status-good' : 'aida-status-warn'}`}>{busy ? 'Checking' : ok === null ? 'Not verified' : ok ? 'Configured' : 'Needs attention'}</span></div>
        <h3 className="font-semibold mt-4">{title}</h3><p className="aida-description flex-1">{busy ? 'Reading workspace configuration…' : detail}</p><Link to={to} className="aida-text-link mt-4">{title === 'AI configuration' && admin ? 'Open AI Models' : 'View details'} <ArrowRight size={14} /></Link>
      </article>)}</div>
    </section>
    <section className="aida-runner-note" aria-label="Agent runner status"><ShieldCheck size={24} className="shrink-0 text-primary-600 dark:text-primary-400" /><div className="flex-1"><h2 className="font-semibold">{busy ? 'Checking the runner…' : !checks.runner ? 'Runner status is unavailable' : checks.runner.enabled ? 'Runner is enabled' : 'Runner is paused'}</h2><p className="aida-description">{checks.runner?.enabled ? `${checks.runner.active} active task(s). Eligible queued tasks can start automatically.` : 'Queued tasks and scheduled scans wait while the runner is paused. Review your scope and model settings before enabling it on the Task Board.'}</p></div><Link to="/board" className="btn btn-secondary">Open Task Board <ArrowRight size={16} /></Link></section>
    <section aria-labelledby="workflow-title"><h2 id="workflow-title" className="text-lg font-semibold mb-4">Four steps to your first result</h2><ol className="grid sm:grid-cols-2 gap-4">{[
      ['Connect your AI', 'Configure a model and test its connection. For an external CLI client, follow the MCP instructions.', admin ? '/settings?tab=ai_models' : '/guide', 'Configure AI'],
      ['Define the assessment', 'Create an assessment to keep the target, findings and evidence together. State what is in and out of scope.', '/assessments', 'Open assessments'],
      ['Plan and review a task', 'Create a task in Backlog, choose its model and review the instructions. Move it to Queued only when you are ready.', '/board', 'Plan a task'],
      ['Review the outcome', 'Use Task Board for all agent tasks. Scan Runs keeps the execution history and finding snapshots for scans.', '/runs', 'Explore Scan Runs'],
    ].map(([title, detail, to, action], i) => <li className="aida-workflow-step" key={title}><span className="aida-step-number">{i+1}</span><div><h3 className="font-semibold">{title}</h3><p className="aida-description">{detail}</p><Link to={to} className="aida-text-link mt-3">{action}<ArrowRight size={14} /></Link></div></li>)}</ol></section>
    <div className="grid md:grid-cols-2 gap-4"><Link to="/schedules" className="aida-check-card hover:border-primary-400"><CheckCircle2 size={20} /><h2 className="font-semibold mt-3">Make checks repeatable</h2><p className="aida-description">Use Scheduler for recurring scans. Preview the next starts in your chosen UTC offset.</p></Link><Link to="/guide" className="aida-check-card hover:border-primary-400"><CircleHelp size={20} /><h2 className="font-semibold mt-3">Understand each workspace</h2><p className="aida-description">The English guide explains Task Board, assessments, scan history and operational controls.</p></Link></div>
  </div>;
}
