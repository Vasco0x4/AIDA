/**
 * Submission-ready report API service — turn a finding into a polished,
 * platform-formatted bug-bounty report grounded in disclosed precedent.
 */
import apiClient from './api';

export const submissionService = {
  async platforms() {
    const { data } = await apiClient.get('/submission/platforms');
    return data; // [{id, label}]
  },

  async generate(cardId, { platform = 'hackerone', save = false, format = 'pdf' } = {}) {
    // Report generation calls the LLM — allow a generous timeout. When save=true
    // the server persists a PDF (format='pdf', default) or Markdown artifact.
    const { data } = await apiClient.post(
      `/submission/${cardId}`,
      { platform, save, format },
      { timeout: 180000 },
    );
    return data; // { card_id, platform, report_markdown, precedents, artifact_id?, disk_path? }
  },

  /** Render already-generated report Markdown to a PDF Blob (no LLM call).
   *  Pass cardId to embed that finding's screenshots into the PDF. */
  async renderPdf(markdown, { title, filename, cardId } = {}) {
    const resp = await apiClient.post(
      '/submission/render-pdf',
      { markdown, title, filename, card_id: cardId ?? null },
      { responseType: 'blob', timeout: 60000 },
    );
    return resp.data; // Blob (application/pdf)
  },
};

export default submissionService;
