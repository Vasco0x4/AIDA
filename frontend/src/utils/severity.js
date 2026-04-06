// Unified severity utilities — single source of truth

export const SEVERITY_ORDER = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, INFO: 0 };

/**
 * Full badge classes: text + background + border
 * Used in CardsTable badge, OverviewView legend, etc.
 */
export const getSeverityBadgeClass = (severity) => {
  switch (severity) {
    case 'CRITICAL': return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-700';
    case 'HIGH':     return 'text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/30 border-orange-200 dark:border-orange-700';
    case 'MEDIUM':   return 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/30 border-yellow-200 dark:border-yellow-700';
    case 'LOW':      return 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-700';
    case 'INFO':     return 'text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-900/30 border-cyan-200 dark:border-cyan-700';
    default:         return 'text-neutral-600 dark:text-neutral-400 bg-neutral-50 dark:bg-neutral-800 border-neutral-200 dark:border-neutral-700';
  }
};

/**
 * Text color only — used in compact/inline contexts
 */
export const getSeverityTextClass = (severity) => {
  switch (severity) {
    case 'CRITICAL': return 'text-red-600 dark:text-red-400';
    case 'HIGH':     return 'text-orange-600 dark:text-orange-400';
    case 'MEDIUM':   return 'text-yellow-600 dark:text-yellow-400';
    case 'LOW':      return 'text-blue-600 dark:text-blue-400';
    case 'INFO':     return 'text-cyan-600 dark:text-cyan-400';
    default:         return 'text-neutral-600 dark:text-neutral-400';
  }
};

/**
 * Solid background color — used in bar charts
 */
export const getSeverityBarClass = (severity) => {
  switch (severity) {
    case 'CRITICAL': return 'bg-red-500';
    case 'HIGH':     return 'bg-orange-500';
    case 'MEDIUM':   return 'bg-yellow-500';
    case 'LOW':      return 'bg-blue-500';
    default:         return 'bg-neutral-500';
  }
};

/**
 * Left border strip color — used on card rows
 */
export const getSeverityStripClass = (severity) => {
  switch (severity) {
    case 'CRITICAL': return 'border-l-red-500';
    case 'HIGH':     return 'border-l-orange-500';
    case 'MEDIUM':   return 'border-l-yellow-500';
    case 'LOW':      return 'border-l-blue-400';
    case 'INFO':     return 'border-l-cyan-400';
    default:         return 'border-l-neutral-300 dark:border-l-neutral-600';
  }
};

/**
 * Dot color — used in filter buttons and legend dots
 */
export const getSeverityDotClass = (severity) => {
  switch (severity) {
    case 'CRITICAL': return 'bg-red-500';
    case 'HIGH':     return 'bg-orange-500';
    case 'MEDIUM':   return 'bg-yellow-500';
    case 'LOW':      return 'bg-blue-500';
    default:         return 'bg-neutral-400';
  }
};
