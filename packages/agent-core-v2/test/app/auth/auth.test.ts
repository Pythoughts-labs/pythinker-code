import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { FileTokenStorage, type TokenInfo } from '@pymodel/pythinker-code-oauth';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DisposableStore } from '#/_base/di/lifecycle';
import { createServices } from '#/_base/di/test';
import { ILogService, type ILogger } from '#/_base/log/log';
import { IAuthSummaryService, IOAuthTokenService } from '#/app/auth/auth';
import { IBootstrapService } from '#/app/bootstrap/bootstrap';
import { AuthSummaryService, OAuthTokenService } from '#/app/auth/authService';
import { AuthStatusService } from '#/app/auth/authStatusService';
import {
  SERVICES_SECTION,
  ServicesConfigSchema,
  servicesFromToml,
  servicesToToml,
  type ServicesConfig,
} from '#/app/auth/configSection';
import { WebSearchProviderService } from '#/app/auth/webSearch/webSearchService';
import { ConfigRegistry } from '#/app/config/configService';
import { IConfigService } from '#/app/config/config';
import type { IAgentIdentity } from '#/app/agentIdentity/agentIdentity';
import { IModelService, type ModelRecord } from '#/kosong/model/model';
import { IProviderService, type ProviderConfig } from '#/kosong/provider/provider';
import { ProviderService } from '#/kosong/provider/providerService';
import '#/kosong/provider/providers/pythinker/pythinker.contrib';

import { stubAgentIdentity } from '../agentIdentity/stubs';
import { stubBootstrap } from '../bootstrap/stubs';

const createdDirs: string[] = [];
const disposables = new DisposableStore();

afterEach(async () => {
  disposables.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  while (createdDirs.length > 0) {
    await rm(createdDirs.pop()!, { recursive: true, force: true });
  }
});

function token(overrides: Partial<TokenInfo> = {}): TokenInfo {
  return {
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    expiresAt: Math.floor(Date.now() / 1000) + 3600,
    scope: '',
    tokenType: 'Bearer',
    expiresIn: 3600,
    ...overrides,
  };
}

function createTokenService(homeDir: string) {
  return createServices(disposables, {
    additionalServices(reg) {
      reg.define(IOAuthTokenService, OAuthTokenService);
      reg.defineInstance(IBootstrapService, stubBootstrap(homeDir));
    },
  }).get(IOAuthTokenService);
}

describe('OAuthTokenService', () => {
  it('reads a fresh token from the explicit file credential slot', async () => {
    const homeDir = await mkdtemp(join(tmpdir(), 'pythinker-oauth-token-'));
    createdDirs.push(homeDir);
    await new FileTokenStorage(join(homeDir, 'credentials')).save('example', token());
    const service = createTokenService(homeDir);
    const ref = { storage: 'file', key: 'oauth/example' } as const;

    await expect(service.getCachedAccessToken('example-provider', ref)).resolves.toBe(
      'access-token',
    );
    await expect(service.status('example-provider', ref)).resolves.toEqual({
      loggedIn: true,
      provider: 'example-provider',
    });
    await expect(service.resolveTokenProvider('example-provider', ref)?.getAccessToken()).resolves.toBe(
      'access-token',
    );
  });

  it('rejects expired tokens and unsupported storage backends', async () => {
    const homeDir = await mkdtemp(join(tmpdir(), 'pythinker-oauth-token-'));
    createdDirs.push(homeDir);
    await new FileTokenStorage(join(homeDir, 'credentials')).save(
      'expired',
      token({ expiresAt: Math.floor(Date.now() / 1000) - 1 }),
    );
    const service = createTokenService(homeDir);
    const expired = { storage: 'file', key: 'oauth/expired' } as const;

    await expect(service.getCachedAccessToken('example-provider', expired)).resolves.toBeUndefined();
    await expect(
      service.resolveTokenProvider('example-provider', expired)?.getAccessToken(),
    ).rejects.toMatchObject({ code: 'auth.login_required' });
    expect(
      service.resolveTokenProvider('example-provider', {
        storage: 'keyring',
        key: 'example',
      }),
    ).toBeUndefined();
  });
});

describe('AuthSummaryService', () => {
  const oauthRef = { storage: 'file', key: 'oauth/example' } as const;
  const providers: Record<string, ProviderConfig> = {
    oauth: { type: 'pythinker', oauth: oauthRef },
    api: { type: 'openai', apiKey: 'sk-example' },
  };
  const models: Record<string, ModelRecord> = {
    'oauth/model': { provider: 'oauth', model: 'model', maxContextSize: 4096 },
    'api/model': { provider: 'api', model: 'model', maxContextSize: 4096 },
  };

  function create(
    getCachedAccessToken = vi.fn<IOAuthTokenService['getCachedAccessToken']>().mockResolvedValue(
      undefined,
    ),
  ): { service: AuthSummaryService; getCachedAccessToken: typeof getCachedAccessToken } {
    const providerService = {
      list: () => providers,
      get: (name: string) => providers[name],
      getDefaultProvider: () => undefined,
    } as unknown as IProviderService;
    const modelService = {
      list: () => models,
      getDefaultModel: () => 'oauth/model',
    } as unknown as IModelService;
    const config = { reload: async () => {} } as unknown as IConfigService;
    const oauth = {
      _serviceBrand: undefined,
      status: async (provider: string, ref: typeof oauthRef) => ({
        loggedIn: (await getCachedAccessToken(provider, ref)) !== undefined,
        provider,
      }),
      getCachedAccessToken,
      resolveTokenProvider: () => undefined,
    } satisfies IOAuthTokenService;
    const log = { warn: vi.fn() } as unknown as ILogger;
    return {
      service: new AuthSummaryService(providerService, modelService, config, oauth, log),
      getCachedAccessToken,
    };
  }

  it('logs a refresh error type without exposing secrets and retains the missing-token contract', async () => {
    const warn = vi.fn();
    const services = createServices(disposables, {
      additionalServices(reg) {
        reg.define(IAuthSummaryService, AuthSummaryService);
        reg.definePartialInstance(IProviderService, {
          list: () => providers, get: (name) => providers[name], getDefaultProvider: () => undefined,
        });
        reg.definePartialInstance(IModelService, { list: () => models });
        reg.definePartialInstance(IConfigService, { reload: async () => {} });
        reg.definePartialInstance(IOAuthTokenService, {
          getCachedAccessToken: async () => undefined,
          resolveTokenProvider: () => ({
            getAccessToken: async () => { throw new TypeError('test-secret-access-token'); },
          }),
        });
        reg.definePartialInstance(ILogService, { warn });
      },
    });

    await expect(services.get(IAuthSummaryService).ensureReady('oauth/model')).rejects.toMatchObject({
      code: 'auth.token_missing', details: { provider_id: 'oauth' },
    });
    expect(warn).toHaveBeenCalledExactlyOnceWith('OAuth credential refresh failed', {
      provider: 'oauth', error_type: 'TypeError',
    });
    expect(JSON.stringify(warn.mock.calls)).not.toContain('test-secret-access-token');
  });

  it('summarizes only providers with explicit OAuth credentials', async () => {
    const getCachedAccessToken = vi
      .fn<IOAuthTokenService['getCachedAccessToken']>()
      .mockResolvedValue('access-token');
    const { service } = create(getCachedAccessToken);

    await expect(service.summarize()).resolves.toEqual([
      { loggedIn: true, provider: 'oauth' },
    ]);
    expect(getCachedAccessToken).toHaveBeenCalledWith('oauth', oauthRef);
  });

  it('accepts API keys and rejects missing stored OAuth tokens', async () => {
    const { service, getCachedAccessToken } = create();

    await expect(service.ensureReady('api/model')).resolves.toBeUndefined();
    await expect(service.ensureReady('oauth/model')).rejects.toMatchObject({
      code: 'auth.token_missing',
      details: { provider_id: 'oauth' },
    });
    expect(getCachedAccessToken).toHaveBeenCalledWith('oauth', oauthRef);
  });

  it('resolves a providerless OAuth model when the default provider is blank', async () => {
    const providerService = new ProviderService();
    providerService.loadAll({}, '   ');
    const modelService = {
      list: () => ({
        flat: {
          protocol: 'openai',
          model: 'model',
          baseUrl: 'https://flat.example.test/v1',
          oauth: oauthRef,
          maxContextSize: 4096,
        },
      }),
      getDefaultModel: () => 'flat',
    } as unknown as IModelService;
    const getCachedAccessToken = vi
      .fn<IOAuthTokenService['getCachedAccessToken']>()
      .mockResolvedValue('access-token');
    const oauth = {
      _serviceBrand: undefined,
      status: vi.fn(),
      getCachedAccessToken,
      resolveTokenProvider: () => undefined,
    } as unknown as IOAuthTokenService;
    const config = { reload: async () => {} } as unknown as IConfigService;
    const log = { warn: vi.fn() } as unknown as ILogger;
    const service = new AuthSummaryService(providerService, modelService, config, oauth, log);

    await expect(service.ensureReady('flat')).resolves.toBeUndefined();
    expect(getCachedAccessToken).toHaveBeenCalledWith('flat.example.test', oauthRef);
  });
});

describe('AuthStatusService', () => {
  it('reports whether the default model can resolve', async () => {
    const providerService = {
      ready: Promise.resolve(),
      list: () => ({ api: { type: 'openai', apiKey: 'sk-example' } }),
      getDefaultProvider: () => undefined,
    } as unknown as IProviderService;
    const modelService = {
      ready: Promise.resolve(),
      list: () => ({
        'api/model': { provider: 'api', model: 'model', maxContextSize: 4096 },
      }),
      getDefaultModel: () => 'api/model',
    } as unknown as IModelService;

    await expect(new AuthStatusService(providerService, modelService).get()).resolves.toEqual({
      ready: true,
      models_ready: true,
      providers_count: 1,
      default_model: 'api/model',
    });
  });
});

describe('services config section', () => {
  it('validates and round-trips explicit service credentials', () => {
    const registry = new ConfigRegistry();
    const value = {
      pymodelSearch: {
        baseUrl: 'https://search.example.test',
        oauth: { storage: 'file', key: 'oauth/search' },
      },
      pymodelFetch: { baseUrl: 'https://fetch.example.test', apiKey: 'fetch-key' },
    };

    expect(registry.getSection(SERVICES_SECTION)).toBeDefined();
    expect(ServicesConfigSchema.parse(value)).toEqual(value);
    const snake = servicesToToml(value, {});
    expect(servicesFromToml(snake)).toEqual(value);
  });
});

describe('WebSearchProviderService', () => {
  it('uses the service credential slot named by config', async () => {
    const resolveTokenProvider = vi.fn(() => ({ getAccessToken: async () => 'stored-token' }));
    const oauth = {
      _serviceBrand: undefined,
      status: vi.fn(),
      getCachedAccessToken: vi.fn(),
      resolveTokenProvider,
    } as unknown as IOAuthTokenService;
    const services: ServicesConfig = {
      pymodelSearch: {
        baseUrl: 'https://search.example.test',
        oauth: { storage: 'file', key: 'oauth/search' },
      },
    };
    const config = {
      get: (section: string) => (section === SERVICES_SECTION ? services : undefined),
    } as unknown as IConfigService;
    const identity = stubAgentIdentity({
      hostRequestHeaders: { 'User-Agent': 'pythinker-test/1.0' },
    }) as IAgentIdentity;
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ search_results: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const provider = new WebSearchProviderService(oauth, config, identity).getWebSearchProvider();
    await provider?.search('query');

    expect(resolveTokenProvider).toHaveBeenCalledWith('services:pymodel-search', {
      storage: 'file',
      key: 'oauth/search',
    });
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>)['Authorization']).toBe('Bearer stored-token');
  });
});
