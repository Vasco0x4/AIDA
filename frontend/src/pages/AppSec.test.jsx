import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import AppSec from './AppSec';
import service from '../services/appsecService';
import { useAuth } from '../contexts/AuthContext';
vi.mock('../services/appsecService', () => ({ default: Object.fromEntries(['projects', 'create', 'scans', 'scan', 'start', 'upload', 'cancel', 'triage', 'task', 'report'].map(k => [k, vi.fn()])) }));
vi.mock('../services/aiModelService', () => ({ default: { list: vi.fn().mockResolvedValue([{ id: 1, name: 'Configured model', model: 'fixture', enabled: true }]) } }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));
const project = { id: 1, name: 'Example code', repository_url: 'https://github.com/team/repo' };
describe('AppSec workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { role: 'admin' } });
    service.projects.mockResolvedValue([project]); service.scans.mockResolvedValue([]);
  });
  const show = (path = '/appsec?project=1') => render(<MemoryRouter initialEntries={[path]}><AppSec /></MemoryRouter>);
  it('requires explicit AI consent before starting a repository scan', async () => {
    const user = userEvent.setup(); show();
    await screen.findByRole('heading', { name: 'Start a source review' });
    await user.selectOptions(screen.getByLabelText('AI Review (optional)'), '1');
    expect(screen.getByRole('button', { name: 'Start review' })).toBeDisabled();
    service.start.mockResolvedValue({ id: 2 });
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: 'Start review' }));
    expect(service.start).toHaveBeenCalledWith(1, { ref: 'main', model_config_id: 1, allow_source_to_model: true });
  });
  it('keeps viewer access read only', async () => {
    useAuth.mockReturnValue({ user: { role: 'viewer' } }); show();
    await screen.findByText(/Read-only access/);
    expect(screen.queryByRole('button', { name: 'New project' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start review' })).not.toBeInTheDocument();
  });
  it('creates a ZIP-only project without provider credentials', async () => {
    service.projects.mockResolvedValue([]); service.create.mockResolvedValue({ id: 3, name: 'Private source', repository_url: '' });
    const user = userEvent.setup(); show('/appsec');
    await user.click(await screen.findByRole('button', { name: 'New project' }));
    await user.type(screen.getByLabelText('Project name'), 'Private source');
    await user.click(screen.getByRole('button', { name: 'Create project' }));
    await waitFor(() => expect(service.create).toHaveBeenCalledWith({ name: 'Private source', repository_url: '' }));
    expect(await screen.findByLabelText('Full commit SHA')).toBeInTheDocument();
  });
  it('shows failures rather than a successful empty report', async () => {
    service.scans.mockResolvedValue([{ id: 5, status: 'failed', requested_ref: 'main', created_at: '2026-11-09T12:00:00' }]);
    service.scan.mockResolvedValue({ id: 5, status: 'failed', error: 'Repository unavailable', findings: [], summary: {} });
    show('/appsec?project=1&scan=5');
    expect(await screen.findByRole('alert')).toHaveTextContent('Repository unavailable');
    expect(screen.queryByRole('button', { name: 'SARIF' })).not.toBeInTheDocument();
  });
});
