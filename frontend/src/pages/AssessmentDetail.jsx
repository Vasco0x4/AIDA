import { useState, useEffect, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Target, Server, Shield, ArrowLeft, AlertTriangle, Info, Eye, TrendingUp, Filter, FolderOpen, RefreshCw, FileText, Plus } from '../components/icons';
import apiClient from '../services/api';
import workspaceService from '../services/workspaceService';
import EditableField from '../components/common/EditableField';
import ReconTable from '../components/assessment/ReconTable';
import PhaseSection from '../components/assessment/PhaseSection';
import PhaseContentViewSimple from '../components/assessment/PhaseContentViewSimple';
import CardsTable from '../components/assessment/CardsTable';
import CommandHistoryRefactored from '../components/assessment/CommandHistoryRefactored';
import ImportScanModal from '../components/assessment/ImportScanModal';
import CredentialsManager from '../components/assessment/CredentialsManager';
import ContextDocumentsPanel from '../components/assessment/ContextDocumentsPanel';

import ChangeContainerModal from '../components/workspace/ChangeContainerModal';
import MarkdownDocumentsModal from '../components/assessment/MarkdownDocumentsModal';
import { useWebSocket } from '../hooks/useWebSocket';
import { getSeverityBarClass, SEVERITY_ORDER } from '../utils/severity';
import { PHASE_NAMES } from '../utils/phases';

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
  return new Date(b.created_at) - new Date(a.created_at);
};

const AssessmentDetail = () => {
  const { id } = useParams();
  const [assessment, setAssessment] = useState(null);
  const [reconData, setReconData] = useState([]);
  const [reconCategories, setReconCategories] = useState(['endpoint', 'subdomain', 'service', 'technology']);
  const [cards, setCards] = useState([]);
  const [sections, setSections] = useState([]);
  const [commands, setCommands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activePhase, setActivePhase] = useState(1); // Phase 1 par défaut
  const [cardFilter, setCardFilter] = useState('overview'); // Filter for cards view
  const [addCardTrigger, setAddCardTrigger] = useState(0);
  const [showImportModal, setShowImportModal] = useState(false);
  const [openingWorkspace, setOpeningWorkspace] = useState(false);
  const [showChangeContainerModal, setShowChangeContainerModal] = useState(false);
  const [showMarkdownModal, setShowMarkdownModal] = useState(false);

  // WebSocket connection for real-time updates
  const { subscribe, isConnected } = useWebSocket(id);

  useEffect(() => {
    loadAssessment();
  }, [id]);

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

    // Section events
    const unsubscribeSectionUpdated = subscribe('section_updated', (data) => {

      setSections(prev => {
        const index = prev.findIndex(s => s.id === data.section.id);
        if (index >= 0) {
          const newSections = [...prev];
          newSections[index] = data.section;
          return newSections;
        } else {
          return [...prev, data.section];
        }
      });
    });

    // Command events
    const unsubscribeCommandCompleted = subscribe('command_completed', (data) => {

      setCommands(prev => [data.command, ...prev]);
    });

    const unsubscribeCommandFailed = subscribe('command_failed', (data) => {

      setCommands(prev => [data.command, ...prev]);
    });

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
      unsubscribeSectionUpdated();
      unsubscribeCommandCompleted();
      unsubscribeCommandFailed();
      unsubscribeAssessmentUpdated();
    };
  }, [id, subscribe]);

  const loadAssessment = async () => {
    try {
      setLoading(true);

      // Load all data in parallel
      const [assessmentRes, reconRes, reconTypesRes, cardsRes, sectionsRes, commandsRes] = await Promise.all([
        apiClient.get(`/assessments/${id}`),
        apiClient.get(`/assessments/${id}/recon`),
        apiClient.get(`/assessments/${id}/recon/types`),
        apiClient.get(`/assessments/${id}/cards`),
        apiClient.get(`/assessments/${id}/sections`),
        apiClient.get(`/assessments/${id}/commands?limit=10000`),
      ]);

      setAssessment(assessmentRes.data);
      setReconData(reconRes.data);
      setReconCategories(reconTypesRes.data.length > 0 ? reconTypesRes.data : reconCategories);
      setCards(cardsRes.data);
      setSections(sectionsRes.data);
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
      setAssessment({ ...assessment, [field]: value });
    } catch (error) {
      console.error('Failed to update assessment:', error);
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
          const { openFolderOnHost } = await import('../services/folderOpenerService');
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
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
    const recentCards = cards.filter(card => new Date(card.created_at) > sevenDaysAgo);

    const last24h = new Date();
    last24h.setDate(last24h.getDate() - 1);
    const last24hCards = cards.filter(card => new Date(card.created_at) > last24h);

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
      phases: sections.length,
      recentCards: recentCards.length,
      last24hCards: last24hCards.length
    };
  }, [cards, commands, reconData, sections]);

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
          <button
            onClick={() => setShowMarkdownModal(true)}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-neutral-700 dark:text-neutral-300 bg-neutral-50 dark:bg-neutral-700/50 border border-neutral-200 dark:border-neutral-600 hover:bg-neutral-100 dark:hover:bg-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-500 rounded-md transition-colors"
            title="View markdown documents"
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Docs</span>
          </button>
          <span className={`px-2 py-1 rounded-full text-xs font-medium ${assessment.status === 'in_progress'
            ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
            : assessment.status === 'completed'
              ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
              : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300'
            }`}>
            {assessment.status}
          </span>
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
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
              <span className="font-medium text-gray-700 dark:text-neutral-300">Client:</span>
              <EditableField
                value={assessment.client_name || ''}
                onSave={(value) => updateAssessment('client_name', value)}
                placeholder="Client name"
                className="text-gray-900 dark:text-neutral-100 ml-2"
              />
            </div>
            <div>
              <span className="font-medium text-gray-700 dark:text-neutral-300">Scope:</span>
              <EditableField
                value={assessment.scope || ''}
                onSave={(value) => updateAssessment('scope', value)}
                placeholder="Assessment scope"
                className="text-gray-900 dark:text-neutral-100 ml-2"
              />
            </div>
            <div>
              <span className="font-medium text-gray-700 dark:text-neutral-300">Domains:</span>
              <EditableField
                value={assessment.target_domains || ''}
                onSave={(value) => updateAssessment('target_domains', value)}
                placeholder="Target domains"
                multiline
                className="text-gray-900 dark:text-neutral-100 ml-2"
              />
            </div>
            <div>
              <span className="font-medium text-gray-700 dark:text-neutral-300">IP Scopes:</span>
              <EditableField
                value={assessment.ip_scopes || ''}
                onSave={(value) => updateAssessment('ip_scopes', value)}
                placeholder="IP scopes"
                multiline
                className="text-gray-900 dark:text-neutral-100 ml-2"
              />
            </div>
            <div>
              <span className="font-medium text-gray-700 dark:text-neutral-300">Limitations:</span>
              <EditableField
                value={assessment.limitations || ''}
                onSave={(value) => updateAssessment('limitations', value)}
                placeholder="Assessment limitations"
                multiline
                className="text-gray-900 dark:text-neutral-100 ml-2"
              />
            </div>
            <div>
              <span className="font-medium text-gray-700 dark:text-neutral-300">Objectives:</span>
              <EditableField
                value={assessment.objectives || ''}
                onSave={(value) => updateAssessment('objectives', value)}
                placeholder="Assessment objectives"
                multiline
                className="text-gray-900 dark:text-neutral-100 ml-2"
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
          {[...reconCategories]
            .sort((a, b) =>
              reconData.filter(i => i.data_type === b).length -
              reconData.filter(i => i.data_type === a).length
            )
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

      {/* Assessment Phases - Vue Pleine Largeur Simple */}
      <div>
        {/* Navigation horizontale + Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-neutral-100">Assessment Phases</h2>
          </div>

          {/* Navigation horizontale des phases */}
          <div className="flex space-x-1 border-b border-gray-200 dark:border-neutral-700">
            {[1, 2, 3, 4, 5].map((phaseNum) => {
              const section = sections.find(s => s.section_type === `phase_${phaseNum}`);
              const hasContent = section?.content;

              return (
                <button
                  key={phaseNum}
                  onClick={() => setActivePhase(phaseNum)}
                  className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activePhase === phaseNum
                    ? 'border-blue-500 text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30'
                    : 'border-transparent text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 hover:border-gray-300 dark:hover:border-neutral-600'
                    }`}
                >
                  <div className="flex items-center gap-2">
                    <span>Phase {phaseNum}</span>
                    {hasContent && (
                      <div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-neutral-400 mt-0.5">
                    {PHASE_NAMES[phaseNum]}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Contenu de la phase active - Pleine largeur */}
        {activePhase && (
          <PhaseContentViewSimple
            phaseNumber={activePhase}
            assessmentId={id}
            section={sections.find(s => s.section_type === `phase_${activePhase}`)}
            onUpdate={loadAssessment}
            cards={cards.filter(c => c.section_number === activePhase)}
            commands={commands.filter(c => c.phase?.includes(`Phase ${activePhase}`))}
          />
        )}
      </div>

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
      {/* Markdown Documents Modal */}
      {showMarkdownModal && (
        <MarkdownDocumentsModal
          assessmentId={parseInt(id)}
          onClose={() => setShowMarkdownModal(false)}
        />
      )}
    </div>
  );
};

export default AssessmentDetail;