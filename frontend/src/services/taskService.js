/**
 * Task / Kanban board API service.
 */
import apiClient from './api';

export const taskService = {
  async getBoard() {
    const { data } = await apiClient.get('/tasks/board');
    return data; // { columns: [{ key, tasks: [...] }] }
  },

  async getColumns() {
    const { data } = await apiClient.get('/tasks/columns');
    return data.columns;
  },

  async listTasks(status) {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    const { data } = await apiClient.get(`/tasks${q}`);
    return data;
  },

  async createTask(payload) {
    const { data } = await apiClient.post('/tasks', payload);
    return data;
  },

  async updateTask(id, payload) {
    const { data } = await apiClient.put(`/tasks/${id}`, payload);
    return data;
  },

  async moveTask(id, status, position = 0, expectedVersion = null) {
    const { data } = await apiClient.post(`/tasks/${id}/move`, {
      status,
      position,
      ...(expectedVersion == null ? {} : { expected_version: expectedVersion }),
    });
    return data;
  },

  async listEvents(id, limit = 200) {
    const { data } = await apiClient.get(`/tasks/${id}/events`, { params: { limit } });
    return data;
  },

  async recoverTask(id) {
    const { data } = await apiClient.post(`/tasks/${id}/recover`);
    return data;
  },

  async retryTask(id) {
    const { data } = await apiClient.post(`/tasks/${id}/retry`);
    return data;
  },

  async setDependencies(id, dependencyIds, expectedVersion = null) {
    const { data } = await apiClient.put(`/tasks/${id}/dependencies`, {
      dependency_ids: dependencyIds,
      ...(expectedVersion == null ? {} : { expected_version: expectedVersion }),
    });
    return data;
  },

  async deleteTask(id) {
    await apiClient.delete(`/tasks/${id}`);
  },

  async stopTask(id) {
    const { data } = await apiClient.post(`/tasks/${id}/stop`);
    return data;
  },

  // Autonomous runner control
  async getRunner() {
    const { data } = await apiClient.get('/tasks/runner');
    return data; // { enabled, active, config }
  },

  async setRunner(enabled) {
    const { data } = await apiClient.put('/tasks/runner', { enabled });
    return data;
  },

  async setRunnerConfig(config) {
    const { data } = await apiClient.put('/tasks/runner/config', config);
    return data;
  },

  // Global kill switch: cancel every running agent, mark tasks failed.
  async killRunner() {
    const { data } = await apiClient.post('/tasks/runner/kill');
    return data; // { killed }
  },
};

export default taskService;
