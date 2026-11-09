/**
 * Scheduled Engagements API service (E4) — cron-triggered recurring audits.
 */
import apiClient from './api';

const scheduleService = {
  async preview(cron, timezone) {
    const { data } = await apiClient.get('/schedules/preview', { params: { cron, timezone } });
    return data;
  },
  async list() {
    const { data } = await apiClient.get('/schedules');
    return data;
  },

  async create(payload) {
    const { data } = await apiClient.post('/schedules', payload);
    return data;
  },

  async update(id, payload) {
    const { data } = await apiClient.put(`/schedules/${id}`, payload);
    return data;
  },

  async remove(id) {
    await apiClient.delete(`/schedules/${id}`);
  },

  async runNow(id) {
    const { data } = await apiClient.post(`/schedules/${id}/run-now`);
    return data;
  },

  async runs(id) {
    const { data } = await apiClient.get(`/schedules/${id}/runs`);
    return data;
  },

  // Findings diff between two audits (recurring-audit view)
  async diffFindings(assessmentId, baselineId) {
    const { data } = await apiClient.get(`/assessments/${assessmentId}/diff/${baselineId}`);
    return data;
  },

  // Compliance mapping of an assessment's findings
  async compliance(assessmentId, framework) {
    const q = framework ? `?framework=${encodeURIComponent(framework)}` : '';
    const { data } = await apiClient.get(`/assessments/${assessmentId}/compliance${q}`);
    return data;
  },
};

export default scheduleService;
