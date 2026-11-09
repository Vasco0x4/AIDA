/**
 * Knowledge base API service (skills, bug-bounty reports, CVEs, playbooks).
 */
import apiClient from './api';

export const knowledgeService = {
  async stats() {
    const { data } = await apiClient.get('/knowledge/stats');
    return data;
  },
  async search(q, { source = null, limit = 15 } = {}) {
    const params = new URLSearchParams();
    if (q) params.append('q', q);
    if (source) params.append('source', source);
    params.append('limit', limit);
    const { data } = await apiClient.get(`/knowledge?${params.toString()}`);
    return data;
  },
  async ingestBugbounty(limit = null) {
    const { data } = await apiClient.post('/knowledge/ingest/bugbounty', { limit }, { timeout: 180000 });
    return data;
  },
  async ingestNvd(keyword, limit = 15) {
    const { data } = await apiClient.post('/knowledge/ingest/nvd', { keyword, limit }, { timeout: 60000 });
    return data;
  },
  async exportBlob(source = null) {
    const q = source ? `?source=${encodeURIComponent(source)}` : '';
    const resp = await apiClient.get(`/knowledge/export${q}`, { responseType: 'blob', timeout: 120000 });
    return resp.data;
  },
  async importFile(file) {
    const fd = new FormData();
    fd.append('file', file);
    const { data } = await apiClient.post('/knowledge/import', fd, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000,
    });
    return data;
  },
};

export default knowledgeService;
