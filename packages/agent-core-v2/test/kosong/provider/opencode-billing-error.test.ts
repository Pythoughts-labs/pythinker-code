import { APIError as OpenAIAPIError } from 'openai';
import { describe, expect, it } from 'vitest';

import { APIProviderQuotaExhaustedError, APIProviderRateLimitError, PROVIDER_API_ERROR_CODE, PROVIDER_AUTH_ERROR_CODE } from '#/kosong/contract/errors';
import { convertOpenAIError } from '#/kosong/provider/bases/openai/openai-common';

describe('OpenCode billing rejection classification', () => {
  it.each([401, 402, 403])('keeps a %s insufficient-balance response out of provider.auth_error', (status) => {
    const source = new OpenAIAPIError(
      status,
      { message: 'Insufficient balance. Manage your billing here: https://opencode.ai/workspace/example/billing' },
      '401 Insufficient balance. Manage your billing here: https://opencode.ai/workspace/example/billing',
      new Headers({ 'x-request-id': 'req-123' }),
    );

    const error = convertOpenAIError(source);

    expect(error.code).toBe(PROVIDER_API_ERROR_CODE);
    expect(error.code).not.toBe(PROVIDER_AUTH_ERROR_CODE);
    expect('statusCode' in error && error.statusCode).toBe(status);
  });

  it('classifies a structured 429 insufficient_quota response as exhausted quota', () => {
    const source = new OpenAIAPIError(429, { code: 'insufficient_quota' }, 'Quota exhausted', new Headers());
    expect(convertOpenAIError(source)).toBeInstanceOf(APIProviderQuotaExhaustedError);
  });

  it('leaves generic 429 billing messages to provider-specific hooks', () => {
    const source = new OpenAIAPIError(429, { message: 'Insufficient balance' }, 'Insufficient balance', new Headers());
    expect(convertOpenAIError(source)).toBeInstanceOf(APIProviderRateLimitError);
  });

  it('still classifies a normal 401 as provider.auth_error', () => {
    const source = new OpenAIAPIError(401, { message: 'Invalid API key' }, '401 Invalid API key', new Headers());
    expect(convertOpenAIError(source).code).toBe(PROVIDER_AUTH_ERROR_CODE);
  });
});
