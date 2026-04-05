/**
 * Timeline API service
 */
import apiClient from './api';

const timelineService = {
  getTimeline: (assessmentId, params = {}) =>
    apiClient.get(`/assessments/${assessmentId}/timeline`, { params }).then(r => r.data),

  createEvent: (assessmentId, event) =>
    apiClient.post(`/assessments/${assessmentId}/timeline`, event).then(r => r.data),

  deleteEvent: (assessmentId, eventId) =>
    apiClient.delete(`/assessments/${assessmentId}/timeline/${eventId}`),

  autoGenerate: (assessmentId) =>
    apiClient.post(`/assessments/${assessmentId}/timeline/auto-generate`).then(r => r.data),
};

export default timelineService;
