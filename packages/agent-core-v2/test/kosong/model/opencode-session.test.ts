import { describe, expect, it } from 'vitest';

import { isOpencodeGatewayBaseUrl, opencodeSessionHeaders } from '#/kosong/model/opencodeSession';

describe('OpenCode session header safety', () => {
  it.each([
    'https://opencode.ai/zen/go/v1',
    'https://api.opencode.ai/v1',
  ])('allows HTTPS OpenCode gateway %s', (baseUrl) => {
    expect(isOpencodeGatewayBaseUrl(baseUrl)).toBe(true);
    expect(opencodeSessionHeaders(baseUrl, 'conversation-1')).toEqual({
      'x-opencode-session': 'conversation-1',
    });
  });

  it.each([
    'http://opencode.ai/zen/go/v1',
    'http://api.opencode.ai/v1',
    'https://evil-opencode.ai/v1',
    'https://opencode.ai.evil.test/v1',
    'not-a-url',
  ])('never sends the session header to unsafe URL %s', (baseUrl) => {
    expect(isOpencodeGatewayBaseUrl(baseUrl)).toBe(false);
    expect(opencodeSessionHeaders(baseUrl, 'conversation-1')).toBeUndefined();
  });

  it('does not send an empty conversation id', () => {
    expect(opencodeSessionHeaders('https://opencode.ai/v1', '   ')).toBeUndefined();
  });
});
