import { describe, expect, it } from 'vitest';

import { buildStatusReportLines } from '#/tui/components/messages/status-panel';

function strip(text: string): string {
  return text.replaceAll(/\u001B\[[0-9;]*m/g, '');
}

describe('status panel report lines', () => {
  it('formats runtime and context status', () => {
    const lines = buildStatusReportLines({
      version: '1.2.3',
      model: 'example/model',
      workDir: '/tmp/project',
      sessionId: 'ses-1',
      sessionTitle: 'Implement status',
      thinkingEffort: 'on',
      permissionMode: 'manual',
      planMode: false,
      towerMode: true,
      towerAvailable: true,
      contextUsage: 0.25,
      contextTokens: 2500,
      maxContextTokens: 10000,
      availableModels: {
        'example/model': {
          provider: 'example',
          model: 'model',
          maxContextSize: 10000,
          displayName: 'Example Model',
        },
      },
      status: {
        model: 'example/model',
        thinkingEffort: 'high',
        permission: 'auto',
        planMode: true,
        towerMode: true,
        contextTokens: 3000,
        maxContextTokens: 12000,
        contextUsage: 0.25,
      },
    }).map(strip);

    const output = lines.join('\n');
    expect(output).toContain('>_ Pythinker Code (v1.2.3)');
    expect(output).toContain('Model        Example Model (thinking high)');
    expect(output).toContain('Permissions  Never Ask');
    expect(output).toContain('Tower mode   on');
    expect(output).toContain('Context window');
    expect(output).toContain('(2.9k / 11.7k)');
  });

  it('shows status load errors as warnings', () => {
    const lines = buildStatusReportLines({
      version: '1.2.3',
      model: '',
      workDir: '/tmp/project',
      sessionId: '',
      sessionTitle: null,
      thinkingEffort: 'off',
      permissionMode: 'manual',
      planMode: false,
      towerMode: false,
      towerAvailable: false,
      contextUsage: 0,
      contextTokens: 0,
      maxContextTokens: 0,
      availableModels: {},
      statusError: 'No active session',
    }).map(strip);

    const output = lines.join('\n');
    expect(output).toContain('Model        not set');
    expect(output).toContain('Session      none');
    expect(output).toContain('Warning      No active session');
    expect(output).toContain('No context window data available.');
  });
});
