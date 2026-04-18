/**
 * Agent runs API service — UI-initiated Claude sessions.
 */
import apiClient from './api';

export const agentService = {
  /** List runs for an assessment (newest first, transcript omitted). */
  list: async (assessmentId, { skip = 0, limit = 50 } = {}) => {
    const response = await apiClient.get(
      `/assessments/${assessmentId}/agent/runs`,
      { params: { skip, limit } }
    );
    return response.data;
  },

  /** Full run state including transcript. */
  get: async (runId) => {
    const response = await apiClient.get(`/agent/runs/${runId}`);
    return response.data;
  },

  /** Start a new run. */
  create: async (assessmentId, { goal, permissionMode, model } = {}) => {
    const response = await apiClient.post(
      `/assessments/${assessmentId}/agent/runs`,
      {
        goal,
        permission_mode: permissionMode || null,
        model: model || null,
      }
    );
    return response.data;
  },

  /** Request cancellation of a running session. */
  stop: async (runId) => {
    const response = await apiClient.post(`/agent/runs/${runId}/stop`);
    return response.data;
  },
};

export default agentService;
