import { runDeviceOAuthFlow, type DeviceCodeInfo } from './device-oauth';
import type { ProviderModelInfo, PythinkerConfigShape } from './provider-config';
import { isRecord } from './utils';

export type MiniMaxRegion = 'global' | 'cn';

export const MINIMAX_OAUTH_PLATFORM_ID_GLOBAL = 'minimax-oauth-global';
export const MINIMAX_OAUTH_PLATFORM_ID_CN = 'minimax-oauth-cn';

export function minimaxOAuthPlatformId(region: MiniMaxRegion): string {
  return region === 'global' ? MINIMAX_OAUTH_PLATFORM_ID_GLOBAL : MINIMAX_OAUTH_PLATFORM_ID_CN;
}

export function minimaxCodingProviderId(region: MiniMaxRegion): string {
  return region === 'global' ? 'minimax-coding-oauth-global' : 'minimax-coding-oauth-cn';
}

interface MiniMaxRegionConfig {
  readonly accountBase: string;
  readonly apiBase: string;
  readonly label: string;
}

const REGIONS: Record<MiniMaxRegion, MiniMaxRegionConfig> = {
  global: {
    accountBase: 'https://account.minimax.io',
    apiBase: 'https://api.minimax.io/anthropic',
    label: 'MiniMax (OAuth · Global)',
  },
  cn: {
    accountBase: 'https://account.minimaxi.com',
    apiBase: 'https://api.minimaxi.com/anthropic',
    label: 'MiniMax (OAuth · China)',
  },
};

export function minimaxRegionLabel(region: MiniMaxRegion): string {
  return REGIONS[region].label;
}

// Reused from OpenClaw's public MiniMax OAuth registration
// (https://github.com/openclaw/openclaw). MiniMax has no self-serve app
// registration for third-party CLIs the way Kimi does, so every integration
// (OpenClaw, Hermes, mmx-cli forks) either registers its own dedicated
// client_id or reuses a known-working one. This is NOT registered to
// Pythinker Code specifically: MiniMax could revoke or rate-limit it at any
// time. Follow-up: register a dedicated client_id for Pythinker.
const CLIENT_ID = '78257093-7e40-4613-99e0-527b14b39113';
const MINIMAX_SCOPE = 'openid profile coding_plan';

// MiniMax's coding-plan surface has no documented /models discovery endpoint
// (unlike Kimi/Codex), so the model list is hand-maintained here. Update when
// MiniMax ships new coding-plan models.
const MINIMAX_CODING_MODELS: readonly ProviderModelInfo[] = [
  {
    id: 'MiniMax-M2.7',
    contextLength: 200_000,
    supportsReasoning: true,
    supportsImageIn: false,
    supportsVideoIn: false,
    supportsToolUse: true,
    displayName: 'MiniMax M2.7',
  },
  {
    id: 'MiniMax-M2.7-highspeed',
    contextLength: 200_000,
    supportsReasoning: true,
    supportsImageIn: false,
    supportsVideoIn: false,
    supportsToolUse: true,
    displayName: 'MiniMax M2.7 (High-Speed)',
  },
];

export function miniMaxCodingModels(): readonly ProviderModelInfo[] {
  return MINIMAX_CODING_MODELS;
}

export interface MiniMaxOAuthTokenBundle {
  readonly accessToken: string;
  readonly refreshToken: string;
  readonly expiresAtMs: number;
}

export interface RunMiniMaxOAuthFlowOptions {
  readonly onCodeReady: (info: DeviceCodeInfo) => void;
  readonly signal?: AbortSignal | undefined;
  readonly fetchImpl?: typeof fetch | undefined;
}

/** Runs the MiniMax device-code OAuth flow for the given region. */
export async function runMiniMaxOAuthFlow(
  region: MiniMaxRegion,
  options: RunMiniMaxOAuthFlowOptions,
): Promise<MiniMaxOAuthTokenBundle> {
  const { accountBase } = REGIONS[region];

  const payload = await runDeviceOAuthFlow({
    deviceAuthorizeUrl: `${accountBase}/oauth2/device/code`,
    deviceAuthorizeBody: { client_id: CLIENT_ID, scope: MINIMAX_SCOPE },
    tokenUrl: `${accountBase}/oauth2/token`,
    tokenBody: (deviceCode) => ({
      client_id: CLIENT_ID,
      device_code: deviceCode,
      grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
    }),
    onCodeReady: options.onCodeReady,
    signal: options.signal,
    fetchImpl: options.fetchImpl,
  });

  const accessToken = payload['access_token'];
  const refreshToken = payload['refresh_token'];
  const expiresIn = Number(payload['expires_in']);
  if (typeof accessToken !== 'string' || accessToken.length === 0) {
    throw new Error('MiniMax OAuth token exchange missing access_token.');
  }
  if (typeof refreshToken !== 'string' || refreshToken.length === 0) {
    throw new Error('MiniMax OAuth token exchange missing refresh_token.');
  }
  return {
    accessToken,
    refreshToken,
    expiresAtMs: Date.now() + (Number.isFinite(expiresIn) && expiresIn > 0 ? expiresIn * 1000 : 60 * 60_000),
  };
}

export interface ApplyMiniMaxOAuthResult {
  readonly defaultModel: string;
  readonly defaultThinking: boolean;
}

/**
 * Writes the region-scoped minimax-coding-oauth provider, model aliases, and
 * default model into the config in place. Uses the Anthropic-Messages-
 * compatible surface MiniMax exposes at `{apiBase}`.
 */
export function applyMiniMaxOAuthConfig(
  config: PythinkerConfigShape,
  region: MiniMaxRegion,
  options: {
    readonly accessToken: string;
    readonly refreshToken: string;
    readonly selectedModel: ProviderModelInfo;
    readonly thinking?: boolean | undefined;
    readonly effort?: string | undefined;
  },
): ApplyMiniMaxOAuthResult {
  const providerKey = minimaxCodingProviderId(region);
  const modelKey = `${providerKey}/${options.selectedModel.id}`;

  config.providers[providerKey] = {
    type: 'anthropic',
    baseUrl: REGIONS[region].apiBase,
    apiKey: options.accessToken,
    source: {
      auth: 'minimax-oauth',
      region,
      refreshToken: options.refreshToken,
    },
  };

  const existingModels = config.models ?? {};
  for (const [key, model] of Object.entries(existingModels)) {
    if (isRecord(model) && model['provider'] === providerKey) {
      delete existingModels[key];
    }
  }

  for (const model of MINIMAX_CODING_MODELS) {
    const aliasKey = `${providerKey}/${model.id}`;
    existingModels[aliasKey] = {
      provider: providerKey,
      model: model.id,
      maxContextSize: model.contextLength,
      capabilities: model.supportsReasoning ? ['thinking', 'tool_use'] : ['tool_use'],
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
