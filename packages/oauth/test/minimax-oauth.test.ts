import { describe, expect, it, vi } from 'vitest';

import {
  applyMiniMaxOAuthConfig,
  miniMaxCodingModels,
  minimaxCodingProviderId,
  minimaxRegionLabel,
  refreshMiniMaxOAuthToken,
  runMiniMaxOAuthFlow,
} from '../src/minimax-oauth';
import type { PythinkerConfigShape } from '../src/provider-config';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function requestBody(init?: RequestInit): URLSearchParams {
  return new URLSearchParams(String(init?.body ?? ''));
}

describe('runMiniMaxOAuthFlow', () => {
  it('uses the official PKCE device flow on the global account host', async () => {
    const requestedUrls: string[] = [];
    let tokenCall = 0;
    const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.endsWith('/oauth2/device/code')) {
        const body = requestBody(init);
        expect(body.get('client_id')).toBe('659cf4c1-615c-45f6-a5f6-4bf15eb476e5');
        expect(body.get('code_challenge_method')).toBe('S256');
        expect(body.get('code_challenge')).toBeTruthy();
        return jsonResponse({
          user_code: 'ABCD-EFGH',
          verification_uri: 'https://platform.minimax.io/oauth-authorize',
          expired_in: Date.now() + 60_000,
          interval: 1,
          state: body.get('state'),
        });
      }
      const body = requestBody(init);
      expect(body.get('grant_type')).toBe('urn:ietf:params:oauth:grant-type:device_code');
      expect(body.get('user_code')).toBe('ABCD-EFGH');
      expect(body.get('code_verifier')).toBeTruthy();
      tokenCall += 1;
      if (tokenCall < 2) return jsonResponse({ status: 'pending' });
      return jsonResponse({
        status: 'success',
        access_token: 'at',
        refresh_token: 'rt',
        expired_in: Date.now() + 3_600_000,
      });
    });

    const bundle = await runMiniMaxOAuthFlow('global', {
      onCodeReady: vi.fn(),
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(bundle.accessToken).toBe('at');
    expect(bundle.refreshToken).toBe('rt');
    expect(requestedUrls[0]).toBe('https://account.minimax.io/oauth2/device/code');
    expect(requestedUrls[1]).toBe('https://account.minimax.io/oauth2/token');
  });

  it('hits the China account host for the cn region', async () => {
    const requestedUrls: string[] = [];
    const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.endsWith('/oauth2/device/code')) {
        const body = requestBody(init);
        return jsonResponse({
          user_code: 'ABCD-EFGH',
          verification_uri: 'https://platform.minimaxi.com/oauth-authorize',
          expired_in: Date.now() + 60_000,
          interval: 1,
          state: body.get('state'),
        });
      }
      return jsonResponse({
        status: 'success',
        access_token: 'at',
        refresh_token: 'rt',
        expired_in: Date.now() + 3_600_000,
      });
    });

    await runMiniMaxOAuthFlow('cn', { onCodeReady: () => {}, fetchImpl: fetchMock as unknown as typeof fetch });

    expect(requestedUrls[0]).toBe('https://account.minimaxi.com/oauth2/device/code');
    expect(requestedUrls[1]).toBe('https://account.minimaxi.com/oauth2/token');
  });

  it('rejects a state mismatch before opening the browser', async () => {
    const onCodeReady = vi.fn();
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        user_code: 'ABCD-EFGH',
        verification_uri: 'https://platform.minimax.io/oauth-authorize',
        expired_in: Date.now() + 60_000,
        interval: 1,
        state: 'wrong-state',
      }),
    );

    await expect(
      runMiniMaxOAuthFlow('global', { onCodeReady, fetchImpl: fetchMock as unknown as typeof fetch }),
    ).rejects.toThrow('state mismatch');
    expect(onCodeReady).not.toHaveBeenCalled();
  });
});

describe('refreshMiniMaxOAuthToken', () => {
  it('uses refresh_token grant and preserves a non-rotated refresh token', async () => {
    const fetchMock = vi.fn(async (_input: string | URL, init?: RequestInit) => {
      const body = requestBody(init);
      expect(body.get('grant_type')).toBe('refresh_token');
      expect(body.get('refresh_token')).toBe('old-rt');
      return jsonResponse({ status: 'success', access_token: 'new-at', expired_in: Date.now() + 3_600_000 });
    });
    const token = await refreshMiniMaxOAuthToken('global', 'old-rt', fetchMock as unknown as typeof fetch);
    expect(token.accessToken).toBe('new-at');
    expect(token.refreshToken).toBe('old-rt');
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
  it('writes an OAuth credential reference without embedding bearer tokens', () => {
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
      oauth: { storage: 'file', key: `oauth/${providerKey}` },
      source: { auth: 'minimax-oauth', region: 'global' },
    });
    expect(config.providers[providerKey]).not.toHaveProperty('apiKey');
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

    expect(config.providers['minimax-coding-oauth-global']).toMatchObject({
      oauth: { storage: 'file', key: 'oauth/minimax-coding-oauth-global' },
    });
    expect(config.providers['minimax-coding-oauth-cn']).toMatchObject({
      oauth: { storage: 'file', key: 'oauth/minimax-coding-oauth-cn' },
      baseUrl: 'https://api.minimaxi.com/anthropic',
    });
  });
});
