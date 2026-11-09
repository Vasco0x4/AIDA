import { utcDate } from '../utils/utcDate';
import { useState, useEffect, useRef, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Target, Server, Shield, ArrowLeft, AlertTriangle, Info, Eye, TrendingUp, Filter, FolderOpen, RefreshCw, Download, Send, Play, Copy, Check, Plus, ChevronDown } from '../components/icons';
import apiClient from '../services/api';
import workspaceService from '../services/workspaceService';
import EditableField from '../components/common/EditableField';
import ReconTable from '../components/assessment/ReconTable';
import CardsTable from '../components/assessment/CardsTable';
import CommandHistoryRefactored from '../components/assessment/CommandHistoryRefactored';
import ImportScanModal from '../components/assessment/ImportScanModal';
import CredentialsManager from '../components/assessment/CredentialsManager';
import ContextDocumentsPanel from '../components/assessment/ContextDocumentsPanel';
import AttackTimeline from '../components/assessment/AttackTimeline';
import SendReportModal from '../components/assessment/SendReportModal';
import FindingsDiff from '../components/assessment/FindingsDiff';
import AssessmentRunHistory from '../components/assessment/AssessmentRunHistory';

import ChangeContainerModal from '../components/workspace/ChangeContainerModal';
import MethodologyReport from '../components/assessment/MethodologyReport';
import AsvsGrid from '../components/assessment/AsvsGrid';
import { useWebSocket } from '../hooks/useWebSocket';
import { getSeverityBarClass, SEVERITY_ORDER } from '../utils/severity';

// Group order: findings first, then observations, then info
const CARD_TYPE_ORDER = { finding: 3, observation: 2, info: 1 };

// Sort: card type group → CVSS score desc → severity → creation date desc
const sortByScore = (a, b) => {
  const aType = CARD_TYPE_ORDER[a.card_type] || 0;
  const bType = CARD_TYPE_ORDER[b.card_type] || 0;
  if (aType !== bType) return bType - aType;
  const aScore = a.cvss_score ?? -1;
  const bScore = b.cvss_score ?? -1;
  if (aScore !== bScore) return bScore - aScore;
  const aOrder = SEVERITY_ORDER[a.severity] || 0;
  const bOrder = SEVERITY_ORDER[b.severity] || 0;
  if (aOrder !== bOrder) return bOrder - aOrder;
  return utcDate(b.created_at) - utcDate(a.created_at);
};

const AssessmentDetail = () => {
  const { id } = useParams();
  const [assessment, setAssessment] = useState(null);
  const [reconData, setReconData] = useState([]);
  const [reconCategories, setReconCategories] = useState(['endpoint', 'subdomain', 'service', 'technology']);
  const [cards, setCards] = useState([]);
  const [commands, setCommands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cardFilter, setCardFilter] = useState('overview'); // Filter for cards view
  const [addCardTrigger, setAddCardTrigger] = useState(0);
  const [showImportModal, setShowImportModal] = useState(false);
  const [openingWorkspace, setOpeningWorkspace] = useState(false);
  const [showChangeContainerModal, setShowChangeContainerModal] = useState(false);

  const [exportingPdf, setExportingPdf] = useState(false);
  const [showPdfMenu, setShowPdfMenu] = useState(false);
  const pdfMenuRef = useRef(null);
  const [showSendReport, setShowSendReport] = useState(false);
  const [showStartAI, setShowStartAI] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);
  const [launchingAI, setLaunchingAI] = useState(false);
  const [launchResult, setLaunchResult] = useState(null);
  const [showMcpNotice, setShowMcpNotice] = useState(false);
  const startAIRef = useRef(null);

  // Close the PDF export menu when clicking outside it.
  useEffect(() => {
    if (!showPdfMenu) return;
    const onDown = (e) => {
      if (pdfMenuRef.current && !pdfMenuRef.current.contains(e.target)) {
        setShowPdfMenu(false);
      }
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [showPdfMenu]);

  // WebSocket connection for real-time updates
  const { subscribe } = useWebSocket(id);

  useEffect(() => {
    loadAssessment();
  }, [id]);

  // Close Start AI popup on click outside
  useEffect(() => {
    if (!showStartAI) return;
    const handleClickOutside = (e) => {
      if (startAIRef.current && !startAIRef.current.contains(e.target)) {
        setShowStartAI(false);
        setLaunchResult(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showStartAI]);

  // Subscribe to WebSocket events for real-time updates
  useEffect(() => {
    if (!id) return;

    // Card events
    const unsubscribeCardAdded = subscribe('card_added', (data) => {

      setCards(prev => [data.card, ...prev]);
    });

    const unsubscribeCardUpdated = subscribe('card_updated', (data) => {

      setCards(prev => prev.map(card =>
        card.id === data.card_id ? data.card : card
      ));
    });

    const unsubscribeCardDeleted = subscribe('card_deleted', (data) => {

      setCards(prev => prev.filter(card => card.id !== data.card_id));
    });

    // Recon events
    const unsubscribeReconAdded = subscribe('recon_added', (data) => {

      setReconData(prev => [data.recon, ...prev]);
    });

    const unsubscribeReconUpdated = subscribe('recon_updated', (data) => {

      setReconData(prev => prev.map(recon =>
        recon.id === data.recon_id ? data.recon : recon
      ));
    });

    const unsubscribeReconDeleted = subscribe('recon_deleted', (data) => {

      setReconData(prev => prev.filter(recon => recon.id !== data.recon_id));
    });

    // Command events — de-dupe by id so a command delivered twice (e.g. a WS
    // event plus a reload) doesn't create duplicate rows / React keys.
    const prependCommand = (data) => {
      setCommands(prev => {
        const cmd = data?.command;
        if (!cmd || prev.some(c => c.id === cmd.id)) return prev;
        return [cmd, ...prev];
      });
    };
    const unsubscribeCommandCompleted = subscribe('command_completed', prependCommand);
    const unsubscribeCommandFailed = subscribe('command_failed', prependCommand);

    // Assessment events
    const unsubscribeAssessmentUpdated = subscribe('assessment_updated', (data) => {

      setAssessment(prev => ({ ...prev, ...data.fields }));
    });

    // Cleanup subscriptions on unmount
    return () => {
      unsubscribeCardAdded();
      unsubscribeCardUpdated();
      unsubscribeCardDeleted();
      unsubscribeReconAdded();
      unsubscribeReconUpdated();
      unsubscribeReconDeleted();
      unsubscribeCommandCompleted();
      unsubscribeCommandFailed();
      unsubscribeAssessmentUpdated();
    };
  }, [id, subscribe]);

  const loadAssessment = async () => {
    try {
      setLoading(true);

      // Load all data in parallel
      const [assessmentRes, reconRes, reconTypesRes, cardsRes, commandsRes] = await Promise.all([
        apiClient.get(`/assessments/${id}`),
        apiClient.get(`/assessments/${id}/recon`),
        apiClient.get(`/assessments/${id}/recon/types`),
        apiClient.get(`/assessments/${id}/cards`),
        apiClient.get(`/assessments/${id}/commands?limit=10000`),
      ]);

      setAssessment(assessmentRes.data);
      setReconData(reconRes.data);
      setReconCategories(reconTypesRes.data.length > 0 ? reconTypesRes.data : reconCategories);
      setCards(cardsRes.data);
      setCommands(commandsRes.data);
    } catch (error) {
      console.error('Failed to load assessment:', error);
    } finally {
      setLoading(false);
    }
  };

  const updateAssessment = async (field, value) => {
    try {
      await apiClient.put(`/assessments/${id}`, { [field]: value });
      setAssessment(prev => ({ ...prev, [field]: value }));
    } catch (error) {
      console.error('Failed to update assessment:', error);
    }
  };

  const handleExportPdf = async ({ includeSecrets = false, template = 'default' } = {}) => {
    setShowPdfMenu(false);
    setExportingPdf(true);
    try {
      const response = await apiClient.get(`/assessments/${id}/report/pdf`, {
        params: { include_secrets: includeSecrets, template },
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
      const suffix = (includeSecrets ? '_with_creds' : '') + (template !== 'default' ? `_${template}` : '');
      const safeName = assessment.name.replace(/[^a-zA-Z0-9 _-]/g, '_');
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `AIDA_Report_${safeName}${suffix}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('PDF export failed:', err);
      alert('Failed to generate PDF report. Check console for details.');
    } finally {
      setExportingPdf(false);
    }
  };

  const handleExportMarkdown = async () => {
    setShowPdfMenu(false);
    try {
      const response = await apiClient.get(`/assessments/${id}/report/markdown`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'text/markdown' }));
      const safeName = assessment.name.replace(/[^a-zA-Z0-9 _-]/g, '_');
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `AIDA_Report_${safeName}.md`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Markdown export failed:', err);
      alert('Failed to generate Markdown report. Check console for details.');
    }
  };

  const handleOpenWorkspace = async () => {
    if (!assessment.workspace_path) {
      alert('No workspace created for this assessment yet.');
      return;
    }

    setOpeningWorkspace(true);

    try {
      // First get the host path from backend
      const result = await workspaceService.openAssessmentWorkspace(id);

      if (result.success && result.host_path) {
        // Try to open via local folder opener service (runs on host)
        try {
          const { openFolderOnHost } = await import('../services/hostHelperService');
          const openResult = await openFolderOnHost(result.host_path);
          if (openResult.success) {
            return; // Success!
          }
        } catch (serviceError) {
          // Folder opener service not available, falling back to clipboard
        }

        // Fallback: Copy path to clipboard
        if (navigator.clipboard) {
          await navigator.clipboard.writeText(result.host_path);
          alert(`Path copied to clipboard:\n\n${result.host_path}\n\nPaste in Finder (Cmd+Shift+G)`);
        } else {
          alert(`Workspace path:\n\n${result.host_path}`);
        }
      }
    } catch (error) {
      console.error('Failed to open workspace:', error);
      alert(error.response?.data?.detail || 'Failed to open workspace folder');
    } finally {
      setOpeningWorkspace(false);
    }
  };

  const handleContainerChange = async (result) => {
    // Close modal
    setShowChangeContainerModal(false);
    // Reload assessment to get updated data
    await loadAssessment();
  };

  // Calculate statistics
  const stats = useMemo(() => {
    const findings = cards.filter(c => c.card_type === 'finding');
    const observations = cards.filter(c => c.card_type === 'observation');
    const infos = cards.filter(c => c.card_type === 'info');

    // Recent activity (last 7 days)
    const sevenDaysAgo = utcDate();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
    const recentCards = cards.filter(card => utcDate(card.created_at) > sevenDaysAgo);

    const last24h = utcDate();
    last24h.setDate(last24h.getDate() - 1);
    const last24hCards = cards.filter(card => utcDate(card.created_at) > last24h);

    return {
      totalCards: cards.length,
      findings: findings.length,
      observations: observations.length,
      infos: infos.length,
      critical: findings.filter(f => f.severity === 'CRITICAL').length,
      high: findings.filter(f => f.severity === 'HIGH').length,
      medium: findings.filter(f => f.severity === 'MEDIUM').length,
      low: findings.filter(f => f.severity === 'LOW').length,
      commands: commands.length,
      recon: reconData.length,
      recentCards: recentCards.length,
      last24hCards: last24hCards.length
    };
  }, [cards, commands, reconData]);

  // Filter cards based on selected filter
  const filteredCards = useMemo(() => {
    let result;
    switch (cardFilter) {
      case 'findings':
        result = cards.filter(c => c.card_type === 'finding');
        break;
      case 'observations':
        result = cards.filter(c => c.card_type === 'observation');
        break;
      case 'info':
        result = cards.filter(c => c.card_type === 'info');
        break;
      case 'critical':
        result = cards.filter(c => c.severity === 'CRITICAL');
        break;
      case 'high':
        result = cards.filter(c => c.severity === 'HIGH');
        break;
      case 'medium':
        result = cards.filter(c => c.severity === 'MEDIUM');
        break;
      case 'low':
        result = cards.filter(c => c.severity === 'LOW');
        break;
      case 'overview':
      default:
        result = cards;
        break;
    }
    return [...result].sort(sortByScore);
  }, [cards, cardFilter]);

  // Recon categories sorted by item count (descending) — counts precomputed to avoid O(n²) in sort
  const sortedReconCategories = useMemo(() => {
    const counts = {};
    for (const item of reconData) {
      counts[item.data_type] = (counts[item.data_type] || 0) + 1;
    }
    return [...reconCategories].sort((a, b) => (counts[b] || 0) - (counts[a] || 0));
  }, [reconData, reconCategories]);

  // Calculate risk distribution percentages
  const getRiskDistribution = () => {
    const total = stats.critical + stats.high + stats.medium + stats.low;
    if (total === 0) return { critical: 0, high: 0, medium: 0, low: 0 };

    return {
      critical: Math.round((stats.critical / total) * 100),
      high: Math.round((stats.high / total) * 100),
      medium: Math.round((stats.medium / total) * 100),
      low: Math.round((stats.low / total) * 100)
    };
  };

  const riskDistribution = getRiskDistribution();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
      </div>
    );
  }

  if (!assessment) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">Assessment not found</h1>
          <p className="text-neutral-600 dark:text-neutral-400 mb-4">The assessment you're looking for doesn't exist.</p>
          <Link to="/assessments" className="btn btn-primary">
            Back to Assessments
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-4">
      {/* Header compact */}
      <div className="flex items-center justify-between border-b border-neutral-200 dark:border-neutral-700 pb-4">
        <div className="flex items-center gap-3">
          <Link
            to="/assessments"
            className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </Link>
          <div className="h-5 w-px bg-neutral-200 dark:bg-neutral-700" />
          <div>
            <h1 className="text-lg font-semibold text-gray-900 dark:text-neutral-100">{assessment.name}</h1>
            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-neutral-400">
              <span>{assessment.client_name || 'No client'}</span>
              {assessment.environment && assessment.environment !== 'non_specifie' && (
                <>
                  <span>•</span>
                  <span className={`font-medium ${assessment.environment === 'production'
                    ? 'text-orange-600 dark:text-orange-400'
                    : 'text-green-600 dark:text-green-400'
                    }`}>
                    {assessment.environment === 'production' ? 'Production' : 'Dev'}
                  </span>
                </>
              )}
              <span>•</span>
              <span>{assessment.status}</span>
              {assessment.container_name && (
                <>
                  <span>•</span>
                  <button
                    onClick={() => setShowChangeContainerModal(true)}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors font-mono text-xs font-medium"
                    title="Click to change container"
                  >
                    <Server className="w-3 h-3" />
                    {assessment.container_name}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowImportModal(true)}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-neutral-700 dark:text-neutral-300 bg-neutral-50 dark:bg-neutral-700/50 border border-neutral-200 dark:border-neutral-600 hover:bg-neutral-100 dark:hover:bg-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-500 rounded-md transition-colors"
            title="Import scan results"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <span>Import</span>
          </button>
          <button
            onClick={handleOpenWorkspace}
            disabled={openingWorkspace}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-neutral-700 dark:text-neutral-300 bg-neutral-50 dark:bg-neutral-700/50 border border-neutral-200 dark:border-neutral-600 hover:bg-neutral-100 dark:hover:bg-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-500 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="Open workspace folder"
          >
            {openingWorkspace ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Opening...</span>
              </>
            ) : (
              <>
                <FolderOpen className="w-3.5 h-3.5" />
                <span>Workspace</span>
              </>
            )}
          </button>

          <div ref={pdfMenuRef} className="relative inline-flex">
            <button
              onClick={() => handleExportPdf({ includeSecrets: false })}
              disabled={exportingPdf}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-neutral-700 dark:text-neutral-300 bg-neutral-50 dark:bg-neutral-700/50 border border-neutral-200 dark:border-neutral-600 hover:bg-neutral-100 dark:hover:bg-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-500 rounded-l-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Export PDF — passwords and tokens are masked"
            >
              {exportingPdf ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Generating...</span>
                </>
              ) : (
                <>
                  <Download className="w-3.5 h-3.5" />
                  <span>PDF</span>
                </>
              )}
            </button>
            <button
              onClick={() => setShowPdfMenu((v) => !v)}
              disabled={exportingPdf}
              className="inline-flex items-center px-1.5 py-1.5 text-xs text-neutral-700 dark:text-neutral-300 bg-neutral-50 dark:bg-neutral-700/50 border border-l-0 border-neutral-200 dark:border-neutral-600 hover:bg-neutral-100 dark:hover:bg-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-500 rounded-r-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="More export options"
              aria-haspopup="menu"
              aria-expanded={showPdfMenu}
            >
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
            {showPdfMenu && (
              <div role="menu" className="absolute right-0 top-full mt-1 z-20 w-72 rounded-md border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 shadow-lg p-1 text-xs">
                <button
                  role="menuitem"
                  onClick={() => handleExportPdf({ includeSecrets: false })}
                  className="w-full text-left px-3 py-2 rounded hover:bg-neutral-100 dark:hover:bg-neutral-700/60"
                >
                  <div className="font-medium text-neutral-800 dark:text-neutral-100">Download PDF — secrets masked</div>
                  <div className="mt-0.5 text-[11px] text-neutral-500 dark:text-neutral-400 leading-snug">
                    Passwords, tokens and cookies replaced by <code className="font-mono">[REDACTED]</code>. Safe to share with the client.
                  </div>
                </button>
                <button
                  role="menuitem"
                  onClick={() => handleExportPdf({ includeSecrets: true })}
                  className="w-full text-left px-3 py-2 rounded hover:bg-rose-50 dark:hover:bg-rose-900/20"
                >
                  <div className="font-medium text-rose-700 dark:text-rose-300">Download PDF — include credentials</div>
                  <div className="mt-0.5 text-[11px] text-neutral-500 dark:text-neutral-400 leading-snug">
                    Plaintext passwords and tokens embedded. Internal use only — file is suffixed <code className="font-mono">_with_creds</code>.
                  </div>
                </button>
                <div className="my-1 border-t border-neutral-100 dark:border-neutral-700" />
                <div className="px-3 pt-1.5 pb-1 text-[10px] font-semibold uppercase tracking-wide text-neutral-400">
                  Compliance appendix (E4)
                </div>
                {[
                  { key: 'owasp', label: 'OWASP Top 10 (2021)' },
                  { key: 'pci', label: 'PCI DSS v4.0' },
                  { key: 'nist', label: 'NIST CSF 2.0' },
                ].map((t) => (
                  <button
                    key={t.key}
                    role="menuitem"
                    onClick={() => handleExportPdf({ includeSecrets: false, template: t.key })}
                    className="w-full text-left px-3 py-2 rounded hover:bg-neutral-100 dark:hover:bg-neutral-700/60"
                  >
                    <div className="font-medium text-neutral-800 dark:text-neutral-100">PDF + {t.label}</div>
                    <div className="mt-0.5 text-[11px] text-neutral-500 dark:text-neutral-400 leading-snug">
                      Findings mapped to {t.label} controls as a report appendix. Secrets masked.
                    </div>
                  </button>
                ))}
                <div className="my-1 border-t border-neutral-100 dark:border-neutral-700" />
                <button
                  role="menuitem"
                  onClick={handleExportMarkdown}
                  className="w-full text-left px-3 py-2 rounded hover:bg-neutral-100 dark:hover:bg-neutral-700/60"
                >
                  <div className="font-medium text-neutral-800 dark:text-neutral-100">Download Markdown</div>
                  <div className="mt-0.5 text-[11px] text-neutral-500 dark:text-neutral-400 leading-snug">
                    Machine-readable report (findings, kill chain, recon) for handoff or diffing. Secrets masked.
                  </div>
                </button>
              </div>
            )}
          </div>
          <button
            onClick={() => setShowSendReport(true)}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-neutral-700 dark:text-neutral-300 bg-neutral-50 dark:bg-neutral-700/50 border border-neutral-200 dark:border-neutral-600 hover:bg-neutral-100 dark:hover:bg-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-500 rounded-md transition-colors"
            title="Send report via Telegram, Slack, or Email"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Send</span>
          </button>
          <div className="relative" ref={startAIRef}>
            <button
              onClick={() => {
                if (!localStorage.getItem('aida_mcp_notice_seen')) {
                  setShowMcpNotice(true);
                  return;
                }
                // Clear any stale result from a previous open so the popup
                // always starts fresh — otherwise reopening after a success
                // shows the old success banner with no launch button.
                if (!showStartAI) setLaunchResult(null);
                setShowStartAI(!showStartAI);
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary-600 hover:bg-primary-700 border border-primary-600 rounded-md transition-colors"
              title="Start AI-driven scan"
            >
              <Play className="w-3.5 h-3.5" />
              <span>Start AI</span>
            </button>
            {showStartAI && (
              <div className="absolute right-0 top-full mt-2 w-96 bg-white dark:bg-neutral-800 rounded-lg shadow-xl border border-neutral-200 dark:border-neutral-700 p-4 z-50">
                <h4 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3">Launch AI Scan</h4>

                {launchResult?.type === 'success' ? (
                  /* Success state — only show confirmation */
                  <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 text-sm">
                    <Check className="w-4 h-4 flex-shrink-0" />
                    <span>Terminal opened with AI scan</span>
                  </div>
                ) : (
                  <>
                    {/* Launch button */}
                    <button
                      onClick={async () => {
                        setLaunchingAI(true);
                        setLaunchResult(null);
                        try {
                          const { launchAidaOnHost } = await import('../services/hostHelperService');
                          const data = await launchAidaOnHost(assessment.name);
                          setLaunchResult(data.success ? { type: 'success', text: 'Terminal opened with AI scan!' } : { type: 'error', text: data.error || 'Failed to launch' });
                        } catch (e) {
                          setLaunchResult({ type: 'error', text: 'Host helper not running. Use the command below instead.' });
                        } finally {
                          setLaunchingAI(false);
                        }
                      }}
                      disabled={launchingAI}
                      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                    >
                      <Play className="w-4 h-4" />
                      {launchingAI ? 'Opening terminal...' : 'Open in Terminal'}
                    </button>

                    {launchResult?.type === 'error' && (
                      <div className="mt-2 flex items-start gap-1.5 px-2.5 py-1.5 rounded text-xs bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400">
                        <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                        <span>{launchResult.text}</span>
                      </div>
                    )}

                    {/* Fallback: copy command */}
                    <div className="mt-3 pt-3 border-t border-neutral-200 dark:border-neutral-700">
                      <p className="text-[10px] text-neutral-500 dark:text-neutral-400 mb-1.5">Or run manually:</p>
                      <div className="relative">
                        <pre className="text-[11px] font-mono bg-neutral-900 text-green-400 px-3 py-2 rounded-lg overflow-x-auto">python3 aida.py -a "{assessment.name}"</pre>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(`python3 aida.py -a "${assessment.name}"`);
                            setCopiedCmd(true);
                            setTimeout(() => setCopiedCmd(false), 2000);
                          }}
                          className="absolute top-1 right-1 p-1 rounded bg-neutral-700 hover:bg-neutral-600"
                        >
                          {copiedCmd ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3 text-neutral-400" />}
                        </button>
                      </div>
                    </div>

                    <div className="mt-2 text-[10px] text-neutral-500 dark:text-neutral-400">
                      Commands requiring approval will appear in the <strong>Commands</strong> page.
                    </div>
                  </>
                )}

                <button onClick={() => { setShowStartAI(false); setLaunchResult(null); }} className="mt-3 w-full text-xs text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300">
                  Close
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Import Scan Modal */}
      {showImportModal && (
        <ImportScanModal
          assessmentId={id}
          onClose={() => setShowImportModal(false)}
          onSuccess={(stats) => {
            // Reload assessment data
            loadAssessment();
          }}
        />
      )}

      {/* Change Container Modal */}
      {showChangeContainerModal && assessment && (
        <ChangeContainerModal
          assessment={assessment}
          onClose={() => setShowChangeContainerModal(false)}
          onSuccess={handleContainerChange}
        />
      )}

      {/* Stats en ligne compactes */}
      <div className="grid grid-cols-6 gap-3 text-center">
        <div className="bg-gray-50 dark:bg-neutral-800 p-3 rounded border border-neutral-200 dark:border-neutral-700">
          <div className="text-lg font-semibold text-gray-900 dark:text-neutral-100">{stats.totalCards}</div>
          <div className="text-xs text-gray-500 dark:text-neutral-400">Cards</div>
        </div>
        <div className="bg-gray-50 dark:bg-neutral-800 p-3 rounded border border-neutral-200 dark:border-neutral-700">
          <div className="text-lg font-semibold text-gray-900 dark:text-neutral-100">{stats.commands}</div>
          <div className="text-xs text-gray-500 dark:text-neutral-400">Commands</div>
        </div>
        <div className="bg-gray-50 dark:bg-neutral-800 p-3 rounded border border-neutral-200 dark:border-neutral-700">
          <div className="text-lg font-semibold text-gray-900 dark:text-neutral-100">{stats.recon}</div>
          <div className="text-xs text-gray-500 dark:text-neutral-400">Recon</div>
        </div>
        <div className="bg-red-50 dark:bg-red-900/30 p-3 rounded border border-red-200 dark:border-red-700">
          <div className="text-lg font-semibold text-red-600 dark:text-red-400">{stats.critical}</div>
          <div className="text-xs text-red-600 dark:text-red-400">Critical</div>
        </div>
        <div className="bg-orange-50 dark:bg-orange-900/30 p-3 rounded border border-orange-200 dark:border-orange-700">
          <div className="text-lg font-semibold text-orange-600 dark:text-orange-400">{stats.high}</div>
          <div className="text-xs text-orange-600 dark:text-orange-400">High</div>
        </div>
        <div className="bg-yellow-50 dark:bg-yellow-900/30 p-3 rounded border border-yellow-200 dark:border-yellow-700">
          <div className="text-lg font-semibold text-yellow-600 dark:text-yellow-400">{stats.medium}</div>
          <div className="text-xs text-yellow-600 dark:text-yellow-400">Medium</div>
        </div>
      </div>

      {/* Assessment Settings - Déplacé en haut */}
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700 bg-gray-50 dark:bg-neutral-900">
          <h2 className="text-sm font-semibold text-gray-800 dark:text-neutral-100">Assessment Settings</h2>
        </div>
        <div className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 text-sm">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500">Client</span>
              <EditableField
                value={assessment.client_name || ''}
                onSave={(value) => updateAssessment('client_name', value)}
                placeholder="Client name"
                className="text-gray-900 dark:text-neutral-100"
              />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500">Scope</span>
              <EditableField
                value={assessment.scope || ''}
                onSave={(value) => updateAssessment('scope', value)}
                placeholder="Assessment scope"
                className="text-gray-900 dark:text-neutral-100"
              />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500">Domains</span>
              <EditableField
                value={assessment.target_domains || ''}
                onSave={(value) => updateAssessment('target_domains', value)}
                placeholder="Target domains"
                multiline
                className="text-gray-900 dark:text-neutral-100"
              />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500">IP Scopes</span>
              <EditableField
                value={assessment.ip_scopes || ''}
                onSave={(value) => updateAssessment('ip_scopes', value)}
                placeholder="IP scopes"
                multiline
                className="text-gray-900 dark:text-neutral-100"
              />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500">Limitations</span>
              <EditableField
                value={assessment.limitations || ''}
                onSave={(value) => updateAssessment('limitations', value)}
                placeholder="Assessment limitations"
                multiline
                className="text-gray-900 dark:text-neutral-100"
              />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500">Objectives</span>
              <EditableField
                value={assessment.objectives || ''}
                onSave={(value) => updateAssessment('objectives', value)}
                placeholder="Assessment objectives"
                multiline
                className="text-gray-900 dark:text-neutral-100"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Credentials & Tokens Section - Minimalist */}
      <div>
        <CredentialsManager assessmentId={id} onUpdate={loadAssessment} />
      </div>

      {/* Context Documents Section */}
      <div>
        <ContextDocumentsPanel assessmentId={parseInt(id)} />
      </div>



      {/* Reconnaissance Data - Dynamic Categories */}
      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-neutral-100">Reconnaissance Data</h2>
        <div className="space-y-3">
          {/* Render categories in pairs (2 columns) */}
          {sortedReconCategories
            .reduce((pairs, category, index, sorted) => {
              if (index % 2 === 0) pairs.push(sorted.slice(index, index + 2));
              return pairs;
            }, []).map((pair, pairIndex) => (
            <div key={pairIndex} className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {pair.map(category => (
                <ReconTable
                  key={category}
                  title={category.charAt(0).toUpperCase() + category.slice(1) + 's'}
                  data={reconData.filter(item => item.data_type === category)}
                  assessmentId={id}
                  onUpdate={loadAssessment}
                />
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Cards & Findings - Compact Horizontal Layout */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-neutral-100">Cards & Findings</h2>
          <div className="flex items-center gap-3">
            <span className="text-sm text-neutral-500 dark:text-neutral-400">{filteredCards.length} cards</span>
            <button
              onClick={() => setAddCardTrigger(t => t + 1)}
              className="px-3 py-1.5 bg-primary-600 dark:bg-primary-700 text-white rounded-lg text-xs font-medium hover:bg-primary-700 dark:hover:bg-primary-600 transition-colors flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Card
            </button>
          </div>
        </div>

        {/* Compact horizontal filter bar - Single row */}
        <div className="flex flex-wrap items-center gap-2 mb-6 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3">
          {/* Type filters */}
          <button
            onClick={() => setCardFilter('overview')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${cardFilter === 'overview'
              ? 'bg-primary-500 text-white shadow-sm'
              : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-600'
              }`}
          >
            <span>All Cards</span>
            <span className={`${cardFilter === 'overview' ? 'opacity-90' : 'opacity-60'}`}>{stats.totalCards}</span>
          </button>

          <button
            onClick={() => setCardFilter('findings')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${cardFilter === 'findings'
              ? 'bg-primary-500 text-white shadow-sm'
              : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-600'
              }`}
          >
            <span>Findings</span>
            <span className={`${cardFilter === 'findings' ? 'opacity-90' : 'opacity-60'}`}>{stats.findings}</span>
          </button>

          <button
            onClick={() => setCardFilter('observations')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${cardFilter === 'observations'
              ? 'bg-primary-500 text-white shadow-sm'
              : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-600'
              }`}
          >
            <span>Observations</span>
            <span className={`${cardFilter === 'observations' ? 'opacity-90' : 'opacity-60'}`}>{stats.observations}</span>
          </button>

          <button
            onClick={() => setCardFilter('info')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${cardFilter === 'info'
              ? 'bg-primary-500 text-white shadow-sm'
              : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-600'
              }`}
          >
            <span>Info</span>
            <span className={`${cardFilter === 'info' ? 'opacity-90' : 'opacity-60'}`}>{stats.infos}</span>
          </button>

          {/* Divider */}
          <div className="h-6 w-px bg-neutral-300 dark:bg-neutral-600 mx-1"></div>

          {/* Severity filters with colored dots and labels */}
          <button
            onClick={() => setCardFilter('critical')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${cardFilter === 'critical'
              ? 'bg-red-500 text-white shadow-sm'
              : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/30'
              }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${cardFilter === 'critical' ? 'bg-white' : 'bg-red-500'}`}></span>
            <span>Critical</span>
            <span className={`${cardFilter === 'critical' ? 'opacity-90' : 'opacity-70'}`}>{stats.critical}</span>
          </button>

          <button
            onClick={() => setCardFilter('high')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${cardFilter === 'high'
              ? 'bg-orange-500 text-white shadow-sm'
              : 'bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300 hover:bg-orange-100 dark:hover:bg-orange-900/30'
              }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${cardFilter === 'high' ? 'bg-white' : 'bg-orange-500'}`}></span>
            <span>High</span>
            <span className={`${cardFilter === 'high' ? 'opacity-90' : 'opacity-70'}`}>{stats.high}</span>
          </button>

          <button
            onClick={() => setCardFilter('medium')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${cardFilter === 'medium'
              ? 'bg-yellow-500 text-white shadow-sm'
              : 'bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-300 hover:bg-yellow-100 dark:hover:bg-yellow-900/30'
              }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${cardFilter === 'medium' ? 'bg-white' : 'bg-yellow-500'}`}></span>
            <span>Medium</span>
            <span className={`${cardFilter === 'medium' ? 'opacity-90' : 'opacity-70'}`}>{stats.medium}</span>
          </button>

          <button
            onClick={() => setCardFilter('low')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${cardFilter === 'low'
              ? 'bg-blue-500 text-white shadow-sm'
              : 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/30'
              }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${cardFilter === 'low' ? 'bg-white' : 'bg-blue-500'}`}></span>
            <span>Low</span>
            <span className={`${cardFilter === 'low' ? 'opacity-90' : 'opacity-70'}`}>{stats.low}</span>
          </button>
        </div>

        {/* Content area - Full width */}
        <div className="w-full">
          {/* Content based on filter */}
          {cardFilter === 'overview' ? (
            <div className="space-y-4">
              {/* Risk Distribution */}
              <div>
                <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
                  <Target className="w-4 h-4 text-primary-500" />
                  Risk Distribution
                </h3>

                {stats.findings > 0 ? (
                  <div className="space-y-4">
                    {/* Visual Bar Chart */}
                    <div className="flex h-8 bg-neutral-100 dark:bg-neutral-700 rounded-lg overflow-hidden">
                      {riskDistribution.critical > 0 && (
                        <div className={`${getSeverityBarClass('CRITICAL')} flex items-center justify-center text-white text-xs font-medium`} style={{ width: `${riskDistribution.critical}%` }}>
                          {riskDistribution.critical}%
                        </div>
                      )}
                      {riskDistribution.high > 0 && (
                        <div className={`${getSeverityBarClass('HIGH')} flex items-center justify-center text-white text-xs font-medium`} style={{ width: `${riskDistribution.high}%` }}>
                          {riskDistribution.high}%
                        </div>
                      )}
                      {riskDistribution.medium > 0 && (
                        <div className={`${getSeverityBarClass('MEDIUM')} flex items-center justify-center text-white text-xs font-medium`} style={{ width: `${riskDistribution.medium}%` }}>
                          {riskDistribution.medium}%
                        </div>
                      )}
                      {riskDistribution.low > 0 && (
                        <div className={`${getSeverityBarClass('LOW')} flex items-center justify-center text-white text-xs font-medium`} style={{ width: `${riskDistribution.low}%` }}>
                          {riskDistribution.low}%
                        </div>
                      )}
                    </div>

                  </div>
                ) : (
                  <div className="text-center py-8 text-neutral-500 dark:text-neutral-400">
                    <Shield className="w-12 h-12 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
                    <p className="text-sm">No findings yet</p>
                  </div>
                )}
              </div>

              {/* Findings */}
              <CardsTable
                cards={filteredCards.filter(c => c.card_type === 'finding')}
                assessmentId={id}
                onUpdate={loadAssessment}
                hideAddButton
                externalTrigger={addCardTrigger}
              />

              {/* Divider — Observations & Info */}
              {(stats.observations + stats.infos) > 0 && (
                <>
                  <div className="relative my-1">
                    <div className="absolute inset-0 flex items-center">
                      <div className="w-full border-t border-neutral-200 dark:border-neutral-700" />
                    </div>
                    <div className="relative flex justify-center">
                      <span className="px-3 bg-white dark:bg-neutral-900 text-xs text-neutral-400 dark:text-neutral-500 font-medium uppercase tracking-wider">
                        Observations & Info
                      </span>
                    </div>
                  </div>
                  <CardsTable
                    cards={filteredCards.filter(c => c.card_type === 'observation' || c.card_type === 'info')}
                    assessmentId={id}
                    onUpdate={loadAssessment}
                    hideAddButton
                  />
                </>
              )}

              {stats.totalCards === 0 && (
                <div className="text-center py-8 text-neutral-500 dark:text-neutral-400">
                  <Shield className="w-12 h-12 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
                  <p className="text-sm">No cards yet</p>
                </div>
              )}
            </div>
          ) : (
            /* Filtered view */
            <div>
              <CardsTable
                cards={filteredCards}
                assessmentId={id}
                onUpdate={loadAssessment}
                hideAddButton
                externalTrigger={addCardTrigger}
              />
            </div>
          )}
        </div>
      </div>

      {/* Canonical run history within this Assessment. */}
      <AssessmentRunHistory assessmentId={parseInt(id)} />

      {/* Legacy comparison for data created before same-Assessment Scan Runs. */}
      <details className="rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 p-4">
        <summary className="cursor-pointer text-sm font-medium">Legacy cross-assessment comparison</summary>
        <div className="mt-4"><FindingsDiff assessment={assessment} /></div>
      </details>

      {/* OWASP ASVS verification grid (ASVS-methodology assessments only) */}
      {assessment?.methodology === 'asvs' && (
        <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4">
          <AsvsGrid assessmentId={parseInt(id)} />
        </div>
      )}

      {/* Methodology Report */}
      <MethodologyReport assessmentId={parseInt(id)} />

      {/* Command History - Version compacte et navigable */}
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <div className="px-4 py-3 border-b border-neutral-200 dark:border-neutral-700 bg-gray-50 dark:bg-neutral-900">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-800 dark:text-neutral-100">Command History</h2>
            <span className="text-xs text-gray-500 dark:text-neutral-400">{commands.length} commands</span>
          </div>
        </div>
        <div className="p-4">
          <CommandHistoryRefactored commands={commands} />
        </div>
      </div>
      {/* Attack Timeline */}
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg">
        <div className="p-4">
          <AttackTimeline assessmentId={parseInt(id)} />
        </div>
      </div>

      {/* Send Report Modal */}
      {showSendReport && (
        <SendReportModal
          assessmentId={parseInt(id)}
          assessmentName={assessment.name}
          onClose={() => setShowSendReport(false)}
        />
      )}



      {/* First-time MCP notice modal */}
      {showMcpNotice && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 dark:bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-strong max-w-md w-full mx-4 animate-slide-up">
            <div className="px-6 pt-6 pb-4">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center">
                  <Info className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">Before you start</h3>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">Authentication required for AI clients</p>
                </div>
              </div>

              <div className="space-y-3 text-sm text-neutral-700 dark:text-neutral-300">
                <p>
                  To connect an AI client (Claude Desktop, Cursor, Gemini, etc.) via MCP, you need to run <code className="font-mono text-xs bg-neutral-100 dark:bg-neutral-700 px-1.5 py-0.5 rounded">aida.py</code> once from your terminal first.
                </p>
                <p>This authenticates against the backend and caches a long-lived API key — every subsequent launch is silent.</p>
                <div className="bg-neutral-900 rounded-lg px-4 py-3 font-mono text-xs text-green-400">
                  python3 aida.py
                </div>
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  Using <strong className="text-neutral-600 dark:text-neutral-300">Claude Code, Codex, Kimi, or Qwen</strong>? The launcher handles everything automatically — no extra step needed.
                </p>
              </div>
            </div>

            <div className="px-6 py-4 border-t border-neutral-200 dark:border-neutral-700 flex justify-end gap-3">
              <button
                onClick={() => setShowMcpNotice(false)}
                className="btn btn-secondary btn-sm"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  localStorage.setItem('aida_mcp_notice_seen', '1');
                  setShowMcpNotice(false);
                  setLaunchResult(null);
                  setShowStartAI(true);
                }}
                className="btn btn-primary btn-sm"
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AssessmentDetail;
