import { describe, expect, it } from 'vitest';

import {
  KIMI_OAUTH_PLATFORM_ID,
  MINIMAX_OAUTH_PLATFORM_ID_CN,
  MINIMAX_OAUTH_PLATFORM_ID_GLOBAL,
  OPENAI_CODEX_OAUTH_PLATFORM_ID,
} from '@pymodel/pythinker-code-oauth';

import { buildPlatformOptions, isOAuthPlatformId } from '#/login/platform-options';
import type { Catalog } from '#/catalog';

describe('buildPlatformOptions', () => {
  it('includes Codex, Kimi, and both MiniMax OAuth entries', () => {
    const options = buildPlatformOptions({} as Catalog);
    const values = options.map((option) => option.value);

    expect(values).toContain(OPENAI_CODEX_OAUTH_PLATFORM_ID);
    expect(values).toContain(KIMI_OAUTH_PLATFORM_ID);
    expect(values).toContain(MINIMAX_OAUTH_PLATFORM_ID_GLOBAL);
    expect(values).toContain(MINIMAX_OAUTH_PLATFORM_ID_CN);
  });

  it('never lets a catalog entry shadow an OAuth platform id', () => {
    const catalog = {
      [KIMI_OAUTH_PLATFORM_ID]: { name: 'Should not surface', api: 'openai' },
    } as unknown as Catalog;

    const options = buildPlatformOptions(catalog);
    const kimiEntries = options.filter((option) => option.value === KIMI_OAUTH_PLATFORM_ID);
    expect(kimiEntries).toHaveLength(1);
    expect(kimiEntries[0]?.label).toBe('Kimi For Coding (OAuth)');
  });
});

describe('isOAuthPlatformId', () => {
  it('recognizes every OAuth-type platform id', () => {
    expect(isOAuthPlatformId(OPENAI_CODEX_OAUTH_PLATFORM_ID)).toBe(true);
    expect(isOAuthPlatformId(KIMI_OAUTH_PLATFORM_ID)).toBe(true);
    expect(isOAuthPlatformId(MINIMAX_OAUTH_PLATFORM_ID_GLOBAL)).toBe(true);
    expect(isOAuthPlatformId(MINIMAX_OAUTH_PLATFORM_ID_CN)).toBe(true);
  });

  it('rejects API-key platform ids', () => {
    expect(isOAuthPlatformId('moonshot-cn')).toBe(false);
    expect(isOAuthPlatformId('catalog:deepseek')).toBe(false);
  });
});
