import { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Shield, Eye, EyeOff, Info, AlertTriangle, Edit2, Trash2, Plus } from '../icons';
import { getSeverityBadgeClass, getSeverityBarClass, getSeverityTextClass } from '../../utils/severity';
import UnifiedModal from '../common/UnifiedModal';
import CvssCalculator from './CvssCalculator';
import apiClient from '../../services/api';

const CardsTable = ({ cards, assessmentId, onUpdate, hideAddButton = false, externalTrigger = 0 }) => {
  const [expandedCards, setExpandedCards] = useState(new Set());

  // Modal state for Add/Edit
  const [showModal, setShowModal] = useState(false);
  const [editingCard, setEditingCard] = useState(null);
  const [formData, setFormData] = useState({
    card_type: 'finding',
    title: '',
    target_service: '',
    severity: 'MEDIUM',
    status: 'potential',
    section_number: '',
    technical_analysis: '',
    proof: '',
    notes: '',
    context: '',
    cvss_vector: null,
    cvss_score: null,
    cvss_mode: 'cvss',  // 'cvss' | 'manual'
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const toggleCard = (cardId) => {
    const newExpanded = new Set(expandedCards);
    if (newExpanded.has(cardId)) {
      newExpanded.delete(cardId);
    } else {
      newExpanded.add(cardId);
    }
    setExpandedCards(newExpanded);
  };

  const getCardIcon = (cardType, severity) => {
    switch (cardType) {
      case 'finding':
        return <Shield className="w-4 h-4" />;
      case 'observation':
        return <Eye className="w-4 h-4" />;
      case 'info':
        return <Info className="w-4 h-4" />;
      default:
        return <AlertTriangle className="w-4 h-4" />;
    }
  };

  const getCardTypeColor = (cardType) => {
    switch (cardType) {
      case 'finding':
        return 'text-red-600 dark:text-red-400';
      case 'observation':
        return 'text-blue-600 dark:text-blue-400';
      case 'info':
        return 'text-green-600 dark:text-green-400';
      default:
        return 'text-neutral-600 dark:text-neutral-400';
    }
  };

  // Open Add modal
  const openAddModal = () => {
    setEditingCard(null);
    setFormData({
      card_type: 'finding',
      title: '',
      target_service: '',
      severity: 'MEDIUM',
      status: 'potential',
      section_number: '',
      technical_analysis: '',
      proof: '',
      notes: '',
      context: '',
      cvss_vector: null,
      cvss_score: null,
      cvss_mode: 'cvss',
    });
    setShowModal(true);
  };

  // Open modal when header button triggers it
  useEffect(() => {
    if (externalTrigger > 0) openAddModal();
  }, [externalTrigger]);

  // Open Edit modal
  const openEditModal = (card) => {
    setEditingCard(card);
    setFormData({
      card_type: card.card_type || 'finding',
      title: card.title || '',
      target_service: card.target_service || '',
      severity: card.severity || 'MEDIUM',
      status: card.status || 'potential',
      section_number: card.section_number || '',
      technical_analysis: card.technical_analysis || '',
      proof: card.proof || '',
      notes: card.notes || '',
      context: card.context || '',
      cvss_vector: card.cvss_vector || null,
      cvss_score: card.cvss_score || null,
      cvss_mode: card.cvss_vector ? 'cvss' : 'manual',
    });
    setShowModal(true);
  };

  // Handle Submit
  const handleSubmit = async () => {
    if (!formData.title.trim()) {
      alert('Title is required');
      return;
    }

    try {
      setIsSubmitting(true);

      const isFinding = formData.card_type === 'finding';
      const useCvss = isFinding && formData.cvss_mode === 'cvss' && formData.cvss_vector;

      const payload = {
        card_type: formData.card_type,
        title: formData.title.trim(),
        target_service: formData.target_service || null,
        severity: isFinding ? formData.severity : null,
        status: formData.status || null,
        section_number: formData.section_number || null,
        technical_analysis: formData.technical_analysis || null,
        proof: formData.proof || null,
        notes: formData.notes || null,
        context: formData.context || null,
        cvss_vector: useCvss ? formData.cvss_vector : null,
        cvss_score: useCvss ? formData.cvss_score : null,
      };

      if (editingCard) {
        await apiClient.patch(`/assessments/${assessmentId}/cards/${editingCard.id}`, payload);
      } else {
        await apiClient.post(`/assessments/${assessmentId}/cards`, payload);
      }

      setShowModal(false);
      onUpdate();
    } catch (error) {
      console.error('Failed to save card:', error);
      alert('Failed to save. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Delete
  const handleDelete = async (cardId) => {
    if (!window.confirm('Are you sure you want to delete this card?')) return;

    try {
      await apiClient.delete(`/assessments/${assessmentId}/cards/${cardId}`);
      onUpdate();
    } catch (error) {
      console.error('Failed to delete card:', error);
      alert('Failed to delete. Please try again.');
    }
  };

  if (cards.length === 0) {
    return (
      <div className="text-center py-8 text-sm text-neutral-500 dark:text-neutral-400">
        {!hideAddButton && (
          <button
            onClick={openAddModal}
            className="mb-4 px-4 py-2 bg-primary-600 dark:bg-primary-700 text-white rounded-lg text-sm hover:bg-primary-700 dark:hover:bg-primary-600 transition-colors"
          >
            <Plus className="w-4 h-4 inline mr-2" />
            Add Card
          </button>
        )}
        <p>No cards in this phase</p>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-2">
        {!hideAddButton && (
          <div className="flex justify-end mb-2">
            <button
              onClick={openAddModal}
              className="px-3 py-1.5 bg-primary-600 dark:bg-primary-700 text-white rounded-lg text-xs hover:bg-primary-700 dark:hover:bg-primary-600 transition-colors flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Card
            </button>
          </div>
        )}

        {cards.map((card) => {
          const isExpanded = expandedCards.has(card.id);
          const cardType = card.card_type || 'unknown';
          const severity = card.severity || 'INFO';
          const title = card.title || 'Untitled';
          const targetService = card.target_service || 'N/A';
          const sectionNumber = card.section_number || 'N/A';
          const isFalsePositive = card.status === 'false_positive';

          return (
            <div key={card.id} id={`card-${card.id}`} className={`flex border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden bg-white dark:bg-neutral-800 hover:border-neutral-300 dark:hover:border-neutral-600 transition-colors ${isFalsePositive ? 'opacity-50' : ''}`}>
              {/* Left color strip */}
              <div className={`w-1 flex-shrink-0 ${
                cardType === 'finding'     ? getSeverityBarClass(severity) :
                cardType === 'observation' ? 'bg-blue-400' :
                cardType === 'info'        ? 'bg-green-400' :
                                            'bg-neutral-300 dark:bg-neutral-600'
              }`} />
              {/* Content */}
              <div className="flex-1 min-w-0">
              {/* Card Row */}
              <div className="w-full px-4 py-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    {/* Expand button */}
                    <button
                      onClick={() => toggleCard(card.id)}
                      className="flex-shrink-0"
                    >
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-neutral-400 dark:text-neutral-500" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-neutral-400 dark:text-neutral-500" />
                      )}
                    </button>

                    {/* Type Icon */}
                    <div className={`flex-shrink-0 ${getCardTypeColor(cardType)}`}>
                      {getCardIcon(cardType, severity)}
                    </div>

                    {/* CVSS score or severity fallback */}
                    {cardType === 'finding' && (
                      card.cvss_score != null ? (
                        <span className={`text-xs font-mono font-bold tabular-nums ${getSeverityTextClass(severity)}`}>
                          {card.cvss_score.toFixed(1)}
                        </span>
                      ) : (
                        <span className={`px-2 py-0.5 text-xs font-medium rounded border ${getSeverityBadgeClass(severity)}`}>
                          {severity}
                        </span>
                      )
                    )}

                    {/* Card Type */}
                    <span className="text-sm font-medium text-neutral-600 dark:text-neutral-300 capitalize">
                      {cardType}
                    </span>

                    {/* Title */}
                    <span className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                      {title}
                    </span>

                    {/* Target */}
                    <span className="text-sm text-neutral-500 dark:text-neutral-400 truncate">
                      {targetService}
                    </span>

                    {/* Section */}
                    <span className="text-sm text-neutral-400 dark:text-neutral-500 font-mono">
                      {sectionNumber}
                    </span>

                    {/* False Positive Indicator */}
                    {isFalsePositive && (
                      <span
                        className="relative group flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded bg-neutral-200 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400"
                        title="Hidden from AI"
                      >
                        <EyeOff className="w-3 h-3" />
                        <span className="absolute hidden group-hover:block bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 text-xs bg-neutral-900 dark:bg-neutral-200 text-white dark:text-neutral-900 rounded whitespace-nowrap z-50 shadow-lg">
                          Hidden from AI
                        </span>
                      </span>
                    )}
                  </div>

                  {/* Action Buttons */}
                  <div className="flex-shrink-0 ml-4 flex items-center gap-1">
                    <button
                      onClick={() => openEditModal(card)}
                      className="p-1.5 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded text-neutral-400 dark:text-neutral-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                      title="Edit"
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleDelete(card.id)}
                      className="p-1.5 hover:bg-red-50 dark:hover:bg-red-900/30 rounded text-neutral-400 dark:text-neutral-500 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Expanded Content */}
              {isExpanded && (
                <div className="px-4 pb-4 border-t border-neutral-100 dark:border-neutral-700 bg-neutral-50/30 dark:bg-neutral-700/30">
                  <div className="pt-4 space-y-4">
                    {/* Technical Analysis */}
                    {card.technical_analysis && (
                      <div>
                        <h4 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">Technical Analysis</h4>
                        <div className="text-sm text-neutral-600 dark:text-neutral-300 bg-white dark:bg-neutral-800 p-3 rounded border border-neutral-200 dark:border-neutral-700">
                          <div className="whitespace-pre-wrap break-words">{card.technical_analysis}</div>
                        </div>
                      </div>
                    )}

                    {/* Proof — scrollable code block */}
                    {card.proof && (
                      <div>
                        <h4 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">Proof</h4>
                        <div className="overflow-x-auto bg-white dark:bg-neutral-800 rounded border border-neutral-200 dark:border-neutral-700">
                          <pre className="p-3 text-xs font-mono text-neutral-600 dark:text-neutral-300 whitespace-pre">{card.proof}</pre>
                        </div>
                      </div>
                    )}

                    {/* Notes */}
                    {card.notes && (
                      <div>
                        <h4 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">Notes</h4>
                        <div className="text-sm text-neutral-600 dark:text-neutral-300 bg-white dark:bg-neutral-800 p-3 rounded border border-neutral-200 dark:border-neutral-700">
                          <div className="whitespace-pre-wrap break-words">{card.notes}</div>
                        </div>
                      </div>
                    )}

                    {/* Context */}
                    {card.context && (
                      <div>
                        <h4 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">Context</h4>
                        <div className="text-sm text-neutral-600 dark:text-neutral-300 bg-white dark:bg-neutral-800 p-3 rounded border border-neutral-200 dark:border-neutral-700">
                          <div className="whitespace-pre-wrap break-words">{card.context}</div>
                        </div>
                      </div>
                    )}

                    {/* Status (for all card types) */}
                    {card.status && (
                      <div>
                        <h4 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">Status</h4>
                        <span className={`inline-flex items-center gap-1.5 px-2 py-1 text-xs font-medium rounded ${card.status === 'confirmed' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300' :
                          card.status === 'potential' ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300' :
                            card.status === 'false_positive' ? 'bg-neutral-200 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400' :
                              'bg-gray-100 dark:bg-neutral-700 text-gray-700 dark:text-neutral-300'
                          }`}>
                          {card.status === 'false_positive' && <EyeOff className="w-3 h-3" />}
                          {card.status === 'false_positive' ? 'False Positive (Hidden from AI)' : card.status}
                        </span>
                      </div>
                    )}

                    {/* CVSS Details */}
                    {(card.cvss_score != null || card.cvss_vector) && (
                      <div>
                        <h4 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">CVSS 4.0</h4>
                        <div className="flex flex-wrap items-center gap-3 text-sm">
                          {card.cvss_score != null && (
                            <span className="font-mono font-semibold text-neutral-800 dark:text-neutral-200">
                              Score: {card.cvss_score.toFixed(1)}
                            </span>
                          )}
                          {card.cvss_vector && (
                            <span className="font-mono text-xs text-neutral-500 dark:text-neutral-400 break-all">
                              {card.cvss_vector}
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Metadata */}
                    <div className="flex items-center gap-4 text-xs text-neutral-500 dark:text-neutral-400 pt-2 border-t border-neutral-200 dark:border-neutral-700">
                      <span>Created: {new Date(card.created_at).toLocaleDateString()}</span>
                      {card.updated_at && card.updated_at !== card.created_at && (
                        <span>Updated: {new Date(card.updated_at).toLocaleDateString()}</span>
                      )}
                    </div>
                  </div>
                </div>
              )}
              </div>{/* end content wrapper */}
            </div>
          );
        })}
      </div>

      {/* Add/Edit Modal */}
      <UnifiedModal
        isOpen={showModal}
        onClose={() => {
          setShowModal(false);
          setEditingCard(null);
        }}
        title={editingCard ? 'Edit Card' : 'Add Card'}
        onSubmit={handleSubmit}
        isSubmitting={isSubmitting}
        size="lg"
      >
        <div className="space-y-4">
          {/* Card Type */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Type <span className="text-red-500 dark:text-red-400">*</span>
            </label>
            <select
              value={formData.card_type}
              onChange={(e) => setFormData({ ...formData, card_type: e.target.value })}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            >
              <option value="finding">Finding</option>
              <option value="observation">Observation</option>
              <option value="info">Info</option>
            </select>
          </div>

          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Title <span className="text-red-500 dark:text-red-400">*</span>
            </label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="e.g., SQL Injection in login form"
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
              autoFocus
            />
          </div>

          {/* Target Service */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Target Service
            </label>
            <input
              type="text"
              value={formData.target_service}
              onChange={(e) => setFormData({ ...formData, target_service: e.target.value })}
              placeholder="e.g., https://example.com/api/login"
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
          </div>

          {/* Severity & Status (only for findings) */}
          {formData.card_type === 'finding' && (
            <div className="space-y-4">
              {/* CVSS / Manual toggle */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, cvss_mode: 'cvss' })}
                  className={`px-3 py-1.5 text-xs rounded-l-lg border transition-colors ${
                    formData.cvss_mode === 'cvss'
                      ? 'bg-primary-600 dark:bg-primary-700 text-white border-primary-600'
                      : 'bg-white dark:bg-neutral-900 text-neutral-600 dark:text-neutral-400 border-neutral-300 dark:border-neutral-700 hover:border-primary-400'
                  }`}
                >
                  CVSS 4.0
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, cvss_mode: 'manual' })}
                  className={`px-3 py-1.5 text-xs rounded-r-lg border-t border-b border-r transition-colors ${
                    formData.cvss_mode === 'manual'
                      ? 'bg-primary-600 dark:bg-primary-700 text-white border-primary-600'
                      : 'bg-white dark:bg-neutral-900 text-neutral-600 dark:text-neutral-400 border-neutral-300 dark:border-neutral-700 hover:border-primary-400'
                  }`}
                >
                  Manual Severity
                </button>
              </div>

              {/* CVSS Calculator */}
              {formData.cvss_mode === 'cvss' && (
                <div className="border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 bg-neutral-50/50 dark:bg-neutral-800/50">
                  <CvssCalculator
                    initialVector={formData.cvss_vector}
                    onChange={(vector, score, severity) => {
                      setFormData(prev => ({
                        ...prev,
                        cvss_vector: vector,
                        cvss_score: score,
                        severity: severity || prev.severity,
                      }));
                    }}
                  />
                </div>
              )}

              {/* Manual severity fallback */}
              {formData.cvss_mode === 'manual' && (
                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    Severity
                  </label>
                  <select
                    value={formData.severity}
                    onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
                    className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  >
                    <option value="CRITICAL">Critical</option>
                    <option value="HIGH">High</option>
                    <option value="MEDIUM">Medium</option>
                    <option value="LOW">Low</option>
                    <option value="INFO">Info</option>
                  </select>
                </div>
              )}

              {/* Status */}
              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  Status
                </label>
                <select
                  value={formData.status}
                  onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                  className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                >
                  <option value="potential">Potential</option>
                  <option value="confirmed">Confirmed</option>
                  <option value="untested">Untested</option>
                  <option value="false_positive">False Positive</option>
                </select>
              </div>
            </div>
          )}

          {/* Mark as False Positive (for observations and info) */}
          {formData.card_type !== 'finding' && (
            <div>
              <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.status === 'false_positive'}
                  onChange={(e) => setFormData({ ...formData, status: e.target.checked ? 'false_positive' : '' })}
                  className="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary-600 focus:ring-primary-500"
                />
                <EyeOff className="w-3.5 h-3.5 text-neutral-400" />
                <span>Mark as False Positive</span>
                <span className="text-xs text-neutral-500">(Hidden from AI)</span>
              </label>
            </div>
          )}

          {/* Section Number */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Phase/Section Number
            </label>
            <input
              type="text"
              value={formData.section_number}
              onChange={(e) => setFormData({ ...formData, section_number: e.target.value })}
              placeholder="e.g., 1, 2, 3..."
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
          </div>

          {/* Technical Analysis */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Technical Analysis
            </label>
            <textarea
              value={formData.technical_analysis}
              onChange={(e) => setFormData({ ...formData, technical_analysis: e.target.value })}
              placeholder="Detailed technical analysis of the issue..."
              rows={4}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
          </div>

          {/* Proof */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Proof / Evidence
            </label>
            <textarea
              value={formData.proof}
              onChange={(e) => setFormData({ ...formData, proof: e.target.value })}
              placeholder="Code snippets, logs, screenshots descriptions..."
              rows={4}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm font-mono focus:ring-2 focus:ring-primary-500 focus:border-transparent placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Notes
            </label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Additional notes..."
              rows={3}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
          </div>

          {/* Context */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Context
            </label>
            <textarea
              value={formData.context}
              onChange={(e) => setFormData({ ...formData, context: e.target.value })}
              placeholder="Context information..."
              rows={3}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
          </div>
        </div>
      </UnifiedModal>
    </>
  );
};

export default CardsTable;
