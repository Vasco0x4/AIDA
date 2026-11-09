/**
 * AI model provider config API service.
 */
import apiClient from './api';

export const aiModelService = {
  async getPresets() {
    const { data } = await apiClient.get('/ai-models/presets');
    return data;
  },
  async list() {
    const { data } = await apiClient.get('/ai-models');
    return data;
  },
  async create(payload) {
    const { data } = await apiClient.post('/ai-models', payload);
    return data;
  },
  async update(id, payload) {
    const { data } = await apiClient.put(`/ai-models/${id}`, payload);
    return data;
  },
  async remove(id) {
    await apiClient.delete(`/ai-models/${id}`);
  },
  async test(id) {
    const { data } = await apiClient.post(`/ai-models/${id}/test`);
    return data;
  },
};

export default aiModelService;
