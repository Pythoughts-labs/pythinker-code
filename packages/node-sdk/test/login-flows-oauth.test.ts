import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import type * as OAuthModule from '@pymodel/pythinker-code-oauth';
import {
  FileTokenStorage,
  KIMI_CODING_PROVIDER_ID,
  MINIMAX_OAUTH_PLATFORM_ID_CN,
  MINIMAX_OAUTH_PLATFORM_ID_GLOBAL,
  minimaxCodingProviderId,
} from '@pymodel/pythinker-code-oauth';

import { runLogin } from '#/login/flows';
import type { LoginUi } from '#/login/types';

const oauthMockState = vi.hoisted(() => ({
  runKimiOAuthFlow: vi.fn(),
  fetchKimiCodingModels: vi.fn(),
  runMiniMaxOAuthFlow: vi.fn(),
}));

vi.mock('@pymodel/pythinker-code-oauth', async (importOriginal) => {
  const actual = await importOriginal<typeof OAuthModule>();
  return {
    ...actual,
    runKimiOAuthFlow: oauthMockState.runKimiOAuthFlow,
    fetchKimiCodingModels: oauthMockState.fetchKimiCodingModels,
    runMiniMaxOAuthFlow: oauthMockState.runMiniMaxOAuthFlow,
  };
});

const homes: string[] = [];

afterEach(() => {
  for (const home of homes.splice(0)) rmSync(home, { recursive: true, force: true });
});

function makeUi(overrides: Partial<LoginUi> = {}): LoginUi {
  const homeDir = mkdtempSync(join(tmpdir(), 'pythinker-login-oauth-'));
  homes.push(homeDir);
  return {
    harness: {
      homeDir,
      ensureConfigFile: vi.fn().mockResolvedValue(undefined),
      getConfig: vi.fn().mockResolvedValue({ providers: {}, models: {} }),
      replaceConfigSections: vi.fn().mockResolvedValue(undefined),
    },
    cancelInFlight: undefined,
    openBrowser: vi.fn(),
    showStatus: vi.fn(),
    showError: vi.fn(),
    showLoginProgressSpinner: vi.fn().mockReturnValue({ stop: vi.fn(), setLabel: vi.fn() }),
    promptPlatformSelection: vi.fn(),
    promptApiKey: vi.fn(),
    promptModelSelectionForOpenPlatform: vi.fn(),
    promptModelSelectionForCatalog: vi.fn(),
    refreshConfigAfterLogin: vi.fn().mockResolvedValue(undefined),
    track: vi.fn(),
    ...overrides,
  };
}

describe('runLogin OAuth dispatch', () => {
  it('shows the complete Codex link on browser failure without changing credentials', async () => {
    const openBrowser = vi.fn(async (_url: string) => false);
    const ui = makeUi({
      openBrowser,
      promptPlatformSelection: vi.fn().mockResolvedValue({
        platformId: 'openai-codex-oauth', catalog: {},
      }),
      promptApiKey: vi.fn().mockResolvedValue(undefined),
    });

    await expect(runLogin(ui)).resolves.toBe(false);

    const authorizeUrl = openBrowser.mock.calls[0]![0];
    expect(new URL(authorizeUrl).searchParams.has('state')).toBe(true);
    expect(new URL(authorizeUrl).searchParams.has('code_challenge')).toBe(true);
    expect(ui.promptApiKey).toHaveBeenCalledWith(
      'OpenAI Codex (OAuth)',
      expect.arrayContaining([authorizeUrl]),
      expect.objectContaining({ title: 'Paste OpenAI Codex redirect URL', secret: false }),
    );
    expect(ui.harness.replaceConfigSections).not.toHaveBeenCalled();
    expect(ui.cancelInFlight).toBeUndefined();
    expect(ui.track).not.toHaveBeenCalled();
  });

  it('routes kimi-oauth to the Kimi device flow and applies a credential reference', async () => {
    oauthMockState.runKimiOAuthFlow.mockImplementation(async ({ onCodeReady }) => {
      onCodeReady({
        deviceCode: 'device-123',
        userCode: 'ABCD-EFGH',
        verificationUri: 'https://kimi.com/code/authorize_device',
        intervalMs: 1,
        expiresAtMs: Date.now() + 60_000,
      });
      return {
        accessToken: 'at',
        refreshToken: 'rt',
        expiresAtMs: Date.now() + 900_000,
        deviceId: 'device-123',
        scope: 'kimi-code',
        tokenType: 'Bearer',
      };
    });
    oauthMockState.fetchKimiCodingModels.mockResolvedValue([
      { id: 'kimi-for-coding', contextLength: 262144, supportsReasoning: true, supportsImageIn: false, supportsVideoIn: false },
    ]);

    const ui = makeUi({
      promptPlatformSelection: vi.fn().mockResolvedValue({ platformId: 'kimi-oauth', catalog: {} }),
      promptModelSelectionForOpenPlatform: vi.fn().mockResolvedValue({
        model: { id: 'kimi-for-coding', contextLength: 262144, supportsReasoning: true, supportsImageIn: false, supportsVideoIn: false },
        effort: 'off',
      }),
    });

    const result = await runLogin(ui);

    expect(result).toBe(true);
    expect(ui.openBrowser).toHaveBeenCalledWith('https://kimi.com/code/authorize_device');
    expect(ui.harness.replaceConfigSections).toHaveBeenCalledWith(
      expect.objectContaining({
        providers: expect.objectContaining({
          [KIMI_CODING_PROVIDER_ID]: expect.objectContaining({
            oauth: { storage: 'file', key: `oauth/${KIMI_CODING_PROVIDER_ID}` },
          }),
        }),
      }),
    );
    expect(ui.track).toHaveBeenCalledWith('login', { provider: KIMI_CODING_PROVIDER_ID, method: 'oauth' });
  });

  it('routes minimax global and cn to independent OAuth credential references', async () => {
    oauthMockState.runMiniMaxOAuthFlow.mockImplementation(async (region, { onCodeReady }) => {
      onCodeReady({
        deviceCode: 'device-123',
        userCode: 'ABCD-EFGH',
        verificationUri: `https://platform.minimax.${region === 'cn' ? 'i.com' : 'io'}/oauth-authorize`,
        intervalMs: 1,
        expiresAtMs: Date.now() + 60_000,
      });
      return {
        accessToken: `at-${region}`,
        refreshToken: `rt-${region}`,
        expiresAtMs: Date.now() + 3_600_000,
        scope: 'openid profile coding_plan',
        tokenType: 'Bearer',
      };
    });

    for (const [platformId, region] of [
      [MINIMAX_OAUTH_PLATFORM_ID_GLOBAL, 'global'],
      [MINIMAX_OAUTH_PLATFORM_ID_CN, 'cn'],
    ] as const) {
      const ui = makeUi({
        promptPlatformSelection: vi.fn().mockResolvedValue({ platformId, catalog: {} }),
        promptModelSelectionForOpenPlatform: vi.fn().mockImplementation(async (models) => ({
          model: models[0],
          effort: 'off',
        })),
      });

      const result = await runLogin(ui);

      expect(result).toBe(true);
      const providerId = minimaxCodingProviderId(region);
      expect(ui.harness.replaceConfigSections).toHaveBeenCalledWith(
        expect.objectContaining({
          providers: expect.objectContaining({
            [providerId]: expect.objectContaining({
              oauth: { storage: 'file', key: `oauth/${providerId}` },
              type: 'anthropic',
            }),
          }),
        }),
      );
    }
  });

  it.each([
    'kimi-oauth',
    MINIMAX_OAUTH_PLATFORM_ID_GLOBAL,
    MINIMAX_OAUTH_PLATFORM_ID_CN,
  ] as const)('returns false when %s is cancelled during model selection', async (platformId) => {
    oauthMockState.runKimiOAuthFlow.mockResolvedValue({
      accessToken: 'at', refreshToken: 'rt', expiresAtMs: Date.now() + 900_000,
      deviceId: 'device-123', scope: 'kimi-code', tokenType: 'Bearer',
    });
    oauthMockState.fetchKimiCodingModels.mockResolvedValue([
      { id: 'kimi-for-coding', contextLength: 262144, supportsReasoning: true, supportsImageIn: false, supportsVideoIn: false },
    ]);
    oauthMockState.runMiniMaxOAuthFlow.mockResolvedValue({
      accessToken: 'at', refreshToken: 'rt', expiresAtMs: Date.now() + 900_000,
      scope: 'openid profile coding_plan', tokenType: 'Bearer',
    });

    let ui!: LoginUi;
    ui = makeUi({
      promptPlatformSelection: vi.fn().mockResolvedValue({ platformId, catalog: {} }),
      promptModelSelectionForOpenPlatform: vi.fn().mockImplementation(async (models) => {
        ui.cancelInFlight?.();
        return { model: models[0], effort: 'off' };
      }),
    });

    await expect(runLogin(ui)).resolves.toBe(false);
    expect(ui.harness.replaceConfigSections).not.toHaveBeenCalled();
    expect(ui.cancelInFlight).toBeUndefined();
  });

  it.each([
    ['kimi-oauth', KIMI_CODING_PROVIDER_ID],
    [MINIMAX_OAUTH_PLATFORM_ID_GLOBAL, minimaxCodingProviderId('global')],
    [MINIMAX_OAUTH_PLATFORM_ID_CN, minimaxCodingProviderId('cn')],
  ] as const)('completes the token and config commit when %s is cancelled during storage', async (platformId, providerId) => {
    const tokens = {
      accessToken: 'new-access', refreshToken: 'new-refresh', expiresAtMs: Date.now() + 900_000,
      deviceId: 'new-device', scope: 'coding', tokenType: 'Bearer',
    };
    oauthMockState.runKimiOAuthFlow.mockResolvedValue(tokens);
    oauthMockState.runMiniMaxOAuthFlow.mockResolvedValue(tokens);
    oauthMockState.fetchKimiCodingModels.mockResolvedValue([
      { id: 'kimi-for-coding', contextLength: 262144, supportsReasoning: true, supportsImageIn: false, supportsVideoIn: false },
    ]);
    const ui = makeUi({
      promptPlatformSelection: vi.fn().mockResolvedValue({ platformId, catalog: {} }),
      promptModelSelectionForOpenPlatform: vi.fn().mockImplementation(async (models) => ({
        model: models[0], effort: 'off',
      })),
    });
    const storage = new FileTokenStorage(join(ui.harness.homeDir, 'credentials'));
    await storage.save(providerId, {
      accessToken: 'old-access', refreshToken: 'old-refresh', expiresAt: Math.floor(Date.now() / 1000) + 900,
      expiresIn: 900, scope: 'coding', tokenType: 'Bearer',
    });
    const writeStarted = Promise.withResolvers<void>();
    const resumeWrite = Promise.withResolvers<void>();
    const save = storage.save.bind(storage);
    const saveSpy = vi.spyOn(FileTokenStorage.prototype, 'save').mockImplementationOnce(async (name, token) => {
      writeStarted.resolve();
      await resumeWrite.promise;
      await save(name, token);
    });
    try {
      const login = runLogin(ui);
      await writeStarted.promise;
      ui.cancelInFlight?.();
      resumeWrite.resolve();

      await expect(login).resolves.toBe(true);
      await expect(storage.load(providerId)).resolves.toMatchObject({
        accessToken: tokens.accessToken, refreshToken: tokens.refreshToken,
      });
      expect(ui.harness.replaceConfigSections).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
        providers: expect.objectContaining({
          [providerId]: expect.objectContaining({ oauth: { storage: 'file', key: `oauth/${providerId}` } }),
        }),
      }));
      if (providerId === KIMI_CODING_PROVIDER_ID) {
        await expect(storage.load(providerId)).resolves.toMatchObject({ metadata: { deviceId: tokens.deviceId } });
        expect(ui.harness.replaceConfigSections).toHaveBeenCalledWith(expect.objectContaining({
          providers: expect.objectContaining({
            [providerId]: expect.objectContaining({
              customHeaders: expect.objectContaining({ 'X-Msh-Device-Id': tokens.deviceId }),
            }),
          }),
        }));
      }
      expect(ui.cancelInFlight).toBeUndefined();
    } finally {
      resumeWrite.resolve();
      saveSpy.mockRestore();
    }
  });

  it('returns false and shows an error when the Kimi device flow fails', async () => {
    oauthMockState.runKimiOAuthFlow.mockRejectedValue(new Error('network down'));
    const ui = makeUi({
      promptPlatformSelection: vi.fn().mockResolvedValue({ platformId: 'kimi-oauth', catalog: {} }),
    });

    const result = await runLogin(ui);

    expect(result).toBe(false);
    expect(ui.showError).toHaveBeenCalledWith(expect.stringContaining('Kimi login failed'));
  });
});
