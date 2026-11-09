import { utcDate } from '../utils/utcDate';
import { useState, useEffect, useMemo, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  FileText,
  Terminal,
  Activity,
  Shield,
  AlertTriangle,
  ArrowUpRight,
  TrendingUp,
  TrendingDown,
  Plus,
  Play
} from '../components/icons';
import CreateAssessmentModal from '../components/assessment/CreateAssessmentModal';
import NVDDigest from '../components/dashboard/NVDDigest';
import assessmentService from '../services/assessmentService';
import apiClient from '../services/api';
import commandService from '../services/commandService';
import toolStatsService from '../services/toolStatsService';
import { useWebSocketContext } from '../contexts/WebSocketContext';

// Utility for smooth Bezier curves
const getControlPoint = (current, previous, next, reverse) => {
  const p = previous || current;
  const n = next || current;
  const smoothing = 0.2; // 0.2 is a good smoothing factor

  const line = (pointA, pointB) => {
    const lengthX = pointB[0] - pointA[0];
    const lengthY = pointB[1] - pointA[1];
    return {
      length: Math.sqrt(Math.pow(lengthX, 2) + Math.pow(lengthY, 2)),
      angle: Math.atan2(lengthY, lengthX)
    };
  };

  const o = line(p, n);
  const angle = o.angle + (reverse ? Math.PI : 0);
  const length = o.length * smoothing;

  const x = current[0] + Math.cos(angle) * length;
  const y = current[1] + Math.sin(angle) * length;

  return [x, y];
};

const generateSmoothPath = (points, closePath) => {
  if (!points || points.length === 0) return '';
  if (points.length === 1) return `M ${points[0][0]} ${points[0][1]}`;

  let d = `M ${points[0][0]} ${points[0][1]}`;

  for (let i = 0; i < points.length - 1; i++) {
    const current = points[i];
    const next = points[i + 1];
    const prev = i > 0 ? points[i - 1] : points[i];
    const nextNext = i < points.length - 2 ? points[i + 2] : points[i + 1];

    const cp1 = getControlPoint(current, prev, next, false);
    const cp2 = getControlPoint(next, current, nextNext, true);

    d += ` C ${cp1[0]} ${cp1[1]}, ${cp2[0]} ${cp2[1]}, ${next[0]} ${next[1]}`;
  }

  if (closePath) {
    d += ' L 1000 100 L 0 100 Z';
  }

  return d;
};

const Dashboard = () => {
  const navigate = useNavigate();
  const [assessments, setAssessments] = useState([]);
  const [allFindings, setAllFindings] = useState([]);
  const [allCommands, setAllCommands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [timelinePeriod, setTimelinePeriod] = useState('30');
  const [hoveredDay, setHoveredDay] = useState(null);
  const [topTools, setTopTools] = useState([]);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const { subscribe } = useWebSocketContext();
  const findingsReloadTimer = useRef(null);

  useEffect(() => {
    loadDashboardData();
  }, []);

  // Real-time updates via WebSocket
  useEffect(() => {
    const reloadCommands = async () => {
      try {
        let allCommandsList = [];
        let skip = 0;
        const limit = 500;
        let hasMore = true;
        while (hasMore) {
          const data = await commandService.getAllCommands({ skip, limit });
          allCommandsList = [...allCommandsList, ...data.commands];
          hasMore = data.has_more;
          skip += limit;
        }
        setAllCommands(allCommandsList);
      } catch (error) {
        // silently ignore
      }
    };

    const reloadFindings = async () => {
      try {
        // One aggregate request instead of one /cards call per assessment.
        const [{ data: assessmentsData }, { data: findingsData }] = await Promise.all([
          apiClient.get('/assessments'),
          apiClient.get('/findings'),
        ]);
        setAssessments(assessmentsData);
        setAllFindings(findingsData);
      } catch (error) {
        // silently ignore
      }
    };

    // Coalesce bursts of card/assessment events (e.g. importing a scan) into a
    // single reload.
    const debouncedReloadFindings = () => {
      if (findingsReloadTimer.current) clearTimeout(findingsReloadTimer.current);
      findingsReloadTimer.current = setTimeout(reloadFindings, 300);
    };

    const unsubscribes = [
      subscribe('command_completed', reloadCommands),
      subscribe('command_failed', reloadCommands),
      subscribe('card_added', debouncedReloadFindings),
      subscribe('card_updated', debouncedReloadFindings),
      subscribe('card_deleted', debouncedReloadFindings),
      subscribe('assessment_created', debouncedReloadFindings),
      subscribe('assessment_updated', debouncedReloadFindings),
      subscribe('assessment_deleted', debouncedReloadFindings),
    ];
    return () => {
      unsubscribes.forEach(unsub => unsub && unsub());
      if (findingsReloadTimer.current) clearTimeout(findingsReloadTimer.current);
    };
  }, [subscribe]);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setLoadError(null);

      // Fetch all assessments and all findings (one aggregate request instead
      // of one /cards call per assessment).
      const [{ data: assessmentsData }, { data: findings }] = await Promise.all([
        apiClient.get('/assessments'),
        apiClient.get('/findings'),
      ]);
      setAssessments(assessmentsData);
      setAllFindings(findings);

      // Fetch ALL commands using global endpoint with pagination
      let allCommandsList = [];
      let skip = 0;
      const limit = 500; // Fetch in batches
      let hasMore = true;

      while (hasMore) {
        const data = await commandService.getAllCommands({ skip, limit });
        allCommandsList = [...allCommandsList, ...data.commands];
        hasMore = data.has_more;
        skip += limit;
      }

      setAllCommands(allCommandsList);

      // Fetch top tools for "Tool Usage" card
      try {
        const tools = await toolStatsService.getTopTools(5, 30); // Top 5, last 30 days
        setTopTools(tools);
      } catch (error) {
        console.error('Failed to load tool stats:', error);
        setTopTools([]);
      }

    } catch (error) {
      setLoadError('Dashboard data could not be loaded. Check the connection and try again.');
      console.error('Failed to load dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Calculate KPIs
  const kpis = useMemo(() => {
    const activeAssessments = assessments.filter(a => a.status === 'active').length;
    const totalFindings = allFindings.length;
    const successfulCommands = allCommands.filter(c => c.success).length;
    const successRate = allCommands.length > 0
      ? Math.round((successfulCommands / allCommands.length) * 100)
      : 0;

    // Get new findings in last 24h
    const last24h = utcDate();
    last24h.setDate(last24h.getDate() - 1);
    const newFindings = allFindings.filter(f => utcDate(f.created_at) > last24h).length;

    // Calculate trend (last 7 days vs previous 7 days)
    const last7days = utcDate();
    last7days.setDate(last7days.getDate() - 7);
    const last14days = utcDate();
    last14days.setDate(last14days.getDate() - 14);

    const commandsLast7 = allCommands.filter(c => utcDate(c.created_at) > last7days).length;
    const commandsPrev7 = allCommands.filter(c => {
      const date = utcDate(c.created_at);
      return date > last14days && date <= last7days;
    }).length;

    const commandsTrend = commandsPrev7 > 0
      ? Math.round(((commandsLast7 - commandsPrev7) / commandsPrev7) * 100)
      : commandsLast7 > 0 ? 100 : 0;

    return {
      totalCommands: allCommands.length,
      activeAssessments,
      totalFindings,
      successRate,
      newFindings,
      commandsTrend
    };
  }, [assessments, allFindings, allCommands]);

  // Findings by severity
  const findingsBySeverity = useMemo(() => {
    const critical = allFindings.filter(f => f.severity === 'CRITICAL').length;
    const high = allFindings.filter(f => f.severity === 'HIGH').length;
    const medium = allFindings.filter(f => f.severity === 'MEDIUM').length;
    const low = allFindings.filter(f => f.severity === 'LOW').length;
    const total = critical + high + medium + low;

    return { critical, high, medium, low, total };
  }, [allFindings]);

  // Assessment status distribution
  const assessmentDistribution = useMemo(() => {
    const active = assessments.filter(a => a.status === 'active').length;
    const completed = assessments.filter(a => a.status === 'completed').length;
    const archived = assessments.filter(a => a.status === 'archived').length;
    const total = assessments.length;

    return {
      active,
      completed,
      archived,
      total,
      activePercent: total > 0 ? Math.round((active / total) * 100) : 0,
      completedPercent: total > 0 ? Math.round((completed / total) * 100) : 0,
      archivedPercent: total > 0 ? Math.round((archived / total) * 100) : 0
    };
  }, [assessments]);

  // Recent findings (last 5)
  const recentFindings = useMemo(() => {
    return [...allFindings]
      .sort((a, b) => utcDate(b.created_at) - utcDate(a.created_at))
      .slice(0, 5);
  }, [allFindings]);

  // Last active assessment for "Resume" button
  const lastActiveAssessment = useMemo(() => {
    return assessments
      .filter(a => a.status === 'active')
      .sort((a, b) => utcDate(b.updated_at || b.created_at) - utcDate(a.updated_at || a.created_at))[0];
  }, [assessments]);

  // Handle assessment creation and redirect
  const handleCreateAssessment = async (createdAssessment) => {
    if (!createdAssessment?.id) return;
    
    setIsCreateModalOpen(false);
    navigate(`/assessments/${createdAssessment.id}`);
  };

  // Commands timeline data (by day)
  const commandsTimelineData = useMemo(() => {
    const days = parseInt(timelinePeriod);
    const data = [];
    const now = utcDate();
    now.setHours(23, 59, 59, 999); // End of today

    for (let i = days - 1; i >= 0; i--) {
      const dayStart = utcDate();
      dayStart.setDate(now.getDate() - i);
      dayStart.setHours(0, 0, 0, 0);

      const dayEnd = utcDate(dayStart);
      dayEnd.setHours(23, 59, 59, 999);

      const dayCommands = allCommands.filter(c => {
        const created = utcDate(c.created_at);
        return created >= dayStart && created <= dayEnd;
      });

      const successCount = dayCommands.filter(c => c.success).length;
      const failedCount = dayCommands.filter(c => !c.success).length;

      data.push({
        date: utcDate(dayStart),
        success: successCount,
        failed: failedCount,
        total: successCount + failedCount
      });
    }

    return data;
  }, [allCommands, timelinePeriod]);

  // Calculate max value for Y axis
  const maxCommandsPerDay = Math.max(
    ...commandsTimelineData.map(d => Math.max(d.success, d.failed)),
    10 // Minimum scale
  );

  // Format date for X axis
  const formatDateLabel = (date, index, total) => {
    const period = parseInt(timelinePeriod);

    // Show fewer labels for longer periods
    let step = 1;
    if (period === 90) step = 7; // Weekly for 3 months
    else if (period === 180) step = 14; // Bi-weekly for 6 months
    else if (period === 365) step = 30; // Monthly for 1 year
    else if (period === 30) step = 3; // Every 3 days for 1 month

    if (index % step !== 0 && index !== total - 1) return '';

    const month = date.toLocaleDateString('en', { month: 'short' });
    const day = date.getDate();
    return `${month} ${day}`;
  };

  // Format date for tooltip
  const formatTooltipDate = (date) => {
    return date.toLocaleDateString('en', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  // Calculate totals for legend
  const totalSuccess = commandsTimelineData.reduce((sum, d) => sum + d.success, 0);
  const totalFailed = commandsTimelineData.reduce((sum, d) => sum + d.failed, 0);

  if (loadError && !loading) return <section className="aida-page-header space-y-4"><h1 className="text-2xl font-bold">Dashboard</h1><p role="alert" className="text-rose-700 dark:text-rose-300">{loadError}</p><p className="text-sm text-neutral-500">Statistics are unavailable, not zero.</p><button className="btn btn-primary" onClick={loadDashboardData}>Retry loading dashboard</button></section>;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-neutral-500 dark:text-neutral-400">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in">
      {/* Header with Quick Actions */}
      <div className="aida-page-header flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="aida-eyebrow">Security workspace</p>
          <h1 className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">Dashboard</h1>
          <p className="mt-1 text-neutral-600 dark:text-neutral-400">
            Your assessments, activity and findings in one place.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 max-w-xl">
          <Link to="/getting-started" className="btn btn-secondary">Workspace checks</Link>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-md transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            New Assessment
          </button>
          {lastActiveAssessment && (
            <Link
              to={`/assessments/${lastActiveAssessment.id}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-neutral-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-700 rounded-md transition-colors"
            >
              <Play className="w-3.5 h-3.5" />
              Open latest assessment
            </Link>
          )}
        </div>
      </div>

      {/* Create Assessment Modal */}
      {isCreateModalOpen && (
        <CreateAssessmentModal
          onClose={() => setIsCreateModalOpen(false)}
          onSuccess={handleCreateAssessment}
        />
      )}

      <div className="grid gap-3 md:grid-cols-3">
        {[['/board', 'Task Board', 'Plan work, queue agents and review results.'], ['/schedules', 'Scheduled scans', 'Set up recurring checks in your timezone.'], ['/runs', 'Run history', 'Follow execution, evidence and finding changes.']].map(([to, title, description]) =>
          <Link key={to} to={to} className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-4 hover:border-primary-500 transition-colors"><p className="font-semibold text-sm">{title} →</p><p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">{description}</p></Link>)}
      </div>
      {/* KPIs - Compact sans cadres lourds */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-6">
        {/* Total Commands */}
        <div className="aida-metric-card">
          <div className="flex items-center justify-between">
            <span className="text-sm text-neutral-500 dark:text-neutral-400 font-medium">Commands · all time</span>
            <Terminal className="w-4 h-4 text-neutral-400 dark:text-neutral-500" />
          </div>
          <div className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">{kpis.totalCommands}</div>
          <div className="flex items-center gap-1 text-xs">
            {kpis.commandsTrend >= 0 ? (
              <>
                <TrendingUp className="w-3 h-3 text-green-500" />
                <span className="text-green-600 dark:text-green-400 font-medium">+{kpis.commandsTrend}%</span>
              </>
            ) : (
              <>
                <TrendingDown className="w-3 h-3 text-red-500" />
                <span className="text-red-600 dark:text-red-400 font-medium">{kpis.commandsTrend}%</span>
              </>
            )}
            <span className="text-neutral-500 dark:text-neutral-400">vs last week</span>
          </div>
        </div>

        {/* Active Assessments */}
        <div className="aida-metric-card">
          <div className="flex items-center justify-between">
            <span className="text-sm text-neutral-500 dark:text-neutral-400 font-medium">Active assessments</span>
            <Activity className="w-4 h-4 text-neutral-400 dark:text-neutral-500" />
          </div>
          <div className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">{kpis.activeAssessments}</div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400">In progress</div>
        </div>

        {/* Total Findings */}
        <div className="aida-metric-card">
          <div className="flex items-center justify-between">
            <span className="text-sm text-neutral-500 dark:text-neutral-400 font-medium">Findings</span>
            <Shield className="w-4 h-4 text-neutral-400 dark:text-neutral-500" />
          </div>
          <div className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">{kpis.totalFindings}</div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400">
            {kpis.newFindings > 0 && (
              <span className="text-orange-600 dark:text-orange-400 font-medium">+{kpis.newFindings} new</span>
            )}
            {kpis.newFindings === 0 && <span>No new findings</span>}
          </div>
        </div>

        {/* Success Rate */}
        <div className="aida-metric-card">
          <div className="flex items-center justify-between">
            <span className="text-sm text-neutral-500 dark:text-neutral-400 font-medium">Command success · all time</span>
            <FileText className="w-4 h-4 text-neutral-400 dark:text-neutral-500" />
          </div>
          <div className="text-3xl font-bold text-neutral-900 dark:text-neutral-100">{kpis.successRate}%</div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400">Commands executed</div>
        </div>
      </div>

      {/* Commands Timeline (Full width) */}
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Commands Timeline</h3>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">Daily command execution success and failure rates</p>
          </div>

          {/* Period selector */}
          <select
            value={timelinePeriod}
            onChange={(e) => setTimelinePeriod(e.target.value)}
            className="px-3 py-1.5 text-sm border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-900 dark:text-neutral-100 hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="30">Last 30 days</option>
            <option value="90">Last 3 months</option>
            <option value="180">Last 6 months</option>
            <option value="365">Last year</option>
          </select>
        </div>

        {commandsTimelineData.length > 0 && commandsTimelineData.some(d => d.total > 0) ? (
          <>
            <div className="relative" style={{ height: '220px' }}>
              {/* Y-axis */}
              <div className="absolute left-0 top-0 bottom-12 w-12 flex flex-col justify-between text-xs text-neutral-500 dark:text-neutral-400 text-right pr-3">
                {[...Array(6)].map((_, i) => {
                  const value = Math.round((maxCommandsPerDay * (5 - i)) / 5);
                  return <span key={i}>{value}</span>;
                })}
              </div>

              {/* Chart area */}
              <div className="absolute left-14 right-0 top-0 bottom-12">
                {/* Horizontal grid lines */}
                <div className="absolute inset-0 flex flex-col justify-between">
                  {[...Array(6)].map((_, i) => (
                    <div key={i} className="w-full border-t border-neutral-100 dark:border-neutral-700"></div>
                  ))}
                </div>

                {/* SVG Chart with 2 lines */}
                <svg className="absolute inset-0 w-full h-full" viewBox="0 0 1000 100" preserveAspectRatio="none">
                  <defs>
                    {/* Gradient for success line */}
                    <linearGradient id="successGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity="0.3" />
                      <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
                    </linearGradient>

                    {/* Gradient for failed line */}
                    <linearGradient id="failedGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#ef4444" stopOpacity="0.3" />
                      <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
                    </linearGradient>
                  </defs>

                  {/* Success line with area fill */}
                  {commandsTimelineData.length > 1 && (() => {
                    const points = commandsTimelineData.map((data, index) => {
                      const x = (index / (commandsTimelineData.length - 1)) * 1000;
                      const y = 100 - ((data.success / maxCommandsPerDay) * 95);
                      return [x, y];
                    });
                    const path = generateSmoothPath(points, false);
                    const areaPath = generateSmoothPath(points, true);

                    return (
                      <>
                        <path
                          d={areaPath}
                          fill="url(#successGradient)"
                        />
                        <path
                          d={path}
                          fill="none"
                          stroke="#10b981"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          vectorEffect="non-scaling-stroke"
                        />
                      </>
                    );
                  })()}

                  {/* Failed line with area fill */}
                  {commandsTimelineData.length > 1 && (() => {
                    const points = commandsTimelineData.map((data, index) => {
                      const x = (index / (commandsTimelineData.length - 1)) * 1000;
                      const y = 100 - ((data.failed / maxCommandsPerDay) * 95);
                      return [x, y];
                    });
                    const path = generateSmoothPath(points, false);
                    const areaPath = generateSmoothPath(points, true);

                    return (
                      <>
                        <path
                          d={areaPath}
                          fill="url(#failedGradient)"
                        />
                        <path
                          d={path}
                          fill="none"
                          stroke="#ef4444"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          vectorEffect="non-scaling-stroke"
                        />
                      </>
                    );
                  })()}
                </svg>

                {/* Interactive overlay - invisible columns for hover detection */}
                <div 
                  className="absolute inset-0 flex"
                  onMouseLeave={() => setHoveredDay(null)}
                >
                  {commandsTimelineData.map((data, index) => {
                    const isHovered = hoveredDay === index;
                    return (
                      <div
                        key={index}
                        className="flex-1 relative cursor-crosshair"
                        onMouseEnter={() => setHoveredDay(index)}
                      >
                        {/* Vertical hover line */}
                        {isHovered && (
                          <div className="absolute inset-y-0 left-1/2 w-px bg-neutral-300 dark:bg-neutral-600 transform -translate-x-1/2 pointer-events-none" />
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Hover points - small and subtle */}
                {hoveredDay !== null && commandsTimelineData[hoveredDay] && (() => {
                  const data = commandsTimelineData[hoveredDay];
                  const xPercent = commandsTimelineData.length > 1
                    ? (hoveredDay / (commandsTimelineData.length - 1)) * 100
                    : 50;
                  const ySuccessPercent = ((data.success / maxCommandsPerDay) * 95);
                  const yFailedPercent = ((data.failed / maxCommandsPerDay) * 95);
                  
                  return (
                    <>
                      {/* Success point - small dot */}
                      <div
                        className="absolute w-2 h-2 bg-green-500 rounded-full pointer-events-none transform -translate-x-1/2 -translate-y-1/2"
                        style={{
                          left: `${xPercent}%`,
                          top: `${100 - ySuccessPercent}%`,
                        }}
                      />
                      {/* Failed point - small dot */}
                      <div
                        className="absolute w-2 h-2 bg-red-500 rounded-full pointer-events-none transform -translate-x-1/2 -translate-y-1/2"
                        style={{
                          left: `${xPercent}%`,
                          top: `${100 - yFailedPercent}%`,
                        }}
                      />
                    </>
                  );
                })()}

                {/* Tooltip - positioned above the highest point */}
                {hoveredDay !== null && commandsTimelineData[hoveredDay] && (() => {
                  const data = commandsTimelineData[hoveredDay];
                  const xPercent = commandsTimelineData.length > 1
                    ? (hoveredDay / (commandsTimelineData.length - 1)) * 100
                    : 50;
                  const maxVal = Math.max(data.success, data.failed);
                  const yMaxPercent = ((maxVal / maxCommandsPerDay) * 95);
                  
                  return (
                    <div
                      className="absolute z-10 pointer-events-none"
                      style={{
                        left: `${xPercent}%`,
                        top: `${Math.max(5, 100 - yMaxPercent - 25)}%`,
                        transform: 'translateX(-50%)'
                      }}
                    >
                      <div className="bg-neutral-800 dark:bg-neutral-700 text-white text-xs rounded-lg px-3 py-2 shadow-lg whitespace-nowrap">
                        <div className="font-medium mb-1">{formatTooltipDate(data.date)}</div>
                        <div className="flex items-center gap-3">
                          <span className="text-green-400">{data.success} success</span>
                          <span className="text-red-400">{data.failed} failed</span>
                        </div>
                        <div className="border-t border-neutral-600 mt-1 pt-1 text-neutral-300">
                          Total: {data.total}
                        </div>
                      </div>
                      {/* Arrow */}
                      <div className="absolute left-1/2 -translate-x-1/2 -bottom-1 w-2 h-2 bg-neutral-800 dark:bg-neutral-700 rotate-45"></div>
                    </div>
                  );
                })()}
              </div>

              {/* X-axis labels */}
              <div className="absolute left-14 right-0 bottom-0 flex justify-between text-xs text-neutral-500 dark:text-neutral-400">
                {commandsTimelineData.map((data, index) => (
                  <div
                    key={index}
                    className="text-center"
                    style={{
                      width: `${100 / commandsTimelineData.length}%`,
                      visibility: formatDateLabel(data.date, index, commandsTimelineData.length) ? 'visible' : 'hidden'
                    }}
                  >
                    {formatDateLabel(data.date, index, commandsTimelineData.length)}
                  </div>
                ))}
              </div>
            </div>

            {/* Legend */}
            <div className="flex items-center justify-center gap-6 mt-6 pt-4 border-t border-neutral-100 dark:border-neutral-700">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                <span className="text-sm text-neutral-600 dark:text-neutral-300">Success</span>
                <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">({totalSuccess.toLocaleString()})</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-red-500 rounded-full"></div>
                <span className="text-sm text-neutral-600 dark:text-neutral-300">Failed</span>
                <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">({totalFailed.toLocaleString()})</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm text-neutral-500 dark:text-neutral-400">Total:</span>
                <span className="text-sm font-bold text-neutral-900 dark:text-neutral-100">{(totalSuccess + totalFailed).toLocaleString()}</span>
              </div>
            </div>
          </>
        ) : (
          <div className="text-center py-16 text-neutral-500 dark:text-neutral-400">
            <Terminal className="w-12 h-12 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
            <p className="text-sm font-medium">No command history yet</p>
            <p className="text-xs mt-1">Commands will appear here once you start executing them</p>
          </div>
        )}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-3 gap-6">
        {/* Left: Findings by Severity */}
        <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6">
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">Findings by Severity</h3>

          {findingsBySeverity.total > 0 ? (
            <div className="space-y-3">
              {/* Critical */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                    <span className="text-sm text-neutral-700 dark:text-neutral-300">Critical</span>
                  </div>
                  <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{findingsBySeverity.critical}</span>
                </div>
                <div className="h-2 bg-neutral-100 dark:bg-neutral-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-red-500"
                    style={{ width: `${findingsBySeverity.total > 0 ? (findingsBySeverity.critical / findingsBySeverity.total) * 100 : 0}%` }}
                  ></div>
                </div>
              </div>

              {/* High */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 bg-orange-500 rounded-full"></div>
                    <span className="text-sm text-neutral-700 dark:text-neutral-300">High</span>
                  </div>
                  <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{findingsBySeverity.high}</span>
                </div>
                <div className="h-2 bg-neutral-100 dark:bg-neutral-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-orange-500"
                    style={{ width: `${findingsBySeverity.total > 0 ? (findingsBySeverity.high / findingsBySeverity.total) * 100 : 0}%` }}
                  ></div>
                </div>
              </div>

              {/* Medium */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 bg-yellow-500 rounded-full"></div>
                    <span className="text-sm text-neutral-700 dark:text-neutral-300">Medium</span>
                  </div>
                  <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{findingsBySeverity.medium}</span>
                </div>
                <div className="h-2 bg-neutral-100 dark:bg-neutral-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-yellow-500"
                    style={{ width: `${findingsBySeverity.total > 0 ? (findingsBySeverity.medium / findingsBySeverity.total) * 100 : 0}%` }}
                  ></div>
                </div>
              </div>

              {/* Low */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                    <span className="text-sm text-neutral-700 dark:text-neutral-300">Low</span>
                  </div>
                  <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{findingsBySeverity.low}</span>
                </div>
                <div className="h-2 bg-neutral-100 dark:bg-neutral-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500"
                    style={{ width: `${findingsBySeverity.total > 0 ? (findingsBySeverity.low / findingsBySeverity.total) * 100 : 0}%` }}
                  ></div>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-neutral-500 dark:text-neutral-400">
              <Shield className="w-12 h-12 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
              <p className="text-sm">No findings yet</p>
            </div>
          )}
        </div>

        {/* Center: Tool Usage */}
        <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Tool Usage</h3>
            <Link
              to="/commands?tab=analytics"
              className="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 flex items-center gap-1"
            >
              View all
              <ArrowUpRight className="w-3 h-3" />
            </Link>
          </div>

          {topTools.length > 0 ? (
            <div className="space-y-3">
              {topTools.map((tool, index) => (
                <div key={tool.tool} className="flex items-center justify-between">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-xs text-neutral-400 dark:text-neutral-500 font-mono w-4">
                      {index + 1}.
                    </span>
                    <code className="text-sm text-neutral-700 dark:text-neutral-300 font-mono truncate">
                      {tool.tool}
                    </code>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <span className="text-xs text-neutral-500 dark:text-neutral-400 font-mono">
                      {tool.count}×
                    </span>
                    <span className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 w-12 text-right">
                      {tool.percentage}%
                    </span>
                  </div>
                </div>
              ))}
              <div className="pt-2 border-t border-neutral-100 dark:border-neutral-700">
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  Last 30 days • Success rate avg: {topTools.length > 0 ? Math.round(topTools.reduce((sum, t) => sum + t.success_rate, 0) / topTools.length) : 0}%
                </p>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-neutral-500 dark:text-neutral-400">
              <Terminal className="w-12 h-12 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
              <p className="text-sm">No tool usage data</p>
            </div>
          )}
        </div>

        {/* Right: Assessment Status */}
        <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6">
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">Assessment Status</h3>

          {assessmentDistribution.total > 0 ? (
            <div className="space-y-4">
              {/* Active */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-primary-100/50 dark:bg-primary-900/20 rounded-lg flex items-center justify-center">
                    <Activity className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                  </div>
                  <div>
                    <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Active</div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400">{assessmentDistribution.activePercent}% of total</div>
                  </div>
                </div>
                <div className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{assessmentDistribution.active}</div>
              </div>

              {/* Completed */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-green-100 dark:bg-green-900/30 rounded-lg flex items-center justify-center">
                    <Shield className="w-5 h-5 text-green-600 dark:text-green-400" />
                  </div>
                  <div>
                    <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Completed</div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400">{assessmentDistribution.completedPercent}% of total</div>
                  </div>
                </div>
                <div className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{assessmentDistribution.completed}</div>
              </div>

              {/* Archived */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-neutral-100 dark:bg-neutral-700 rounded-lg flex items-center justify-center">
                    <FileText className="w-5 h-5 text-gray-600 dark:text-gray-400" />
                  </div>
                  <div>
                    <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Archived</div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400">{assessmentDistribution.archivedPercent}% of total</div>
                  </div>
                </div>
                <div className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{assessmentDistribution.archived}</div>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-neutral-500 dark:text-neutral-400">
              <Activity className="w-12 h-12 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
              <p className="text-sm">No assessments yet</p>
            </div>
          )}
        </div>
      </div>

      <NVDDigest />

      {/* Recent Findings Table */}
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Recent Findings</h3>
          <Link to="/assessments" className="text-sm text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 flex items-center gap-1">
            View all
            <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>

        {recentFindings.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-neutral-200 dark:border-neutral-700">
                  <th className="text-left py-2 px-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">Finding</th>
                  <th className="text-left py-2 px-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase w-28">Severity</th>
                  <th className="text-left py-2 px-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase w-40">Target</th>
                  <th className="text-right py-2 px-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase w-24">Time</th>
                </tr>
              </thead>
              <tbody>
                {recentFindings.map((finding) => (
                  <tr key={finding.id} className="border-b border-neutral-100 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors">
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${finding.severity === 'CRITICAL' ? 'bg-red-500' :
                          finding.severity === 'HIGH' ? 'bg-orange-500' :
                            finding.severity === 'MEDIUM' ? 'bg-yellow-500' :
                              'bg-blue-500'
                          }`}></div>
                        <span className="text-sm text-neutral-900 dark:text-neutral-100">{finding.title}</span>
                      </div>
                    </td>
                    <td className="py-3 px-3">
                      <span className={`inline-flex px-2 py-1 text-xs font-medium rounded ${finding.severity === 'CRITICAL' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' :
                        finding.severity === 'HIGH' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300' :
                          finding.severity === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300' :
                            'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                        }`}>
                        {finding.severity}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <span className="text-sm text-neutral-600 dark:text-neutral-400 truncate block max-w-[160px]" title={finding.target_service}>
                        {finding.target_service || 'N/A'}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-right">
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">
                        {(() => {
                          const now = utcDate();
                          const created = utcDate(finding.created_at);
                          const diffMs = now - created;
                          const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
                          const diffDays = Math.floor(diffHours / 24);

                          if (diffDays > 0) return `${diffDays}d ago`;
                          if (diffHours > 0) return `${diffHours}h ago`;
                          return 'Just now';
                        })()}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-neutral-500 dark:text-neutral-400">
            <AlertTriangle className="w-12 h-12 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
            <p className="text-sm">No findings yet</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
