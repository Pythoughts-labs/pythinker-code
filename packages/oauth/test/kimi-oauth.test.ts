import { describe, expect, it, vi } from 'vitest';

import {
  applyKimiOAuthConfig,
  fetchKimiCodingModels,
  KIMI_CODING_BASE_URL,
  KIMI_CODING_PROVIDER_ID,
  runKimiOAuthFlow,
} from '../src/kimi-oauth';
import type { PythinkerConfigShape } from '../src/provider-config';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('runKimiOAuthFlow', () => {
  it('requests a device code, notifies the caller, and exchanges it for tokens', async () => {
    let tokenCall = 0;
    const fetchMock = vi.fn(async (input: string | URL) => {
      const url = String(input);
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
      return jsonResponse({ access_token: 'at', refresh_token: 'rt', expires_in: 900 });
    });

    const onCodeReady = vi.fn();
    const bundle = await runKimiOAuthFlow({ onCodeReady, fetchImpl: fetchMock as unknown as typeof fetch });

    expect(onCodeReady).toHaveBeenCalledWith(expect.objectContaining({ userCode: 'ABCD-EFGH' }));
    expect(bundle.accessToken).toBe('at');
    expect(bundle.refreshToken).toBe('rt');
    expect(bundle.deviceId).toMatch(/^[0-9a-f-]{36}$/);

    expect(fetchMock).toHaveBeenCalledWith(
      'https://auth.kimi.com/api/oauth/device_authorization',
      expect.objectContaining({
        headers: expect.objectContaining({ 'X-Msh-Device-Id': bundle.deviceId }),
      }),
    );
  });

  it('throws when the token exchange response is missing an access_token', async () => {
    const fetchMock = vi.fn(async (input: string | URL) => {
      if (String(input).endsWith('device_authorization')) {
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
      runKimiOAuthFlow({ onCodeReady: () => {}, fetchImpl: fetchMock as unknown as typeof fetch }),
    ).rejects.toThrow('missing access_token');
  });
});

describe('fetchKimiCodingModels', () => {
  it('fetches models from the Kimi coding base URL with device headers', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        data: [
          { id: 'kimi-for-coding', context_length: 262144, supports_reasoning: true },
        ],
      }),
    );

    const models = await fetchKimiCodingModels(
      'access-token',
      'device-123',
      fetchMock as unknown as typeof fetch,
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
  it('writes a pythinker-wire provider with custom headers and model aliases', () => {
    const config: PythinkerConfigShape = { providers: {} };
    const models = [
      { id: 'kimi-for-coding', contextLength: 262144, supportsReasoning: true, supportsImageIn: true, supportsVideoIn: false },
    ];

    const result = applyKimiOAuthConfig(config, {
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      deviceId: 'device-123',
      models,
      selectedModel: models[0]!,
      thinking: true,
    });

    expect(result.defaultModel).toBe(`${KIMI_CODING_PROVIDER_ID}/kimi-for-coding`);
    expect(config.providers[KIMI_CODING_PROVIDER_ID]).toMatchObject({
      type: 'pythinker',
      baseUrl: KIMI_CODING_BASE_URL,
      apiKey: 'access-token',
      customHeaders: expect.objectContaining({ 'X-Msh-Device-Id': 'device-123' }),
      source: { auth: 'kimi-oauth', refreshToken: 'refresh-token', deviceId: 'device-123' },
    });
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
