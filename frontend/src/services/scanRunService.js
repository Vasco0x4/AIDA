import apiClient from './api';

const scanRunService = {
  async list(params = {}) {
    return (await apiClient.get('/scan-runs', { params })).data;
  },
  async forAssessment(assessmentId, params = {}) {
    return (await apiClient.get(`/assessments/${assessmentId}/runs`, { params })).data;
  },
  async get(id) {
    return (await apiClient.get(`/scan-runs/${id}`, { timeout: 15000 })).data;
  },
  async findings(id, params = {}) {
    return (await apiClient.get(`/scan-runs/${id}/findings`, { params, timeout: 15000 })).data;
  },
  async diff(id) {
    return (await apiClient.get(`/scan-runs/${id}/diff`, { timeout: 15000 })).data;
  },
  async events(id, { beforeId, limit = 100 } = {}) {
    return (await apiClient.get(`/scan-runs/${id}/events`, {
      timeout: 15000,
      params: { limit, ...(beforeId ? { before_id: beforeId } : {}) },
    })).data;
  },
  async pause(id) {
    return (await apiClient.post(`/scan-runs/${id}/pause`)).data;
  },
  async resume(id) {
    return (await apiClient.post(`/scan-runs/${id}/resume`)).data;
  },
  async cancel(id) {
    return (await apiClient.post(`/scan-runs/${id}/cancel`)).data;
  },
  async retry(id) {
    return (await apiClient.post(`/scan-runs/${id}/retry`)).data;
  },
  async report(id, format = 'html') {
    return (await apiClient.get(`/scan-runs/${id}/report`, {
      params: { format }, responseType: 'blob',
    })).data;
  },
};

export default scanRunService;
