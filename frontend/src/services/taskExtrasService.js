/**
 * Task comments + context file attachments API.
 */
import apiClient from './api';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

export const taskExtrasService = {
  async listComments(taskId) {
    const { data } = await apiClient.get(`/tasks/${taskId}/comments`);
    return data;
  },
  async addComment(taskId, body) {
    const { data } = await apiClient.post(`/tasks/${taskId}/comments`, { body });
    return data;
  },
  async deleteComment(commentId) {
    await apiClient.delete(`/tasks/comments/${commentId}`);
  },

  async listFiles(taskId) {
    const { data } = await apiClient.get(`/tasks/${taskId}/files`);
    return data;
  },
  async uploadFile(taskId, file) {
    const fd = new FormData();
    fd.append('file', file);
    const { data } = await apiClient.post(`/tasks/${taskId}/files`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
  async deleteFile(fileId) {
    await apiClient.delete(`/tasks/files/${fileId}`);
  },
  fileUrl(fileId) {
    return `${API_BASE}/tasks/files/${fileId}/content`;
  },
};

export default taskExtrasService;
