const OPENCODE_HOST = 'opencode.ai';

export const OPENCODE_SESSION_HEADER = 'x-opencode-session';

export function isOpencodeGatewayBaseUrl(baseUrl: string | undefined): boolean {
  if (baseUrl === undefined || baseUrl.length === 0) return false;
  let parsed: URL;
  try {
    parsed = new URL(baseUrl);
  } catch {
    return false;
  }
  if (parsed.protocol !== 'https:') return false;
  const host = parsed.hostname.toLowerCase();
  return host === OPENCODE_HOST || host.endsWith(`.${OPENCODE_HOST}`);
}

export function opencodeSessionHeaders(
  baseUrl: string | undefined,
  conversationId: string | undefined,
): Record<string, string> | undefined {
  const id = conversationId?.trim();
  if (!isOpencodeGatewayBaseUrl(baseUrl) || id === undefined || id.length === 0) return undefined;
  return { [OPENCODE_SESSION_HEADER]: id };
}
