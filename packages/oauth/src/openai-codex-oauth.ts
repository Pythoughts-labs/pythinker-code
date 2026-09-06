import { createHash, randomBytes } from 'node:crypto';
import { createServer, type Server } from 'node:http';

import { readApiErrorMessage } from './api-error';
import { renderOAuthErrorPage, renderOpenAICodexOAuthSuccessPage } from './oauth-pages';
import { parseSupportsThinkingType, type SupportsThinkingType } from './provider-config';
import { capabilitiesForModel } from './open-platform';
import { isRecord } from './utils';

export const OPENAI_CODEX_OAUTH_PLATFORM_ID = 'openai-codex-oauth';
export const OPENAI_CODEX_PROVIDER_ID = 'openai-codex';

const CLIENT_ID = 'app_EMoamEEZ73f0CkXaXp7hrann';
const AUTHORIZE_URL = 'https://auth.openai.com/oauth/authorize';
const TOKEN_URL = 'https://auth.openai.com/oauth/token';
export const OPENAI_CODEX_REDIRECT_URI = 'http://localhost:1455/auth/callback';
export const OPENAI_CODEX_AUTH_INPUT_MAX_LENGTH = 16_384;
const CALLBACK_PORT = 1455;
const CALLBACK_PATH = '/auth/callback';
const SCOPE =
  'openid profile email offline_access api.connectors.read api.connectors.invoke';
const CODEX_BASE_URL = 'https://chatgpt.com/backend-api/codex';
const CODEX_ORIGINATOR = 'codex_cli_rs';
const JWT_AUTH_CLAIM = 'https://api.openai.com/auth';
const DEFAULT_CALLBACK_TIMEOUT_MS = 120_000;

export interface OpenAICodexModelInfo {
  readonly id: string;
  readonly contextLength: number;
  readonly supportsReasoning: boolean;
  readonly supportedReasoningEfforts?: readonly string[] | undefined;
  readonly supportsImageIn: boolean;
  readonly supportsVideoIn: boolean;
  readonly supportsToolUse?: boolean | undefined;
  readonly supportsFastMode?: boolean | undefined;
  readonly supportsThinkingType?: SupportsThinkingType | undefined;
  readonly displayName?: string | undefined;
}

export interface OpenAICodexConfigShape {
  providers: Record<string, Record<string, unknown>>;
  models?: Record<string, Record<string, unknown>> | undefined;
  defaultModel?: string | undefined;
  thinking?: {
    enabled?: boolean | undefined;
    mode?: 'auto' | 'on' | 'off' | undefined;
    effort?: string | undefined;
    [key: string]: unknown;
  } | undefined;
  [key: string]: unknown;
}

export interface OpenAICodexPkcePair {
  readonly verifier: string;
  readonly challenge: string;
  readonly state: string;
}

export interface OpenAICodexTokenBundle {
  readonly accessToken: string;
  readonly refreshToken: string;
  readonly expiresAtMs: number;
  readonly accountId: string;
}

/**
 * `{ denied: true }` is the consent page answering `error=access_denied` — the
 * user pressed Deny, so there is nothing to retry and no URL worth pasting.
 * `null` is every other dead end, where manual input can still rescue the flow.
 */
export type OpenAICodexCallbackResult =
  | { readonly code: string }
  | { readonly denied: true }
  | null;

/**
 * The user denied the authorization request on the consent page. Callers
 * report it as a cancellation, not a failure.
 */
export class OAuthAccessDeniedError extends Error {
  constructor(message = 'Authorization denied.') {
    super(message);
    this.name = 'OAuthAccessDeniedError';
  }
}

export interface OpenAICodexCallbackServer {
  readonly redirectUri: string;
  /**
   * `false` when the port was already taken, so no redirect will ever arrive
   * and the caller must ask the user to paste the URL back.
   */
  readonly loopback: boolean;
  waitForCode(opts?: {
    readonly signal?: AbortSignal | undefined;
    readonly timeoutMs?: number | undefined;
  }): Promise<OpenAICodexCallbackResult>;
  cancelWait(): void;
  close(): void;
}

export function createOpenAICodexPkcePair(): OpenAICodexPkcePair {
  const verifier = randomBytes(32).toString('base64url');
  const challenge = createHash('sha256').update(verifier).digest('base64url');
  const state = randomBytes(32).toString('base64url');
  return { verifier, challenge, state };
}

/**
 * Builds the authorization URL for the codex_cli OAuth flow with the PKCE
 * challenge and state bound to the given pair.
 */
export function buildOpenAICodexAuthorizeUrl(pair: OpenAICodexPkcePair): string {
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    response_type: 'code',
    redirect_uri: OPENAI_CODEX_REDIRECT_URI,
    scope: SCOPE,
    code_challenge: pair.challenge,
    code_challenge_method: 'S256',
    state: pair.state,
    id_token_add_organizations: 'true',
    codex_cli_simplified_flow: 'true',
    originator: CODEX_ORIGINATOR,
  });
  return `${AUTHORIZE_URL}?${params.toString()}`;
}

/**
 * Extracts code/state from a manual paste: a full callback URL, a bare URL
 * fragment, or a query-string chunk.
 */
export function parseOpenAICodexAuthorizationInput(input: string): {
  readonly code?: string;
  readonly state?: string;
} {
  if (input.length > OPENAI_CODEX_AUTH_INPUT_MAX_LENGTH) {
    throw new Error('OpenAI Codex authorization input is too long.');
  }
  const value = input.trim();
  if (value.length === 0) return {};

  try {
    const url = new URL(value);
    return {
      code: url.searchParams.get('code') ?? undefined,
      state: url.searchParams.get('state') ?? undefined,
    };
  } catch {
    // fall through
  }

  if (value.includes('#')) {
    const [code, state] = value.split('#', 2);
    return { code, state };
  }
  if (value.includes('code=')) {
    const params = new URLSearchParams(value.startsWith('?') ? value.slice(1) : value);
    return {
      code: params.get('code') ?? undefined,
      state: params.get('state') ?? undefined,
    };
  }
  return { code: value };
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  const payload = parts[1];
  if (payload === undefined || payload.length === 0) return null;
  try {
    return JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as Record<
      string,
      unknown
    >;
  } catch {
    return null;
  }
}

/**
 * Reads the chatgpt_account_id from the access token's JWT payload, from the
 * auth claim first and the root claim as a fallback.
 */
export function extractOpenAICodexAccountId(accessToken: string): string | undefined {
  const payload = decodeJwtPayload(accessToken);
  if (payload === null) return undefined;

  const authClaim = payload[JWT_AUTH_CLAIM];
  if (typeof authClaim === 'object' && authClaim !== null) {
    const accountId = (authClaim as Record<string, unknown>)['chatgpt_account_id'];
    if (typeof accountId === 'string' && accountId.length > 0) {
      return accountId;
    }
  }

  const rootAccountId = payload['chatgpt_account_id'];
  if (typeof rootAccountId === 'string' && rootAccountId.length > 0) {
    return rootAccountId;
  }

  return undefined;
}

/**
 * Exchanges the authorization code for a token bundle, deriving the account
 * id from the returned access token.
 */
export async function exchangeOpenAICodexAuthorizationCode(
  code: string,
  verifier: string,
  fetchImpl: typeof fetch = fetch,
): Promise<OpenAICodexTokenBundle> {
  const response = await fetchImpl(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: CLIENT_ID,
      code,
      code_verifier: verifier,
      redirect_uri: OPENAI_CODEX_REDIRECT_URI,
    }),
  });
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    const detail = body.length > 0 ? ` ${body}` : '';
    throw new Error(
      `OpenAI Codex token exchange failed (HTTP ${String(response.status)}).${detail}`,
    );
  }
  const payload: unknown = await response.json();
  if (typeof payload !== 'object' || payload === null) {
    throw new Error('OpenAI Codex token exchange returned an unexpected payload.');
  }
  const record = payload as Record<string, unknown>;
  const accessToken = record['access_token'];
  const refreshToken = record['refresh_token'];
  const expiresIn = Number(record['expires_in']);
  if (typeof accessToken !== 'string' || accessToken.length === 0) {
    throw new Error('OpenAI Codex token exchange missing access_token.');
  }
  if (typeof refreshToken !== 'string' || refreshToken.length === 0) {
    throw new Error('OpenAI Codex token exchange missing refresh_token.');
  }
  if (!Number.isFinite(expiresIn) || expiresIn <= 0) {
    throw new Error('OpenAI Codex token exchange missing expires_in.');
  }
  const accountId = extractOpenAICodexAccountId(accessToken);
  if (accountId === undefined) {
    throw new Error('OpenAI Codex token exchange missing chatgpt_account_id claim.');
  }
  return {
    accessToken,
    refreshToken,
    expiresAtMs: Date.now() + expiresIn * 1000,
    accountId,
  };
}

/**
 * Starts the local callback server that receives the OAuth redirect. Returns
 * a no-op server when the port is unavailable so the flow can fall back to
 * manual input.
 */
export async function startOpenAICodexCallbackServer(
  expectedState: string,
): Promise<OpenAICodexCallbackServer> {
  let settleWait: ((value: OpenAICodexCallbackResult) => void) | undefined;
  let server: Server | undefined;

  const waitPromise = new Promise<OpenAICodexCallbackResult>((resolve) => {
    settleWait = resolve;
  });

  const close = (): void => {
    if (server === undefined) return;
    server.removeAllListeners();
    server.close();
    server = undefined;
  };

  const noopServer: OpenAICodexCallbackServer = {
    redirectUri: OPENAI_CODEX_REDIRECT_URI,
    loopback: false,
    waitForCode: async () => null,
    cancelWait: () => {},
    close: () => {},
  };
  const errorPage = renderOAuthErrorPage();
  const successPage = renderOpenAICodexOAuthSuccessPage();

  return new Promise((resolve) => {
    const callbackServer = createServer((req, res) => {
      try {
        const url = new URL(req.url ?? '', 'http://localhost');
        if (url.pathname !== CALLBACK_PATH) {
          res.writeHead(404).end('Not found');
          return;
        }
        const errorParam = url.searchParams.get('error');
        if (errorParam !== null) {
          res.writeHead(400, { 'content-type': 'text/html; charset=utf-8' }).end(
            errorPage,
          );
          settleWait?.(errorParam === 'access_denied' ? { denied: true } : null);
          settleWait = undefined;
          return;
        }
        const stateParam = url.searchParams.get('state');
        if (stateParam !== expectedState) {
          res.writeHead(400, { 'content-type': 'text/html; charset=utf-8' }).end(
            errorPage,
          );
          settleWait?.(null);
          settleWait = undefined;
          return;
        }
        const code = url.searchParams.get('code');
        if (code === null || code.length === 0) {
          res.writeHead(400, { 'content-type': 'text/html; charset=utf-8' }).end(
            errorPage,
          );
          settleWait?.(null);
          settleWait = undefined;
          return;
        }
        res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }).end(
          successPage,
        );
        settleWait?.({ code });
        settleWait = undefined;
      } catch {
        res.writeHead(500).end('Internal error');
        settleWait?.(null);
        settleWait = undefined;
      }
    });

    server = callbackServer;
    callbackServer
      .listen(CALLBACK_PORT, '127.0.0.1', () => {
        resolve({
          redirectUri: OPENAI_CODEX_REDIRECT_URI,
          loopback: true,
          waitForCode: async (opts = {}) => {
            const timeoutMs = opts.timeoutMs ?? DEFAULT_CALLBACK_TIMEOUT_MS;
            return new Promise<OpenAICodexCallbackResult>((resolveWait, rejectWait) => {
              let timer: NodeJS.Timeout | undefined;
              const onAbort = (): void => {
                // Tear down here rather than leaning on the `waitPromise.then`
                // below: an already-aborted signal returns before that handler
                // is ever registered, which left both the full timeout and the
                // listening callback server alive to hold the host's event
                // loop. Every other exit from the wait closes the server, so
                // this path has to as well.
                cleanup();
                close();
                settleWait?.(null);
                settleWait = undefined;
                rejectWait(
                  opts.signal?.reason instanceof Error
                    ? opts.signal.reason
                    : new Error('OpenAI Codex login cancelled.'),
                );
              };
              const cleanup = (): void => {
                if (timer !== undefined) clearTimeout(timer);
                opts.signal?.removeEventListener('abort', onAbort);
              };
              timer = setTimeout(() => {
                settleWait?.(null);
                settleWait = undefined;
                cleanup();
                resolveWait(null);
              }, timeoutMs);
              if (opts.signal !== undefined) {
                if (opts.signal.aborted) {
                  onAbort();
                  return;
                }
                opts.signal.addEventListener('abort', onAbort, { once: true });
              }
              void waitPromise.then((result) => {
                cleanup();
                close();
                resolveWait(result);
              });
            });
          },
          cancelWait: () => {
            settleWait?.(null);
            settleWait = undefined;
          },
          close,
        });
      })
      .on('error', () => {
        resolve(noopServer);
      });
  });
}

export interface RunOpenAICodexOAuthFlowOptions {
  readonly openBrowser?: (url: string) => void | Promise<boolean>;
  readonly onManualInput?: (authorizeUrl: string) => Promise<string | undefined>;
  readonly signal?: AbortSignal | undefined;
  readonly timeoutMs?: number | undefined;
}

/**
 * Runs the full OAuth flow: opens the authorize URL, waits for the local
 * callback (or manual paste), then exchanges the code for tokens.
 */
export async function runOpenAICodexOAuthFlow(
  options: RunOpenAICodexOAuthFlowOptions = {},
): Promise<OpenAICodexTokenBundle> {
  options.signal?.throwIfAborted();
  const pkce = createOpenAICodexPkcePair();
  const authorizeUrl = buildOpenAICodexAuthorizeUrl(pkce);
  const callbackServer = await startOpenAICodexCallbackServer(pkce.state);
  const onAbort = (): void => {
    callbackServer.close();
  };

  try {
    options.signal?.addEventListener('abort', onAbort, { once: true });
    options.signal?.throwIfAborted();
    let opened = false;
    try {
      opened = options.openBrowser !== undefined && (await options.openBrowser(authorizeUrl)) !== false;
    } catch {
      // Launcher errors can contain the authorization URL. Recover through the
      // manual prompt instead of exposing process arguments in an error log.
    }
    options.signal?.throwIfAborted();
    if (!opened) {
      callbackServer.close();
      if (options.onManualInput === undefined) {
        throw new Error('Could not open the sign-in page. Start login again with manual input available.');
      }
    }

    let code: string | undefined;
    const callbackResult = opened
      ? await callbackServer.waitForCode({
          signal: options.signal,
          timeoutMs: options.timeoutMs,
        })
      : null;
    if (callbackResult !== null && 'denied' in callbackResult) {
      throw new OAuthAccessDeniedError();
    }
    if (callbackResult !== null) {
      code = callbackResult.code;
    } else if (options.onManualInput !== undefined) {
      const manualInput = await options.onManualInput(authorizeUrl);
      options.signal?.throwIfAborted();
      if (manualInput === undefined) {
        throw new Error('OpenAI Codex login cancelled.');
      }
      const parsed = parseOpenAICodexAuthorizationInput(manualInput);
      if (parsed.state !== undefined && parsed.state !== pkce.state) {
        throw new Error('OAuth state mismatch. Start login again.');
      }
      code = parsed.code;
    }

    if (code === undefined || code.length === 0) {
      throw new Error('No authorization code received from OpenAI Codex OAuth flow.');
    }

    options.signal?.throwIfAborted();
    return await exchangeOpenAICodexAuthorizationCode(code, pkce.verifier);
  } finally {
    options.signal?.removeEventListener('abort', onAbort);
    callbackServer.close();
  }
}

const CODEX_DEFAULT_CONTEXT_LENGTH = 256_000;
/**
 * Codex `/models` gates its catalog by `client_version`. Bump this when newer
 * models stop appearing after an OpenAI Codex CLI release.
 */
export const OPENAI_CODEX_CLI_CLIENT_VERSION = '0.145.0';

const CODEX_REASONING_EFFORT_ORDER = ['low', 'medium', 'high', 'xhigh', 'max'] as const;

export class OpenAICodexApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export interface FetchOpenAICodexModelsOptions {
  readonly accessToken: string;
  readonly accountId: string;
  readonly fetchImpl?: typeof fetch | undefined;
  readonly signal?: AbortSignal | undefined;
}

// The Codex /models catalog advertises reasoning levels its own /responses
// endpoint refuses: `ultra` is listed for the gpt-5.6 family but answers
// `Invalid value: 'ultra'. Supported values are: ...`. Writing an unusable
// level into config.toml surfaces as a failed turn the user cannot diagnose,
// so only levels /responses actually accepts are kept.
const CODEX_RESPONSES_REASONING_EFFORTS = new Set([
  'none',
  'minimal',
  'low',
  'medium',
  'high',
  'xhigh',
  'max',
]);

function readCodexReasoningEfforts(item: Record<string, unknown>): readonly string[] {
  const levels = item['supported_reasoning_levels'];
  if (!Array.isArray(levels)) return [];
  return levels.flatMap((level) => {
    if (!isRecord(level)) return [];
    const effort = level['effort'];
    if (typeof effort !== 'string' || effort.length === 0) return [];
    return CODEX_RESPONSES_REASONING_EFFORTS.has(effort) ? [effort] : [];
  });
}

function readCodexInputModalities(item: Record<string, unknown>): readonly string[] {
  const modalities = item['input_modalities'];
  if (!Array.isArray(modalities)) return ['text', 'image'];
  return modalities.filter((value): value is string => typeof value === 'string');
}

// Codex gates fast mode via `service_tiers`: entries arrive either as bare
// tier ids or as {id, name, description} objects. Both 'priority' and 'fast'
// tiers advertise fast mode.
function readCodexFastMode(item: Record<string, unknown>): boolean {
  const tiers = item['service_tiers'];
  if (!Array.isArray(tiers)) return false;
  return tiers.some((tier) => {
    if (typeof tier === 'string') return tier === 'priority' || tier === 'fast';
    if (!isRecord(tier)) return false;
    return tier['id'] === 'priority' || tier['id'] === 'fast';
  });
}

function toCodexModelInfo(item: unknown): OpenAICodexModelInfo | undefined {
  if (!isRecord(item)) return undefined;

  const id =
    typeof item['slug'] === 'string' && item['slug'].length > 0
      ? item['slug']
      : typeof item['id'] === 'string' && item['id'].length > 0
        ? item['id']
        : undefined;
  if (id === undefined) return undefined;

  if (id === 'codex-auto-review') return undefined;
  const visibility = item['visibility'];
  if (typeof visibility === 'string' && visibility !== 'list') return undefined;

  let contextLength = Number(item['context_window'] ?? item['max_context_window'] ?? item['context_length']);
  if (!Number.isInteger(contextLength) || contextLength <= 0) {
    contextLength = CODEX_DEFAULT_CONTEXT_LENGTH;
  }

  const displayName = item['display_name'];
  const normalizedDisplayName =
    typeof displayName === 'string' && displayName.length > 0 ? displayName : undefined;

  const reasoningEfforts = readCodexReasoningEfforts(item);
  const nonNoneReasoning = reasoningEfforts.filter((effort) => effort !== 'none');
  const supportsReasoning =
    typeof item['supports_reasoning'] === 'boolean'
      ? item['supports_reasoning']
      : nonNoneReasoning.length > 0;

  const inputModalities = readCodexInputModalities(item);
  const supportsImageIn =
    typeof item['supports_image_in'] === 'boolean'
      ? item['supports_image_in']
      : inputModalities.includes('image');

  const supportsToolUse = Object.hasOwn(item, 'supports_tool_use')
    ? Boolean(item['supports_tool_use'])
    : Object.hasOwn(item, 'supports_parallel_tool_calls')
      ? Boolean(item['supports_parallel_tool_calls'])
      : true;

  let supportsThinkingType = parseSupportsThinkingType(item['supports_thinking_type']);
  if (supportsThinkingType === undefined && reasoningEfforts.length > 0) {
    supportsThinkingType =
      reasoningEfforts.length === 1 && reasoningEfforts[0] !== 'none' ? 'only' : 'both';
  }

  return {
    id,
    contextLength,
    supportsReasoning,
    supportedReasoningEfforts:
      nonNoneReasoning.length > 0 ? nonNoneReasoning : undefined,
    supportsImageIn,
    supportsVideoIn: Boolean(item['supports_video_in']),
    supportsToolUse,
    supportsFastMode: readCodexFastMode(item),
    supportsThinkingType,
    displayName: normalizedDisplayName,
  };
}

function capabilitiesForOpenAICodexModel(model: OpenAICodexModelInfo): string[] | undefined {
  const capabilities = capabilitiesForModel(model);
  return model.supportsFastMode === true
    ? [...(capabilities ?? []), 'fast_mode']
    : capabilities;
}

function parseCodexModelsPayload(payload: unknown): OpenAICodexModelInfo[] {
  if (!isRecord(payload)) {
    throw new Error(`Unexpected models response for ${CODEX_BASE_URL}.`);
  }

  const rawModels = Array.isArray(payload['models'])
    ? payload['models']
    : Array.isArray(payload['data'])
      ? payload['data']
      : undefined;
  if (rawModels === undefined) {
    throw new Error(`Unexpected models response for ${CODEX_BASE_URL}.`);
  }

  return rawModels
    .map((item) => toCodexModelInfo(item))
    .filter((item): item is OpenAICodexModelInfo => item !== undefined);
}

/**
 * Lists the Codex model catalog for an account, gated by the pinned
 * client_version.
 */
export async function fetchOpenAICodexModels(
  options: FetchOpenAICodexModelsOptions,
): Promise<OpenAICodexModelInfo[]> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const modelsUrl = `${CODEX_BASE_URL}/models?client_version=${encodeURIComponent(OPENAI_CODEX_CLI_CLIENT_VERSION)}`;
  const response = await fetchImpl(modelsUrl, {
    headers: {
      Authorization: `Bearer ${options.accessToken}`,
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'chatgpt-account-id': options.accountId,
      originator: CODEX_ORIGINATOR,
      'OpenAI-Beta': 'responses=experimental',
    },
    signal: options.signal,
  });
  if (!response.ok) {
    throw new OpenAICodexApiError(
      await readApiErrorMessage(response, `Failed to list OpenAI Codex models (HTTP ${response.status}).`),
      response.status,
    );
  }
  const payload: unknown = await response.json();
  return parseCodexModelsPayload(payload);
}

export interface ApplyOpenAICodexOAuthResult {
  readonly defaultModel: string;
  readonly defaultThinking: boolean;
}

/**
 * Writes the openai-codex provider, model aliases, default model, and top
 * reasoning effort into the config in place.
 */
export function applyOpenAICodexOAuthConfig(
  config: OpenAICodexConfigShape,
  options: {
    readonly accessToken: string;
    readonly accountId?: string | undefined;
    readonly refreshToken?: string | undefined;
    readonly models: readonly OpenAICodexModelInfo[];
    readonly selectedModel: OpenAICodexModelInfo;
    readonly thinking?: boolean | undefined;
    /**
     * The effort level the user picked. Omitted, the model's top supported
     * effort is used, which is what callers that never asked the user get.
     */
    readonly effort?: string;
  },
): ApplyOpenAICodexOAuthResult {
  if (options.models.length === 0) {
    throw new Error('No models available for OpenAI Codex.');
  }

  const providerKey = OPENAI_CODEX_PROVIDER_ID;
  const modelKey = `${providerKey}/${options.selectedModel.id}`;
  const accountId = options.accountId ?? extractOpenAICodexAccountId(options.accessToken);
  if (accountId === undefined) {
    throw new Error('OpenAI Codex provider config missing chatgpt_account_id.');
  }

  config.providers[providerKey] = {
    type: 'openai_responses',
    baseUrl: CODEX_BASE_URL,
    apiKey: options.accessToken,
    customHeaders: {
      'chatgpt-account-id': accountId,
      originator: CODEX_ORIGINATOR,
      'OpenAI-Beta': 'responses=experimental',
    },
    source: {
      auth: 'openai-codex-oauth',
      refreshToken: options.refreshToken,
      accountId,
    },
  };

  const existingModels = config.models ?? {};
  for (const [key, model] of Object.entries(existingModels)) {
    if (typeof model === 'object' && model !== null && model['provider'] === providerKey) {
      delete existingModels[key];
    }
  }

  for (const model of options.models) {
    const aliasKey = `${providerKey}/${model.id}`;
    existingModels[aliasKey] = {
      provider: providerKey,
      model: model.id,
      maxContextSize: model.contextLength,
      capabilities: capabilitiesForOpenAICodexModel(model),
      supportEfforts: model.supportedReasoningEfforts,
      displayName: model.displayName,
    };
  }

  config.models = existingModels;
  config.defaultModel = modelKey;
  const defaultThinking = options.thinking ?? true;
  const supportedEfforts = options.selectedModel.supportedReasoningEfforts;
  const topEffort =
    supportedEfforts === undefined || supportedEfforts.includes('max')
      ? 'max'
      : CODEX_REASONING_EFFORT_ORDER.findLast((effort) => supportedEfforts.includes(effort)) ??
        'max';
  // A level the user picked wins over the derived top effort, but only when the
  // model actually declares it — otherwise we would persist an unusable level.
  const picked =
    options.effort !== undefined &&
    options.effort !== 'off' &&
    (supportedEfforts === undefined || supportedEfforts.includes(options.effort))
      ? options.effort
      : undefined;
  config.thinking = {
    ...config.thinking,
    enabled: defaultThinking,
    effort: picked ?? topEffort,
  };

  return { defaultModel: modelKey, defaultThinking };
}
