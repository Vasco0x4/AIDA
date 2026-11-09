/**
 * Subdomain Takeover API service (persisted background scans + notes).
 */
import apiClient from './api';

export const takeoverService = {
  async startScan(domain, { subdomains = null, assessmentId = null } = {}) {
    const { data } = await apiClient.post('/takeover/scan', {
      domain, subdomains, assessment_id: assessmentId,
    });
    return data; // { scan_id, status }
  },
  async listScans() {
    const { data } = await apiClient.get('/takeover/scans');
    return data;
  },
  async getScan(scanId) {
    const { data } = await apiClient.get(`/takeover/scans/${scanId}`);
    return data;
  },
  async deleteScan(scanId) {
    await apiClient.delete(`/takeover/scans/${scanId}`);
  },
  async setNote(resultId, note) {
    const { data } = await apiClient.patch(`/takeover/results/${resultId}`, { note });
    return data;
  },
  async deleteResult(resultId) {
    await apiClient.delete(`/takeover/results/${resultId}`);
  },
  async fingerprints() {
    const { data } = await apiClient.get('/takeover/fingerprints');
    return data;
  },
};

export default takeoverService;
