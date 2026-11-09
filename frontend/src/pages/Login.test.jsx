import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Login from './Login';
import { useAuth } from '../contexts/AuthContext';
import api from '../services/api';

vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));
vi.mock('../services/api', () => ({ default: { get: vi.fn(), defaults: { baseURL: '/api' } } }));

const auth = {
  login: vi.fn(), verifyOtp: vi.fn(), ssoLogin: vi.fn(), backendUnreachable: false,
};

describe('Login two-step flow', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/');
    window.location.hash = '';
    Object.values(auth).forEach((value) => { if (typeof value === 'function') value.mockReset(); });
    useAuth.mockReturnValue(auth);
    api.get.mockResolvedValue({ data: { enabled: false, provider: null } });
  });

  it('asks for the second factor without resubmitting the password', async () => {
    auth.login.mockResolvedValue({ otpRequired: true, challengeId: 'challenge-id' });
    auth.verifyOtp.mockResolvedValue({ token: 'full-token' });
    const events = userEvent.setup();
    render(<Login />);
    await events.type(screen.getByLabelText(/username/i), 'admin');
    await events.type(screen.getByLabelText(/^password/i), 'password');
    await events.click(screen.getByRole('button', { name: /sign in/i }));

    const input = await screen.findByLabelText(/authenticator or recovery code/i);
    expect(screen.queryByLabelText(/^password/i)).not.toBeInTheDocument();
    await events.type(input, '123456');
    await events.click(screen.getByRole('button', { name: /verify and sign in/i }));
    await waitFor(() => expect(auth.verifyOtp).toHaveBeenCalledWith('challenge-id', '123456'));
    expect(auth.login).toHaveBeenCalledTimes(1);
  });

  it('accepts an OIDC OTP challenge from the redirect hash', async () => {
    window.location.hash = '#challenge=sso-challenge';
    auth.verifyOtp.mockResolvedValue({ token: 'full-token' });
    const events = userEvent.setup();
    render(<Login />);
    const input = await screen.findByLabelText(/authenticator or recovery code/i);
    await events.type(input, 'ABCDE-12345-FGHIJ-67890');
    await events.click(screen.getByRole('button', { name: /verify and sign in/i }));
    await waitFor(() => expect(auth.verifyOtp).toHaveBeenCalledWith(
      'sso-challenge', 'ABCDE-12345-FGHIJ-67890',
    ));
    expect(auth.login).not.toHaveBeenCalled();
    expect(auth.ssoLogin).not.toHaveBeenCalled();
  });
});
