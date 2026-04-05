import { useState, useEffect, useCallback } from 'react';
import { Shield, Terminal, Eye, Target, Info, Zap, ChevronDown, ChevronUp, RefreshCw, Plus, Trash2, Clock } from 'lucide-react';
import timelineService from '../../services/timelineService';

const PHASE_CONFIG = {
  recon: { label: 'Reconnaissance', color: 'blue', icon: Target, description: 'Information gathering and enumeration' },
  scanning: { label: 'Scanning', color: 'cyan', icon: Eye, description: 'Vulnerability scanning and analysis' },
  exploitation: { label: 'Exploitation', color: 'red', icon: Zap, description: 'Exploiting discovered vulnerabilities' },
  post_exploitation: { label: 'Post-Exploitation', color: 'orange', icon: Terminal, description: 'Privilege escalation and lateral movement' },
  reporting: { label: 'Reporting', color: 'green', icon: Info, description: 'Documentation and reporting' },
};

const SEVERITY_COLORS = {
  CRITICAL: 'bg-red-500',
  HIGH: 'bg-orange-500',
  MEDIUM: 'bg-yellow-500',
  LOW: 'bg-blue-500',
  INFO: 'bg-neutral-400',
};

const EVENT_ICONS = {
  command: Terminal,
  finding: Shield,
  observation: Eye,
  recon: Target,
  info: Info,
  manual: Plus,
};

function TimelineEventCard({ event, onDelete }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = EVENT_ICONS[event.event_type] || Info;
  const severityColor = SEVERITY_COLORS[event.severity] || SEVERITY_COLORS.INFO;
  const time = new Date(event.created_at).toLocaleString();

  return (
    <div className="relative flex gap-3 group">
      {/* Dot on the line */}
      <div className="flex flex-col items-center z-10">
        <div className={`w-8 h-8 rounded-full flex items-center justify-center ${severityColor} text-white shadow-md`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>

      {/* Card */}
      <div className="flex-1 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3 mb-3 hover:shadow-md transition-shadow">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`px-1.5 py-0.5 text-[10px] font-semibold rounded ${severityColor} text-white`}>
                {event.severity || 'INFO'}
              </span>
              <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300">
                {event.event_type}
              </span>
              {event.tags && event.tags.split(',').map((tag, i) => (
                <span key={i} className="px-1.5 py-0.5 text-[10px] rounded bg-neutral-50 dark:bg-neutral-750 text-neutral-500 dark:text-neutral-400">
                  {tag.trim()}
                </span>
              ))}
            </div>
            <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100 mt-1 break-words">
              {event.title}
            </p>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5 flex items-center gap-1">
              <Clock className="w-3 h-3" /> {time}
            </p>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {(event.description || event.command_text || event.card_title || event.recon_name) && (
              <button onClick={() => setExpanded(!expanded)} className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-700">
                {expanded ? <ChevronUp className="w-4 h-4 text-neutral-400" /> : <ChevronDown className="w-4 h-4 text-neutral-400" />}
              </button>
            )}
            <button
              onClick={() => onDelete(event.id)}
              className="p-1 rounded hover:bg-red-50 dark:hover:bg-red-900/20 text-neutral-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {expanded && (
          <div className="mt-2 pt-2 border-t border-neutral-100 dark:border-neutral-700 text-xs text-neutral-600 dark:text-neutral-400 space-y-1">
            {event.description && <p>{event.description}</p>}
            {event.command_text && (
              <p className="font-mono bg-neutral-50 dark:bg-neutral-900 px-2 py-1 rounded">{event.command_text}</p>
            )}
            {event.card_title && <p>Finding: {event.card_title}</p>}
            {event.recon_name && <p>Recon: {event.recon_name}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function PhaseSection({ phase, events, onDelete }) {
  const [collapsed, setCollapsed] = useState(false);
  const config = PHASE_CONFIG[phase] || { label: phase, color: 'neutral', icon: Info, description: '' };
  const PhaseIcon = config.icon;

  const colorMap = {
    blue: 'border-blue-400 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300',
    cyan: 'border-cyan-400 bg-cyan-50 dark:bg-cyan-900/20 text-cyan-700 dark:text-cyan-300',
    red: 'border-red-400 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300',
    orange: 'border-orange-400 bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300',
    green: 'border-green-400 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300',
    neutral: 'border-neutral-400 bg-neutral-50 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300',
  };

  const lineColorMap = {
    blue: 'bg-blue-300 dark:bg-blue-700',
    cyan: 'bg-cyan-300 dark:bg-cyan-700',
    red: 'bg-red-300 dark:bg-red-700',
    orange: 'bg-orange-300 dark:bg-orange-700',
    green: 'bg-green-300 dark:bg-green-700',
    neutral: 'bg-neutral-300 dark:bg-neutral-700',
  };

  return (
    <div className="relative">
      {/* Phase header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg border-l-4 mb-3 transition-colors ${colorMap[config.color]}`}
      >
        <PhaseIcon className="w-5 h-5 shrink-0" />
        <div className="flex-1 text-left">
          <span className="font-semibold text-sm">{config.label}</span>
          <span className="text-xs ml-2 opacity-75">({events.length} events)</span>
        </div>
        {collapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
      </button>

      {/* Events */}
      {!collapsed && (
        <div className="relative ml-4 pl-4">
          {/* Vertical line */}
          <div className={`absolute left-[15px] top-0 bottom-0 w-0.5 ${lineColorMap[config.color]}`} />
          {events.map(event => (
            <TimelineEventCard key={event.id} event={event} onDelete={onDelete} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function AttackTimeline({ assessmentId }) {
  const [timeline, setTimeline] = useState({ events: [], total: 0, phases: {} });
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [filterPhase, setFilterPhase] = useState('');
  const [filterType, setFilterType] = useState('');

  const loadTimeline = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterPhase) params.phase = filterPhase;
      if (filterType) params.event_type = filterType;
      const data = await timelineService.getTimeline(assessmentId, params);
      setTimeline(data);
    } catch (err) {
      console.error('Failed to load timeline:', err);
    } finally {
      setLoading(false);
    }
  }, [assessmentId, filterPhase, filterType]);

  useEffect(() => { loadTimeline(); }, [loadTimeline]);

  const handleAutoGenerate = async () => {
    setGenerating(true);
    try {
      const result = await timelineService.autoGenerate(assessmentId);
      if (result.generated > 0) {
        await loadTimeline();
      }
    } catch (err) {
      console.error('Failed to auto-generate:', err);
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async (eventId) => {
    try {
      await timelineService.deleteEvent(assessmentId, eventId);
      setTimeline(prev => ({
        ...prev,
        events: prev.events.filter(e => e.id !== eventId),
        total: prev.total - 1,
      }));
    } catch (err) {
      console.error('Failed to delete event:', err);
    }
  };

  // Group events by phase in order
  const phaseOrder = ['recon', 'scanning', 'exploitation', 'post_exploitation', 'reporting'];
  const grouped = {};
  for (const event of timeline.events) {
    if (!grouped[event.phase]) grouped[event.phase] = [];
    grouped[event.phase].push(event);
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Attack Timeline</h3>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">{timeline.total} events across {Object.keys(grouped).length} phases</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Filters */}
          <select
            value={filterPhase}
            onChange={e => setFilterPhase(e.target.value)}
            className="text-xs px-2 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
          >
            <option value="">All phases</option>
            {phaseOrder.map(p => (
              <option key={p} value={p}>{PHASE_CONFIG[p]?.label || p}</option>
            ))}
          </select>
          <select
            value={filterType}
            onChange={e => setFilterType(e.target.value)}
            className="text-xs px-2 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
          >
            <option value="">All types</option>
            <option value="command">Commands</option>
            <option value="finding">Findings</option>
            <option value="observation">Observations</option>
            <option value="recon">Recon</option>
            <option value="manual">Manual</option>
          </select>

          <button
            onClick={loadTimeline}
            disabled={loading}
            className="p-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 text-neutral-500 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={handleAutoGenerate}
            disabled={generating}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors disabled:opacity-50"
          >
            <Zap className={`w-3.5 h-3.5 ${generating ? 'animate-pulse' : ''}`} />
            {generating ? 'Generating...' : 'Auto-Generate'}
          </button>
        </div>
      </div>

      {/* Phase summary bar */}
      {timeline.total > 0 && (
        <div className="flex rounded-lg overflow-hidden h-2">
          {phaseOrder.map(phase => {
            const count = timeline.phases[phase] || 0;
            if (count === 0) return null;
            const pct = (count / timeline.total) * 100;
            const colorMap = { recon: 'bg-blue-400', scanning: 'bg-cyan-400', exploitation: 'bg-red-400', post_exploitation: 'bg-orange-400', reporting: 'bg-green-400' };
            return (
              <div
                key={phase}
                className={`${colorMap[phase] || 'bg-neutral-400'} transition-all`}
                style={{ width: `${pct}%` }}
                title={`${PHASE_CONFIG[phase]?.label}: ${count} events`}
              />
            );
          })}
        </div>
      )}

      {/* Timeline body */}
      {loading && timeline.total === 0 ? (
        <div className="text-center py-12 text-neutral-500 dark:text-neutral-400">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
          Loading timeline...
        </div>
      ) : timeline.total === 0 ? (
        <div className="text-center py-12 border-2 border-dashed border-neutral-200 dark:border-neutral-700 rounded-lg">
          <Zap className="w-8 h-8 text-neutral-400 mx-auto mb-3" />
          <p className="text-sm font-medium text-neutral-600 dark:text-neutral-400">No timeline events yet</p>
          <p className="text-xs text-neutral-500 dark:text-neutral-500 mt-1">Click "Auto-Generate" to build the timeline from existing commands and findings</p>
        </div>
      ) : (
        <div className="space-y-2">
          {phaseOrder.map(phase => {
            const events = grouped[phase];
            if (!events || events.length === 0) return null;
            return <PhaseSection key={phase} phase={phase} events={events} onDelete={handleDelete} />;
          })}
          {/* Any phases not in phaseOrder */}
          {Object.keys(grouped).filter(p => !phaseOrder.includes(p)).map(phase => (
            <PhaseSection key={phase} phase={phase} events={grouped[phase]} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  );
}
