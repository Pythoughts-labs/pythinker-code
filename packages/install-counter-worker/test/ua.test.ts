import { describe, expect, it } from "vitest";
import { isInstallUserAgent } from "../src/ua";

describe("isInstallUserAgent", () => {
  it("counts curl, wget, powershell", () => {
    expect(isInstallUserAgent("curl/8.5.0")).toBe(true);
    expect(isInstallUserAgent("Wget/1.21.4")).toBe(true);
    expect(isInstallUserAgent("WindowsPowerShell/5.1")).toBe(true);
    expect(isInstallUserAgent("Mozilla/5.0 ... PowerShell/7.4.0")).toBe(true);
  });

  it("skips browsers, bots, empty", () => {
    expect(isInstallUserAgent("Mozilla/5.0 (X11) Chrome/124")).toBe(false);
    expect(isInstallUserAgent("Googlebot/2.1")).toBe(false);
    expect(isInstallUserAgent("")).toBe(false);
    expect(isInstallUserAgent(null)).toBe(false);
  });
});
