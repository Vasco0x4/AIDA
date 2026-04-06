import React, { useState } from 'react';
import { Plus, Trash2, Edit2, ChevronDown, ChevronRight } from '../icons/index';
import UnifiedModal from '../common/UnifiedModal';
import apiClient from '../../services/api';

const ITEMS_LIMIT = 5;

const ReconTable = ({ title, data, assessmentId, onUpdate }) => {
  const [isAdding, setIsAdding] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [newItem, setNewItem] = useState('');
  const [loading, setLoading] = useState(false);
  const [expandedItems, setExpandedItems] = useState(new Set());

  // Modal state for Edit
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [editFormData, setEditFormData] = useState({
    name: '',
    details: {},
    discovered_in_phase: null
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const dataType = title.toLowerCase().slice(0, -1); // Remove 's' from title

  const handleAdd = async () => {
    if (!newItem.trim()) return;

    try {
      setLoading(true);
      await apiClient.post(`/assessments/${assessmentId}/recon`, {
        data_type: dataType,
        name: newItem.trim(),
        details: {},
        discovered_in_phase: null,
      });
      setNewItem('');
      setIsAdding(false);
      onUpdate();
    } catch (error) {
      console.error('Failed to add recon data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this item?')) return;

    try {
      await apiClient.delete(`/assessments/${assessmentId}/recon/${id}`);
      onUpdate();
    } catch (error) {
      console.error('Failed to delete recon data:', error);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    }
    if (e.key === 'Escape') {
      setNewItem('');
      setIsAdding(false);
    }
  };

  const toggleExpanded = (itemId) => {
    const newExpanded = new Set(expandedItems);
    if (newExpanded.has(itemId)) {
      newExpanded.delete(itemId);
    } else {
      newExpanded.add(itemId);
    }
    setExpandedItems(newExpanded);
  };

  // Open Edit Modal
  const openEditModal = (item) => {
    setEditingItem(item);
    setEditFormData({
      name: item.name || '',
      details: item.details || {},
      discovered_in_phase: item.discovered_in_phase || null
    });
    setShowEditModal(true);
  };

  // Handle Edit Submit
  const handleEditSubmit = async () => {
    if (!editFormData.name.trim()) {
      alert('Name is required');
      return;
    }

    try {
      setIsSubmitting(true);

      const payload = {
        data_type: dataType,
        name: editFormData.name.trim(),
        details: editFormData.details,
        discovered_in_phase: editFormData.discovered_in_phase || null
      };

      await apiClient.patch(`/recon/${editingItem.id}`, payload);

      setShowEditModal(false);
      setEditingItem(null);
      onUpdate();
    } catch (error) {
      console.error('Failed to update recon data:', error);
      alert('Failed to update. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300">{title}</h3>
          <button
            onClick={() => setIsAdding(true)}
            className="btn-ghost btn-xs"
          >
            <Plus className="w-3 h-3" />
            Add
          </button>
        </div>

        <div className="border border-neutral-200 dark:border-neutral-700 rounded overflow-hidden bg-white dark:bg-neutral-800">
          {data.length === 0 && !isAdding ? (
            <div className="px-3 py-4 text-center text-xs text-neutral-500 dark:text-neutral-400">
              No {title.toLowerCase()} discovered yet
            </div>
          ) : (
            <table className="w-full text-xs">
              <tbody>
                {(showAll ? data : data.slice(0, ITEMS_LIMIT)).map((item) => {
                  const isExpanded = expandedItems.has(item.id);
                  const hasDetails = item.details && Object.keys(item.details).length > 0;

                  return (
                    <React.Fragment key={item.id}>
                      <tr id={`recon-${item.id}`} className="border-b border-neutral-100 dark:border-neutral-700 last:border-b-0 hover:bg-neutral-50/50 dark:hover:bg-neutral-700/50">
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            {hasDetails && (
                              <button
                                onClick={() => toggleExpanded(item.id)}
                                className="p-0.5 hover:bg-neutral-100 dark:hover:bg-neutral-600 rounded text-neutral-400 dark:text-neutral-500 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                              >
                                {isExpanded ? (
                                  <ChevronDown className="w-3 h-3" />
                                ) : (
                                  <ChevronRight className="w-3 h-3" />
                                )}
                              </button>
                            )}
                            <span className="font-mono text-neutral-900 dark:text-neutral-100">{item.name}</span>
                            {item.details?.in_scope === false && (
                              <span className="px-1.5 py-0.5 text-[10px] bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 rounded font-medium">
                                OUT OF SCOPE
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-2 py-2 text-neutral-500 dark:text-neutral-400 text-right">
                          {item.discovered_in_phase ? (
                            <span className="text-xs">
                              {item.discovered_in_phase.includes('Phase')
                                ? item.discovered_in_phase.replace('Phase ', '').split(' - ')[0]
                                : item.discovered_in_phase}
                            </span>
                          ) : (
                            <span className="text-neutral-300 dark:text-neutral-600">-</span>
                          )}
                        </td>
                        <td className="px-2 py-2 w-px">
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => openEditModal(item)}
                              className="p-0.5 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded text-neutral-300 dark:text-neutral-600 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                              title="Edit"
                            >
                              <Edit2 className="w-3 h-3" />
                            </button>
                            <button
                              onClick={() => handleDelete(item.id)}
                              className="p-0.5 hover:bg-red-50 dark:hover:bg-red-900/30 rounded text-neutral-300 dark:text-neutral-600 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                              title="Delete"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>
                        </td>
                      </tr>
                      {isExpanded && hasDetails && (
                        <tr className="bg-neutral-50/30 dark:bg-neutral-700/30">
                          <td colSpan="3" className="px-3 py-2">
                            <div className="space-y-1">
                              {Object.entries(item.details).map(([key, value]) => (
                                <div key={key} className="flex gap-2 text-xs">
                                  <span className="font-medium text-neutral-600 dark:text-neutral-400 w-20">{key}:</span>
                                  <span className="font-mono text-neutral-800 dark:text-neutral-200">{String(value)}</span>
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}

                {isAdding && (
                  <tr className="bg-primary-50/20 dark:bg-primary-900/20">
                    <td colSpan="3" className="p-0">
                      <input
                        type="text"
                        value={newItem}
                        onChange={(e) => setNewItem(e.target.value)}
                        onKeyDown={handleKeyDown}
                        onBlur={() => {
                          if (!newItem.trim()) setIsAdding(false);
                        }}
                        placeholder={`Enter ${dataType} name...`}
                        className="w-full px-3 py-2 bg-transparent outline-none text-xs font-mono text-neutral-900 dark:text-neutral-100 placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
                        autoFocus
                        disabled={loading}
                      />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        {data.length > ITEMS_LIMIT && (
          <button
            onClick={() => setShowAll(v => !v)}
            className="mt-2 w-full text-xs text-neutral-500 dark:text-neutral-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors py-1"
          >
            {showAll ? 'Show less' : `Show more (${data.length - ITEMS_LIMIT} more)`}
          </button>
        )}

        {isAdding && (
          <div className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
            Press Enter to save, Esc to cancel
          </div>
        )}
      </div>

      {/* Edit Modal */}
      <UnifiedModal
        isOpen={showEditModal}
        onClose={() => {
          setShowEditModal(false);
          setEditingItem(null);
        }}
        title={`Edit ${dataType}`}
        onSubmit={handleEditSubmit}
        isSubmitting={isSubmitting}
        size="md"
      >
        <div className="space-y-4">
          {/* Name field */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Name <span className="text-red-500 dark:text-red-400">*</span>
            </label>
            <input
              type="text"
              value={editFormData.name}
              onChange={(e) => setEditFormData({ ...editFormData, name: e.target.value })}
              placeholder={`Enter ${dataType} name...`}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
              autoFocus
            />
          </div>

          {/* Phase field */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Discovered in Phase
            </label>
            <input
              type="text"
              value={editFormData.discovered_in_phase || ''}
              onChange={(e) => setEditFormData({ ...editFormData, discovered_in_phase: e.target.value })}
              placeholder="e.g., Phase 1 - Reconnaissance"
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
          </div>

          {/* Additional Details (JSON) */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Additional Details
              <span className="text-xs text-neutral-500 dark:text-neutral-400 ml-2">(optional, JSON format)</span>
            </label>
            <textarea
              value={JSON.stringify(editFormData.details, null, 2)}
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value);
                  setEditFormData({ ...editFormData, details: parsed });
                } catch (err) {
                  // Keep invalid JSON in state for user to fix
                  setEditFormData({ ...editFormData, details: e.target.value });
                }
              }}
              placeholder='{"port": 443, "in_scope": true}'
              rows={4}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 rounded-lg text-sm font-mono focus:ring-2 focus:ring-primary-500 focus:border-transparent placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
            />
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              Add custom key-value pairs like ports, status, etc.
            </p>
          </div>
        </div>
      </UnifiedModal>
    </>
  );
};

export default ReconTable;
