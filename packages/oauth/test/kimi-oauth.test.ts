import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  applyKimiOAuthConfig,
  fetchKimiCodingModels,
  KIMI_CODING_BASE_URL,
  KIMI_CODING_PROVIDER_ID,
  refreshKimiOAuthToken,
  runKimiOAuthFlow,
} from '../src/kimi-oauth';
import type { PythinkerConfigShape } from '../src/provider-config';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => vi.restoreAllMocks());

describe('runKimiOAuthFlow', () => {
  it('requests a device code, notifies the caller, and exchanges it for tokens', async () => {
    let tokenCall = 0;
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = new Request(input).url;
      if (url === 'https://auth.kimi.com/api/oauth/device_authorization') {
        return jsonResponse({
          device_code: 'device-123',
          user_code: 'ABCD-EFGH',
          verification_uri: 'https://kimi.com/code/authorize_device',
          interval: 1,
        });
      }
      tokenCall += 1;
      if (tokenCall < 2) return jsonResponse({ error: 'authorization_pending' }, 400);
      return jsonResponse({ access_token: 'at', refresh_token: 'rt', expires_in: 900, scope: 'kimi-code', token_type: 'Bearer' });
    });

    const onCodeReady = vi.fn();
    const bundle = await runKimiOAuthFlow({ onCodeReady, fetchImpl: fetchMock });

    expect(onCodeReady).toHaveBeenCalledWith(expect.objectContaining({ userCode: 'ABCD-EFGH' }));
    expect(bundle.accessToken).toBe('at');
    expect(bundle.refreshToken).toBe('rt');
    expect(bundle.deviceId).toMatch(/^[0-9a-f-]{36}$/);
    expect(bundle.scope).toBe('kimi-code');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://auth.kimi.com/api/oauth/device_authorization',
      expect.objectContaining({
        headers: expect.objectContaining({ 'X-Msh-Device-Id': bundle.deviceId }),
      }),
    );
  });

  it('throws when the token exchange response is missing an access_token', async () => {
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      if (new Request(input).url.endsWith('device_authorization')) {
        return jsonResponse({
          device_code: 'device-123',
          user_code: 'ABCD-EFGH',
          verification_uri: 'https://kimi.com/code/authorize_device',
          interval: 1,
        });
      }
      return jsonResponse({ refresh_token: 'rt' });
    });

    await expect(
      runKimiOAuthFlow({ onCodeReady: () => {}, fetchImpl: fetchMock }),
    ).rejects.toThrow('missing access_token');
  });
});

describe('refreshKimiOAuthToken', () => {
  it('bounds refresh requests with a thirty-second deadline', async () => {
    const controller = new AbortController();
    const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(controller.signal);
    const fetchMock = vi.fn<typeof fetch>(async (_input, init) => {
      expect(init?.signal).toBeInstanceOf(AbortSignal);
      controller.abort(new DOMException('Refresh deadline reached', 'TimeoutError'));
      init?.signal?.throwIfAborted();
      throw new Error('Expected an aborted request');
    });

    await expect(refreshKimiOAuthToken('rt', 'device-123', fetchMock)).rejects.toThrow('Refresh deadline reached');
    expect(timeout).toHaveBeenCalledWith(30_000);
  });

  it('preserves the device id and accepts refresh-token rotation', async () => {
    const fetchMock = vi.fn<typeof fetch>(async (_input, init) => {
      expect(init?.headers).toEqual(expect.objectContaining({ 'X-Msh-Device-Id': 'device-123' }));
      const body = init?.body;
      if (!(body instanceof URLSearchParams)) throw new Error('Expected an OAuth form body');
      expect(body.get('grant_type')).toBe('refresh_token');
      expect(body.get('refresh_token')).toBe('old-rt');
      return jsonResponse({ access_token: 'new-at', refresh_token: 'new-rt', expires_in: 900 });
    });
    const token = await refreshKimiOAuthToken('old-rt', 'device-123', fetchMock);
    expect(token.accessToken).toBe('new-at');
    expect(token.refreshToken).toBe('new-rt');
    expect(token.deviceId).toBe('device-123');
  });

  it.each([undefined, ''])('preserves the previous refresh token when the response sends %s', async (refreshToken) => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      jsonResponse({ access_token: 'new-at', refresh_token: refreshToken, expires_in: 900 }),
    );

    const token = await refreshKimiOAuthToken('old-rt', 'device-123', fetchMock);

    expect(token.accessToken).toBe('new-at');
    expect(token.refreshToken).toBe('old-rt');
    expect(token.deviceId).toBe('device-123');
  });
});

describe('fetchKimiCodingModels', () => {
  it('fetches models from the Kimi coding base URL with device headers', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      jsonResponse({
        data: [
          { id: 'kimi-for-coding', context_length: 262144, supports_reasoning: true },
        ],
      }),
    );

    const models = await fetchKimiCodingModels(
      'access-token',
      'device-123',
      fetchMock,
    );

    expect(models).toHaveLength(1);
    expect(models[0]?.id).toBe('kimi-for-coding');
    expect(fetchMock).toHaveBeenCalledWith(
      `${KIMI_CODING_BASE_URL}/models`,
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer access-token',
          'X-Msh-Device-Id': 'device-123',
        }),
      }),
    );
  });
});

describe('applyKimiOAuthConfig', () => {
  it('writes a credential reference with custom device headers and no bearer token', () => {
    const config: PythinkerConfigShape = { providers: {} };
    const selectedModel = {
      id: 'kimi-for-coding', contextLength: 262144, supportsReasoning: true, supportsImageIn: true, supportsVideoIn: false,
    };
    const models = [selectedModel];

    const result = applyKimiOAuthConfig(config, {
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      deviceId: 'device-123',
      models,
      selectedModel,
      thinking: true,
    });

    expect(result.defaultModel).toBe(`${KIMI_CODING_PROVIDER_ID}/kimi-for-coding`);
    expect(config.providers[KIMI_CODING_PROVIDER_ID]).toMatchObject({
      type: 'pythinker',
      baseUrl: KIMI_CODING_BASE_URL,
      oauth: { storage: 'file', key: `oauth/${KIMI_CODING_PROVIDER_ID}` },
      customHeaders: expect.objectContaining({ 'X-Msh-Device-Id': 'device-123' }),
      source: { auth: 'kimi-oauth', deviceId: 'device-123' },
    });
    expect(config.providers[KIMI_CODING_PROVIDER_ID]).not.toHaveProperty('apiKey');
    expect(config.models?.[`${KIMI_CODING_PROVIDER_ID}/kimi-for-coding`]).toMatchObject({
      provider: KIMI_CODING_PROVIDER_ID,
      model: 'kimi-for-coding',
      maxContextSize: 262144,
    });
    expect(config.thinking).toEqual({ enabled: true });
  });

  it('throws when no models are available', () => {
    const config: PythinkerConfigShape = { providers: {} };
    expect(() =>
      applyKimiOAuthConfig(config, {
        accessToken: 'at',
        refreshToken: 'rt',
        deviceId: 'device-123',
        models: [],
        selectedModel: { id: 'x', contextLength: 1, supportsReasoning: false, supportsImageIn: false, supportsVideoIn: false },
      }),
    ).toThrow('No models available for Kimi For Coding.');
  });
});
