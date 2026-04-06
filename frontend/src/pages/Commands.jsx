import { useState, useEffect, useCallback, useRef, Fragment } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Terminal, Clock, Search, ChevronDown, ChevronRight, Check, X, Plus, Activity, TrendingUp, AlertCircle, BarChart3 } from '../components/icons';
import commandService from '../services/commandService';
import commandSettingsService from '../services/commandSettingsService';
import toolStatsService from '../services/toolStatsService';
import useInfiniteScroll from '../hooks/useInfiniteScroll';
import { useWebSocketContext } from '../contexts/WebSocketContext';

const Commands = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  // Stats state
  const [stats, setStats] = useState({ total: 0, passed: 0, failed: 0, avg_execution_time: 0 });

  // Command list state
  const [commands, setCommands] = useState([]);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [hasMore, setHasMore] = useState(true);
  const [total, setTotal] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [expandedCommand, setExpandedCommand] = useState(null);
  const [searchDebounceTimer, setSearchDebounceTimer] = useState(null);

  // Main tab state - initialize from URL param
  const [mainTab, setMainTab] = useState(searchParams.get('tab') || 'all'); // 'all' | 'approval' | 'analytics'

  // Analytics states
  const [toolStats, setToolStats] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsPeriod, setAnalyticsPeriod] = useState('30'); // 30, 90, 180, all
  const [includeFailedCommands, setIncludeFailedCommands] = useState(true);

  // Approval sub-tab state
  const [approvalTab, setApprovalTab] = useState('pending'); // 'pending' | 'history'
  const [historyFilter, setHistoryFilter] = useState('all'); // 'all' | 'approved' | 'rejected' | 'timeout'

  // Pending commands state
  const [pendingCommands, setPendingCommands] = useState([]);
  const [historyCommands, setHistoryCommands] = useState([]);
  const [pendingCount, setPendingCount] = useState(0);

  // Command settings state
  const [executionMode, setExecutionMode] = useState('open');
  const [filterKeywords, setFilterKeywords] = useState([]);
  const [newKeyword, setNewKeyword] = useState('');
  const [savingMode, setSavingMode] = useState(false);
  const [httpMethodRules, setHttpMethodRules] = useState({});

  // Approval state
  const [processingId, setProcessingId] = useState(null);
  const [expandedPendingId, setExpandedPendingId] = useState(null);
  const [expandedHistoryId, setExpandedHistoryId] = useState(null);

  // WebSocket for real-time updates
  const { subscribe } = useWebSocketContext();

  // Keep filters in a ref so WebSocket handlers always see the latest values
  const filterRef = useRef({ statusFilter, searchQuery, typeFilter });
  useEffect(() => {
    filterRef.current = { statusFilter, searchQuery, typeFilter };
  }, [statusFilter, searchQuery, typeFilter]);

  // Load initial data
  useEffect(() => {
    loadStats();
    loadSettings();
    loadInitialCommands();
    loadPendingCommands();

    // Load analytics if tab=analytics on mount
    if (mainTab === 'analytics') {
      loadAnalytics();
    }
  }, []);

  // Load analytics when tab changes or filters update
  useEffect(() => {
    if (mainTab === 'analytics') {
      loadAnalytics();
    }
  }, [mainTab, analyticsPeriod, includeFailedCommands]);

  // Subscribe to WebSocket events for real-time updates
  useEffect(() => {
    const prependCommand = (data, isSuccess) => {
      const newCmd = data?.command;
      if (!newCmd) return;
      const { statusFilter: sf, searchQuery: sq, typeFilter: tf } = filterRef.current;
      const statusMatch = sf === 'all' || (isSuccess ? sf === 'passed' : sf === 'failed');
      const searchMatch = !sq ||
        newCmd.command?.toLowerCase().includes(sq.toLowerCase()) ||
        newCmd.assessment_name?.toLowerCase().includes(sq.toLowerCase());
      const cmdType = newCmd.command_type || 'shell';
      const typeMatch = tf === 'all' || cmdType === tf;
      if (statusMatch && searchMatch && typeMatch) {
        setCommands(prev => [newCmd, ...prev]);
        setTotal(prev => prev + 1);
      }
      loadStats();
    };

    const unsubscribes = [
      subscribe('command_pending_approval', () => loadPendingCommands()),
      subscribe('command_approved', () => {
        loadPendingCommands();
        loadInitialCommands();
        loadStats();
      }),
      subscribe('command_rejected', () => loadPendingCommands()),
      subscribe('command_timeout', () => loadPendingCommands()),
      subscribe('command_completed', (data) => prependCommand(data, true)),
      subscribe('command_failed', (data) => prependCommand(data, false)),
    ];
    return () => unsubscribes.forEach(unsub => unsub && unsub());
  }, [subscribe]);

  const loadStats = async () => {
    try {
      const data = await commandService.getStats();
      setStats(data);
    } catch (error) {
      // console.error('Failed to load stats:', error);
    }
  };

  const loadSettings = async () => {
    try {
      const settings = await commandSettingsService.getCommandSettings();
      setExecutionMode(settings.execution_mode || 'open');
      setFilterKeywords(settings.filter_keywords || []);
      setHttpMethodRules(settings.http_method_rules || {});
    } catch (error) {
      // console.error('Failed to load settings:', error);
    }
  };

  const loadPendingCommands = async () => {
    try {
      const data = await commandSettingsService.listPendingCommands();
      const allCmds = data.commands || [];
      setPendingCommands(allCmds.filter(c => c.status === 'pending'));
      setHistoryCommands(allCmds.filter(c => c.status !== 'pending'));
      setPendingCount(data.pending_count || 0);
    } catch (error) {
      // console.error('Failed to load pending commands:', error);
    }
  };

  const loadAnalytics = async () => {
    try {
      setAnalyticsLoading(true);
      const params = {
        top_n: 20,
        include_failed: includeFailedCommands
      };

      // Add period filter
      if (analyticsPeriod !== 'all') {
        params.since_days = parseInt(analyticsPeriod);
      }

      const data = await toolStatsService.getToolStats(params);
      setToolStats(data);
    } catch (error) {
      console.error('Failed to load analytics:', error);
      setToolStats(null);
    } finally {
      setAnalyticsLoading(false);
    }
  };

  const loadMore = useCallback(async () => {
    if (loading || !hasMore) return;
    try {
      setLoading(true);
      const skip = commands.length;
      const status = statusFilter === 'passed' ? 'success' : statusFilter === 'failed' ? 'failed' : null;
      const command_type = typeFilter !== 'all' ? typeFilter : null;
      const data = await commandService.getAllCommands({ skip, limit: 50, status, search: searchQuery.trim() || null, command_type });
      setCommands((prev) => [...prev, ...data.commands]);
      setTotal(data.total);
      setHasMore(data.has_more);
    } catch (error) {
      // console.error('Failed to load commands:', error);
    } finally {
      setLoading(false);
    }
  }, [commands.length, statusFilter, typeFilter, searchQuery, hasMore, loading]);

  const loadInitialCommands = async () => {
    try {
      setInitialLoading(true);
      const data = await commandService.getAllCommands({ skip: 0, limit: 50, status: null, search: null });
      setCommands(data.commands);
      setTotal(data.total);
      setHasMore(data.has_more);
    } catch (error) {
      // console.error('Failed to load commands:', error);
    } finally {
      setInitialLoading(false);
    }
  };

  // Stable reload — always reads fresh values from filterRef, accepts overrides for
  // values that changed THIS render (state not yet committed when called synchronously)
  const reloadWithFilters = useCallback(async ({ sf, tf, sq } = {}) => {
    const resolvedSf = sf ?? filterRef.current.statusFilter;
    const resolvedTf = tf ?? filterRef.current.typeFilter;
    const resolvedSq = sq ?? filterRef.current.searchQuery;
    try {
      setLoading(true);
      const status = resolvedSf === 'passed' ? 'success' : resolvedSf === 'failed' ? 'failed' : null;
      const command_type = resolvedTf !== 'all' ? resolvedTf : null;
      const data = await commandService.getAllCommands({ skip: 0, limit: 50, status, search: resolvedSq.trim() || null, command_type });
      setCommands(data.commands);
      setTotal(data.total);
      setHasMore(data.has_more);
      setExpandedCommand(null);
    } catch (error) {
      // console.error('Failed to reload commands:', error);
    } finally {
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleStatusFilterChange = (newStatus) => {
    setStatusFilter(newStatus);
    filterRef.current = { ...filterRef.current, statusFilter: newStatus };
    if (!initialLoading) reloadWithFilters({ sf: newStatus });
  };

  const handleTypeFilterChange = (newType) => {
    setTypeFilter(newType);
    filterRef.current = { ...filterRef.current, typeFilter: newType };
    if (!initialLoading) reloadWithFilters({ tf: newType });
  };

  const handleSearchChange = (value) => {
    setSearchQuery(value);
    filterRef.current = { ...filterRef.current, searchQuery: value };
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    const timer = setTimeout(() => { if (!initialLoading) reloadWithFilters({ sq: value }); }, 500);
    setSearchDebounceTimer(timer);
  };

  useEffect(() => { return () => { if (searchDebounceTimer) clearTimeout(searchDebounceTimer); }; }, [searchDebounceTimer]);

  const sentryRef = useInfiniteScroll({ onLoadMore: loadMore, hasMore, loading, threshold: 300 });

  // Mode and keyword handlers
  const handleModeChange = async (newMode) => {
    setSavingMode(true);
    try {
      await commandSettingsService.updateCommandSettings({ execution_mode: newMode });
      setExecutionMode(newMode);
    } catch (error) {
      console.error('Failed to update mode:', error);
    } finally {
      setSavingMode(false);
    }
  };

  const handleAddKeyword = async () => {
    if (!newKeyword.trim()) return;
    try {
      const result = await commandSettingsService.addKeyword(newKeyword.trim());
      setFilterKeywords(result.filter_keywords);
      setNewKeyword('');
    } catch (error) {
      console.error('Failed to add keyword:', error);
    }
  };

  const handleRemoveKeyword = async (keyword) => {
    try {
      const result = await commandSettingsService.removeKeyword(keyword);
      setFilterKeywords(result.filter_keywords);
    } catch (error) {
      console.error('Failed to remove keyword:', error);
    }
  };

  const handleHttpMethodRuleChange = async (method, action) => {
    const updated = { ...httpMethodRules, [method]: action };
    // Remove 'inherit' entries to keep the stored object clean
    if (action === 'inherit') delete updated[method];
    try {
      const result = await commandSettingsService.updateHttpMethodRules(updated);
      setHttpMethodRules(result.http_method_rules || {});
    } catch (error) {
      console.error('Failed to update HTTP method rule:', error);
    }
  };

  // Approval handlers
  const handleApprove = async (commandId) => {
    setProcessingId(commandId);
    try {
      await commandSettingsService.approveCommand(commandId);
      await loadPendingCommands();
      await loadInitialCommands();
      await loadStats();
    } catch (error) {
      console.error('Failed to approve command:', error);
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (commandId) => {
    setProcessingId(commandId);
    try {
      await commandSettingsService.rejectCommand(commandId);
      await loadPendingCommands();
    } catch (error) {
      console.error('Failed to reject command:', error);
    } finally {
      setProcessingId(null);
    }
  };

  // Helpers
  const getStatusDot = (status, success) => {
    if (status === 'pending') return 'bg-amber-400';
    if (status === 'executed' || status === 'approved') return 'bg-green-500';
    if (status === 'rejected') return 'bg-red-500';
    if (status === 'timeout') return 'bg-orange-500';
    if (success === true) return 'bg-green-500';
    if (success === false) return 'bg-red-500';
    return 'bg-neutral-400';
  };

  const getStatusLabel = (status) => {
    if (status === 'pending') return 'Pending';
    if (status === 'executed') return 'Approved';
    if (status === 'rejected') return 'Rejected';
    if (status === 'timeout') return 'Timeout';
    return '—';
  };

  const formatTime = (dateStr) => {
    if (!dateStr) return '—';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return date.toLocaleDateString();
  };

  // Smart preview: context around matched keyword, or first line of command
  const getCommandPreview = (command, matchedKeywords = []) => {
    if (!command) return '';
    if (matchedKeywords && matchedKeywords.length > 0) {
      const kw = matchedKeywords[0];
      const idx = command.toLowerCase().indexOf(kw.toLowerCase());
      if (idx !== -1) {
        const start = Math.max(0, idx - 35);
        const end = Math.min(command.length, idx + kw.length + 35);
        return (start > 0 ? '…' : '') + command.slice(start, end) + (end < command.length ? '…' : '');
      }
    }
    const lines = command.split('\n').filter(l => l.trim());
    const firstLine = lines[0] || command;
    const truncated = firstLine.length > 80 ? firstLine.substring(0, 80) + '…' : firstLine;
    return lines.length > 1 ? `${truncated} [+${lines.length - 1}]` : truncated;
  };

  const filteredHistory = historyCommands.filter(cmd => {
    if (historyFilter === 'all') return true;
    if (historyFilter === 'approved') return cmd.status === 'executed';
    if (historyFilter === 'rejected') return cmd.status === 'rejected';
    if (historyFilter === 'timeout') return cmd.status === 'timeout';
    return true;
  });

  if (initialLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-neutral-500 dark:text-neutral-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">Commands</h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Execution history and approval queue</p>
      </div>

      {/* Stats Header */}
      <div className="grid grid-cols-4 gap-4">
        <div className="card p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-neutral-100 dark:bg-neutral-800 rounded-lg">
              <Terminal className="w-5 h-5 text-neutral-600 dark:text-neutral-400" />
            </div>
            <div>
              <p className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">{stats.total.toLocaleString()}</p>
              <p className="text-xs text-neutral-500">Total Commands</p>
            </div>
          </div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-neutral-100 dark:bg-neutral-800 rounded-lg">
              <Clock className="w-5 h-5 text-neutral-600 dark:text-neutral-400" />
            </div>
            <div>
              <p className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">{stats.avg_execution_time}s</p>
              <p className="text-xs text-neutral-500">Avg Time</p>
            </div>
          </div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
              <TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-2xl font-semibold text-green-600 dark:text-green-400">{stats.passed.toLocaleString()}</p>
              <p className="text-xs text-neutral-500">Passed</p>
            </div>
          </div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
              <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
            </div>
            <div>
              <p className="text-2xl font-semibold text-red-600 dark:text-red-400">{stats.failed.toLocaleString()}</p>
              <p className="text-xs text-neutral-500">Failed</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Tabs */}
      <div className="flex items-center gap-6 border-b border-neutral-200 dark:border-neutral-700">
        <button
          onClick={() => setMainTab('all')}
          className={`pb-3 text-sm font-medium border-b-2 -mb-px transition-colors ${mainTab === 'all'
            ? 'border-neutral-900 dark:border-neutral-100 text-neutral-900 dark:text-neutral-100'
            : 'border-transparent text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
            }`}
        >
          All Commands
        </button>
        <button
          onClick={() => setMainTab('approval')}
          className={`pb-3 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-2 ${mainTab === 'approval'
            ? 'border-neutral-900 dark:border-neutral-100 text-neutral-900 dark:text-neutral-100'
            : 'border-transparent text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
            }`}
        >
          Command Approval
          {pendingCount > 0 && (
            <span className="px-1.5 py-0.5 text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 rounded">
              {pendingCount}
            </span>
          )}
        </button>
        <button
          onClick={() => setMainTab('analytics')}
          className={`pb-3 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-2 ${mainTab === 'analytics'
            ? 'border-neutral-900 dark:border-neutral-100 text-neutral-900 dark:text-neutral-100'
            : 'border-transparent text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
            }`}
        >
          <BarChart3 className="w-4 h-4" />
          Tool Analytics
        </button>
      </div>

      {/* All Commands Tab */}
      {mainTab === 'all' && (
        <div className="space-y-4">
          {/* Search & Filter */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Search commands..."
                className="w-full pl-9 pr-4 py-2 text-sm border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            {/* Status filter */}
            <div className="flex items-center text-xs border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden">
              {[
                { value: 'all',    label: 'All',    dot: null },
                { value: 'passed', label: 'Passed', dot: 'bg-green-500' },
                { value: 'failed', label: 'Failed', dot: 'bg-red-500' },
              ].map(({ value, label, dot }) => (
                <button
                  key={value}
                  onClick={() => handleStatusFilterChange(value)}
                  className={`px-3 py-2 transition-colors flex items-center gap-1.5 ${
                    statusFilter === value
                      ? 'bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900'
                      : 'text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800'
                  }`}
                >
                  {dot && <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dot} ${statusFilter === value ? 'opacity-70' : ''}`} />}
                  {label}
                </button>
              ))}
            </div>
            {/* Type filter */}
            <div className="flex items-center text-xs border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden">
              {[
                { value: 'all',    label: 'All',    dot: null },
                { value: 'shell',  label: 'Shell',  dot: 'bg-neutral-400' },
                { value: 'python', label: 'Python', dot: 'bg-emerald-500' },
                { value: 'http',   label: 'HTTP',   dot: 'bg-blue-500' },
              ].map(({ value, label, dot }) => (
                <button
                  key={value}
                  onClick={() => handleTypeFilterChange(value)}
                  className={`px-3 py-2 transition-colors flex items-center gap-1.5 ${
                    typeFilter === value
                      ? 'bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900'
                      : 'text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800'
                  }`}
                >
                  {dot && <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dot} ${typeFilter === value ? 'opacity-70' : ''}`} />}
                  {label}
                </button>
              ))}
            </div>
            {/* Filtered count */}
            {(statusFilter !== 'all' || typeFilter !== 'all' || searchQuery) && (
              <span className="text-xs text-neutral-400 dark:text-neutral-500 ml-1">
                {total.toLocaleString()} result{total !== 1 ? 's' : ''}
              </span>
            )}
          </div>

          {/* Commands Table */}
          <div className="card p-0 overflow-hidden">
            {commands.length === 0 ? (
              <div className="py-12 text-center text-neutral-500">
                <Terminal className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">
                {searchQuery
                  ? 'No matching commands'
                  : typeFilter !== 'all'
                  ? `No ${typeFilter} commands found`
                  : 'No commands executed yet'}
              </p>
              </div>
            ) : (
              <table className="table-notion">
                <thead>
                  <tr>
                    <th className="w-px"></th>
                    <th>Command</th>
                    <th>Assessment</th>
                    <th>Duration</th>
                    <th>Executed</th>
                    <th className="w-px"></th>
                  </tr>
                </thead>
                <tbody>
                  {commands.map((cmd) => (
                    <Fragment key={cmd.id}>
                      <tr className="cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800/50" onClick={() => setExpandedCommand(expandedCommand === cmd.id ? null : cmd.id)}>
                        <td><div className={`w-2 h-2 rounded-full ${getStatusDot(null, cmd.success)}`} /></td>
                        <td>
                          {cmd.command_type === 'python' ? (
                            <span className="inline-flex items-center gap-1.5">
                              <span className="px-1.5 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 rounded font-mono">python</span>
                              <code className="text-xs font-mono text-neutral-500 dark:text-neutral-400">
                                {(cmd.source_code?.split('\n').find(l => l.trim()) || 'python script').slice(0, 50)}…
                              </code>
                            </span>
                          ) : cmd.command_type === 'http' ? (
                            <span className="inline-flex items-center gap-1.5">
                              <span className="px-1.5 py-0.5 text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded font-mono">http</span>
                              <code className="text-xs font-mono text-neutral-500 dark:text-neutral-400">
                                {cmd.command?.length > 60 ? cmd.command.substring(0, 60) + '...' : cmd.command}
                              </code>
                            </span>
                          ) : (
                            <code className="text-xs font-mono text-neutral-700 dark:text-neutral-300">
                              {getCommandPreview(cmd.command)}
                            </code>
                          )}
                        </td>
                        <td className="text-sm text-neutral-600 dark:text-neutral-400">{cmd.assessment_name}</td>
                        <td className="text-xs text-neutral-500">{cmd.execution_time?.toFixed(2)}s</td>
                        <td className="text-xs text-neutral-500">{formatTime(cmd.created_at)}</td>
                        <td>{expandedCommand === cmd.id ? <ChevronDown className="w-4 h-4 text-neutral-400" /> : <ChevronRight className="w-4 h-4 text-neutral-400" />}</td>
                      </tr>
                      {expandedCommand === cmd.id && (
                        <tr>
                          <td colSpan="6" className="p-4 bg-neutral-50 dark:bg-neutral-800/50">
                            <div className="space-y-3">
                              <div>
                                <span className="text-xs font-medium text-neutral-500 uppercase flex items-center gap-1.5">
                                  {cmd.command_type === 'python' && (
                                    <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 rounded font-mono">python</span>
                                  )}
                                  {cmd.command_type === 'http' && (
                                    <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded font-mono">http</span>
                                  )}
                                  {cmd.command_type !== 'python' && cmd.command_type !== 'http' && 'Command'}
                                </span>
                                {cmd.command_type === 'python' ? (
                                  <pre className="block mt-1 p-2 bg-neutral-900 text-emerald-300 border border-neutral-700 rounded text-xs font-mono overflow-auto max-h-48 whitespace-pre-wrap">{cmd.source_code}</pre>
                                ) : cmd.command_type === 'http' ? (
                                  <pre className="block mt-1 p-2 bg-neutral-900 text-blue-300 border border-neutral-700 rounded text-xs font-mono overflow-auto max-h-48 whitespace-pre-wrap">{cmd.source_code}</pre>
                                ) : (
                                  <pre className="block mt-1 p-2 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded text-xs font-mono whitespace-pre-wrap break-all">{cmd.command}</pre>
                                )}
                              </div>
                              {cmd.stdout && (
                                <div>
                                  <span className="text-xs font-medium text-neutral-500 uppercase">Output</span>
                                  <pre className="mt-1 p-3 bg-neutral-900 text-neutral-100 rounded text-xs font-mono max-h-48 overflow-auto">{cmd.stdout}</pre>
                                </div>
                              )}
                              {cmd.stderr && (
                                <div>
                                  <span className="text-xs font-medium text-red-500 uppercase">Error</span>
                                  <pre className="mt-1 p-3 bg-red-950 text-red-100 rounded text-xs font-mono max-h-48 overflow-auto">{cmd.stderr}</pre>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            )}
            {hasMore && (
              <div ref={sentryRef} className="py-4 text-center">
                {loading && <span className="text-sm text-neutral-500">Loading...</span>}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Command Approval Tab */}
      {mainTab === 'approval' && (
        <div className="space-y-4">
          {/* Mode Selector */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm text-neutral-500">Execution Mode:</span>
              <div className="flex items-center text-xs border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden">
                {['open', 'filter', 'closed'].map((mode) => (
                  <button
                    key={mode}
                    onClick={() => handleModeChange(mode)}
                    disabled={savingMode}
                    className={`px-3 py-1.5 transition-colors ${executionMode === mode
                      ? 'bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900'
                      : 'text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800'
                      }`}
                  >
                    {mode.charAt(0).toUpperCase() + mode.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Keywords (only show in filter mode) */}
          {executionMode === 'filter' && (
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-xs text-neutral-500">Blocked keywords:</span>
              {filterKeywords.map((kw) => (
                <span key={kw} className="inline-flex items-center gap-1 px-2 py-0.5 bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 rounded text-xs">
                  {kw}
                  <button onClick={() => handleRemoveKeyword(kw)} className="ml-1 text-neutral-400 hover:text-red-500 transition-colors">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
              <div className="inline-flex items-center">
                <input
                  type="text"
                  value={newKeyword}
                  onChange={(e) => setNewKeyword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddKeyword()}
                  placeholder="+ add"
                  className="w-16 px-2 py-0.5 text-xs border border-dashed border-neutral-300 dark:border-neutral-600 rounded bg-transparent focus:outline-none focus:border-neutral-400 placeholder:text-neutral-400"
                />
              </div>
            </div>
          )}

          {/* HTTP Method Rules */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs text-neutral-500">HTTP method rules:</span>
            {['GET', 'POST', 'PUT', 'DELETE', 'PATCH'].map((method) => {
              const action = httpMethodRules[method] || 'inherit';
              return (
                <div key={method} className="inline-flex items-center border border-neutral-200 dark:border-neutral-700 rounded overflow-hidden text-xs">
                  <span className="px-2 py-1 bg-neutral-50 dark:bg-neutral-800 font-mono text-neutral-700 dark:text-neutral-300 border-r border-neutral-200 dark:border-neutral-700">{method}</span>
                  {['auto_approve', 'inherit', 'require_approval'].map((opt) => (
                    <button
                      key={opt}
                      onClick={() => handleHttpMethodRuleChange(method, opt)}
                      className={`px-2 py-1 transition-colors ${action === opt
                        ? opt === 'auto_approve'
                          ? 'bg-green-600 text-white'
                          : opt === 'require_approval'
                            ? 'bg-amber-500 text-white'
                            : 'bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900'
                        : 'text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800'
                      }`}
                    >
                      {opt === 'auto_approve' ? 'allow' : opt === 'require_approval' ? 'ask' : 'mode'}
                    </button>
                  ))}
                </div>
              );
            })}
          </div>

          {/* Approval Sub-tabs */}
          <div className="flex items-center gap-4 border-b border-neutral-200 dark:border-neutral-700">
            <button
              onClick={() => setApprovalTab('pending')}
              className={`pb-2 text-sm font-medium border-b-2 -mb-px transition-colors ${approvalTab === 'pending'
                ? 'border-neutral-900 dark:border-neutral-100 text-neutral-900 dark:text-neutral-100'
                : 'border-transparent text-neutral-500 hover:text-neutral-700'
                }`}
            >
              Pending {pendingCount > 0 && `(${pendingCount})`}
            </button>
            <button
              onClick={() => setApprovalTab('history')}
              className={`pb-2 text-sm font-medium border-b-2 -mb-px transition-colors ${approvalTab === 'history'
                ? 'border-neutral-900 dark:border-neutral-100 text-neutral-900 dark:text-neutral-100'
                : 'border-transparent text-neutral-500 hover:text-neutral-700'
                }`}
            >
              Approval History
            </button>
          </div>

          {/* Pending Commands */}
          {approvalTab === 'pending' && (
            <div className="card p-0 overflow-hidden">
              {pendingCommands.length === 0 ? (
                <div className="py-12 text-center text-neutral-500">
                  <Terminal className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">No commands pending approval</p>
                </div>
              ) : (
                <table className="table-notion">
                  <thead>
                    <tr>
                      <th className="w-px"></th>
                      <th>Command</th>
                      <th>Assessment</th>
                      <th>Keywords</th>
                      <th>Time</th>
                      <th className="w-24"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {pendingCommands.map((cmd) => (
                      <Fragment key={cmd.id}>
                        <tr
                          className="group cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800/50"
                          onClick={() => setExpandedPendingId(expandedPendingId === cmd.id ? null : cmd.id)}
                        >
                          <td><div className={`w-2 h-2 rounded-full ${getStatusDot(cmd.status)}`} /></td>
                          <td>
                            <code className="text-xs font-mono text-neutral-700 dark:text-neutral-300">
                              {getCommandPreview(cmd.command, cmd.matched_keywords)}
                            </code>
                          </td>
                          <td className="text-sm text-neutral-600 dark:text-neutral-400">{cmd.assessment_name}</td>
                          <td>
                            {cmd.matched_keywords?.map((kw) => (
                              <span key={kw} className="mr-1 px-1.5 py-0.5 text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 rounded">{kw}</span>
                            ))}
                          </td>
                          <td className="text-xs text-neutral-500">{formatTime(cmd.created_at)}</td>
                          <td>
                            <div className="flex items-center gap-1">
                              <button
                                onClick={(e) => { e.stopPropagation(); handleApprove(cmd.id); }}
                                disabled={processingId === cmd.id}
                                className="p-1.5 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded"
                                title="Approve"
                              >
                                <Check className="w-4 h-4" />
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); handleReject(cmd.id); }}
                                disabled={processingId === cmd.id}
                                className="p-1.5 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                                title="Reject"
                              >
                                <X className="w-4 h-4" />
                              </button>
                              {expandedPendingId === cmd.id
                                ? <ChevronDown className="w-3 h-3 text-neutral-400" />
                                : <ChevronRight className="w-3 h-3 text-neutral-400" />
                              }
                            </div>
                          </td>
                        </tr>
                        {expandedPendingId === cmd.id && (
                          <tr>
                            <td colSpan="6" className="p-0">
                              <div className="px-4 py-3 bg-neutral-50 dark:bg-neutral-800/50 border-t border-neutral-100 dark:border-neutral-700">
                                <span className="text-xs font-medium text-neutral-400 uppercase mb-1 block">Full Command</span>
                                <pre className="text-xs font-mono text-neutral-800 dark:text-neutral-200 bg-neutral-900 dark:bg-black p-3 rounded whitespace-pre-wrap break-all max-h-64 overflow-auto">
                                  {cmd.command}
                                </pre>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Approval History */}
          {approvalTab === 'history' && (
            <div className="space-y-4">
              {/* History Filter */}
              <div className="flex items-center text-xs border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden w-fit">
                {['all', 'approved', 'rejected', 'timeout'].map((filter) => (
                  <button
                    key={filter}
                    onClick={() => setHistoryFilter(filter)}
                    className={`px-3 py-1.5 transition-colors ${historyFilter === filter
                      ? 'bg-neutral-900 dark:bg-neutral-100 text-white dark:text-neutral-900'
                      : 'text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800'
                      }`}
                  >
                    {filter.charAt(0).toUpperCase() + filter.slice(1)}
                  </button>
                ))}
              </div>

              <div className="card p-0 overflow-hidden">
                {filteredHistory.length === 0 ? (
                  <div className="py-12 text-center text-neutral-500">
                    <Clock className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    <p className="text-sm">No approval history</p>
                  </div>
                ) : (
                  <table className="table-notion">
                    <thead>
                      <tr>
                        <th className="w-px"></th>
                        <th>Command</th>
                        <th>Assessment</th>
                        <th>Status</th>
                        <th>Resolved</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredHistory.map((cmd) => (
                        <Fragment key={cmd.id}>
                          <tr
                            className="cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800/50"
                            onClick={() => setExpandedHistoryId(expandedHistoryId === cmd.id ? null : cmd.id)}
                          >
                            <td><div className={`w-2 h-2 rounded-full ${getStatusDot(cmd.status)}`} /></td>
                            <td>
                              <code className="text-xs font-mono text-neutral-700 dark:text-neutral-300">
                                {getCommandPreview(cmd.command)}
                              </code>
                            </td>
                            <td className="text-sm text-neutral-600 dark:text-neutral-400">{cmd.assessment_name}</td>
                            <td>
                              <span className={`text-xs px-2 py-0.5 rounded ${cmd.status === 'executed' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300' :
                                cmd.status === 'rejected' ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' :
                                  cmd.status === 'timeout' ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300' :
                                    'bg-neutral-100 text-neutral-600'
                                }`}>
                                {getStatusLabel(cmd.status)}
                              </span>
                            </td>
                            <td className="text-xs text-neutral-500">{formatTime(cmd.resolved_at)}</td>
                          </tr>
                          {expandedHistoryId === cmd.id && (
                            <tr>
                              <td colSpan="5" className="p-0">
                                <div className="px-4 py-3 bg-neutral-50 dark:bg-neutral-800/50 border-t border-neutral-100 dark:border-neutral-700">
                                  <span className="text-xs font-medium text-neutral-400 uppercase mb-1 block">Full Command</span>
                                  <pre className="text-xs font-mono text-neutral-800 dark:text-neutral-200 bg-neutral-900 dark:bg-black p-3 rounded whitespace-pre-wrap break-all max-h-64 overflow-auto">
                                    {cmd.command}
                                  </pre>
                                  {cmd.rejection_reason && (
                                    <div className="mt-2 text-xs text-red-600 dark:text-red-400">
                                      <span className="font-medium">Reason: </span>{cmd.rejection_reason}
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tool Analytics Tab */}
      {mainTab === 'analytics' && (
        <div className="space-y-4">
          {/* Compact Filters Bar */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <select
                value={analyticsPeriod}
                onChange={(e) => setAnalyticsPeriod(e.target.value)}
                className="px-3 py-1.5 text-xs border border-neutral-200 dark:border-neutral-700 rounded bg-white dark:bg-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-1 focus:ring-primary-500"
              >
                <option value="30">30d</option>
                <option value="90">90d</option>
                <option value="180">180d</option>
                <option value="all">All</option>
              </select>

              <label className="flex items-center gap-1.5 text-xs text-neutral-600 dark:text-neutral-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeFailedCommands}
                  onChange={(e) => setIncludeFailedCommands(e.target.checked)}
                  className="w-3 h-3 rounded border-neutral-300 dark:border-neutral-600 text-primary-600 focus:ring-primary-500"
                />
                Failed
              </label>
            </div>

            {toolStats && (
              <div className="text-xs text-neutral-500">
                {toolStats.total_commands.toLocaleString()} commands • {toolStats.total_assessments} assessments
              </div>
            )}
          </div>

          {analyticsLoading ? (
            <div className="flex items-center justify-center py-16">
              <div className="text-sm text-neutral-500">Loading...</div>
            </div>
          ) : toolStats ? (
            <div className="grid grid-cols-3 gap-4">
              {/* Left: Compact Tools List */}
              <div className="col-span-2 card p-0 overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-neutral-50 dark:bg-neutral-800/50">
                    <tr className="border-b border-neutral-200 dark:border-neutral-700">
                      <th className="px-3 py-2 text-left font-medium text-neutral-500 dark:text-neutral-400 w-8">#</th>
                      <th className="px-3 py-2 text-left font-medium text-neutral-500 dark:text-neutral-400">Tool</th>
                      <th className="px-3 py-2 text-right font-medium text-neutral-500 dark:text-neutral-400 w-16">Count</th>
                      <th className="px-3 py-2 text-right font-medium text-neutral-500 dark:text-neutral-400 w-16">Share</th>
                      <th className="px-3 py-2 text-center font-medium text-neutral-500 dark:text-neutral-400 w-20">Success</th>
                    </tr>
                  </thead>
                  <tbody>
                    {toolStats.most_used_tools.map((tool, idx) => (
                      <tr
                        key={tool.tool}
                        className="border-b border-neutral-100 dark:border-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-800/30 transition-colors"
                      >
                        <td className="px-3 py-2 text-neutral-400 dark:text-neutral-500">{idx + 1}</td>
                        <td className="px-3 py-2">
                          <code className="text-neutral-900 dark:text-neutral-100 font-mono">
                            {tool.tool}
                          </code>
                        </td>
                        <td className="px-3 py-2 text-right text-neutral-600 dark:text-neutral-400 font-mono">
                          {tool.count}
                        </td>
                        <td className="px-3 py-2 text-right font-semibold text-neutral-900 dark:text-neutral-100">
                          {tool.percentage}%
                        </td>
                        <td className="px-3 py-2 text-center">
                          <div className="inline-flex items-center gap-1">
                            <div className={`w-1 h-4 rounded-full ${tool.success_rate >= 95 ? 'bg-green-500' :
                              tool.success_rate >= 85 ? 'bg-green-400' :
                                tool.success_rate >= 70 ? 'bg-yellow-500' :
                                  tool.success_rate >= 50 ? 'bg-orange-500' :
                                    'bg-red-500'
                              }`} />
                            <span className={`font-mono ${tool.success_rate >= 85 ? 'text-green-600 dark:text-green-400' :
                              tool.success_rate >= 70 ? 'text-yellow-600 dark:text-yellow-400' :
                                'text-red-600 dark:text-red-400'
                              }`}>
                              {tool.success_rate.toFixed(0)}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Right: Compact Categories */}
              <div className="card p-4 space-y-3">
                <div className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
                  Categories
                </div>

                {Object.entries(toolStats.tool_categories)
                  .sort(([, a], [, b]) => b.count - a.count)
                  .map(([category, data]) => (
                    <div key={category} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-neutral-700 dark:text-neutral-300 capitalize font-medium">
                          {category}
                        </span>
                        <div className="flex items-center gap-2">
                          <span className="text-neutral-500 dark:text-neutral-400 font-mono">
                            {data.count}
                          </span>
                          <span className="font-semibold text-neutral-900 dark:text-neutral-100 w-10 text-right">
                            {data.percentage}%
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <div className="flex-1 h-1.5 bg-neutral-100 dark:bg-neutral-800 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary-500 rounded-full"
                            style={{ width: `${data.percentage}%` }}
                          />
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {data.tools.slice(0, 3).map(t => (
                          <code key={t} className="text-[10px] px-1 py-0.5 bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 rounded">
                            {t}
                          </code>
                        ))}
                        {data.tools.length > 3 && (
                          <span className="text-[10px] text-neutral-400">
                            +{data.tools.length - 3}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          ) : (
            <div className="card p-12 text-center">
              <BarChart3 className="w-10 h-10 mx-auto mb-2 text-neutral-300 dark:text-neutral-600" />
              <p className="text-sm text-neutral-500">No data</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Commands;
