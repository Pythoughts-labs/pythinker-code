import { describe, expect, it, vi } from 'vitest';

import { runDeviceOAuthFlow } from '../src/device-oauth';

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('runDeviceOAuthFlow cancellation', () => {
  it('aborts the initial authorization request and never exposes a device code', async () => {
    const controller = new AbortController();
    const onCodeReady = vi.fn();
    const fetchMock = vi.fn(async (_input: string | URL, init?: RequestInit) => {
      return await new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        signal?.addEventListener(
          'abort',
          () => reject(signal.reason instanceof Error ? signal.reason : new DOMException('Aborted', 'AbortError')),
          { once: true },
        );
      });
    });

    const flow = runDeviceOAuthFlow({
      deviceAuthorizeUrl: 'https://example.test/device/code',
      deviceAuthorizeBody: { client_id: 'client' },
      tokenUrl: 'https://example.test/token',
      tokenBody: (deviceCode) => ({ device_code: deviceCode }),
      onCodeReady,
      fetchImpl: fetchMock as unknown as typeof fetch,
      signal: controller.signal,
    });
    controller.abort(new Error('cancelled'));

    await expect(flow).rejects.toThrow('cancelled');
    expect(onCodeReady).not.toHaveBeenCalled();
  });

  it('does not invoke onCodeReady when cancellation lands after the response resolves', async () => {
    const controller = new AbortController();
    const onCodeReady = vi.fn();
    const fetchMock = vi.fn(async () => {
      controller.abort(new Error('cancelled-after-response'));
      return jsonResponse({
        device_code: 'device-123',
        user_code: 'ABCD',
        verification_uri: 'https://example.test/verify',
      });
    });

    await expect(
      runDeviceOAuthFlow({
        deviceAuthorizeUrl: 'https://example.test/device/code',
        deviceAuthorizeBody: { client_id: 'client' },
        tokenUrl: 'https://example.test/token',
        tokenBody: (deviceCode) => ({ device_code: deviceCode }),
        onCodeReady,
        fetchImpl: fetchMock as unknown as typeof fetch,
        signal: controller.signal,
      }),
    ).rejects.toThrow('cancelled-after-response');
    expect(onCodeReady).not.toHaveBeenCalled();
  });
});
