import { utcDate } from './utcDate';
/**
 * Utility functions for formatting data
 */

/**
 * Format date to readable string
 */
export const formatDate = (dateString) => {
  if (!dateString) return 'N/A';
  const date = utcDate(dateString);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};

/**
 * Format datetime to readable string
 */
export const formatDateTime = (dateString) => {
  if (!dateString) return 'N/A';
  const date = utcDate(dateString);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

/**
 * Format time only
 */
export const formatTime = (dateString) => {
  if (!dateString) return 'N/A';
  const date = utcDate(dateString);
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

/**
 * Format execution time (seconds to readable)
 */
export const formatExecutionTime = (seconds) => {
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`;
  if (seconds < 60) return `${seconds.toFixed(2)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = (seconds % 60).toFixed(0);
  return `${minutes}m ${secs}s`;
};

/**
 * Get severity color class
 */
export const getSeverityColor = (severity) => {
  const colors = {
    CRITICAL: 'text-error-600 bg-error-50',
    HIGH: 'text-error-500 bg-error-50',
    MEDIUM: 'text-warning-600 bg-warning-50',
    LOW: 'text-primary-600 bg-primary-50',
    INFO: 'text-neutral-600 bg-neutral-100',
  };
  return colors[severity] || colors.INFO;
};

/**
 * Get status emoji
 */
export const getStatusEmoji = (status) => {
  const emojis = {
    confirmed: '🔴',
    potential: '🟡',
    untested: '⚪',
  };
  return emojis[status] || '⚪';
};

/**
 * Get assessment status color
 */
export const getAssessmentStatusColor = (status) => {
  const colors = {
    in_progress: 'text-primary-600 bg-primary-50',
    completed: 'text-success-600 bg-success-50',
    archived: 'text-neutral-500 bg-neutral-100',
  };
  return colors[status] || colors.in_progress;
};

/**
 * Truncate text
 */
export const truncate = (text, maxLength = 100) => {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
};

/**
 * Format card type label
 */
export const formatCardType = (type) => {
  const labels = {
    finding: 'Finding',
    observation: 'Observation',
    info: 'Info',
  };
  return labels[type] || type;
};
