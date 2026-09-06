import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { FileTokenStorage, type TokenInfo } from '@pymodel/pythinker-code-oauth';
import { DisposableStore } from '@pymodel/agent-core-v2/_base/di/lifecycle';
import { createServices } from '@pymodel/agent-core-v2/_base/di/test';
import { IBootstrapService } from '@pymodel/agent-core-v2/app/bootstrap/bootstrap';
import { IOAuthTokenService } from '@pymodel/agent-core-v2/app/auth/auth';
import { OAuthTokenService } from '@pymodel/agent-core-v2/app/auth/authService';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { OAuthTokenReader } from '../../agent-core/src/services/auth/oauthToken';

import { ErrorCodes, PythinkerError, type PythinkerConfig, type Logger } from '#/index';

import { ProviderManager } from '../../agent-core/src/session/provider-manager';

function oauthConfig(): PythinkerConfig {
  return {
    providers: {
      'oauth-example': {
        type: 'openai',
        baseUrl: 'https://api.example.test/v1',
        apiKey: '',
        oauth: { storage: 'file', key: 'oauth/example' },
      },
    },
    models: {
      'oauth-example/model': {
        provider: 'oauth-example',
        model: 'example-model',
        maxContextSize: 262144,
      },
    },
    defaultModel: 'oauth-example/model',
  };
}

async function resolveRuntimeProviderWithOAuth(options: {
  readonly config: PythinkerConfig;
  readonly resolveOAuthTokenProvider?: import('../../agent-core/src/session/provider-manager').OAuthTokenProviderResolver;
  readonly log?: Logger;
}) {
  const manager = new ProviderManager({
    config: options.config,
    resolveOAuthTokenProvider: options.resolveOAuthTokenProvider,
  });
  const model = options.config.defaultModel;
  if (model === undefined) {
    throw new PythinkerError(ErrorCodes.CONFIG_INVALID, 'No model is selected.');
  }
  const { providerName, provider } = manager.resolveProviderConfig(model);

  const providerConfig = options.config.providers[providerName];
  if (providerConfig?.oauth !== undefined && (providerConfig.apiKey ?? '').length > 0) {
    throw new PythinkerError(
      ErrorCodes.CONFIG_INVALID,
      `Provider "${providerName}" has both apiKey and oauth set in config.toml — they are mutually exclusive. Remove one.`,
    );
  }

  const oauthRef = providerConfig?.oauth;
  const tokenProvider = options.resolveOAuthTokenProvider?.(providerName, oauthRef);

  if (tokenProvider === undefined) {
    throw new PythinkerError(
      ErrorCodes.AUTH_LOGIN_REQUIRED,
      `OAuth provider "${providerName}" requires login before it can be used.`,
    );
  }

  // Replicate the old API's eager token fetch during resolution so
  // test mocks see the expected call sequence.
  try {
    await tokenProvider.getAccessToken(undefined);
  } catch (error) {
    if (
      !(error instanceof PythinkerError && error.code === ErrorCodes.AUTH_LOGIN_REQUIRED)
    ) {
      options.log?.warn('oauth token fetch failed', { providerName, error });
    }
    throw new PythinkerError(
      ErrorCodes.AUTH_LOGIN_REQUIRED,
      `OAuth provider "${providerName}" requires login before it can be used.`,
      { cause: error },
    );
  }

  return {
    providerName,
    provider,
    resolveAuth: async (opts?: { forceRefresh?: boolean }) => {
      try {
        const apiKey = await tokenProvider.getAccessToken(
          opts?.forceRefresh ? { force: true } : undefined,
        );
        if (apiKey.trim().length === 0) {
          throw new PythinkerError(
            ErrorCodes.AUTH_LOGIN_REQUIRED,
            `OAuth provider "${providerName}" requires login before it can be used.`,
          );
        }
        return { apiKey };
      } catch (error) {
        if (
          !(error instanceof PythinkerError && error.code === ErrorCodes.AUTH_LOGIN_REQUIRED)
        ) {
          options.log?.warn('oauth token fetch failed', { providerName, error });
        }
        throw new PythinkerError(
          ErrorCodes.AUTH_LOGIN_REQUIRED,
          `OAuth provider "${providerName}" requires login before it can be used.`,
          { cause: error },
        );
      }
    },
  };
}

describe('resolveRuntimeProviderWithOAuth', () => {
  it('returns request-scoped OAuth auth without storing the initial access token in provider config', async () => {
    const tokens = ['initial-oauth-token', 'rotated-oauth-token', 'force-refreshed-oauth-token'];
    const getAccessToken = vi.fn().mockImplementation(async () => {
      const token = tokens.shift();
      if (token === undefined) throw new Error('unexpected token request');
      return token;
    });

    const resolved = await resolveRuntimeProviderWithOAuth({
      config: oauthConfig(),
      resolveOAuthTokenProvider: (_providerName, oauthRef) => {
        expect(oauthRef).toEqual({ storage: 'file', key: 'oauth/example' });
        return { getAccessToken };
      },
    });

    expect(resolved.providerName).toBe('oauth-example');
    expect(resolved.provider).toMatchObject({
      type: 'openai',
      model: 'example-model',
      baseUrl: 'https://api.example.test/v1',
    });
    expect(resolved.provider.apiKey).toBeUndefined();
    await expect(resolved.resolveAuth?.()).resolves.toEqual({ apiKey: 'rotated-oauth-token' });
    await expect(resolved.resolveAuth?.({ forceRefresh: true })).resolves.toEqual({
      apiKey: 'force-refreshed-oauth-token',
    });
    expect(getAccessToken.mock.calls).toEqual([[undefined], [undefined], [{ force: true }]]);
  });

  it('throws a clear login-required error when no token provider exists', async () => {
    await expect(
      resolveRuntimeProviderWithOAuth({
        config: oauthConfig(),
      }),
    ).rejects.toThrow(/requires login/);
  });

  it('rejects providers that set both apiKey and oauth on the same config', async () => {
    const conflicting: PythinkerConfig = {
      ...oauthConfig(),
      providers: {
        'oauth-example': {
          type: 'openai',
          baseUrl: 'https://api.example.test/v1',
          apiKey: 'static-key',
          oauth: { storage: 'file', key: 'oauth/example' },
        },
      },
    };

    await expect(
      resolveRuntimeProviderWithOAuth({
        config: conflicting,
        resolveOAuthTokenProvider: () => ({
          getAccessToken: vi.fn().mockResolvedValue('unused'),
        }),
      }),
    ).rejects.toThrow(/mutually exclusive/);
  });

  it('wraps token provider failures as login-required errors', async () => {
    await expect(
      resolveRuntimeProviderWithOAuth({
        config: oauthConfig(),
        resolveOAuthTokenProvider: () => ({
          getAccessToken: vi.fn().mockRejectedValue(new Error('missing token')),
        }),
      }),
    ).rejects.toMatchObject({
      name: 'PythinkerError',
      code: 'auth.login_required',
    });
  });

  it('logs token provider failures except plain login-required errors', async () => {
    const log = testLogger();
    await expect(
      resolveRuntimeProviderWithOAuth({
        config: oauthConfig(),
        log,
        resolveOAuthTokenProvider: () => ({
          getAccessToken: vi.fn().mockRejectedValue(new Error('token endpoint down')),
        }),
      }),
    ).rejects.toMatchObject({ code: 'auth.login_required' });
    expect(log.warn).toHaveBeenCalledWith(
      'oauth token fetch failed',
      expect.objectContaining({
        providerName: 'oauth-example',
        error: expect.any(Error),
      }),
    );

    vi.clearAllMocks();
    await expect(
      resolveRuntimeProviderWithOAuth({
        config: oauthConfig(),
        log,
        resolveOAuthTokenProvider: () => ({
          getAccessToken: vi.fn().mockRejectedValue(
            new PythinkerError(ErrorCodes.AUTH_LOGIN_REQUIRED, 'not logged in'),
          ),
        }),
      }),
    ).rejects.toMatchObject({ code: 'auth.login_required' });
    expect(log.warn).not.toHaveBeenCalled();
  });
});

function testLogger(): Logger {
  const logger: Logger = {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
    createChild: () => logger,
  };
  return logger;
}

const tokenHomes: string[] = [];
const tokenDisposables = new DisposableStore();

afterEach(async () => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  tokenDisposables.clear();
  await Promise.all(tokenHomes.splice(0).map((home) => rm(home, { recursive: true, force: true })));
});

async function tokenFixture(engine: 'v1' | 'v2') {
  const homeDir = await mkdtemp(join(tmpdir(), 'pythinker-refresh-'));
  tokenHomes.push(homeDir);
  const storage = new FileTokenStorage(join(homeDir, 'credentials'));
  const ref = { storage: 'file', key: 'oauth/example' } as const;
  const provider = engine === 'v1'
    ? new OAuthTokenReader(homeDir).resolveOAuthTokenProvider('example', ref)
    : createServices(tokenDisposables, {
      additionalServices(reg) {
        reg.define(IOAuthTokenService, OAuthTokenService);
        reg.definePartialInstance(IBootstrapService, { homeDir, scope: (name) => name });
      },
    }).get(IOAuthTokenService).resolveTokenProvider('example', ref);
  if (provider === undefined) throw new Error('File OAuth provider missing');
  const initial: TokenInfo = {
    accessToken: 'initial-at', refreshToken: 'initial-rt',
    expiresAt: Math.floor(Date.now() / 1000) + 60, expiresIn: 60, scope: '', tokenType: 'Bearer',
    metadata: { provider: 'kimi', deviceId: 'device-123' },
  };
  await storage.save('example', initial);
  return { storage, provider, initial };
}

describe.each(['v1', 'v2'] as const)('%s stored OAuth refresh', (engine) => {
  it.each(['kimi', 'minimax'] as const)('shares and persists %s refreshes, including forced refresh', async (kind) => {
    const { storage, provider, initial } = await tokenFixture(engine);
    if (kind === 'minimax') {
      await storage.save('example', { ...initial, metadata: { provider: 'minimax', region: 'global' } });
    }
    let calls = 0;
    const fetchMock = vi.fn<typeof fetch>(async (_input, init) => {
      const body = init?.body;
      if (!(body instanceof URLSearchParams)) throw new Error('Expected an OAuth form body');
      expect(body.get('refresh_token')).toBe(calls === 0 ? 'initial-rt' : 'rotated-rt');
      calls += 1;
      return new Response(JSON.stringify({
        status: 'success', access_token: `refreshed-at-${calls}`, refresh_token: 'rotated-rt',
        expires_in: 900, expired_in: Date.now() + 900_000,
      }));
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(Promise.all([provider.getAccessToken(), provider.getAccessToken()]))
      .resolves.toEqual(['refreshed-at-1', 'refreshed-at-1']);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await expect(provider.getAccessToken()).resolves.toBe('refreshed-at-1');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await expect(provider.getAccessToken({ force: true })).resolves.toBe('refreshed-at-2');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await expect(storage.load('example')).resolves.toMatchObject({
      accessToken: 'refreshed-at-2', refreshToken: 'rotated-rt', metadata: { provider: kind },
    });
  });

  it.each(['replace', 'remove'] as const)('does not overwrite a credential %s during refresh', async (change) => {
    const { storage, provider, initial } = await tokenFixture(engine);
    const winner = { ...initial, accessToken: 'new-login-at', refreshToken: 'new-login-rt' };
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => {
      if (change === 'replace') await storage.save('example', winner);
      else await storage.remove('example');
      return new Response(JSON.stringify({ access_token: 'late-at', refresh_token: 'late-rt', expires_in: 900 }));
    }));

    await expect(provider.getAccessToken()).rejects.toThrow('credential changed');
    await expect(storage.load('example')).resolves.toEqual(change === 'replace' ? winner : undefined);
  });

  it('does not fall back to a token that expired while refresh failed', async () => {
    const { storage, provider, initial } = await tokenFixture(engine);
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => {
      vi.spyOn(Date, 'now').mockReturnValue(initial.expiresAt * 1000);
      throw new Error('token endpoint unavailable');
    }));

    await expect(provider.getAccessToken()).rejects.toThrow('token endpoint unavailable');
    await expect(storage.load('example')).resolves.toEqual(initial);
  });
});
