/**
 * Artifact API service — evidence files (screenshots, PoC videos) attached to a
 * finding. Media endpoints are auth-protected (Bearer header), so binary content
 * is fetched as a blob through the authenticated client and exposed as an object
 * URL for <img>/<video> tags.
 */
import apiClient from './api';

export const artifactService = {
  async list(assessmentId, cardId = null) {
    const { data } = await apiClient.get(`/assessments/${assessmentId}/artifacts`, {
      params: cardId != null ? { card_id: cardId } : {},
    });
    return data;
  },

  /** Fetch artifact bytes with auth and return an object URL (caller revokes it). */
  async contentUrl(artifactId) {
    const resp = await apiClient.get(`/artifacts/${artifactId}/content`, {
      responseType: 'blob',
    });
    return URL.createObjectURL(resp.data);
  },

  async remove(artifactId) {
    await apiClient.delete(`/artifacts/${artifactId}`);
  },
};

export default artifactService;
