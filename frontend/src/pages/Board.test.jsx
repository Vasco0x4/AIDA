import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Board from './Board';
import taskService from '../services/taskService';
import aiModelService from '../services/aiModelService';
import { useAuth } from '../contexts/AuthContext';

vi.mock('../services/taskService', () => ({ default: {
  getBoard: vi.fn(), getRunner: vi.fn(), setRunner: vi.fn(), moveTask: vi.fn(), listEvents: vi.fn().mockResolvedValue([]),
} }));
vi.mock('../services/aiModelService', () => ({ default: { list: vi.fn() } }));
vi.mock('../services/taskExtrasService', () => ({ default: {
  listComments: vi.fn().mockResolvedValue([]), listFiles: vi.fn().mockResolvedValue([]),
} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));
const subscribe = vi.fn(() => () => {});
vi.mock('../contexts/WebSocketContext', () => ({ useWebSocketContext: () => ({ subscribe }) }));

const task = { id: 7, title: 'Review staging', target: 'staging.example', priority: 'high', status: 'backlog', version: 4, source: 'ui' };
const board = { columns: ['backlog', 'queued', 'running', 'needs_review', 'done', 'failed'].map(key => ({ key, tasks: key === 'backlog' ? [task] : [] })) };
const renderBoard = () => render(<MemoryRouter><Board /></MemoryRouter>);

describe('Task board', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { role: 'admin' } });
    taskService.getBoard.mockResolvedValue(board);
    taskService.getRunner.mockResolvedValue({ enabled: false, active: 0 });
    aiModelService.list.mockResolvedValue([]);
  });
  it('keeps viewer access read-only without requesting admin model settings', async () => {
    useAuth.mockReturnValue({ user: { role: 'viewer' } });
    renderBoard();
    expect(await screen.findByRole('button', { name: 'Resume runner' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'New task' })).toBeDisabled();
    expect(aiModelService.list).not.toHaveBeenCalled();
  });
  it('shows a recoverable connection error instead of an enabled runner', async () => {
    taskService.getBoard.mockRejectedValue(new Error('offline'));
    renderBoard();
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to refresh');
    expect(screen.getByRole('button', { name: 'Runner unavailable' })).toBeDisabled();
  });
  it('keeps model loading out of live board refreshes', async () => {
    const user = userEvent.setup(); renderBoard();
    await screen.findByRole('group', { name: 'Task: Review staging' });
    await user.click(screen.getByRole('button', { name: 'Refresh board' }));
    await waitFor(() => expect(taskService.getBoard).toHaveBeenCalledTimes(2));
    expect(aiModelService.list).toHaveBeenCalledTimes(1);
  });
  it('retains the paused runner state when resume fails', async () => {
    taskService.setRunner.mockRejectedValue(new Error('offline'));
    const user = userEvent.setup(); renderBoard();
    await user.click(await screen.findByRole('button', { name: 'Resume runner' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be changed');
    expect(screen.getByRole('button', { name: 'Resume runner' })).toBeEnabled();
  });
  it('filters cards without losing the underlying task', async () => {
    const user = userEvent.setup(); renderBoard();
    await screen.findByRole('group', { name: 'Task: Review staging' });
    await user.type(screen.getByRole('textbox', { name: 'Search tasks' }), 'missing');
    expect(screen.queryByRole('group', { name: 'Task: Review staging' })).not.toBeInTheDocument();
    await user.clear(screen.getByRole('textbox', { name: 'Search tasks' }));
    expect(screen.getByRole('group', { name: 'Task: Review staging' })).toBeInTheDocument();
  });
  it('opens a task with the keyboard and moves it with its version', async () => {
    const user = userEvent.setup(); renderBoard();
    const card = await screen.findByRole('group', { name: 'Task: Review staging' });
    card.focus(); await user.keyboard('{Enter}');
    await user.selectOptions(screen.getByLabelText('Move task to'), 'queued');
    await waitFor(() => expect(taskService.moveTask).toHaveBeenCalledWith(7, 'queued', 0, 4));
  });
});
