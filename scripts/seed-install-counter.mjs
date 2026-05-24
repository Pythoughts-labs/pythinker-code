#!/usr/bin/env node
// One-time backfill: seed the D1 counter from the last N days of bot-filtered
// /install.sh + /install.ps1 fetches in Cloudflare GraphQL Analytics.
//
// Usage:
//   CF_API_TOKEN=... CF_ZONE_TAG=... node scripts/seed-install-counter.mjs --dry-run
//   CF_API_TOKEN=... CF_ZONE_TAG=... node scripts/seed-install-counter.mjs        # writes via wrangler
//   node scripts/seed-install-counter.mjs --start 1000                            # manual fallback, no API
//
// Caveat: CF analytics dataset availability/lookback/sampling vary by plan;
// the seed is approximate. Use --start when analytics are unavailable.
import { execFileSync } from "node:child_process";

const args = process.argv.slice(2);
const dryRun = args.includes("--dry-run");
const startIdx = args.indexOf("--start");
const manualStart = startIdx >= 0 ? Number(args[startIdx + 1]) : null;
const DAYS = 30;

// Mirrors src/ua.ts — keep in sync.
const INSTALL_UA = /(^curl\/)|(^Wget\/)|(PowerShell)/i;

const QUERY = `query($zone:String!,$since:Time!,$until:Time!){
  viewer{zones(filter:{zoneTag:$zone}){
    httpRequestsAdaptiveGroups(
      limit:10000,
      filter:{datetime_geq:$since,datetime_leq:$until,
        clientRequestPath_in:["/install.sh","/install.ps1"],
        clientRequestHTTPMethodName:"GET"}
    ){count dimensions{userAgent}}
  }}}`;

async function queryDay(token, zone, since, until) {
  const r = await fetch("https://api.cloudflare.com/client/v4/graphql", {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ query: QUERY, variables: { zone, since, until } }),
  });
  const data = await r.json();
  if (data.errors?.length) throw new Error(data.errors[0].message);
  const groups = data.data.viewer.zones[0]?.httpRequestsAdaptiveGroups ?? [];
  return groups
    .filter((g) => INSTALL_UA.test(g.dimensions.userAgent ?? ""))
    .reduce((sum, g) => sum + g.count, 0);
}

// Free-plan analytics caps each query at a 1-day range and retains only a short
// window, so query day-by-day and tolerate per-day gaps (skip days that error).
async function fetchAnalyticsCount() {
  const token = process.env.CF_API_TOKEN;
  const zone = process.env.CF_ZONE_TAG;
  if (!token || !zone) throw new Error("CF_API_TOKEN and CF_ZONE_TAG are required (or use --start N)");

  let total = 0;
  let counted = 0;
  for (let d = 0; d < DAYS; d++) {
    const until = new Date(Date.now() - d * 864e5).toISOString();
    const since = new Date(Date.now() - (d + 1) * 864e5).toISOString();
    try {
      total += await queryDay(token, zone, since, until);
      counted++;
    } catch (e) {
      console.warn(`  (day -${d} unavailable: ${String(e.message).slice(0, 60)})`);
    }
  }
  console.log(`Summed ${counted}/${DAYS} day(s) of available analytics.`);
  return total;
}

const seed = manualStart != null ? manualStart : await fetchAnalyticsCount();
console.log(`Computed seed value: ${seed}`);

if (dryRun) {
  console.log("--dry-run: not writing.");
  process.exit(0);
}

execFileSync(
  "npx",
  ["wrangler", "d1", "execute", "install_counter", "--remote",
   "--command", `UPDATE counter SET n = ${Number(seed)} WHERE id = 1`],
  { cwd: "packages/install-counter-worker", stdio: "inherit" },
);
console.log(`Counter seeded to ${seed}.`);
