import api from './api';
const root = '/appsec/integrations';
const options = { timeout: 90000 };
export default {
  list: () => api.get(root).then(r => r.data),
  create: body => api.post(root, body, options).then(r => r.data),
  check: id => api.post(`${root}/${id}/check`, {}, options).then(r => r.data),
  rotate: (id, token) => api.put(`${root}/${id}/token`, { token }, options).then(r => r.data),
  disconnect: id => api.delete(`${root}/${id}`).then(r => r.data),
  repositories: (id, page) => api.get(`${root}/${id}/repositories`, { ...options, params: { page } }).then(r => r.data),
  grants: id => api.get(`${root}/${id}/grants`).then(r => r.data),
  allow: (id, repo, allowed) => api.put(`${root}/${id}/repositories/${repo}`, { allowed }, options).then(r => r.data),
};
