import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from './api';
import {
  disableOtp, enableOtp, getStoredToken, getStoredUser, login, setupOtp, verifyOtp,
} from './authService';

vi.mock('./api', () => ({ default: { post: vi.fn(), get: vi.fn() } }));

const user = { id: 1, username: 'admin', otp_enabled: true };

describe('two-step authentication service', () => {
  beforeEach(() => {
    localStorage.clear();
    api.post.mockReset();
  });

  it('does not persist a session when a password returns an OTP challenge', async () => {
    api.post.mockResolvedValue({ data: {
      otp_required: true, otp_enabled: true, challenge_id: 'challenge-id', user,
    } });
    const result = await login('admin', 'password');
    expect(result).toMatchObject({ otpRequired: true, challengeId: 'challenge-id' });
    expect(getStoredToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });

  it('stores only the full session issued after OTP verification', async () => {
    api.post.mockResolvedValue({ data: { access_token: 'full-token', user } });
    const result = await verifyOtp('challenge-id', ' 123456 ');
    expect(api.post).toHaveBeenCalledWith('/auth/otp/verify', {
      challenge_id: 'challenge-id', code: '123456',
    });
    expect(result.token).toBe('full-token');
    expect(getStoredToken()).toBe('full-token');
    expect(getStoredUser()).toEqual(user);
  });

  it('keeps non-OTP password login backwards compatible', async () => {
    api.post.mockResolvedValue({ data: { access_token: 'token', user } });
    await expect(login('admin', 'password')).resolves.toEqual({ token: 'token', user });
    expect(getStoredToken()).toBe('token');
  });

  it('omits the local password for verified OIDC-only sessions', async () => {
    api.post
      .mockResolvedValueOnce({ data: { secret: 'secret' } })
      .mockResolvedValueOnce({ data: { enabled: true, recovery_codes: [] } })
      .mockResolvedValueOnce({ data: { enabled: false } });
    await setupOtp('');
    await enableOtp('', '123456');
    await disableOtp('', '123456');
    expect(api.post.mock.calls).toEqual([
      ['/auth/otp/setup', {}],
      ['/auth/otp/enable', { code: '123456' }],
      ['/auth/otp/disable', { code: '123456' }],
    ]);
  });
});
