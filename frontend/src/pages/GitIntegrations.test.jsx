import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import GitIntegrations from './GitIntegrations';
import service from '../services/gitIntegrationService';
import { useAuth } from '../contexts/AuthContext';
vi.mock('../services/gitIntegrationService', () => ({ default: Object.fromEntries(['list','create','check','rotate','disconnect','repositories','grants','allow'].map(k => [k, vi.fn()])) }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));
const connection = { id: 1, name: 'Engineering', provider: 'github', enabled: true, origin: 'https://github.com', account: 'fixture' };
const repo = { provider_id: '42', path: 'team/private', default_branch: 'develop', allowed: false, private: true };
describe('Git integrations', () => {
  beforeEach(() => { vi.resetAllMocks(); useAuth.mockReturnValue({ user: { role: 'admin' } }); service.list.mockResolvedValue([]); service.grants.mockResolvedValue([]); service.repositories.mockResolvedValue({ items: [repo], has_more: false }); });
  const show = () => render(<MemoryRouter><GitIntegrations /></MemoryRouter>);
  it('verifies a connection and clears the token', async () => {
    const user = userEvent.setup(); show();
    await user.type(screen.getByLabelText('Connection name'), 'Engineering');
    await user.type(screen.getByLabelText('Access token'), 'fixture-secret');
    service.create.mockImplementation(async () => { service.list.mockResolvedValue([connection]); return connection; });
    await user.click(screen.getByRole('button', { name: 'Check & connect' }));
    await screen.findByRole('checkbox', { name: 'Allow team/private' });
    expect(service.create).toHaveBeenCalledWith(expect.objectContaining({ token: 'fixture-secret', provider: 'github' }));
    expect(screen.queryByDisplayValue('fixture-secret')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open project' })).not.toBeInTheDocument();
  });
  it('requires explicit permission before offering the project', async () => {
    service.list.mockResolvedValue([connection]); const user = userEvent.setup(); show();
    const checkbox = await screen.findByRole('checkbox', { name: 'Allow team/private' });
    expect(checkbox).not.toBeChecked();
    service.allow.mockImplementation(async () => { service.grants.mockResolvedValue([{ ...repo, allowed: true, project_id: 9 }]); service.repositories.mockResolvedValue({items:[{...repo,allowed:true}],has_more:false}); });
    await user.click(checkbox);
    await waitFor(() => expect(service.allow).toHaveBeenCalledWith('1','42',true));
    expect(await screen.findByRole('link', { name: 'Open project' })).toHaveAttribute('href','/appsec?project=9');
  });
  it('does not request connection metadata for viewers', () => {
    useAuth.mockReturnValue({ user: { role: 'viewer' } }); show();
    expect(screen.queryByLabelText('Access token')).not.toBeInTheDocument();
    expect(service.list).not.toHaveBeenCalled();
  });
});
