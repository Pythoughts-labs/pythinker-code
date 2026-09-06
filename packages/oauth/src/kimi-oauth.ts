import { randomUUID } from 'node:crypto';
import { release } from 'node:os';

import { runDeviceOAuthFlow, type DeviceCodeInfo } from './device-oauth';
import { capabilitiesForModel, fetchOpenPlatformModels } from './open-platform';
import type { ProviderModelInfo, PythinkerConfigShape } from './provider-config';
import { isRecord } from './utils';

export const KIMI_OAUTH_PLATFORM_ID = 'kimi-oauth';
export const KIMI_CODING_PROVIDER_ID = 'kimi-coding-oauth';

// kimi-cli's own public client_id: embedded in the official kimi-cli and in
// every community port of its device-code login (opencode-kimi-auth,
// opencode-kimi-full, opencode-kimi-subscription, ...). No registration is
// required, the same trust model as the existing OpenAI Codex client_id.
const CLIENT_ID = '17e5f671-d194-4dfb-9706-5516cb48c098';
const DEVICE_AUTH_URL = 'https://auth.kimi.com/api/oauth/device_authorization';
const TOKEN_URL = 'https://auth.kimi.com/api/oauth/token';
export const KIMI_CODING_BASE_URL = 'https://api.kimi.com/coding/v1';
const KIMI_SCOPE = 'kimi-code';

function sanitizeHeaderValue(value: string): string {
  return value.replace(/[^\x20-\x7e]/g, '').trim();
}

/**
 * kimi-cli fingerprints every request (OAuth and inference) with these
 * headers. `X-Msh-Device-Id` must stay stable across the OAuth flow and
 * subsequent inference calls, so it is generated once at login time and
 * persisted in the provider config's `source` and `customHeaders`.
 */
function kimiHeaders(deviceId: string): Record<string, string> {
  return {
    'X-Msh-Platform': process.platform,
    'X-Msh-Version': '1.0.0',
    'X-Msh-Device-Name': 'pythinker-code',
    'X-Msh-Device-Model': process.arch,
    'X-Msh-Os-Version': sanitizeHeaderValue(release()),
    'X-Msh-Device-Id': deviceId,
  };
}

export interface KimiOAuthTokenBundle {
  readonly accessToken: string;
  readonly refreshToken: string;
  readonly expiresAtMs: number;
  readonly deviceId: string;
}

export interface RunKimiOAuthFlowOptions {
  readonly onCodeReady: (info: DeviceCodeInfo) => void;
  readonly signal?: AbortSignal | undefined;
  readonly fetchImpl?: typeof fetch | undefined;
}

/**
 * Runs the Kimi For Coding device-code OAuth flow and returns the token
 * bundle plus the device id generated for this login (kept stable for the
 * lifetime of the credential).
 */
export async function runKimiOAuthFlow(
  options: RunKimiOAuthFlowOptions,
): Promise<KimiOAuthTokenBundle> {
  const deviceId = randomUUID();
  const headers = kimiHeaders(deviceId);

  const payload = await runDeviceOAuthFlow({
    deviceAuthorizeUrl: DEVICE_AUTH_URL,
    deviceAuthorizeBody: { client_id: CLIENT_ID, scope: KIMI_SCOPE },
    tokenUrl: TOKEN_URL,
    tokenBody: (deviceCode) => ({
      client_id: CLIENT_ID,
      device_code: deviceCode,
      grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
    }),
    headers,
    onCodeReady: options.onCodeReady,
    signal: options.signal,
    fetchImpl: options.fetchImpl,
  });

  const accessToken = payload['access_token'];
  const refreshToken = payload['refresh_token'];
  const expiresIn = Number(payload['expires_in']);
  if (typeof accessToken !== 'string' || accessToken.length === 0) {
    throw new Error('Kimi OAuth token exchange missing access_token.');
  }
  if (typeof refreshToken !== 'string' || refreshToken.length === 0) {
    throw new Error('Kimi OAuth token exchange missing refresh_token.');
  }
  return {
    accessToken,
    refreshToken,
    expiresAtMs: Date.now() + (Number.isFinite(expiresIn) && expiresIn > 0 ? expiresIn * 1000 : 15 * 60_000),
    deviceId,
  };
}

/** Lists Kimi For Coding models via the shared open-platform /models fetch. */
export async function fetchKimiCodingModels(
  accessToken: string,
  deviceId: string,
  fetchImpl: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<ProviderModelInfo[]> {
  return fetchOpenPlatformModels(
    { id: KIMI_CODING_PROVIDER_ID, name: 'Kimi For Coding', baseUrl: KIMI_CODING_BASE_URL },
    accessToken,
    fetchImpl,
    signal,
    kimiHeaders(deviceId),
  );
}

export interface ApplyKimiOAuthResult {
  readonly defaultModel: string;
  readonly defaultThinking: boolean;
}

/**
 * Writes the kimi-coding-oauth provider, model aliases, and default model
 * into the config in place. Mirrors `applyOpenAICodexOAuthConfig`'s shape.
 */
export function applyKimiOAuthConfig(
  config: PythinkerConfigShape,
  options: {
    readonly accessToken: string;
    readonly refreshToken: string;
    readonly deviceId: string;
    readonly models: readonly ProviderModelInfo[];
    readonly selectedModel: ProviderModelInfo;
    readonly thinking?: boolean | undefined;
    readonly effort?: string | undefined;
  },
): ApplyKimiOAuthResult {
  if (options.models.length === 0) {
    throw new Error('No models available for Kimi For Coding.');
  }

  const providerKey = KIMI_CODING_PROVIDER_ID;
  const modelKey = `${providerKey}/${options.selectedModel.id}`;

  config.providers[providerKey] = {
    type: 'pythinker',
    baseUrl: KIMI_CODING_BASE_URL,
    apiKey: options.accessToken,
    customHeaders: kimiHeaders(options.deviceId),
    source: {
      auth: 'kimi-oauth',
      refreshToken: options.refreshToken,
      deviceId: options.deviceId,
    },
  };

  const existingModels = config.models ?? {};
  for (const [key, model] of Object.entries(existingModels)) {
    if (isRecord(model) && model['provider'] === providerKey) {
      delete existingModels[key];
    }
  }

  for (const model of options.models) {
    const aliasKey = `${providerKey}/${model.id}`;
    existingModels[aliasKey] = {
      provider: providerKey,
      model: model.id,
      maxContextSize: model.contextLength,
      capabilities: capabilitiesForModel(model),
      supportEfforts: model.supportEfforts,
      defaultEffort: model.defaultEffort,
      displayName: model.displayName,
    };
  }

  config.models = existingModels;
  config.defaultModel = modelKey;
  const defaultThinking = options.thinking ?? false;
  config.thinking = {
    ...config.thinking,
    enabled: defaultThinking,
    ...(options.effort !== undefined && options.effort !== 'off' ? { effort: options.effort } : {}),
  };

  return { defaultModel: modelKey, defaultThinking };
}
