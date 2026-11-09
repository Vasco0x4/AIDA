import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RunDashboard from './RunDashboard';
import scanRunService from '../services/scanRunService';
import { useAuth } from '../contexts/AuthContext';

vi.mock('../services/scanRunService', () => ({ default: {
  list: vi.fn(), get: vi.fn(), findings: vi.fn(), diff: vi.fn(), events: vi.fn(),
  pause: vi.fn(), resume: vi.fn(), cancel: vi.fn(), retry: vi.fn(), report: vi.fn(),
} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const run = { id: 12, title: 'Nightly lab — run 2', status: 'running', assessment_id: 7,
  target: 'http://127.0.0.1:3000', created_at: '2026-11-06T10:00:00Z',
  meta: { paused: false, scan_profile: 'safe_web_baseline' } };
const diff = { summary: { new: 1, recurring: 1, remediated: 1, reopened: 1 },
  new: [{ card_id: 1, fingerprint: 'a', title: 'New exposed debug', severity: 'HIGH', target_service: 'http://lab' }],
  recurring: [{ card_id: 2, fingerprint: 'b', title: 'Missing CSP', severity: 'MEDIUM', target_service: 'http://lab' }],
  remediated: [{ card_id: 3, fingerprint: 'c', title: 'Old header', severity: 'LOW', target_service: 'http://lab' }],
  reopened: [{ card_id: 4, fingerprint: 'd', title: 'Debug returned', severity: 'HIGH', target_service: 'http://lab' }] };

describe('RunDashboard', () => {
  afterEach(() => vi.useRealTimers());
  beforeEach(() => {
    useAuth.mockReturnValue({ user: { role: 'admin' } });
    scanRunService.list.mockResolvedValue([run]);
    scanRunService.get.mockResolvedValue(run);
    scanRunService.diff.mockResolvedValue(diff);
    scanRunService.findings.mockResolvedValue([{ id: 1, title: '<img src=x onerror=alert(1)>',
      severity: 'HIGH', target_service: 'http://lab', proof: 'AIDA-E2E-CANARY',
      technical_analysis: 'Real response evidence', lifecycle_status: 'new' }]);
    scanRunService.events.mockResolvedValue([
      { id: 1, event_type: 'status', payload: { status: 'running' }, created_at: '2026-11-06T10:00:00Z' },
      { id: 2, event_type: 'finding', payload: { title: 'Missing CSP' }, created_at: '2026-11-06T10:00:01Z' },
    ]);
    scanRunService.pause.mockImplementation(async () => { const paused = { ...run, status: 'queued', meta: { paused: true } }; scanRunService.get.mockResolvedValue(paused); return paused; });
    scanRunService.resume.mockImplementation(async () => { scanRunService.get.mockResolvedValue(run); return run; });
    scanRunService.report.mockResolvedValue(new Blob(['report'], { type: 'text/html' }));
    window.URL.createObjectURL = vi.fn(() => 'blob:report');
    window.URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });

  function renderDashboard() {
    return render(<MemoryRouter initialEntries={['/runs/12']}><Routes>
      <Route path="/runs/:id?" element={<RunDashboard />} />
    </Routes></MemoryRouter>);
  }

  it('renders lifecycle counts, evidence and chronological events safely', async () => {
    renderDashboard();
    expect(await screen.findByRole('heading', { name: /Nightly lab/ })).toBeInTheDocument();
    expect(screen.getByText('1 new')).toBeInTheDocument();
    expect(screen.getByText('1 recurring')).toBeInTheDocument();
    expect(screen.getByText('1 remediated')).toBeInTheDocument();
    expect(screen.getByText('1 reopened')).toBeInTheDocument();
    expect(screen.getByText('AIDA-E2E-CANARY')).toBeInTheDocument();
    expect(document.querySelector('img[src="x"]')).not.toBeInTheDocument();
    expect(await screen.findByText('finding')).toBeInTheDocument();
    expect(screen.getAllByText(/Missing CSP/).length).toBeGreaterThan(0);
  });

  it('pauses then resumes the selected run and exports its report', async () => {
    const user = userEvent.setup();
    renderDashboard();
    await user.click(await screen.findByRole('button', { name: /pause run/i }));
    expect(await screen.findByRole('button', { name: /resume run/i })).toBeInTheDocument();
    expect(scanRunService.pause).toHaveBeenCalledWith(12);
    await user.click(screen.getByRole('button', { name: /resume run/i }));
    await waitFor(() => expect(scanRunService.resume).toHaveBeenCalledWith(12));
    await user.click(screen.getByRole('button', { name: /export html/i }));
    expect(scanRunService.report).toHaveBeenCalledWith(12, 'html');
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:report');
  });

  it('loads an earlier event page with a stable cursor', async () => {
    scanRunService.events.mockResolvedValue(Array.from({ length: 100 }, (_, index) => ({
      id: index + 1, event_type: 'status', payload: {}, created_at: '2026-11-06T10:00:00Z' })));
    const user = userEvent.setup();
    renderDashboard();
    const earlier = await screen.findByRole('button', { name: /load earlier events/i });
    await user.click(earlier);
    await waitFor(() => expect(scanRunService.events).toHaveBeenLastCalledWith(12,
      expect.objectContaining({ beforeId: 1, limit: 100 })));
  });

  it('refreshes active runs and stops polling after completion', async () => {
    vi.useFakeTimers();
    scanRunService.get.mockClear();
    scanRunService.get.mockResolvedValueOnce(run).mockResolvedValue({ ...run, status: 'done', result_summary: 'Finished successfully' });
    renderDashboard();
    await act(async () => {});
    expect(scanRunService.get).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(screen.getByText('Finished successfully')).toBeInTheDocument();
    expect(scanRunService.get).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(scanRunService.get).toHaveBeenCalledTimes(2);
  });

  it('retains evidence after a failed update and retries automatically', async () => {
    vi.useFakeTimers();
    scanRunService.get.mockResolvedValueOnce(run).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(run);
    renderDashboard();
    await act(async () => {});
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(screen.getByRole('alert')).toHaveTextContent('Retrying automatically');
    expect(screen.getByText('AIDA-E2E-CANARY')).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not offer mutations to viewers', async () => {
    useAuth.mockReturnValue({ user: { role: 'viewer' } });
    renderDashboard();
    expect(await screen.findByRole('heading', { name: /Nightly lab/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pause run/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /cancel run/i })).not.toBeInTheDocument();
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
  });
});
