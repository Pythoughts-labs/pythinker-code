# Install Downloads Counter — Design

**Date:** 2026-05-24
**Status:** Approved (brainstorming) — pending implementation plan

## Problem

Pythinker is installed via `curl -fsSL https://pythinker.com/install.sh | bash`
(and `irm https://pythinker.com/install.ps1 | iex` on Windows). There is no
count of how many times the install script is fetched. We want a **bot-filtered
fetch count**, surfaced as a **README badge** and a **raw JSON API endpoint**.

## Constraints & key facts

- **Cloudflare fronts the VPS.** `pythinker.com` is proxied by Cloudflare; the
  origin is a self-hosted VPS that serves the script (backed by
  `scripts/install-native.sh`).
- **Edge caching makes origin logs useless for counting.** The install endpoint
  is served with `Cache-Control: public, max-age=300, s-maxage=900,
  stale-if-error=86400`. Most fetches are served from Cloudflare's edge cache
  and never reach the VPS, so VPS access logs would massively undercount. The
  count **must** happen at the edge, in a Worker that runs on every request
  before cache.
- **Vanity metric, not audited.** UA-based bot filtering blocks honest browsers
  and crawlers, but not a deliberate `curl -A 'curl/8.5.0'` loop. This counter
  is accepted as a vanity/marketing number, not a tamper-resistant metric. This
  limitation is intentional and documented.

## Chosen approach

A Cloudflare Worker bound to the install + API routes increments an atomic D1
counter on each non-bot fetch, then serves the script bytes from a DNS-only
origin hostname. The badge and JSON API read the same counter.

### Architecture

```
curl/irm ──> CF edge ──> Worker(/install.sh, /install.ps1)
                           │  UA bot-filter (curl/wget/powershell ⇒ real install)
                           │  ctx.waitUntil(D1: UPDATE counter SET n=n+1)  ← fail-open, non-blocking
                           └─ fetch ORIGIN_HOST/<script>  (edge-cached, stale-if-error)
shields.io ─> /api/installs/badge ─> D1 SELECT n ─> {schemaVersion,label,message,color}
tooling   ─> /api/installs        ─> D1 SELECT n ─> {"installs": N}
```

The Worker never fetches its own proxied route (which would recurse). It fetches
a **DNS-only (grey-cloud)** `origin.pythinker.com` pointing at the VPS, keeping
the VPS as the single source of truth for the script bytes.

## Components

- **`packages/install-counter-worker/`** — new Worker package, mirroring the
  conventions of `examples/feedback-worker/` (TypeScript, `wrangler.jsonc`,
  `Env` interface, `export default { fetch }`).
  - **`wrangler.jsonc`** — routes for `pythinker.com/install.sh`,
    `pythinker.com/install.ps1`, `pythinker.com/api/installs`,
    `pythinker.com/api/installs/badge`; one D1 binding `DB`; var
    `ORIGIN_HOST = "origin.pythinker.com"`.
  - **`src/index.ts`** — request router:
    - install routes → bot-filter, `ctx.waitUntil` increment, serve from origin
    - api routes → read counter, return JSON
  - **`package.json`** — `dev` / `deploy` scripts, `wrangler` + `typescript`
    devDeps (match feedback-worker versions).
- **D1 database `install_counter`** — single-row counter:
  ```sql
  CREATE TABLE counter (id INTEGER PRIMARY KEY, n INTEGER NOT NULL DEFAULT 0);
  INSERT INTO counter (id, n) VALUES (1, 0);
  ```
- **`scripts/seed-install-counter.mjs`** — one-time backfill. Queries the
  Cloudflare GraphQL Analytics API (`httpRequestsAdaptiveGroups`) for the last
  ~30 days of bot-filtered `/install.sh` + `/install.ps1` requests and writes
  the result as the starting `n`. Requires a read-only CF analytics API token,
  passed via env var, never committed.
- **README badge** — one new shields.io `endpoint` badge next to the existing
  Downloads badge:
  `https://img.shields.io/endpoint?url=https://pythinker.com/api/installs/badge`.

## Data flow & bot filter

- Real installs send `User-Agent` of `curl/*`, `Wget/*`, or PowerShell
  (`WindowsPowerShell`, `PowerShell`). Only these are counted; browsers,
  Googlebot, uptime monitors, etc. are skipped. The matcher is a single regex
  constant, unit-tested.
- Increment runs as
  `ctx.waitUntil(env.DB.prepare("UPDATE counter SET n = n + 1 WHERE id = 1").run())`
  — executed after the response is returned, so it never delays or breaks the
  install pipe. `UPDATE … n = n + 1` is atomic in D1, so concurrent fetches do
  not race.
- `/api/installs` → `{"installs": N}`.
- `/api/installs/badge` → `{"schemaVersion": 1, "label": "installs",
  "message": "12,345", "color": "blue"}` (thousands-formatted message), served
  with `Cache-Control: public, max-age=300`.

## Error handling (fail-open is the rule)

- **D1 write throws** → swallowed inside `waitUntil`; the install response is
  unaffected. A counter outage must never break installs.
- **Origin fetch fails** → serve from `caches.default` to replicate today's
  `stale-if-error=86400`. A VPS outage must not break `curl | bash` when
  Cloudflare already holds the same bytes.
- **D1 read fails on `/api/*`** → return `200` with `message: "unknown"` / grey
  color for the badge (keeps the shields.io payload valid) and
  `{"installs": null}` for the JSON endpoint.

## Testing

- **Unit:** UA classifier — `curl/8.5.0`, `Wget/1.21`, PowerShell ⇒ counted;
  Chrome, Googlebot, empty UA ⇒ skipped.
- **Unit:** badge JSON shape + thousands formatting; `/api/installs` shape.
- **Behavior:** simulated D1 throw ⇒ install response still `200` with script
  bytes (fail-open).
- **Behavior:** origin fetch targets `ORIGIN_HOST`, never the proxied route
  (loopback guard).
- **Integration:** `wrangler dev` with local D1 — curl each route, assert the
  counter increments for a `curl` UA and does not for a browser UA.

## Out of scope (logged, not built)

- Per-OS / daily breakdowns (single total counter only).
- Unique-install dedup (raw fetch count, not distinct hosts).
- Completed-install beacons (counts fetches, not successful installs).
- A live number rendered on pythinker.com (badge + API only).

## Open operational tasks (for the plan, not the code)

- Create DNS-only `origin.pythinker.com` → VPS.
- Create the D1 database and bind it; run the schema migration.
- Provision a read-only CF analytics API token for the seed script.
- Run the seed script once before announcing the badge.
