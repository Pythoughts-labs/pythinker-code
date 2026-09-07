import { execFile } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import { promisify } from 'node:util';

import {
  BROWSER_LAUNCH_MAX_ATTEMPTS,
  BROWSER_LAUNCH_RETRY_DELAY_MS,
  BROWSER_LAUNCH_TIMEOUT_MS,
  BROWSER_URL_MAX_LENGTH,
  WINDOWS_BROWSER_SCRIPT,
} from '#/constant/browser';
import { resolveCommandPath } from '#/utils/process/resolve-command';

const execFileAsync = promisify(execFile);

export async function openUrl(url: string) {
  if (url.length > BROWSER_URL_MAX_LENGTH || /[\u0000-\u0020\u007F]/.test(url)) return false;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return false;
  } catch {
    return false;
  }

  const isWindows = process.platform === 'win32';
  let command: string | undefined;
  try {
    command = resolveCommandPath(
      isWindows ? 'powershell.exe' : process.platform === 'darwin' ? 'open' : 'xdg-open',
    );
  } catch {
    return false;
  }
  if (command === undefined) return false;
  const args = isWindows
    ? ['-NoProfile', '-NonInteractive', '-Command', WINDOWS_BROWSER_SCRIPT]
    : [url];
  const deadline = Date.now() + BROWSER_LAUNCH_TIMEOUT_MS;

  for (let attempt = 1; attempt <= BROWSER_LAUNCH_MAX_ATTEMPTS; attempt++) {
    const remaining = deadline - Date.now();
    if (remaining <= 0) return false;
    try {
      await execFileAsync(command, args, {
        shell: false,
        windowsHide: true,
        timeout: remaining,
        killSignal: 'SIGKILL',
        maxBuffer: 16_384,
        env: isWindows ? { ...process.env, PYTHINKER_CODE_BROWSER_URL: url } : undefined,
      });
      return true;
    } catch (error) {
      // Only EAGAIN proves process creation failed. Exit errors and timeouts
      // can follow a successful browser launch; retrying could open more tabs.
      if (
        attempt === BROWSER_LAUNCH_MAX_ATTEMPTS ||
        !(error instanceof Error) ||
        !('code' in error) ||
        error.code !== 'EAGAIN' ||
        ('killed' in error && error.killed === true)
      ) {
        return false;
      }
    }
    const backoff = BROWSER_LAUNCH_RETRY_DELAY_MS + Math.floor(Math.random() * BROWSER_LAUNCH_RETRY_DELAY_MS);
    if (Date.now() + backoff >= deadline) return false;
    await delay(backoff);
  }
  return false;
}
