import { visibleWidth } from '@pymodel/pi-tui';
import { describe, expect, it } from 'vitest';

import { ApiKeyInputDialogComponent } from '#/tui/components/dialogs/api-key-input-dialog';

describe('ApiKeyInputDialogComponent', () => {
  it('preserves every authorization URL character when wrapping a narrow dialog', () => {
    const url = 'https://example.test/oauth/authorize?client_id=fixture&response_type=code&redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback&code_challenge=fixture&state=fixture';
    const dialog = new ApiKeyInputDialogComponent('OpenAI Codex', [url], () => {});
    const lines = dialog.render(40);
    const plain = lines.map((line) => line.replaceAll(/\u001B\[[0-9;]*m/g, ''));
    const content = plain.map((line) => line.replaceAll('│', '').trim()).join('');

    expect(content).toContain(url);
    expect(lines.every((line) => visibleWidth(line) <= 40)).toBe(true);
  });

  it('keeps every line within narrow widths', () => {
    const dialog = new ApiKeyInputDialogComponent(
      'Pythinker Code',
      ['Paste your API key below.', 'It will be stored locally.'],
      () => {},
    );
    dialog.focused = true;

    for (const width of [39, 20, 10]) {
      for (const line of dialog.render(width)) {
        expect(visibleWidth(line)).toBeLessThanOrEqual(width);
      }
    }
  });
});
