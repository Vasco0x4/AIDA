/**
 * Command Settings Service - API calls for command execution mode and keywords
 */
import apiClient from './api';

/**
 * Get current command execution settings
 * @returns {Promise<{execution_mode: string, filter_keywords: string[]}>}
 */
export const getCommandSettings = async () => {
    const response = await apiClient.get('/command-settings');
    return response.data;
};

/**
 * Update command execution settings
 * @param {Object} settings - {execution_mode?: string, filter_keywords?: string[]}
 * @returns {Promise<Object>}
 */
export const updateCommandSettings = async (settings) => {
    const response = await apiClient.put('/command-settings', settings);
    return response.data;
};

/**
 * Add a filter keyword
 * @param {string} keyword
 * @returns {Promise<Object>}
 */
export const addKeyword = async (keyword) => {
    const response = await apiClient.post('/command-settings/keywords', { keyword });
    return response.data;
};

/**
 * Remove a filter keyword
 * @param {string} keyword
 * @returns {Promise<Object>}
 */
export const removeKeyword = async (keyword) => {
    const response = await apiClient.delete(`/command-settings/keywords/${encodeURIComponent(keyword)}`);
    return response.data;
};

/**
 * Get pending command count (for notification badge)
 * @returns {Promise<{pending_count: number}>}
 */
export const getPendingCount = async () => {
    const response = await apiClient.get('/pending-commands/count');
    return response.data;
};

/**
 * List pending commands
 * @param {Object} params - {status_filter?: string, assessment_id?: number}
 * @returns {Promise<Object>}
 */
export const listPendingCommands = async (params = {}) => {
    const response = await apiClient.get('/pending-commands', { params });
    return response.data;
};

/**
 * Approve a pending command
 * @param {number} commandId
 * @param {string} approvedBy
 * @returns {Promise<Object>}
 */
export const approveCommand = async (commandId, approvedBy = 'admin') => {
    const response = await apiClient.post(`/pending-commands/${commandId}/approve`, {
        approved_by: approvedBy
    });
    return response.data;
};

/**
 * Reject a pending command
 * @param {number} commandId
 * @param {string} rejectedBy
 * @param {string} reason
 * @returns {Promise<Object>}
 */
export const rejectCommand = async (commandId, rejectedBy = 'admin', reason = '') => {
    const response = await apiClient.post(`/pending-commands/${commandId}/reject`, {
        rejected_by: rejectedBy,
        rejection_reason: reason
    });
    return response.data;
};

/**
 * Update HTTP method rules
 * @param {Object} rules - e.g. { GET: 'auto_approve', POST: 'require_approval' }
 * @returns {Promise<Object>}
 */
export const updateHttpMethodRules = async (rules) => {
    const response = await apiClient.put('/command-settings', { http_method_rules: rules });
    return response.data;
};

export default {
    getCommandSettings,
    getSettings: getCommandSettings,
    updateCommandSettings,
    addKeyword,
    removeKeyword,
    updateHttpMethodRules,
    getPendingCount,
    listPendingCommands,
    approveCommand,
    rejectCommand
};
