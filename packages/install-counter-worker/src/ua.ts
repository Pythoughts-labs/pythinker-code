// Real curl|bash / irm installs send curl, wget, or PowerShell agents.
// Browsers and crawlers are excluded. Vanity filter — not spoof-proof.
const INSTALL_UA = /(^curl\/)|(^Wget\/)|(PowerShell)/i;

export function isInstallUserAgent(ua: string | null): boolean {
  return ua != null && INSTALL_UA.test(ua);
}
