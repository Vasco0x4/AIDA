import { utcDate } from '../../utils/utcDate';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { MoreVertical, Calendar, User, Tag, Clock, Edit3, Pin, PinOff } from 'lucide-react';
import AssessmentCardActions from './AssessmentCardActions';
import StatusDropdown from './StatusDropdown';
import apiClient from '../../services/api';
import { usePinnedAssessments } from '../../hooks/usePinnedAssessments';

const AssessmentsTable = ({
  assessments = [],
  folders = [],
  onAssessmentUpdate,
  onAssessmentDelete,
  onAssessmentEdit,
  loading = false
}) => {
  const [sortField, setSortField] = useState('created_at');
  const [sortDirection, setSortDirection] = useState('desc');
  const { isPinned, togglePin } = usePinnedAssessments();

  const getCategoryFromName = (name) => {
    // Extract category from assessment name patterns
    if (name.toLowerCase().includes('api')) return 'API';
    if (name.toLowerCase().includes('web')) return 'Website';
    if (name.toLowerCase().includes('infra') || name.toLowerCase().includes('network')) return 'External Infra';
    if (name.toLowerCase().includes('mobile')) return 'Mobile';
    if (name.toLowerCase().includes('cloud')) return 'Cloud';
    return 'General';
  };

  const getCategoryColor = (category) => {
    switch (category) {
      case 'API':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300';
      case 'Website':
        return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300';
      case 'External Infra':
        return 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300';
      case 'Mobile':
        return 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300';
      case 'Cloud':
        return 'bg-cyan-100 dark:bg-cyan-900/30 text-cyan-800 dark:text-cyan-300';
      case 'General':
        return 'bg-neutral-100 dark:bg-neutral-700 text-neutral-800 dark:text-neutral-300';
      default:
        return 'bg-neutral-100 dark:bg-neutral-700 text-neutral-800 dark:text-neutral-300';
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'active':
        return 'bg-primary-100/50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300';
      case 'completed':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300';
      case 'archived':
        return 'bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300';
      default:
        return 'bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300';
    }
  };

  const formatDeadline = (endDate) => {
    if (!endDate) return 'No deadline';
    
    const end = utcDate(endDate);
    const now = utcDate();
    const diffTime = end - now;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays < 0) return `${Math.abs(diffDays)} days ago`;
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Tomorrow';
    if (diffDays <= 7) return `${diffDays} days from now`;
    return `${Math.ceil(diffDays / 7)} weeks from now`;
  };

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const handleStatusChange = async (assessmentId, newStatus) => {
    try {
      // Simply update the status - no folder changes, no archive/unarchive endpoints
      await apiClient.put(`/assessments/${assessmentId}`, { status: newStatus });

      // Call the parent update function to reload data
      if (onAssessmentUpdate) {
        onAssessmentUpdate();
      }
    } catch (error) {
      console.error('Failed to update assessment status:', error);
    }
  };

  const handleTogglePin = (e, assessmentId) => {
    e.preventDefault();
    e.stopPropagation();
    togglePin(assessmentId);
  };

  const sortedAssessments = [...assessments].sort((a, b) => {
    // Pinned items always float to the top
    const aPinned = isPinned(a.id);
    const bPinned = isPinned(b.id);
    if (aPinned !== bPinned) return aPinned ? -1 : 1;

    let aValue = a[sortField];
    let bValue = b[sortField];

    if (sortField === 'created_at' || sortField === 'end_date') {
      aValue = utcDate(aValue);
      bValue = utcDate(bValue);
    }

    if (sortDirection === 'asc') {
      return aValue > bValue ? 1 : -1;
    } else {
      return aValue < bValue ? 1 : -1;
    }
  });

  if (loading) {
    return (
      <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden">
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
          <span className="ml-3 text-neutral-600 dark:text-neutral-400">Updating...</span>
        </div>
      </div>
    );
  }

  if (assessments.length === 0) {
    return (
      <div className="empty-state">
        <div className="text-center py-12">
          <div className="w-16 h-16 mx-auto mb-4 bg-neutral-100 dark:bg-neutral-700 rounded-full flex items-center justify-center">
            <Tag className="w-8 h-8 text-neutral-400 dark:text-neutral-500" />
          </div>
          <h3 className="text-lg font-medium text-neutral-900 dark:text-neutral-100 mb-2">No assessments found</h3>
          <p className="text-neutral-500 dark:text-neutral-400">Create your first assessment to get started</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-neutral-50 dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-700">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider w-1/4">
                <button
                  onClick={() => handleSort('name')}
                  className="flex items-center gap-1 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
                >
                  Name
                  {sortField === 'name' && (
                    <span className="text-xs">{sortDirection === 'asc' ? '↑' : '↓'}</span>
                  )}
                </button>
              </th>
              <th className="px-3 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider w-1/6">
                Category
              </th>
              <th className="px-3 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider w-1/6">
                <button
                  onClick={() => handleSort('client_name')}
                  className="flex items-center gap-1 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
                >
                  Client
                  {sortField === 'client_name' && (
                    <span className="text-xs">{sortDirection === 'asc' ? '↑' : '↓'}</span>
                  )}
                </button>
              </th>
              <th className="px-3 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider w-1/6">
                <button
                  onClick={() => handleSort('status')}
                  className="flex items-center gap-1 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
                >
                  Status
                  {sortField === 'status' && (
                    <span className="text-xs">{sortDirection === 'asc' ? '↑' : '↓'}</span>
                  )}
                </button>
              </th>
              <th className="px-3 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider w-1/6">
                Folder
              </th>
              <th className="px-3 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider w-1/6">
                <button
                  onClick={() => handleSort('end_date')}
                  className="flex items-center gap-1 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
                >
                  Deadline
                  {sortField === 'end_date' && (
                    <span className="text-xs">{sortDirection === 'asc' ? '↑' : '↓'}</span>
                  )}
                </button>
              </th>
              <th className="px-3 py-3 text-right text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider w-16">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-neutral-800 divide-y divide-neutral-200 dark:divide-neutral-700">
            {sortedAssessments.map((assessment) => {
              const pinned = isPinned(assessment.id);
              return (
              <tr key={assessment.id} className={`hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors group${pinned ? ' bg-amber-50/30 dark:bg-amber-900/5' : ''}`}>
                <td className="px-4 py-3 whitespace-nowrap">
                  <div className="flex items-center gap-1.5">
                    {pinned && <Pin className="w-3 h-3 text-amber-500 shrink-0" />}
                    <Link
                      to={`/assessments/${assessment.id}`}
                      className="text-sm font-medium text-neutral-900 dark:text-neutral-100 hover:text-primary-600 dark:hover:text-primary-400 transition-colors truncate block"
                      title={assessment.name}
                    >
                      {assessment.name}
                    </Link>
                  </div>
                </td>
                <td className="px-3 py-3 whitespace-nowrap">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${getCategoryColor(assessment.category || getCategoryFromName(assessment.name))}`}>
                    {assessment.category || getCategoryFromName(assessment.name)}
                  </span>
                </td>
                <td className="px-3 py-3 whitespace-nowrap">
                  <div className="flex items-center">
                    <User className="w-3 h-3 text-neutral-400 dark:text-neutral-500 mr-1.5" />
                    <span className="text-xs text-neutral-900 dark:text-neutral-100 truncate">
                      {assessment.client_name || 'No client'}
                    </span>
                  </div>
                </td>
                <td className="px-3 py-3 whitespace-nowrap">
                  <StatusDropdown
                    currentStatus={assessment.status}
                    onStatusChange={(newStatus) => handleStatusChange(assessment.id, newStatus)}
                    disabled={loading}
                  />
                </td>
                <td className="px-3 py-3 whitespace-nowrap">
                  {assessment.folder_id ? (
                    <div className="flex items-center gap-2">
                      <svg className="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: folders.find(f => f.id === assessment.folder_id)?.color || '#06b6d4' }}>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                      </svg>
                      <span className="text-xs text-neutral-900 dark:text-neutral-100 truncate">
                        {folders.find(f => f.id === assessment.folder_id)?.name || 'Unknown'}
                      </span>
                    </div>
                  ) : (
                    <span className="text-xs text-neutral-400 dark:text-neutral-500 italic">No folder</span>
                  )}
                </td>
                <td className="px-3 py-3 whitespace-nowrap">
                  <div className="flex items-center text-xs text-neutral-500 dark:text-neutral-400">
                    <Calendar className="w-3 h-3 mr-1.5" />
                    <span className="truncate">{formatDeadline(assessment.end_date)}</span>
                  </div>
                </td>
                <td className="px-3 py-3 whitespace-nowrap text-right text-sm font-medium">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={(e) => handleTogglePin(e, assessment.id)}
                      className={`p-1.5 rounded transition-all ${
                        pinned
                          ? 'text-amber-500 hover:bg-amber-100 dark:hover:bg-amber-900/30'
                          : 'opacity-0 group-hover:opacity-100 hover:bg-neutral-100 dark:hover:bg-neutral-600 text-neutral-400 dark:text-neutral-500'
                      }`}
                      title={pinned ? 'Unpin' : 'Pin to top'}
                    >
                      {pinned ? <PinOff className="w-4 h-4" /> : <Pin className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        onAssessmentEdit(assessment);
                      }}
                      className="p-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-600 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Edit assessment"
                    >
                      <Edit3 className="w-4 h-4 text-neutral-600 dark:text-neutral-400" />
                    </button>
                    <AssessmentCardActions
                      assessment={assessment}
                      folders={folders}
                      onAssessmentUpdate={onAssessmentUpdate}
                      onAssessmentDelete={onAssessmentDelete}
                    />
                  </div>
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default AssessmentsTable;
