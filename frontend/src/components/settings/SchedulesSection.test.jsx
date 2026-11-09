import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import SchedulesSection from './SchedulesSection';
import scheduleService from '../../services/scheduleService';
import scanProfileService from '../../services/scanProfileService';
import { assessmentService } from '../../services/assessmentService';
import aiModelService from '../../services/aiModelService';
import { useAuth } from '../../contexts/AuthContext';

vi.mock('../../services/scheduleService', () => ({ default: {
  list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), runNow: vi.fn(), preview: vi.fn().mockResolvedValue({ occurrences: ['2026-11-09T03:00:00Z'] }),
} }));
vi.mock('../../services/scanProfileService', () => ({ default: {
  list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(),
} }));
vi.mock('../../services/assessmentService', () => ({ assessmentService: { getAll: vi.fn() } }));
vi.mock('../../services/aiModelService', () => ({ default: { list: vi.fn() } }));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const profile = { id: 2, name: 'Careful baseline', kind: 'safe_web_baseline', enabled: true,
  rate_limit_seconds: 3, max_pages: 4, max_response_bytes: 250000, timeout_seconds: 4 };
const schedule = { id: 5, name: 'Nightly lab', cron: '0 3 * * *', task_title: 'Lab run',
  enabled: true, priority: 'medium', orchestrate: false, run_count: 1,
  assessment_id: 7, scan_profile_id: 2, scan_profile: 'safe_web_baseline',
  authorized_scope: '127.0.0.1', last_task_id: 12, last_task_status: 'done' };

describe('SchedulesSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    scheduleService.list.mockResolvedValue([]);
    scheduleService.create.mockResolvedValue(schedule);
    scheduleService.update.mockResolvedValue(schedule);
    scheduleService.runNow.mockResolvedValue({ id: 13 });
    scanProfileService.list.mockResolvedValue([profile]);
    assessmentService.getAll.mockResolvedValue([{ id: 7, name: 'Local lab', scope: '127.0.0.1' }]);
    aiModelService.list.mockResolvedValue([]);
    useAuth.mockReturnValue({ user: { role: 'admin' } });
  });

  function renderSection() {
    return render(<MemoryRouter><SchedulesSection /></MemoryRouter>);
  }

  it('requires an Assessment but does not require a reusable profile', async () => {
    scanProfileService.list.mockResolvedValue([]);
    assessmentService.getAll.mockResolvedValue([]);
    renderSection();
    expect(await screen.findByText('Create an Assessment before adding a schedule.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new schedule/i })).toBeDisabled();
    expect(screen.getByText(/Profiles are optional/)).toBeInTheDocument();
  });

  it('shows a retryable load error instead of a misleading empty setup', async () => {
    scheduleService.list.mockRejectedValueOnce(new Error('offline'));
    const user = userEvent.setup();
    renderSection();
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded');
    expect(screen.queryByText('Set up your first schedule')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^refresh$/i }));
    expect(await screen.findByText('Set up your first schedule')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('traps dialog focus, closes with Escape, and restores the trigger', async () => {
    const user = userEvent.setup();
    renderSection();
    const trigger = await screen.findByRole('button', { name: /new schedule/i });
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: /new scheduled scan/i });
    expect(within(dialog).getByLabelText(/schedule name/i)).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('creates an authorized same-Assessment run from explicit scope and profile', async () => {
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole('button', { name: /new schedule/i }));
    const dialog = screen.getByRole('dialog');
    await user.type(within(dialog).getByLabelText(/schedule name/i), 'Nightly lab');
    await user.selectOptions(within(dialog).getByLabelText(/^Assessment/i), '7');
    await user.selectOptions(within(dialog).getByLabelText(/Scan Profile/i), '2');
    await user.type(within(dialog).getByLabelText(/Task title/i), 'Local baseline');
    await user.type(within(dialog).getByLabelText(/Target URL/i), 'http://127.0.0.1:3000');
    await user.type(within(dialog).getByLabelText(/Authorized scope/i), '127.0.0.1');
    await user.type(within(dialog).getByLabelText(/Authorization reference/i), 'Owned isolated lab');
    await user.click(within(dialog).getByLabelText(/I confirm/i));
    await user.click(within(dialog).getByRole('button', { name: /create schedule/i }));

    await waitFor(() => expect(scheduleService.create).toHaveBeenCalledTimes(1));
    const payload = scheduleService.create.mock.calls[0][0];
    expect(payload).toMatchObject({ assessment_id: 7, scan_profile_id: 2,
      scan_profile: 'safe_web_baseline', authorized_scope: '127.0.0.1',
      authorization_reference: 'Owned isolated lab', authorization_confirmed: true,
      orchestrate: false });
  });

  it('links the latest run and surfaces run-now success without assuming completion', async () => {
    scheduleService.list.mockResolvedValue([schedule]);
    const user = userEvent.setup();
    renderSection();
    expect(await screen.findByRole('link', { name: /view run #12/i })).toHaveAttribute('href', '/runs/12');
    await user.click(screen.getByRole('button', { name: /run nightly lab now/i }));
    expect(await screen.findByRole('status')).toHaveTextContent(/Scan Run #13 queued/i);
  });

  it('keeps viewer access read-only', async () => {
    useAuth.mockReturnValue({ user: { role: 'viewer' } });
    scheduleService.list.mockResolvedValue([schedule]);
    renderSection();
    expect(await screen.findByText('Nightly lab')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /new schedule/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /run nightly lab now/i })).not.toBeInTheDocument();
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
  });

  it('prevents duplicate run-now submissions while the request is pending', async () => {
    scheduleService.list.mockResolvedValue([schedule]);
    let finish;
    scheduleService.runNow.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const user = userEvent.setup(); renderSection();
    const trigger = await screen.findByRole('button', { name: /run nightly lab now/i });
    await user.click(trigger);
    expect(trigger).toBeDisabled();
    await user.click(trigger);
    expect(scheduleService.runNow).toHaveBeenCalledTimes(1);
    finish({ id: 13 });
    await screen.findByRole('status');
  });

  it('previews the schedule without creating a schedule or starting a run', async () => {
    const user = userEvent.setup(); renderSection();
    await user.click(await screen.findByRole('button', { name: /new schedule/i }));
    await waitFor(() => expect(scheduleService.preview).toHaveBeenCalled());
    expect(screen.getByText(/Preview only. No scan is started./)).toBeInTheDocument();
  });

  it('uses UTC by default and previews a selected positive offset without reversing its sign', async () => {
    const user = userEvent.setup(); renderSection();
    await user.click(await screen.findByRole('button', { name: /new schedule/i }));
    const zone = screen.getByLabelText('Timezone');
    expect(zone).toHaveValue('UTC');
    await user.selectOptions(zone, 'Etc/GMT-5');
    await waitFor(() => expect(scheduleService.preview).toHaveBeenLastCalledWith('0 3 * * *', 'Etc/GMT-5'));
    expect(screen.getByText('Next five runs · UTC+05:00')).toBeInTheDocument();
    expect(scheduleService.create).not.toHaveBeenCalled();
  });

  it('preserves an existing regional timezone when editing', async () => {
    scheduleService.list.mockResolvedValue([{ ...schedule, timezone: 'Asia/Tashkent' }]);
    const user = userEvent.setup(); renderSection();
    const row = (await screen.findByText('Nightly lab')).closest('article');
    await user.click(within(row).getByRole('button', { name: 'Edit' }));
    expect(screen.getByLabelText('Timezone')).toHaveValue('Asia/Tashkent');
  });
});
