import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { NewTaskModal } from './Board';
import taskService from '../services/taskService';
import taskExtrasService from '../services/taskExtrasService';

vi.mock('../services/taskService', () => ({ default: { moveTask: vi.fn().mockResolvedValue({}) } }));
vi.mock('../services/taskExtrasService', () => ({ default: { uploadFile: vi.fn() } }));

it('uploads context before queuing, and retries without creating a duplicate task', async () => {
  const user = userEvent.setup();
  const onCreate = vi.fn().mockResolvedValue({ id: 21, version: 1 });
  const onClose = vi.fn();
  taskExtrasService.uploadFile.mockRejectedValueOnce(new Error('Upload unavailable')).mockResolvedValueOnce({});
  const { container } = render(<NewTaskModal models={[]} onCreate={onCreate} onClose={onClose} />);
  await user.type(screen.getByLabelText('Title'), 'Staging check');
  await user.type(screen.getByLabelText(/Authorized scope/), 'staging.example');
  await user.selectOptions(screen.getByLabelText('Start in'), 'queued');
  await user.upload(container.querySelector('input[type="file"]'), new File(['context'], 'scope.txt', { type: 'text/plain' }));
  await user.click(screen.getByRole('button', { name: 'Create task' }));
  await screen.findByText(/Task saved in Backlog/);
  expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ status: 'backlog' }));
  expect(taskService.moveTask).not.toHaveBeenCalled();
  expect(onClose).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Retry remaining steps' }));
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  expect(onCreate).toHaveBeenCalledOnce();
  expect(taskService.moveTask).toHaveBeenCalledWith(21, 'queued', 0, 1);
});
