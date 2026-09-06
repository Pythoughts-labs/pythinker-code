import type { ExecFileOptions } from 'node:child_process';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { openUrl } from '#/utils/open-url';

const mocks = vi.hoisted(() => ({
  execFile: vi.fn<(
    command: string,
    args: readonly string[],
    options: ExecFileOptions,
    callback: (error: NodeJS.ErrnoException | null, stdout: string, stderr: string) => void,
  ) => void>(),
  resolveCommandPath: vi.fn<(command: string) => string | undefined>(),
}));

vi.mock('node:child_process', () => ({ execFile: mocks.execFile }));
vi.mock('node:timers/promises', () => ({
  setTimeout: (ms: number) => new Promise<void>((resolve) => { setTimeout(resolve, ms); }),
}));
vi.mock('#/utils/process/resolve-command', () => ({
  resolveCommandPath: mocks.resolveCommandPath,
}));

const authorizeUrl =
  'https://auth.openai.com/oauth/authorize?client_id=fixture&response_type=code' +
  '&redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback' +
  '&scope=openid+profile&code_challenge=fixture&state=fixture';

beforeEach(() => {
  vi.clearAllMocks();
  mocks.resolveCommandPath.mockImplementation((command) => `/trusted/${command}`);
  mocks.execFile.mockImplementation((_command, _args, _options, callback) => {
    callback?.(null, '', '');
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('openUrl', () => {
  it('keeps the complete Windows OAuth URL out of command source', async () => {
    vi.stubGlobal('process', { ...process, platform: 'win32' });

    const pending = openUrl(authorizeUrl);

    expect(mocks.resolveCommandPath).toHaveBeenCalledWith('powershell.exe');
    expect(mocks.execFile).toHaveBeenCalledWith(
      '/trusted/powershell.exe',
      [
        '-NoProfile',
        '-NonInteractive',
        '-Command',
        'Start-Process -FilePath $env:PYTHINKER_CODE_BROWSER_URL -ErrorAction Stop',
      ],
      expect.objectContaining({
        shell: false,
        windowsHide: true,
        timeout: expect.any(Number),
        killSignal: 'SIGKILL',
        env: expect.objectContaining({ PYTHINKER_CODE_BROWSER_URL: authorizeUrl }),
      }),
      expect.any(Function),
    );
    expect(mocks.execFile.mock.calls[0]?.[1].join(' ')).not.toContain(authorizeUrl);
    await expect(pending).resolves.toBe(true);
  });

  it('does not interpolate quotes, expansions, or shell metacharacters on Windows', async () => {
    vi.stubGlobal('process', { ...process, platform: 'win32' });
    const url = 'https://example.test/login?x=%PATH%&y=$($env:HOME);echo&z=\'quoted\'&next=%22';

    await expect(openUrl(url)).resolves.toBe(true);

    expect(mocks.execFile.mock.calls[0]?.[2].env?.['PYTHINKER_CODE_BROWSER_URL']).toBe(url);
    expect(mocks.execFile.mock.calls[0]?.[1].join(' ')).not.toContain('example.test');
  });

  it.each([
    ['darwin', 'open'],
    ['linux', 'xdg-open'],
  ] as const)('passes the URL as a direct argument on %s', async (platform, command) => {
    vi.stubGlobal('process', { ...process, platform });

    await expect(openUrl(authorizeUrl)).resolves.toBe(true);

    expect(mocks.execFile).toHaveBeenCalledWith(
      `/trusted/${command}`,
      [authorizeUrl],
      expect.objectContaining({ shell: false }),
      expect.any(Function),
    );
  });

  it.each([
    ['malformed', 'not a URL'],
    ['option', '--help'],
    ['script scheme', 'javascript:alert(1)'],
    ['file scheme', 'file:///tmp/example.exe'],
    ['control character', 'https://example.test/\nnext'],
    ['oversized', `https://example.test/${'a'.repeat(16_384)}`],
  ])('rejects unsafe browser input without starting a process: %s', async (_label, url) => {
    await expect(openUrl(url)).resolves.toBe(false);
    expect(mocks.execFile).not.toHaveBeenCalled();
  });

  it('reports a missing launcher without executing a cwd fallback', async () => {
    mocks.resolveCommandPath.mockReturnValue(undefined);

    await expect(openUrl(authorizeUrl)).resolves.toBe(false);

    expect(mocks.execFile).not.toHaveBeenCalled();
  });

  it('reports launcher resolution errors without exposing process data', async () => {
    mocks.resolveCommandPath.mockImplementation(() => { throw new Error('cwd unavailable'); });

    await expect(openUrl(authorizeUrl)).resolves.toBe(false);

    expect(mocks.execFile).not.toHaveBeenCalled();
  });

  it('does not retry once the overall deadline has expired', async () => {
    vi.useFakeTimers();
    mocks.execFile.mockImplementation((_command, _args, _options, callback) => {
      vi.setSystemTime(Date.now() + 10_000);
      callback(Object.assign(new Error('spawn failed'), { code: 'EAGAIN' }), '', '');
    });

    await expect(openUrl(authorizeUrl)).resolves.toBe(false);

    expect(mocks.execFile).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('retries EAGAIN once after a delay with a smaller remaining deadline', async () => {
    vi.useFakeTimers();
    mocks.execFile.mockImplementationOnce((_command, _args, _options, callback) => {
      callback(Object.assign(new Error('spawn failed'), { code: 'EAGAIN' }), '', '');
    });
    const pending = openUrl(authorizeUrl);
    const result = expect(pending).resolves.toBe(true);

    expect(mocks.execFile).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(199);
    expect(mocks.execFile).toHaveBeenCalledTimes(1);
    await vi.runAllTimersAsync();
    await result;

    expect(mocks.execFile).toHaveBeenCalledTimes(2);
    expect(mocks.execFile.mock.calls[1]?.[2].timeout).toBeLessThan(
      mocks.execFile.mock.calls[0]![2].timeout!,
    );
    expect(vi.getTimerCount()).toBe(0);
  });

  it('stops after two failed process starts', async () => {
    vi.useFakeTimers();
    mocks.execFile.mockImplementation((_command, _args, _options, callback) => {
      callback(Object.assign(new Error('spawn failed'), { code: 'EAGAIN' }), '', '');
    });
    const result = expect(openUrl(authorizeUrl)).resolves.toBe(false);

    await vi.runAllTimersAsync();
    await result;

    expect(mocks.execFile).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each(['ENOENT', 'EACCES', 'ETIMEDOUT'])('does not retry %s', async (code) => {
    mocks.execFile.mockImplementation((_command, _args, _options, callback) => {
      callback(Object.assign(new Error(`sensitive-url=${authorizeUrl}`), { code }), '', '');
    });

    await expect(openUrl(authorizeUrl)).resolves.toBe(false);

    expect(mocks.execFile).toHaveBeenCalledTimes(1);
  });

  it('does not reopen a browser after an ambiguous killed launcher', async () => {
    mocks.execFile.mockImplementation((_command, _args, _options, callback) => {
      callback(Object.assign(new Error('timed out'), { killed: true, code: 'EAGAIN' }), '', '');
    });

    await expect(openUrl(authorizeUrl)).resolves.toBe(false);

    expect(mocks.execFile).toHaveBeenCalledTimes(1);
  });
});
