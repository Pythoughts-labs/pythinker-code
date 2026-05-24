import { describe, expect, it } from "vitest";
import { badgeJson, formatCompact, installsJson } from "../src/badge";

describe("formatCompact (pepy-style abbreviation)", () => {
  it("leaves values under 1000 as integers", () => {
    expect(formatCompact(0)).toBe("0");
    expect(formatCompact(42)).toBe("42");
    expect(formatCompact(999)).toBe("999");
  });

  it("abbreviates thousands with up to one decimal, dropping trailing .0", () => {
    expect(formatCompact(1000)).toBe("1k");
    expect(formatCompact(1234)).toBe("1.2k");
    expect(formatCompact(5000)).toBe("5k");
    expect(formatCompact(5100)).toBe("5.1k");
    expect(formatCompact(5500)).toBe("5.5k");
    expect(formatCompact(12345)).toBe("12.3k");
  });

  it("abbreviates millions with M", () => {
    expect(formatCompact(1_000_000)).toBe("1M");
    expect(formatCompact(1_500_000)).toBe("1.5M");
  });
});

describe("installsJson", () => {
  it("returns the raw (un-abbreviated) count for tooling", () => {
    expect(installsJson(12345)).toEqual({ installs: 12345 });
    expect(installsJson(null)).toEqual({ installs: null });
  });
});

describe("badgeJson", () => {
  it("is a clean shields-endpoint badge with a compact message", () => {
    expect(badgeJson(5500)).toEqual({
      schemaVersion: 1,
      label: "installs",
      message: "5.5k",
      color: "#2563eb",
      labelColor: "#1f2937",
      style: "flat-square",
    });
  });

  it("degrades to a valid non-empty message when count unknown", () => {
    const b = badgeJson(null);
    expect(b.schemaVersion).toBe(1);
    expect(b.message).toBe("unknown");
    expect(b.color).toBe("lightgrey");
  });
});
