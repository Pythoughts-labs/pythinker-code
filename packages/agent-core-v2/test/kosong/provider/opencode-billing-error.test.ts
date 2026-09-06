import { APIError as OpenAIAPIError } from 'openai';
import { describe, expect, it } from 'vitest';

import { PROVIDER_API_ERROR_CODE, PROVIDER_AUTH_ERROR_CODE } from '#/kosong/contract/errors';
import { convertOpenAIError } from '#/kosong/provider/bases/openai/openai-common';

describe('OpenCode billing rejection classification', () => {
  it('keeps a 401 insufficient-balance response out of provider.auth_error', () => {
    const source = new OpenAIAPIError(
      401,
      { message: 'Insufficient balance. Manage your billing here: https://opencode.ai/workspace/example/billing' },
      '401 Insufficient balance. Manage your billing here: https://opencode.ai/workspace/example/billing',
      new Headers({ 'x-request-id': 'req-123' }),
    );

    const error = convertOpenAIError(source);

    expect(error.code).toBe(PROVIDER_API_ERROR_CODE);
    expect(error.code).not.toBe(PROVIDER_AUTH_ERROR_CODE);
    expect('statusCode' in error && error.statusCode).toBe(401);
  });

  it('still classifies a normal 401 as provider.auth_error', () => {
    const source = new OpenAIAPIError(401, { message: 'Invalid API key' }, '401 Invalid API key', new Headers());
    expect(convertOpenAIError(source).code).toBe(PROVIDER_AUTH_ERROR_CODE);
  });
});
