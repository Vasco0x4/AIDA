import api from './api';
const root = '/appsec';
export default {
  projects: () => api.get(`${root}/projects`).then(r => r.data),
  create: body => api.post(`${root}/projects`, body).then(r => r.data),
  scans: id => api.get(`${root}/projects/${id}/scans`, { timeout: 15000 }).then(r => r.data),
  scan: id => api.get(`${root}/scans/${id}`, { timeout: 15000 }).then(r => r.data),
  start: (id, body) => api.post(`${root}/projects/${id}/scans`, body).then(r => r.data),
  upload: (id, file, params) => api.post(`${root}/projects/${id}/upload`, file, { params, headers: { 'Content-Type': 'application/zip' } }).then(r => r.data),
  cancel: id => api.post(`${root}/scans/${id}/cancel`).then(r => r.data),
  triage: (id, status) => api.patch(`${root}/findings/${id}`, { status }).then(r => r.data),
  task: id => api.post(`${root}/findings/${id}/task`).then(r => r.data),
  report: (id, format) => api.get(`${root}/scans/${id}/report`, { params: { format }, responseType: 'blob' }).then(r => r.data),
};
