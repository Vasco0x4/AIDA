/**
 * Notification configuration API service
 */
import apiClient from './api';

const notificationService = {
  listConfigs: () =>
    apiClient.get('/notifications').then(r => r.data),

  getConfig: (channel) =>
    apiClient.get(`/notifications/${channel}`).then(r => r.data),

  createConfig: (data) =>
    apiClient.post('/notifications', data).then(r => r.data),

  updateConfig: (channel, data) =>
    apiClient.put(`/notifications/${channel}`, data).then(r => r.data),

  deleteConfig: (channel) =>
    apiClient.delete(`/notifications/${channel}`),

  testChannel: (channel) =>
    apiClient.post('/notifications/test', { channel }).then(r => r.data),

  sendReport: (assessmentId, data) =>
    apiClient.post(`/notifications/send-report/${assessmentId}`, data).then(r => r.data),
};

export default notificationService;
