export const BROWSER_LAUNCH_TIMEOUT_MS = 10_000;
export const BROWSER_LAUNCH_MAX_ATTEMPTS = 2;
export const BROWSER_LAUNCH_RETRY_DELAY_MS = 200;
export const BROWSER_URL_MAX_LENGTH = 16_384;
export const WINDOWS_BROWSER_SCRIPT =
  'Start-Process -FilePath $env:PYTHINKER_CODE_BROWSER_URL -ErrorAction Stop';
