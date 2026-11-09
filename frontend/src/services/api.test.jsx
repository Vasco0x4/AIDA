import { describe, it, expect, vi } from 'vitest';

describe('API origin', () => {
  it('uses the current site when no build-time API URL is configured', async () => {
    vi.stubEnv('VITE_API_URL', '');
    vi.resetModules();
    const { default: api } = await import('./api');
    expect(api.defaults.baseURL).toBe('/api');
    vi.unstubAllEnvs();
  });
});
