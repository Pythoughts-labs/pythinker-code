import { describe, expect, it, vi } from 'vitest';

import {
  applyMiniMaxOAuthConfig,
  miniMaxCodingModels,
  minimaxCodingProviderId,
  minimaxRegionLabel,
  runMiniMaxOAuthFlow,
} from '../src/minimax-oauth';
import type { PythinkerConfigShape } from '../src/provider-config';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('runMiniMaxOAuthFlow', () => {
  it('hits the global account host by default', async () => {
    const requestedUrls: string[] = [];
    let tokenCall = 0;
    const fetchMock = vi.fn(async (input: string | URL) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.endsWith('/oauth2/device/code')) {
        return jsonResponse({
          device_code: 'device-123',
          user_code: 'ABCD-EFGH',
          verification_uri: 'https://platform.minimax.io/oauth-authorize',
          interval: 1,
        });
      }
      tokenCall += 1;
      if (tokenCall < 2) return jsonResponse({ error: 'authorization_pending' }, 400);
      return jsonResponse({ access_token: 'at', refresh_token: 'rt', expires_in: 3600 });
    });

    const onCodeReady = vi.fn();
    const bundle = await runMiniMaxOAuthFlow('global', {
      onCodeReady,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(bundle.accessToken).toBe('at');
    expect(requestedUrls[0]).toBe('https://account.minimax.io/oauth2/device/code');
    expect(requestedUrls[1]).toBe('https://account.minimax.io/oauth2/token');
  });

  it('hits the China account host for the cn region', async () => {
    const requestedUrls: string[] = [];
    const fetchMock = vi.fn(async (input: string | URL) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.endsWith('/oauth2/device/code')) {
        return jsonResponse({
          device_code: 'device-123',
          user_code: 'ABCD-EFGH',
          verification_uri: 'https://platform.minimaxi.com/oauth-authorize',
          interval: 1,
        });
      }
      return jsonResponse({ access_token: 'at', refresh_token: 'rt' });
    });

    await runMiniMaxOAuthFlow('cn', { onCodeReady: () => {}, fetchImpl: fetchMock as unknown as typeof fetch });

    expect(requestedUrls[0]).toBe('https://account.minimaxi.com/oauth2/device/code');
    expect(requestedUrls[1]).toBe('https://account.minimaxi.com/oauth2/token');
  });

  it('throws when the token exchange is missing a refresh_token', async () => {
    const fetchMock = vi.fn(async (input: string | URL) => {
      if (String(input).endsWith('/oauth2/device/code')) {
        return jsonResponse({
          device_code: 'device-123',
          user_code: 'ABCD-EFGH',
          verification_uri: 'https://platform.minimax.io/oauth-authorize',
          interval: 1,
        });
      }
      return jsonResponse({ access_token: 'at' });
    });

    await expect(
      runMiniMaxOAuthFlow('global', { onCodeReady: () => {}, fetchImpl: fetchMock as unknown as typeof fetch }),
    ).rejects.toThrow('missing refresh_token');
  });
});

describe('minimaxRegionLabel / minimaxCodingProviderId', () => {
  it('returns distinct labels and provider ids per region', () => {
    expect(minimaxRegionLabel('global')).toBe('MiniMax (OAuth · Global)');
    expect(minimaxRegionLabel('cn')).toBe('MiniMax (OAuth · China)');
    expect(minimaxCodingProviderId('global')).toBe('minimax-coding-oauth-global');
    expect(minimaxCodingProviderId('cn')).toBe('minimax-coding-oauth-cn');
  });
});

describe('applyMiniMaxOAuthConfig', () => {
  it('writes an anthropic-wire provider scoped to the region', () => {
    const config: PythinkerConfigShape = { providers: {} };
    const [model] = miniMaxCodingModels();

    const result = applyMiniMaxOAuthConfig(config, 'global', {
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      selectedModel: model!,
      thinking: true,
    });

    const providerKey = minimaxCodingProviderId('global');
    expect(result.defaultModel).toBe(`${providerKey}/${model!.id}`);
    expect(config.providers[providerKey]).toMatchObject({
      type: 'anthropic',
      baseUrl: 'https://api.minimax.io/anthropic',
      apiKey: 'access-token',
      source: { auth: 'minimax-oauth', region: 'global', refreshToken: 'refresh-token' },
    });
    expect(config.models?.[`${providerKey}/${model!.id}`]).toMatchObject({
      provider: providerKey,
      model: model!.id,
    });
    expect(config.thinking).toEqual({ enabled: true });
  });

  it('keeps global and china providers independent', () => {
    const config: PythinkerConfigShape = { providers: {} };
    const [model] = miniMaxCodingModels();

    applyMiniMaxOAuthConfig(config, 'global', { accessToken: 'g-at', refreshToken: 'g-rt', selectedModel: model! });
    applyMiniMaxOAuthConfig(config, 'cn', { accessToken: 'c-at', refreshToken: 'c-rt', selectedModel: model! });

    expect(config.providers['minimax-coding-oauth-global']).toMatchObject({ apiKey: 'g-at' });
    expect(config.providers['minimax-coding-oauth-cn']).toMatchObject({
      apiKey: 'c-at',
      baseUrl: 'https://api.minimaxi.com/anthropic',
    });
  });
});
