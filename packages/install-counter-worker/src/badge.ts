export function installsJson(count: number | null) {
  return { installs: count };
}

// pepy-style abbreviation: 5000 -> "5k", 5100 -> "5.1k", 1.5e6 -> "1.5M".
// One decimal, trailing ".0" dropped; values under 1000 stay as integers.
export function formatCompact(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return trim(n / 1000) + "k";
  return trim(n / 1_000_000) + "M";
}

function trim(x: number): string {
  const r = Math.round(x * 10) / 10;
  return Number.isInteger(r) ? String(r) : r.toFixed(1);
}

export function badgeJson(count: number | null) {
  if (count == null) {
    return { schemaVersion: 1, label: "installs", message: "unknown", color: "lightgrey", style: "flat-square" };
  }
  return {
    schemaVersion: 1,
    label: "installs",
    message: formatCompact(count),
    color: "#2563eb",
    labelColor: "#1f2937",
    style: "flat-square",
  };
}
