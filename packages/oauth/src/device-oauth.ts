import { readApiErrorMessage } from './api-error';
import { OAuthAccessDeniedError } from './openai-codex-oauth';
import { isRecord } from './utils';

/**
 * Generic RFC 8628 (OAuth 2.0 Device Authorization Grant) flow shared by
 * providers whose CLI-facing login is a device code rather than a redirect
 * (Kimi and other RFC 8628-compatible providers). Providers differ only in
 * URLs / client_id / scope / headers / token-payload field names — this module
 * owns the polling state machine only and hands back the raw parsed token JSON
 * for each provider to interpret.
 */

const DEFAULT_POLL_INTERVAL_MS = 5_000;
const DEFAULT_EXPIRES_IN_MS = 15 * 60_000;
const SLOW_DOWN_BACKOFF_MS = 5_000;

export class DeviceOAuthApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export class DeviceCodeExpiredError extends Error {
  constructor(message = 'The device code expired before authorization completed.') {
    super(message);
    this.name = 'DeviceCodeExpiredError';
  }
}

export interface DeviceCodeInfo {
  readonly deviceCode: string;
  readonly userCode: string;
  readonly verificationUri: string;
  readonly verificationUriComplete?: string | undefined;
  readonly intervalMs: number;
  readonly expiresAtMs: number;
}

function stringField(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key];
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function positiveSeconds(value: unknown): number | undefined {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

/**
 * Requests a device code + user code from the authorization server. Fields
 * are read defensively since compatible providers can vary optional fields.
 */
export async function requestDeviceCode(
  url: string,
  body: Record<string, string>,
  headers: Record<string, string> = {},
  fetchImpl: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<DeviceCodeInfo> {
  signal?.throwIfAborted();
  const response = await fetchImpl(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
      ...headers,
    },
    body: new URLSearchParams(body),
    signal,
  });
  signal?.throwIfAborted();
  if (!response.ok) {
    throw new DeviceOAuthApiError(
      await readApiErrorMessage(response, `Device authorization request failed (HTTP ${response.status}).`),
      response.status,
    );
  }
  const payload: unknown = await response.json();
  if (!isRecord(payload)) {
    throw new Error('Device authorization response was not a JSON object.');
  }
  const deviceCode = stringField(payload, 'device_code');
  const userCode = stringField(payload, 'user_code');
  const verificationUri =
    stringField(payload, 'verification_uri') ?? stringField(payload, 'verification_url');
  if (deviceCode === undefined || userCode === undefined || verificationUri === undefined) {
    throw new Error('Device authorization response is missing required fields.');
  }
  const intervalSeconds = positiveSeconds(payload['interval']);
  const expiresInSeconds = positiveSeconds(payload['expires_in']);
  return {
    deviceCode,
    userCode,
    verificationUri,
    verificationUriComplete: stringField(payload, 'verification_uri_complete'),
    intervalMs: intervalSeconds !== undefined ? intervalSeconds * 1000 : DEFAULT_POLL_INTERVAL_MS,
    expiresAtMs:
      Date.now() + (expiresInSeconds !== undefined ? expiresInSeconds * 1000 : DEFAULT_EXPIRES_IN_MS),
  };
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const onAbort = (): void => {
      clearTimeout(timer);
      reject(signal?.reason instanceof Error ? signal.reason : new Error('Device OAuth login cancelled.'));
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

export interface PollDeviceTokenOptions {
  readonly intervalMs: number;
  readonly expiresAtMs: number;
  readonly signal?: AbortSignal | undefined;
  readonly fetchImpl?: typeof fetch | undefined;
}

/**
 * Polls the token endpoint until the user completes authorization, the
 * device code expires, or the caller aborts. Returns the raw parsed JSON
 * payload on success — each provider interprets its own token field names.
 */
export async function pollForDeviceToken(
  url: string,
  body: Record<string, string>,
  headers: Record<string, string>,
  options: PollDeviceTokenOptions,
): Promise<Record<string, unknown>> {
  const fetchImpl = options.fetchImpl ?? fetch;
  let intervalMs = options.intervalMs;

  for (;;) {
    if (Date.now() >= options.expiresAtMs) throw new DeviceCodeExpiredError();
    options.signal?.throwIfAborted();
    await sleep(intervalMs, options.signal);
    options.signal?.throwIfAborted();

    const response = await fetchImpl(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        Accept: 'application/json',
        ...headers,
      },
      body: new URLSearchParams(body),
      signal: options.signal,
    });
    const payload: unknown = await response.json().catch(() => undefined);
    if (response.ok && isRecord(payload)) return payload;

    const error = isRecord(payload) && typeof payload['error'] === 'string' ? payload['error'] : undefined;
    if (error === 'authorization_pending') continue;
    if (error === 'slow_down') {
      intervalMs += SLOW_DOWN_BACKOFF_MS;
      continue;
    }
    if (error === 'access_denied') throw new OAuthAccessDeniedError();
    if (error === 'expired_token') throw new DeviceCodeExpiredError();

    const description = isRecord(payload) ? stringField(payload, 'error_description') : undefined;
    throw new DeviceOAuthApiError(
      description ?? `Device token request failed (HTTP ${response.status}).`,
      response.status,
    );
  }
}

export interface RunDeviceOAuthFlowOptions {
  readonly deviceAuthorizeUrl: string;
  readonly deviceAuthorizeBody: Record<string, string>;
  readonly tokenUrl: string;
  readonly tokenBody: (deviceCode: string) => Record<string, string>;
  readonly headers?: Record<string, string> | undefined;
  readonly onCodeReady: (info: DeviceCodeInfo) => void;
  readonly signal?: AbortSignal | undefined;
  readonly fetchImpl?: typeof fetch | undefined;
}

/**
 * Runs the full RFC 8628 device flow: requests a device/user code, hands it
 * to the caller, then polls until the token arrives, expires, or is denied.
 */
export async function runDeviceOAuthFlow(
  options: RunDeviceOAuthFlowOptions,
): Promise<Record<string, unknown>> {
  options.signal?.throwIfAborted();
  const info = await requestDeviceCode(
    options.deviceAuthorizeUrl,
    options.deviceAuthorizeBody,
    options.headers,
    options.fetchImpl,
    options.signal,
  );
  options.signal?.throwIfAborted();
  options.onCodeReady(info);
  options.signal?.throwIfAborted();
  return pollForDeviceToken(options.tokenUrl, options.tokenBody(info.deviceCode), options.headers ?? {}, {
    intervalMs: info.intervalMs,
    expiresAtMs: info.expiresAtMs,
    signal: options.signal,
    fetchImpl: options.fetchImpl,
  });
}
