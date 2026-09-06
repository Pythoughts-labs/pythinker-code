import { describe, expect, it, vi } from 'vitest';

import { OAuthAccessDeniedError } from '../src/openai-codex-oauth';
import {
  DeviceCodeExpiredError,
  DeviceOAuthApiError,
  pollForDeviceToken,
  requestDeviceCode,
  runDeviceOAuthFlow,
} from '../src/device-oauth';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('requestDeviceCode', () => {
  it('parses the device code response and applies default interval/expiry when absent', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        device_code: 'device-123',
        user_code: 'ABCD-EFGH',
        verification_uri: 'https://example.test/verify',
      }),
    );
    const before = Date.now();

    const info = await requestDeviceCode(
      'https://example.test/device/code',
      { client_id: 'client-1' },
      { 'X-Test': '1' },
      fetchMock as unknown as typeof fetch,
    );

    expect(info.deviceCode).toBe('device-123');
    expect(info.userCode).toBe('ABCD-EFGH');
    expect(info.verificationUri).toBe('https://example.test/verify');
    expect(info.intervalMs).toBe(5_000);
    expect(info.expiresAtMs).toBeGreaterThanOrEqual(before + 15 * 60_000);

    expect(fetchMock).toHaveBeenCalledWith(
      'https://example.test/device/code',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Test': '1' }),
      }),
    );
  });

  it('honors server-provided interval and expires_in', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        device_code: 'device-123',
        user_code: 'ABCD-EFGH',
        verification_uri: 'https://example.test/verify',
        interval: 2,
        expires_in: 60,
      }),
    );
    const before = Date.now();

    const info = await requestDeviceCode(
      'https://example.test/device/code',
      {},
      undefined,
      fetchMock as unknown as typeof fetch,
    );

    expect(info.intervalMs).toBe(2_000);
    expect(info.expiresAtMs).toBeGreaterThanOrEqual(before + 60_000);
    expect(info.expiresAtMs).toBeLessThan(before + 61_000);
  });

  it('throws when the response is missing required fields', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ device_code: 'device-123' }));
    await expect(
      requestDeviceCode('https://example.test/device/code', {}, undefined, fetchMock as unknown as typeof fetch),
    ).rejects.toThrow('missing required fields');
  });

  it('surfaces HTTP errors as DeviceOAuthApiError', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error_description: 'bad client' }, 400));
    const error = await requestDeviceCode(
      'https://example.test/device/code',
      {},
      undefined,
      fetchMock as unknown as typeof fetch,
    ).catch((error: unknown) => error);
    expect(error).toBeInstanceOf(DeviceOAuthApiError);
    expect((error as DeviceOAuthApiError).status).toBe(400);
    expect((error as Error).message).toBe('bad client');
  });
});

describe('pollForDeviceToken', () => {
  it('keeps polling through authorization_pending and returns the token on success', async () => {
    let call = 0;
    const fetchMock = vi.fn(async () => {
      call += 1;
      if (call < 3) return jsonResponse({ error: 'authorization_pending' }, 400);
      return jsonResponse({ access_token: 'at', refresh_token: 'rt', expires_in: 900 });
    });

    const result = await pollForDeviceToken(
      'https://example.test/token',
      { device_code: 'device-123' },
      {},
      { intervalMs: 1, expiresAtMs: Date.now() + 60_000, fetchImpl: fetchMock as unknown as typeof fetch },
    );

    expect(result['access_token']).toBe('at');
    expect(call).toBe(3);
  });

  it(
    'backs off on slow_down and keeps polling',
    async () => {
      let call = 0;
      const fetchMock = vi.fn(async () => {
        call += 1;
        if (call === 1) return jsonResponse({ error: 'slow_down' }, 400);
        return jsonResponse({ access_token: 'at', refresh_token: 'rt' });
      });

      const result = await pollForDeviceToken(
        'https://example.test/token',
        {},
        {},
        { intervalMs: 1, expiresAtMs: Date.now() + 60_000, fetchImpl: fetchMock as unknown as typeof fetch },
      );

      expect(result['access_token']).toBe('at');
      expect(call).toBe(2);
    },
    10_000,
  );

  it('throws OAuthAccessDeniedError on access_denied', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error: 'access_denied' }, 400));
    await expect(
      pollForDeviceToken(
        'https://example.test/token',
        {},
        {},
        { intervalMs: 1, expiresAtMs: Date.now() + 60_000, fetchImpl: fetchMock as unknown as typeof fetch },
      ),
    ).rejects.toBeInstanceOf(OAuthAccessDeniedError);
  });

  it('throws DeviceCodeExpiredError when the server reports expired_token', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error: 'expired_token' }, 400));
    await expect(
      pollForDeviceToken(
        'https://example.test/token',
        {},
        {},
        { intervalMs: 1, expiresAtMs: Date.now() + 60_000, fetchImpl: fetchMock as unknown as typeof fetch },
      ),
    ).rejects.toBeInstanceOf(DeviceCodeExpiredError);
  });

  it('throws DeviceCodeExpiredError once the deadline passes without a fetch', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error: 'authorization_pending' }, 400));
    await expect(
      pollForDeviceToken(
        'https://example.test/token',
        {},
        {},
        { intervalMs: 1, expiresAtMs: Date.now() - 1, fetchImpl: fetchMock as unknown as typeof fetch },
      ),
    ).rejects.toBeInstanceOf(DeviceCodeExpiredError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects with an abort reason when the signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort(new Error('cancelled'));
    const fetchMock = vi.fn(async () => jsonResponse({ error: 'authorization_pending' }, 400));
    await expect(
      pollForDeviceToken(
        'https://example.test/token',
        {},
        {},
        {
          intervalMs: 10_000,
          expiresAtMs: Date.now() + 60_000,
          signal: controller.signal,
          fetchImpl: fetchMock as unknown as typeof fetch,
        },
      ),
    ).rejects.toThrow('cancelled');
  });
});

describe('runDeviceOAuthFlow', () => {
  it('requests a code, notifies the caller, then polls until the token arrives', async () => {
    let tokenCall = 0;
    const fetchMock = vi.fn(async (input: string | URL) => {
      const url = String(input);
      if (url.endsWith('/device/code')) {
        return jsonResponse({
          device_code: 'device-123',
          user_code: 'ABCD-EFGH',
          verification_uri: 'https://example.test/verify',
          interval: 1,
        });
      }
      tokenCall += 1;
      if (tokenCall < 2) return jsonResponse({ error: 'authorization_pending' }, 400);
      return jsonResponse({ access_token: 'at', refresh_token: 'rt' });
    });

    const onCodeReady = vi.fn();
    const result = await runDeviceOAuthFlow({
      deviceAuthorizeUrl: 'https://example.test/device/code',
      deviceAuthorizeBody: { client_id: 'client-1' },
      tokenUrl: 'https://example.test/token',
      tokenBody: (deviceCode) => ({ client_id: 'client-1', device_code: deviceCode }),
      onCodeReady,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(onCodeReady).toHaveBeenCalledWith(
      expect.objectContaining({ userCode: 'ABCD-EFGH', deviceCode: 'device-123' }),
    );
    expect(result['access_token']).toBe('at');
  });
});
