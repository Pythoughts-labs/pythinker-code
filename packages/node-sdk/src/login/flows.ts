import { join } from 'node:path';

import {
  applyKimiOAuthConfig,
  applyMiniMaxOAuthConfig,
  applyOpenAICodexOAuthConfig,
  applyOpenPlatformConfig,
  fetchKimiCodingModels,
  fetchOpenAICodexModels,
  fetchOpenPlatformModels,
  FileTokenStorage,
  filterModelsByPrefix,
  getOpenPlatformById,
  miniMaxCodingModels,
  minimaxCodingProviderId,
  minimaxRegionLabel,
  resolveOAuthTokenStorageName,
  KIMI_CODING_PROVIDER_ID,
  KIMI_OAUTH_PLATFORM_ID,
  MINIMAX_OAUTH_PLATFORM_ID_CN,
  MINIMAX_OAUTH_PLATFORM_ID_GLOBAL,
  OPENAI_CODEX_OAUTH_PLATFORM_ID,
  OPENAI_CODEX_PROVIDER_ID,
  OAuthAccessDeniedError,
  OpenAICodexApiError,
  OpenPlatformApiError,
  runKimiOAuthFlow,
  runMiniMaxOAuthFlow,
  runOpenAICodexOAuthFlow,
  type DeviceCodeInfo,
  type MiniMaxRegion,
  type OpenAICodexModelInfo,
  type OpenPlatformDefinition,
  type ProviderModelInfo,
  type PythinkerConfigShape,
  type TokenInfo,
} from '@pymodel/pythinker-code-oauth';

import {
  catalogProviderModels,
  DEFAULT_CATALOG_URL,
  fetchCatalog,
  importCatalogProvider,
  resolveCatalogImport,
  type CatalogProviderEntry,
} from '#/catalog';
import type { PythinkerConfig } from '#/types';

import { formatErrorMessage } from '../error-format';
import { catalogProviderIdFromPlatformValue } from './platform-values';
import type { LoginProgressSpinnerHandle, LoginUi } from './types';

export async function runLogin(ui: LoginUi): Promise<boolean> {
  const selection = await ui.promptPlatformSelection();
  if (selection === undefined) return false;
  const { platformId, catalog } = selection;

  const catalogProviderId = catalogProviderIdFromPlatformValue(platformId);
  if (catalogProviderId !== undefined) {
    return connectCatalogProvider(ui, catalogProviderId, catalog[catalogProviderId]);
  }
  if (platformId === OPENAI_CODEX_OAUTH_PLATFORM_ID) {
    return handleOpenAICodexOAuthLogin(ui);
  }
  if (platformId === KIMI_OAUTH_PLATFORM_ID) {
    return handleKimiOAuthLogin(ui);
  }
  if (platformId === MINIMAX_OAUTH_PLATFORM_ID_GLOBAL) {
    return handleMiniMaxOAuthLogin(ui, 'global');
  }
  if (platformId === MINIMAX_OAUTH_PLATFORM_ID_CN) {
    return handleMiniMaxOAuthLogin(ui, 'cn');
  }
  const platform = getOpenPlatformById(platformId);
  return platform === undefined ? false : handleOpenPlatformLogin(ui, platform);
}

async function handleOpenPlatformLogin(
  ui: LoginUi,
  platform: OpenPlatformDefinition,
): Promise<boolean> {
  const apiKey = await ui.promptApiKey(platform.name, [
    `${'base_url'.padEnd(12)}${platform.baseUrl}`,
    `${'saved to'.padEnd(12)}~/.pythinker-code/config.toml`,
  ]);
  if (apiKey === undefined) return false;

  const controller = new AbortController();
  let committing = false;
  const cancelLogin = (): void => {
    if (!committing) controller.abort();
  };
  ui.cancelInFlight = cancelLogin;
  try {
    let models: ProviderModelInfo[];
    try {
      models = filterModelsByPrefix(
        await fetchOpenPlatformModels(platform, apiKey, fetch, controller.signal),
        platform,
      );
    } catch (error) {
      if (controller.signal.aborted) return false;
      ui.showError(`Failed to verify API key: ${formatErrorMessage(error)}`);
      if (error instanceof OpenPlatformApiError && error.status === 401) {
        ui.showStatus('The provider rejected this API key.');
      }
      return false;
    }
    if (models.length === 0) {
      ui.showError('No models available for this platform.');
      return false;
    }

    const picked = await ui.promptModelSelectionForOpenPlatform(models, platform);
    if (picked === undefined) return false;
    const selectedModel = models.find((model) => model.id === picked.model.id);
    if (selectedModel === undefined) return false;

    controller.signal.throwIfAborted();
    const current = await ui.harness.getConfig({ reload: true });
    controller.signal.throwIfAborted();
    const next = cloneOAuthConfig(current);
    applyOpenPlatformConfig(next, {
      platform,
      models,
      selectedModel,
      thinking: picked.effort !== 'off',
      effort: picked.effort === 'off' || picked.effort === 'on' ? undefined : picked.effort,
      apiKey,
    });
    committing = true;
    await ui.harness.replaceConfigSections({
      providers: next.providers,
      models: next.models,
      defaultModel: next.defaultModel,
      thinking: next.thinking,
    });
    await ui.refreshConfigAfterLogin();
    ui.track('login', { provider: platform.id, method: 'api_key' });
    ui.showStatus(`Setup complete: ${platform.name} · ${selectedModel.id}`);
    return true;
  } finally {
    if (ui.cancelInFlight === cancelLogin) ui.cancelInFlight = undefined;
  }
}

export async function connectCatalogProvider(
  ui: LoginUi,
  providerId: string,
  selectedCatalogEntry?: CatalogProviderEntry,
): Promise<boolean> {
  let entry = selectedCatalogEntry;
  if (entry === undefined) {
    const controller = new AbortController();
    const cancelLogin = (): void => controller.abort();
    ui.cancelInFlight = cancelLogin;
    try {
      entry = (await fetchCatalog(DEFAULT_CATALOG_URL, { signal: controller.signal }))[providerId];
    } catch (error) {
      if (controller.signal.aborted) return false;
      ui.showError(`Failed to load model catalog: ${formatErrorMessage(error)}`);
      return false;
    } finally {
      if (ui.cancelInFlight === cancelLogin) ui.cancelInFlight = undefined;
    }
  }
  if (entry === undefined || resolveCatalogImport(entry).kind !== 'ok') {
    ui.showError(`Catalog provider "${providerId}" is not available for direct import.`);
    return false;
  }

  const apiKey = await ui.promptApiKey(entry.name ?? providerId, [
    `${'saved to'.padEnd(12)}~/.pythinker-code/config.toml`,
  ]);
  if (apiKey === undefined) return false;
  const models = catalogProviderModels(entry);
  if (models.length === 0) {
    ui.showError('No models available for this platform.');
    return false;
  }
  const picked = await ui.promptModelSelectionForCatalog(providerId, models);
  if (picked === undefined) return false;

  await importCatalogProvider(ui.harness, {
    providerId,
    entry,
    catalogUrl: DEFAULT_CATALOG_URL,
    apiKey,
    defaultModel: picked.model.id,
    thinking: picked.effort !== 'off',
    effort: picked.effort === 'off' || picked.effort === 'on' ? undefined : picked.effort,
  });
  await ui.refreshConfigAfterLogin();
  ui.track('login', { provider: providerId, method: 'api_key' });
  ui.showStatus(`Setup complete: ${entry.name ?? providerId} · ${picked.model.id}`);
  return true;
}

async function handleOpenAICodexOAuthLogin(ui: LoginUi): Promise<boolean> {
  const controller = new AbortController();
  let committing = false;
  const cancelLogin = (): void => {
    if (!committing) controller.abort();
  };
  ui.cancelInFlight = cancelLogin;
  try {
    let tokens;
    try {
      tokens = await runOpenAICodexOAuthFlow({
        signal: controller.signal,
        openBrowser: (url) => ui.openBrowser(url),
        onManualInput: (authorizeUrl) =>
          ui.promptApiKey(
            'OpenAI Codex (OAuth)',
            [
              'Automatic sign-in did not complete. Open this complete link in your browser:',
              authorizeUrl,
              'After sign-in, paste the full localhost redirect URL here.',
              'If OpenAI rejects the request again, press Esc and start /login again.',
            ],
            {
              title: 'Paste OpenAI Codex redirect URL',
              secret: false,
              emptyMessage: 'Redirect URL cannot be empty.',
            },
          ),
      });
    } catch (error) {
      if (controller.signal.aborted) return false;
      if (error instanceof OAuthAccessDeniedError) {
        ui.showError(`OpenAI Codex login cancelled: ${formatErrorMessage(error)}`);
        return false;
      }
      ui.showError(`OpenAI Codex login failed: ${formatErrorMessage(error)}`);
      return false;
    }

    let models: OpenAICodexModelInfo[];
    try {
      models = await fetchOpenAICodexModels({
        accessToken: tokens.accessToken,
        accountId: tokens.accountId,
        signal: controller.signal,
      });
    } catch (error) {
      if (controller.signal.aborted) return false;
      ui.showError(`Failed to list OpenAI Codex models: ${formatErrorMessage(error)}`);
      if (error instanceof OpenAICodexApiError && error.status === 401) {
        ui.showStatus('Sign in again if your OpenAI Codex session expired.');
      }
      return false;
    }
    if (models.length === 0) {
      ui.showError('No models available for OpenAI Codex.');
      return false;
    }

    const picked = await ui.promptModelSelectionForOpenPlatform(models, {
      id: OPENAI_CODEX_PROVIDER_ID,
      name: 'OpenAI Codex (OAuth)',
    });
    if (picked === undefined) return false;
    const selectedModel = models.find((model) => model.id === picked.model.id);
    if (selectedModel === undefined) return false;

    controller.signal.throwIfAborted();
    const current = await ui.harness.getConfig({ reload: true });
    controller.signal.throwIfAborted();
    const next = cloneConfig(current);
    applyOpenAICodexOAuthConfig(next, {
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
      accountId: tokens.accountId,
      models,
      selectedModel,
      thinking: picked.effort !== 'off',
      effort: picked.effort === 'off' || picked.effort === 'on' ? undefined : picked.effort,
    });
    committing = true;
    await ui.harness.replaceConfigSections({
      providers: next.providers,
      models: next.models,
      defaultModel: next.defaultModel,
      thinking: next.thinking,
    });
    await ui.refreshConfigAfterLogin();
    ui.track('login', { provider: OPENAI_CODEX_PROVIDER_ID, method: 'oauth' });
    ui.showStatus(`Setup complete: OpenAI Codex · ${selectedModel.id}`);
    return true;
  } finally {
    if (ui.cancelInFlight === cancelLogin) ui.cancelInFlight = undefined;
  }
}

async function handleKimiOAuthLogin(ui: LoginUi): Promise<boolean> {
  const controller = new AbortController();
  let committing = false;
  const cancelLogin = (): void => {
    if (!committing) controller.abort();
  };
  ui.cancelInFlight = cancelLogin;
  try {
    let spinner: LoginProgressSpinnerHandle | undefined;
    let tokens;
    try {
      tokens = await runKimiOAuthFlow({
        signal: controller.signal,
        onCodeReady: (info: DeviceCodeInfo) => {
          void ui.openBrowser(info.verificationUriComplete ?? info.verificationUri);
          spinner = ui.showLoginProgressSpinner(
            `Waiting for authorization — open ${info.verificationUri} and enter code ${info.userCode}`,
          );
        },
      });
    } catch (error) {
      spinner?.stop({ ok: false, label: 'Sign-in failed.' });
      if (controller.signal.aborted) return false;
      if (error instanceof OAuthAccessDeniedError) {
        ui.showError(`Kimi login cancelled: ${formatErrorMessage(error)}`);
        return false;
      }
      ui.showError(`Kimi login failed: ${formatErrorMessage(error)}`);
      return false;
    }
    spinner?.stop({ ok: true, label: 'Authorized.' });

    let models: ProviderModelInfo[];
    try {
      models = await fetchKimiCodingModels(tokens.accessToken, tokens.deviceId, fetch, controller.signal);
    } catch (error) {
      if (controller.signal.aborted) return false;
      ui.showError(`Failed to list Kimi For Coding models: ${formatErrorMessage(error)}`);
      return false;
    }
    if (models.length === 0) {
      ui.showError('No models available for Kimi For Coding.');
      return false;
    }

    try {
      const picked = await ui.promptModelSelectionForOpenPlatform(models, {
        id: KIMI_CODING_PROVIDER_ID,
        name: 'Kimi For Coding',
      });
      if (picked === undefined) return false;
      const selectedModel = models.find((model) => model.id === picked.model.id);
      if (selectedModel === undefined) return false;

      controller.signal.throwIfAborted();
      const current = await ui.harness.getConfig({ reload: true });
      controller.signal.throwIfAborted();
      const next = cloneOAuthConfig(current);
      applyKimiOAuthConfig(next, {
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
        deviceId: tokens.deviceId,
        models,
        selectedModel,
        thinking: picked.effort !== 'off',
        effort: picked.effort === 'off' || picked.effort === 'on' ? undefined : picked.effort,
      });
      committing = true;
      await persistOAuthToken(ui, KIMI_CODING_PROVIDER_ID, {
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
        expiresAt: Math.floor(tokens.expiresAtMs / 1000),
        expiresIn: Math.max(1, Math.floor((tokens.expiresAtMs - Date.now()) / 1000)),
        scope: tokens.scope,
        tokenType: tokens.tokenType,
        metadata: { provider: 'kimi', deviceId: tokens.deviceId },
      });
      await ui.harness.replaceConfigSections({
        providers: next.providers,
        models: next.models,
        defaultModel: next.defaultModel,
        thinking: next.thinking,
      });
      await ui.refreshConfigAfterLogin();
      ui.track('login', { provider: KIMI_CODING_PROVIDER_ID, method: 'oauth' });
      ui.showStatus(`Setup complete: Kimi For Coding · ${selectedModel.id}`);
      return true;
    } catch (error) {
      if (controller.signal.aborted) return false;
      throw error;
    }
  } finally {
    if (ui.cancelInFlight === cancelLogin) ui.cancelInFlight = undefined;
  }
}

async function handleMiniMaxOAuthLogin(ui: LoginUi, region: MiniMaxRegion): Promise<boolean> {
  const controller = new AbortController();
  let committing = false;
  const cancelLogin = (): void => {
    if (!committing) controller.abort();
  };
  ui.cancelInFlight = cancelLogin;
  const regionLabel = minimaxRegionLabel(region);
  try {
    let spinner: LoginProgressSpinnerHandle | undefined;
    let tokens;
    try {
      tokens = await runMiniMaxOAuthFlow(region, {
        signal: controller.signal,
        onCodeReady: (info: DeviceCodeInfo) => {
          void ui.openBrowser(info.verificationUriComplete ?? info.verificationUri);
          spinner = ui.showLoginProgressSpinner(
            `Waiting for authorization — open ${info.verificationUri} and enter code ${info.userCode}`,
          );
        },
      });
    } catch (error) {
      spinner?.stop({ ok: false, label: 'Sign-in failed.' });
      if (controller.signal.aborted) return false;
      if (error instanceof OAuthAccessDeniedError) {
        ui.showError(`${regionLabel} login cancelled: ${formatErrorMessage(error)}`);
        return false;
      }
      ui.showError(`${regionLabel} login failed: ${formatErrorMessage(error)}`);
      return false;
    }
    spinner?.stop({ ok: true, label: 'Authorized.' });

    try {
      const providerId = minimaxCodingProviderId(region);
      const models = [...miniMaxCodingModels()];
      const picked = await ui.promptModelSelectionForOpenPlatform(models, {
        id: providerId,
        name: regionLabel,
      });
      if (picked === undefined) return false;
      const selectedModel = models.find((model) => model.id === picked.model.id);
      if (selectedModel === undefined) return false;

      controller.signal.throwIfAborted();
      const current = await ui.harness.getConfig({ reload: true });
      controller.signal.throwIfAborted();
      const next = cloneOAuthConfig(current);
      applyMiniMaxOAuthConfig(next, region, {
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
        selectedModel,
        thinking: picked.effort !== 'off',
        effort: picked.effort === 'off' || picked.effort === 'on' ? undefined : picked.effort,
      });
      committing = true;
      await persistOAuthToken(ui, providerId, {
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
        expiresAt: Math.floor(tokens.expiresAtMs / 1000),
        expiresIn: Math.max(1, Math.floor((tokens.expiresAtMs - Date.now()) / 1000)),
        scope: tokens.scope,
        tokenType: tokens.tokenType,
        metadata: { provider: 'minimax', region },
      });
      await ui.harness.replaceConfigSections({
        providers: next.providers,
        models: next.models,
        defaultModel: next.defaultModel,
        thinking: next.thinking,
      });
      await ui.refreshConfigAfterLogin();
      ui.track('login', { provider: providerId, method: 'oauth' });
      ui.showStatus(`Setup complete: ${regionLabel} · ${selectedModel.id}`);
      return true;
    } catch (error) {
      if (controller.signal.aborted) return false;
      throw error;
    }
  } finally {
    if (ui.cancelInFlight === cancelLogin) ui.cancelInFlight = undefined;
  }
}

async function persistOAuthToken(ui: LoginUi, providerId: string, token: TokenInfo): Promise<void> {
  const storage = new FileTokenStorage(join(ui.harness.homeDir, 'credentials'));
  await storage.save(resolveOAuthTokenStorageName(`oauth/${providerId}`), token);
}

function cloneConfig(config: PythinkerConfig): PythinkerConfig {
  return {
    ...config,
    providers: { ...config.providers },
    models: { ...config.models },
  };
}

/** Builds the package-neutral mutable config surface without unsafe assertions. */
function cloneOAuthConfig(config: PythinkerConfig): PythinkerConfigShape {
  const providers: PythinkerConfigShape['providers'] = {};
  for (const [providerId, provider] of Object.entries(config.providers)) {
    providers[providerId] = { ...provider };
  }
  const models: NonNullable<PythinkerConfigShape['models']> = {};
  for (const [modelId, model] of Object.entries(config.models ?? {})) {
    models[modelId] = { ...model };
  }
  return {
    providers,
    models,
    defaultModel: config.defaultModel,
    thinking: config.thinking === undefined ? undefined : { ...config.thinking },
  };
}
