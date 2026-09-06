import {
  buildPlatformOptions,
  catalogModelToAlias,
  catalogProviderIdFromPlatformValue,
  isOAuthPlatformId,
  DEFAULT_CATALOG_URL,
  resolveCatalogImport,
  type Catalog,
  type CatalogModel,
  type ModelAlias,
  type PlatformSelection,
  type ThinkingEffort,
} from '@pymodel/pythinker-code-sdk';
import {
  KIMI_CODING_PROVIDER_ID,
  KIMI_OAUTH_PLATFORM_ID,
  MINIMAX_OAUTH_PLATFORM_ID_CN,
  MINIMAX_OAUTH_PLATFORM_ID_GLOBAL,
  minimaxCodingProviderId,
  OPENAI_CODEX_OAUTH_PLATFORM_ID,
  capabilitiesForModel,
  OPENAI_CODEX_PROVIDER_ID,
  type OpenAICodexModelInfo,
  type OpenPlatformDefinition,
  type ProviderModelInfo,
} from '@pymodel/pythinker-code-oauth';

import {
  ApiKeyInputDialogComponent,
  type ApiKeyInputDialogOptions,
  type ApiKeyInputResult,
} from '../components/dialogs/api-key-input-dialog';
import { ChoicePickerComponent, type ChoiceOption } from '../components/dialogs/choice-picker';
import { ModelSelectorComponent } from '../components/dialogs/model-selector';
import {
  AuthenticationMethodSelectorComponent,
  PlatformSelectorComponent,
  type AuthenticationMethod,
  type PlatformSelectorProvider,
} from '../components/dialogs/platform-selector';
import { createPythinkerCodeUserAgent } from '#/cli/version';
import { fetchCatalogOrBuiltIn } from '#/utils/catalog-fetch';
import { formatErrorMessage } from '#/tui/utils/event-payload';
import type { SlashCommandHost } from './dispatch';

/** Maps an OAuth-type platform picker value to the provider id it writes into config. */
function oauthPlatformConfigProviderId(platformValue: string): string | undefined {
  switch (platformValue) {
    case OPENAI_CODEX_OAUTH_PLATFORM_ID:
      return OPENAI_CODEX_PROVIDER_ID;
    case KIMI_OAUTH_PLATFORM_ID:
      return KIMI_CODING_PROVIDER_ID;
    case MINIMAX_OAUTH_PLATFORM_ID_GLOBAL:
      return minimaxCodingProviderId('global');
    case MINIMAX_OAUTH_PLATFORM_ID_CN:
      return minimaxCodingProviderId('cn');
    default:
      return undefined;
  }
}

export async function promptPlatformSelection(
  host: SlashCommandHost,
): Promise<PlatformSelection | undefined> {
  const method = await promptAuthenticationMethodSelection(host);
  if (method === undefined) return undefined;

  const catalog = method === 'api_key' ? await loadLoginCatalog(host) : {};
  if (catalog === undefined) return undefined;

  const config = await host.harness.getConfig({ reload: true });
  const providers = buildPlatformOptions(catalog)
    .filter((option) => (method === 'oauth' ? isOAuthPlatformId(option.value) : !isOAuthPlatformId(option.value)))
    .map((option): PlatformSelectorProvider => {
      const providerId = catalogProviderIdFromPlatformValue(option.value) ?? option.value;
      const configProviderId = oauthPlatformConfigProviderId(option.value) ?? providerId;
      const configured = config.providers[configProviderId];
      return {
        value: option.value,
        label: option.label,
        status: configured === undefined ? 'unconfigured' : 'configured',
      };
    })
    .toSorted((left, right) => left.label.localeCompare(right.label));

  if (providers.length === 0) {
    host.showStatus(
      method === 'oauth'
        ? 'No account providers available.'
        : 'No API key providers available.',
    );
    return undefined;
  }

  return new Promise((resolve) => {
    const selector = new PlatformSelectorComponent({
      providers,
      onSelect: (platformId): void => {
        host.restoreEditor();
        resolve({ platformId, catalog });
      },
      onCancel: (): void => {
        host.restoreEditor();
        resolve(undefined);
      },
    });
    host.mountEditorReplacement(selector);
  });
}

function promptAuthenticationMethodSelection(
  host: SlashCommandHost,
): Promise<AuthenticationMethod | undefined> {
  return new Promise((resolve) => {
    const selector = new AuthenticationMethodSelectorComponent({
      onSelect: (method): void => {
        host.restoreEditor();
        resolve(method);
      },
      onCancel: (): void => {
        host.restoreEditor();
        resolve(undefined);
      },
    });
    host.mountEditorReplacement(selector);
  });
}

async function loadLoginCatalog(host: SlashCommandHost): Promise<Catalog | undefined> {
  const controller = new AbortController();
  const cancel = (): void => {
    controller.abort();
  };
  host.cancelInFlight = cancel;
  const spinner = host.showLoginProgressSpinner('Loading provider catalog');
  try {
    const loaded = await fetchCatalogOrBuiltIn(DEFAULT_CATALOG_URL, {
      signal: controller.signal,
      userAgent: createPythinkerCodeUserAgent(),
    });
    spinner.stop({
      ok: true,
      label: loaded.fromBuiltIn
        ? 'Provider catalog loaded from the built-in snapshot.'
        : 'Provider catalog loaded.',
    });
    return loaded.catalog;
  } catch (error) {
    if (controller.signal.aborted) {
      spinner.stop({ ok: false, label: 'Aborted.' });
      return undefined;
    }
    spinner.stop({ ok: false, label: 'Failed to load provider catalog.' });
    host.showError(`Failed to load provider catalog: ${formatErrorMessage(error)}`);
    return undefined;
  } finally {
    if (host.cancelInFlight === cancel) host.cancelInFlight = undefined;
  }
}

export function promptLogoutProviderSelection(
  host: SlashCommandHost,
  options: readonly ChoiceOption[],
  currentValue: string | undefined,
): Promise<string | undefined> {
  return new Promise((resolve) => {
    const picker = new ChoicePickerComponent({
      title: 'Select a provider to log out',
      options,
      currentValue,
      onSelect: (value) => {
        host.restoreEditor();
        resolve(value);
      },
      onCancel: () => {
        host.restoreEditor();
        resolve(undefined);
      },
    });
    host.mountEditorReplacement(picker);
  });
}

export function promptApiKey(
  host: SlashCommandHost,
  platformName: string,
  subtitleLines: readonly string[] = ['Your key will be saved to ~/.pythinker-code/config.toml'],
  options: ApiKeyInputDialogOptions = {},
): Promise<string | undefined> {
  return new Promise((resolve) => {
    const dialog = new ApiKeyInputDialogComponent(
      platformName,
      subtitleLines,
      (result: ApiKeyInputResult) => {
        host.restoreEditor();
        resolve(result.kind === 'ok' ? result.value : undefined);
      },
      options,
    );
    host.mountEditorReplacement(dialog);
  });
}

/**
 * Asks for the provider endpoint the catalog did not declare (or declared
 * only as an env placeholder) — required for catalog imports whose protocol
 * was guessed, where the built-in default endpoint would point at the wrong
 * host. Esc cancels the import.
 */
export function promptBaseUrl(host: SlashCommandHost, platformName: string): Promise<string | undefined> {
  return new Promise((resolve) => {
    const dialog = new ApiKeyInputDialogComponent(
      platformName,
      ['The catalog declares no endpoint for this provider — enter its base URL.'],
      (result: ApiKeyInputResult) => {
        host.restoreEditor();
        resolve(result.kind === 'ok' ? result.value : undefined);
      },
      {
        title: `Enter base URL for ${platformName}`,
        mask: false,
        emptyHint: 'Base URL cannot be empty.',
      },
    );
    host.mountEditorReplacement(dialog);
  });
}

export function promptCatalogProviderSelection(host: SlashCommandHost, catalog: Catalog): Promise<string | undefined> {
  return new Promise((resolve) => {
    const options: ChoiceOption[] = Object.entries(catalog)
      .filter(([, entry]) => resolveCatalogImport(entry).kind !== 'invalid')
      .map(([id, entry]) => ({
        value: id,
        label: entry.name ?? id,
        description:
          typeof entry.api === 'string' && entry.api.length > 0 ? entry.api : undefined,
      }))
      .toSorted((a, b) => a.label.localeCompare(b.label));

    if (options.length === 0) {
      host.showError('Catalog has no providers with supported wire types.');
      resolve(undefined);
      return;
    }

    const picker = new ChoicePickerComponent({
      title: 'Select a provider',
      options,
      searchable: true,
      onSelect: (value) => {
        host.restoreEditor();
        resolve(value);
      },
      onCancel: () => {
        host.restoreEditor();
        resolve(undefined);
      },
    });
    host.mountEditorReplacement(picker);
  });
}

export async function promptModelSelectionForOpenPlatform(
  host: SlashCommandHost,
  models: ProviderModelInfo[],
  platform: OpenPlatformDefinition,
): Promise<{ model: ProviderModelInfo; thinking: ThinkingEffort } | undefined> {
  const modelDict: Record<string, ModelAlias> = {};
  for (const m of models) {
    modelDict[`${platform.id}/${m.id}`] = {
      provider: platform.id,
      model: m.id,
      maxContextSize: m.contextLength,
      capabilities: capabilitiesForModel(m),
      displayName: m.displayName,
    };
  }
  const selection = await runModelSelector(host, modelDict);
  if (selection === undefined) return undefined;
  const model = models.find((m) => `${platform.id}/${m.id}` === selection.alias);
  return model ? { model, thinking: selection.thinking } : undefined;
}

export async function promptModelSelectionForCodex(
  host: SlashCommandHost,
  models: OpenAICodexModelInfo[],
): Promise<{ model: OpenAICodexModelInfo; thinking: ThinkingEffort } | undefined> {
  const modelDict: Record<string, ModelAlias> = {};
  for (const model of models) {
    const capabilities = capabilitiesForModel(model) ?? [];
    modelDict[`${OPENAI_CODEX_PROVIDER_ID}/${model.id}`] = {
      provider: OPENAI_CODEX_PROVIDER_ID,
      model: model.id,
      maxContextSize: model.contextLength,
      capabilities: model.supportsFastMode === true ? [...capabilities, 'fast_mode'] : capabilities,
      supportEfforts:
        model.supportedReasoningEfforts === undefined
          ? undefined
          : [...model.supportedReasoningEfforts],
      displayName: model.displayName,
    };
  }
  const selection = await runModelSelector(host, modelDict);
  if (selection === undefined) return undefined;
  const model = models.find(
    (candidate) => `${OPENAI_CODEX_PROVIDER_ID}/${candidate.id}` === selection.alias,
  );
  return model === undefined ? undefined : { model, thinking: selection.thinking };
}

export async function promptModelSelectionForCatalog(
  host: SlashCommandHost,
  providerId: string,
  models: CatalogModel[],
): Promise<{ model: CatalogModel; thinking: ThinkingEffort } | undefined> {
  const modelDict: Record<string, ModelAlias> = {};
  for (const m of models) {
    modelDict[`${providerId}/${m.id}`] = catalogModelToAlias(providerId, m);
  }
  const selection = await runModelSelector(host, modelDict);
  if (selection === undefined) return undefined;
  const model = models.find((m) => `${providerId}/${m.id}` === selection.alias);
  return model ? { model, thinking: selection.thinking } : undefined;
}

export function runModelSelector(
  host: SlashCommandHost,
  modelDict: Record<string, ModelAlias>,
): Promise<{ alias: string; thinking: ThinkingEffort } | undefined> {
  return new Promise((resolve) => {
    const firstAlias = Object.keys(modelDict)[0] ?? '';
    const caps = modelDict[firstAlias]?.capabilities ?? [];
    const initialThinking = caps.includes('always_thinking') || caps.includes('thinking');
    const selector = new ModelSelectorComponent({
      models: modelDict,
      currentValue: firstAlias,
      currentThinkingEffort: initialThinking ? 'on' : 'off',
      searchable: true,
      onSelect: ({ alias, thinking }) => {
        host.restoreEditor();
        resolve({ alias, thinking });
      },
      onCancel: () => {
        host.restoreEditor();
        resolve(undefined);
      },
    });
    host.mountEditorReplacement(selector);
  });
}
