import apiClient from './api';

const scanProfileService = {
  async list() {
    return (await apiClient.get('/scan-profiles')).data;
  },
  async create(payload) {
    return (await apiClient.post('/scan-profiles', payload)).data;
  },
  async update(id, payload) {
    return (await apiClient.put(`/scan-profiles/${id}`, payload)).data;
  },
  async remove(id) {
    await apiClient.delete(`/scan-profiles/${id}`);
  },
};

export default scanProfileService;
