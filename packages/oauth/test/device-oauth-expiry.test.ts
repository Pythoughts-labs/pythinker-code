import { afterEach, describe, expect, it, vi } from 'vitest';

import { DeviceCodeExpiredError, pollForDeviceToken } from '../src/device-oauth';

afterEach(() => {
  vi.useRealTimers();
});

describe('pollForDeviceToken local expiry', () => {
  it('does not send a token request when the deadline passes during sleep', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(1_000));
    const fetchMock = vi.fn();

    const polling = pollForDeviceToken(
      'https://example.test/token',
      { device_code: 'device-123' },
      {},
      {
        intervalMs: 20,
        expiresAtMs: 1_010,
        fetchImpl: fetchMock as unknown as typeof fetch,
      },
    );

    await vi.advanceTimersByTimeAsync(20);

    await expect(polling).rejects.toBeInstanceOf(DeviceCodeExpiredError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects a success response that arrives after the local deadline', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2_000));
    const fetchMock = vi.fn(async () => {
      vi.setSystemTime(new Date(2_020));
      return new Response(JSON.stringify({ access_token: 'late-token' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const polling = pollForDeviceToken(
      'https://example.test/token',
      { device_code: 'device-123' },
      {},
      {
        intervalMs: 1,
        expiresAtMs: 2_010,
        fetchImpl: fetchMock as unknown as typeof fetch,
      },
    );

    await vi.advanceTimersByTimeAsync(1);

    await expect(polling).rejects.toBeInstanceOf(DeviceCodeExpiredError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
