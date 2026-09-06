import { randomUUID } from 'node:crypto';
import { release } from 'node:os';

import { runDeviceOAuthFlow, type DeviceCodeInfo } from './device-oauth';
import { capabilitiesForModel, fetchOpenPlatformModels } from './open-platform';
import type { ProviderModelInfo, PythinkerConfigShape } from './provider-config';
import { isRecord } from './utils';

export const KIMI_OAUTH_PLATFORM_ID = 'kimi-oauth';
export const KIMI_CODING_PROVIDER_ID = 'kimi-coding-oauth';

const CLIENT_ID = '17e5f671-d194-4dfb-9706-5516cb48c098';
const DEVICE_AUTH_URL = 'https://auth.kimi.com/api/oauth/device_authorization';
const TOKEN_URL = 'https://auth.kimi.com/api/oauth/token';
export const KIMI_CODING_BASE_URL = 'https://api.kimi.com/coding/v1';
const KIMI_SCOPE = 'kimi-code';

function sanitizeHeaderValue(value: string): string {
  return value.replace(/[^\x20-\x7e]/g, '').trim();
}

/** Stable Kimi client identity headers used for OAuth, discovery, and inference. */
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
  readonly scope: string;
  readonly tokenType: string;
}

export interface RunKimiOAuthFlowOptions {
  readonly onCodeReady: (info: DeviceCodeInfo) => void;
  readonly signal?: AbortSignal | undefined;
  readonly fetchImpl?: typeof fetch | undefined;
}

function parseKimiTokenPayload(payload: Record<string, unknown>, deviceId: string): KimiOAuthTokenBundle {
  const accessToken = payload['access_token'];
  const refreshToken = payload['refresh_token'];
  const expiresIn = Number(payload['expires_in']);
  if (typeof accessToken !== 'string' || accessToken.length === 0) {
    throw new Error('Kimi OAuth token exchange missing access_token.');
  }
  if (typeof refreshToken !== 'string' || refreshToken.length === 0) {
    throw new Error('Kimi OAuth token exchange missing refresh_token.');
  }
  const normalizedExpiresIn = Number.isFinite(expiresIn) && expiresIn > 0 ? expiresIn : 15 * 60;
  return {
    accessToken,
    refreshToken,
    expiresAtMs: Date.now() + normalizedExpiresIn * 1000,
    deviceId,
    scope: typeof payload['scope'] === 'string' ? payload['scope'] : KIMI_SCOPE,
    tokenType: typeof payload['token_type'] === 'string' ? payload['token_type'] : 'Bearer',
  };
}

/** Runs the Kimi For Coding device-code OAuth flow. */
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

  return parseKimiTokenPayload(payload, deviceId);
}

/** Refreshes Kimi credentials while preserving the login device identity. */
export async function refreshKimiOAuthToken(
  refreshToken: string,
  deviceId: string,
  fetchImpl: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<KimiOAuthTokenBundle> {
  signal?.throwIfAborted();
  const response = await fetchImpl(TOKEN_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
      ...kimiHeaders(deviceId),
    },
    body: new URLSearchParams({
      client_id: CLIENT_ID,
      grant_type: 'refresh_token',
      refresh_token: refreshToken,
    }),
    signal,
  });
  const payload: unknown = await response.json().catch(() => undefined);
  if (response.status === 401 || response.status === 403) {
    throw new Error('Kimi OAuth refresh was rejected. Sign in again.');
  }
  if (!response.ok || !isRecord(payload)) {
    throw new Error(`Kimi OAuth refresh failed (HTTP ${response.status}).`);
  }
  return parseKimiTokenPayload(payload, deviceId);
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

/** Writes Kimi OAuth provider/model configuration without embedding bearer tokens in config.toml. */
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
    oauth: { storage: 'file', key: `oauth/${providerKey}` },
    customHeaders: kimiHeaders(options.deviceId),
    source: {
      auth: 'kimi-oauth',
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
