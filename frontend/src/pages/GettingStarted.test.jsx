import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import GettingStarted from './GettingStarted';
import api from '../services/api';
const session = vi.hoisted(() => ({ user: { role: 'admin' } }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => session }));
vi.mock('../services/api', () => ({ default: { get: vi.fn() } }));
const system = { backend: { status: 'connected' }, database: { connected: true }, exegol: { running: true, container: 'test-executor' } };
beforeEach(() => {
  session.user = { role: 'admin' };
  api.get.mockReset();
  api.get.mockImplementation(path => Promise.resolve({ data: path === '/system/status' ? system : path === '/tasks/runner' ? { enabled: false, active: 0 } : [{ enabled: true }] }));
});
describe('Getting started workspace checks', () => {
  it('shows configured services without claiming AI credentials were tested', async () => {
    render(<MemoryRouter><GettingStarted /></MemoryRouter>);
    expect(await screen.findByText('Runner is paused')).toBeInTheDocument();
    expect(screen.getAllByText('Configured')).toHaveLength(3);
    expect(screen.getByText(/Test credentials in AI Models/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open AI Models' })).toHaveAttribute('href', '/settings?tab=ai_models');
  });
  it('shows unavailable status instead of false success and allows retry', async () => {
    api.get.mockRejectedValue(new Error('Offline'));
    render(<MemoryRouter><GettingStarted /></MemoryRouter>);
    expect(await screen.findByText('Runner status is unavailable')).toBeInTheDocument();
    expect(screen.getAllByText('Not verified')).toHaveLength(3);
    fireEvent.click(screen.getByRole('button', { name: 'Refresh checks' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(6));
  });
  it('does not request administrative model configuration for viewers', async () => {
    session.user = { role: 'viewer' };
    render(<MemoryRouter><GettingStarted /></MemoryRouter>);
    await screen.findByText('Runner is paused');
    expect(api.get.mock.calls.map(([path]) => path)).not.toContain('/ai-models');
    expect(screen.getByText(/Ask an administrator/)).toBeInTheDocument();
  });
});
