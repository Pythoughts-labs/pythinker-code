import { createHash, randomBytes } from 'node:crypto';

import type { DeviceCodeInfo } from './device-oauth';
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

// Public client registration used by the official MiniMax CLI.
// Keep this protocol aligned with MiniMax-AI/cli src/auth/oauth.ts.
const CLIENT_ID = '659cf4c1-615c-45f6-a5f6-4bf15eb476e5';
const MINIMAX_SCOPE = 'openid profile coding_plan';
const DEVICE_GRANT = 'urn:ietf:params:oauth:grant-type:device_code';
const DEFAULT_INTERVAL_MS = 3_000;

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
  readonly scope: string;
  readonly tokenType: string;
}

export interface RunMiniMaxOAuthFlowOptions {
  readonly onCodeReady: (info: DeviceCodeInfo) => void;
  readonly signal?: AbortSignal;
  readonly fetchImpl?: typeof fetch;
}

function stringField(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key];
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function positiveNumber(value: unknown): number | undefined {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

function createPkce(): { verifier: string; challenge: string; state: string } {
  const verifier = randomBytes(32).toString('base64url');
  const challenge = createHash('sha256').update(verifier).digest('base64url');
  const state = randomBytes(16).toString('base64url');
  return { verifier, challenge, state };
}

function abortableSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const onAbort = (): void => {
      clearTimeout(timer);
      reject(signal?.reason instanceof Error ? signal.reason : new Error('MiniMax OAuth login cancelled.'));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    if (signal !== undefined) {
      if (signal.aborted) {
        onAbort();
        return;
      }
      signal.addEventListener('abort', onAbort, { once: true });
    }
  });
}

async function postForm(
  url: string,
  body: Record<string, string>,
  fetchImpl: typeof fetch,
  signal?: AbortSignal,
): Promise<Response> {
  signal?.throwIfAborted();
  return fetchImpl(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
    },
    body: new URLSearchParams(body),
    signal,
  });
}

/**
 * Runs the PKCE-bound MiniMax device-code flow used by the official MiniMax CLI.
 * MiniMax returns an absolute millisecond deadline in `expired_in`, an interval
 * in milliseconds, and polls by `user_code` + `code_verifier`.
 */
export async function runMiniMaxOAuthFlow(
  region: MiniMaxRegion,
  options: RunMiniMaxOAuthFlowOptions,
): Promise<MiniMaxOAuthTokenBundle> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const { accountBase } = REGIONS[region];
  const pkce = createPkce();
  const codeResponse = await postForm(
    `${accountBase}/oauth2/device/code`,
    {
      client_id: CLIENT_ID,
      scope: MINIMAX_SCOPE,
      code_challenge: pkce.challenge,
      code_challenge_method: 'S256',
      state: pkce.state,
    },
    fetchImpl,
    options.signal,
  );
  if (!codeResponse.ok) {
    throw new Error(`MiniMax OAuth authorization failed (HTTP ${codeResponse.status}).`);
  }
  const rawCode: unknown = await codeResponse.json();
  if (!isRecord(rawCode)) throw new Error('MiniMax OAuth authorization returned an invalid payload.');
  const userCode = stringField(rawCode, 'user_code');
  const verificationUri = stringField(rawCode, 'verification_uri');
  const returnedState = stringField(rawCode, 'state');
  if (userCode === undefined || verificationUri === undefined) {
    throw new Error('MiniMax OAuth authorization response is missing required fields.');
  }
  if (returnedState !== pkce.state) {
    throw new Error('MiniMax OAuth state mismatch. Start login again.');
  }
  const expiresAtMs = positiveNumber(rawCode['expired_in']);
  if (expiresAtMs === undefined) throw new Error('MiniMax OAuth authorization returned invalid expired_in.');
  const intervalMs = positiveNumber(rawCode['interval']) ?? DEFAULT_INTERVAL_MS;
  const info: DeviceCodeInfo = {
    // MiniMax authorizes by user_code rather than exposing a separate device_code.
    deviceCode: userCode,
    userCode,
    verificationUri,
    intervalMs,
    expiresAtMs,
  };
  options.signal?.throwIfAborted();
  options.onCodeReady(info);

  while (Date.now() < expiresAtMs) {
    await abortableSleep(Math.min(intervalMs, Math.max(1, expiresAtMs - Date.now())), options.signal);
    if (Date.now() >= expiresAtMs) break;
    const tokenResponse = await postForm(
      `${accountBase}/oauth2/token`,
      {
        grant_type: DEVICE_GRANT,
        client_id: CLIENT_ID,
        user_code: userCode,
        code_verifier: pkce.verifier,
      },
      fetchImpl,
      options.signal,
    );
    options.signal?.throwIfAborted();
    if (Date.now() >= expiresAtMs) break;
    if (!tokenResponse.ok) {
      throw new Error(`MiniMax OAuth token request failed (HTTP ${tokenResponse.status}).`);
    }
    const rawToken: unknown = await tokenResponse.json();
    options.signal?.throwIfAborted();
    if (Date.now() >= expiresAtMs) break;
    if (!isRecord(rawToken)) throw new Error('MiniMax OAuth token response was invalid.');
    const status = stringField(rawToken, 'status');
    if (status === 'pending') continue;
    if (status !== 'success') {
      const message = isRecord(rawToken['base_resp'])
        ? stringField(rawToken['base_resp'], 'status_msg')
        : undefined;
      throw new Error(message ?? `MiniMax OAuth token request failed: ${status ?? 'unknown status'}.`);
    }
    const accessToken = stringField(rawToken, 'access_token');
    const refreshToken = stringField(rawToken, 'refresh_token') ?? '';
    const tokenExpiresAtMs = positiveNumber(rawToken['expired_in']);
    if (accessToken === undefined || tokenExpiresAtMs === undefined) {
      throw new Error('MiniMax OAuth token response is incomplete.');
    }
    return {
      accessToken,
      refreshToken,
      expiresAtMs: tokenExpiresAtMs,
      scope: MINIMAX_SCOPE,
      tokenType: 'Bearer',
    };
  }
  throw new Error('MiniMax OAuth timed out before authorization completed.');
}

export async function refreshMiniMaxOAuthToken(
  region: MiniMaxRegion,
  refreshToken: string,
  fetchImpl: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<MiniMaxOAuthTokenBundle> {
  const deadline = AbortSignal.timeout(30_000);
  const requestSignal = signal === undefined ? deadline : AbortSignal.any([signal, deadline]);
  const response = await postForm(
    `${REGIONS[region].accountBase}/oauth2/token`,
    { grant_type: 'refresh_token', refresh_token: refreshToken, client_id: CLIENT_ID },
    fetchImpl,
    requestSignal,
  );
  if (!response.ok) throw new Error(`MiniMax OAuth refresh failed (HTTP ${response.status}).`);
  const payload: unknown = await response.json();
  requestSignal.throwIfAborted();
  if (!isRecord(payload) || payload['status'] !== 'success') {
    throw new Error('MiniMax OAuth refresh returned an unsuccessful response.');
  }
  const accessToken = stringField(payload, 'access_token');
  const rotatedRefreshToken = stringField(payload, 'refresh_token') ?? refreshToken;
  const expiresAtMs = positiveNumber(payload['expired_in']);
  if (accessToken === undefined || expiresAtMs === undefined) {
    throw new Error('MiniMax OAuth refresh returned an incomplete token bundle.');
  }
  return {
    accessToken,
    refreshToken: rotatedRefreshToken,
    expiresAtMs,
    scope: MINIMAX_SCOPE,
    tokenType: 'Bearer',
  };
}

export interface ApplyMiniMaxOAuthResult {
  readonly defaultModel: string;
  readonly defaultThinking: boolean;
}

/** Writes the region-scoped MiniMax provider and model aliases. */
export function applyMiniMaxOAuthConfig(
  config: PythinkerConfigShape,
  region: MiniMaxRegion,
  options: {
    readonly accessToken: string;
    readonly refreshToken: string;
    readonly selectedModel: ProviderModelInfo;
    readonly thinking?: boolean;
    readonly effort?: string;
  },
): ApplyMiniMaxOAuthResult {
  const providerKey = minimaxCodingProviderId(region);
  const modelKey = `${providerKey}/${options.selectedModel.id}`;

  config.providers[providerKey] = {
    type: 'anthropic',
    baseUrl: REGIONS[region].apiBase,
    oauth: { storage: 'file', key: `oauth/${providerKey}` },
    source: {
      auth: 'minimax-oauth',
      region,
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
    effort: options.effort !== 'off' ? options.effort : undefined,
  };

  return { defaultModel: modelKey, defaultThinking };
}
