---
title: Release & Distribution Orchestration — Design Spec
status: approved-design
date: 2026-05-31
scope: TechMatrix-labs/{pythinker-code, homebrew-pythinker, pythinker-home}
provenance: multi-agent design workflow wf_620b356a-d6e (5 subsystem designs -> adversarial stress-tests -> synthesis -> completeness critic -> final merge); ground-truthed against live repos + PyPI on 2026-05-31
---

# Pythinker-code 3-Repo Release & Distribution Orchestration — Final Design Spec

**Scope:** TechMatrix-labs/{pythinker-code, homebrew-pythinker, pythinker-home}. Coherent evolution — no consolidation, no churn. Respects C1–C5. This is the approval-ready architecture; every punch-list item from the completeness critique is resolved inline (fixed, or justified out-of-scope in one line). Ground-truthed against the live repos on 2026-05-31.

---

## 1. Target Architecture Overview

```
                              ┌──────────────────────────────────────────────────────────────┐
                              │  SSOT = pyproject.toml:3  (the ONLY authoritative version)     │
                              │  scripts/release.py rewrites all derived files + uv.lock,       │
                              │  runs local gates, opens release/X.Y.Z PR  (never pushes main)  │
                              └───────────────────────────────┬──────────────────────────────┘
                                                              │ merge (CodeRabbit status=success, C2)
                                                              │ then human pushes tag(s): sub-pkg tags first, then vX.Y.Z
   ┌──────────────────────────────────────────────────────────▼───────────────────────────────────────────┐
   │                          TechMatrix-labs/pythinker-code  (PUBLIC, source of truth)                      │
   │                                                                                                         │
   │  on tag v* : release-cli ┃ linux-installer ┃ windows-installer ┃ homebrew-tap ┃ docker(P2) ┃ promote   │
   └───┬──────────────┬──────────────┬───────────────┬───────────────────┬─────────────────────┬───────────┘
       │ OIDC          │ GITHUB_TOKEN  │ GITHUB_TOKEN   │ App: tap-publisher │ GITHUB_TOKEN          │ App:
       │ (trusted pub) │ contents:write│ contents:write │ (per-run token)    │ packages:write (GHCR) │ release-bot
       ▼               ▼               ▼               ▼                    ▼                       ▼ (per-run)
  ┌─────────┐   ┌───────────────────────────────────┐  ┌──────────────────────┐  ┌────────────┐  ┌─────────────────┐
  │  PyPI   │   │  GitHub Release (~28 assets+.sha)  │  │ homebrew-pythinker   │  │  ghcr.io/  │  │ pythinker-home  │
  │ TestPyPI│   │  prerelease→(promote)→make_latest  │  │ (PUBLIC) Formula/*.rb│  │ pythinker- │  │ (PRIVATE site)  │
  │ (OIDC)  │   │  /releases/latest (prerelease-excl)│  │ App contents:write   │  │ code (P2)  │  │                 │
  └────┬────┘   └─────────────────┬─────────────────┘  └──────────────────────┘  └────────────┘  │ repository_     │
       │                          │                          ▲          ▲                          │ dispatch         │
       │ pip/pipx/uv              │ curl|sh, irm|iex,        │ scoop(P2)│ winget(P2 manual PAT)     │ sync-pythinker- │
       │ (core/host/review pins   │ in-app updater read here │ App:scoop│                           │ products        │
       │  resolve = BLOCKING)     │                          │ publisher│                           └────────┬────────┘
       ▼                          ▼                          │          │                                    │ own GITHUB_TOKEN
   end users                  end users               scoop-pythinker  microsoft/winget-pkgs                 │ (pull data)
                                                       (PUBLIC, P2)     (external, P2)                        ▼
                                                                                          sync-upstream-products.ts
                                                                                          pulls /releases/latest + raw@tag,
                                                                                          writes pythinkerCodeRelease.ts +
                                                                                          public/install.{sh,ps1} + version.json,
                                                                                          commit→push main ─► Dokploy build-from-source
                                                                                          (nixpacks → bun run server.ts) ─► pythinker.com
                                                                                                       ▲
                                                                                          daily cron 04:17 + drift reconcile (backstops)

  Nix: nix run github:TechMatrix-labs/pythinker-code  (P2: needs apps.default — currently UNVERIFIED; auth=none)

  AUTH EDGE SUMMARY (every cross-repo / privileged write):
    PyPI/TestPyPI ............ OIDC trusted publishing (no token)        [unchanged, GOOD]
    GH Release asset upload .. same-repo GITHUB_TOKEN contents:write     [unchanged, least-priv]
    promote flip ............. same-repo GITHUB_TOKEN contents:write     [unchanged]
    Homebrew tap write ....... App pythinker-tap-publisher (per-run)     [unchanged, the pattern]
    Site dispatch (×2 files) . App pythinker-release-bot (per-run)       [NEW P0 — replaces PAT]
    Scoop bucket write (P2) .. App pythinker-scoop-publisher (per-run)   [NEW, P2]
    GHCR push (P2) ........... same-repo GITHUB_TOKEN packages:write     [NEW, P2, OIDC-native]
    WinGet submit (P2) ....... fine-grained PAT, MANUAL workflow_dispatch [P2, deferred, isolated]
    core gh-pages docs ....... RETIRED (target 404); PAT deleted         [PAT eliminated]
    Site data pull ........... site's own GITHUB_TOKEN                   [unchanged, token-safe]
```

After P0+P1: **zero long-lived cross-repo PATs** on the release path. The only remaining PAT (WinGet, P2) is isolated to a manual, opt-in workflow.

---

## 2. The Unified Release Flow (end-to-end)

### Happy path

1. **Maintainer authors the narrative** (irreducible human step, C5): writes/moves the `## Unreleased` bullets in `CHANGELOG.md` describing this release, and writes the matching README "What's New" bullets. (The tool rewrites the *heading + version snippet + asset names*; the human writes prose — all in one PR, satisfying C4.)
2. **Maintainer runs** `python scripts/release.py --set-version X.Y.Z` (add `--bump-core A.B.C` / `--bump-host A.B.C` if a sub-package also moves). **There is intentionally no `--bump-review`** — see §3.
3. **Tool — Phase 1 (validate preconditions, fail loud, no writes):** clean tree; `git fetch origin` and assert local `main` == `origin/main` (kills the stale-base class); compute target, assert monotonic + semver; assert a `## Unreleased` section exists. If its body is empty → **warn, not abort** (a CI-only/docs patch release may legitimately have no shipped-code entry; the `changelog-entry-required.yml` gate already skips `release/*` PRs).
4. **Tool — Phase 2 (rewrite derived files, atomic):** `pyproject.toml:3`; if `--bump-*`, sub-package `version` + matching root pin `pythinker-core[contrib]==` (`pyproject.toml:28`) / `pythinker-host==` (`pyproject.toml:47`) in the same transaction; **regenerate `uv.lock`** (`uv lock`); promote `## Unreleased` → `## X.Y.Z (DATE)` in `CHANGELOG.md` + `docs/en/release-notes/changelog.md` (+ breaking-changes heading); rewrite README heading/snippet/asset-names + `packages/linux-installer/README.md` + `docs/en/guides/getting-started.md:47` `PythinkerSetup-X.Y.Z.exe`. Pyproject/sub-package writes use **tomlkit** (already a dep at `pyproject.toml:48`) **with a `tomllib` parse-back assertion** that the pin string re-reads to the intended version — not bare regex on the dependency-string array.
5. **Tool — Phase 3 (local gates = the same gates CI runs):** `check_version_tag.py`; `check_pythinker_dependency_versions.py` (**extended to also assert the `pythinker-review==0.1.0` pin matches `packages/pythinker-review` — §3**); README/CHANGELOG fixed-string greps (`grep -qF`, not unescaped-dot regex); `uv sync --frozen --all-extras --all-packages` (catches lock drift before push); `pytest tests/test_version_lockstep.py`. Any failure aborts **before** the branch leaves the laptop.
6. **Tool — Phase 4 (branch+PR, never main, C1):** `git switch -c release/X.Y.Z` → commit `chore(release): prepare X.Y.Z` → push → `gh pr create --base main`. Branch prefix `release/*` and title `chore(release)` are a **hard contract** with `changelog-entry-required.yml`'s skip logic (it guards on **both** the title `chore(release)*` at line 54 AND head branch `release/*` at line 57 — verified; documented + asserted in a test). Prints the post-merge tag command(s); when `--bump-*` was used, prints the ordered sequence: push **sub-package tags first** (`pythinker-core-A.B.C`, `pythinker-host-A.B.C`), wait for their OIDC publish jobs to land on PyPI, **then** `vX.Y.Z`.
7. **Reviewer** confirms CodeRabbit commit status == `success` on the PR head (C2, enforced by the existing merge-gate hook), merges.
8. **Maintainer pushes the tag(s)** (the deliberate last human action) in the printed order. For a pure code release: `git tag vX.Y.Z && git push origin vX.Y.Z`.
9. **CI fires (unchanged build topology):** release-cli (5-platform PyInstaller → GitHub Release as **prerelease**), linux-installer, windows-installer, homebrew-tap, [docker P2], and **promote-release**.
10. **promote-release polls BLOCKING channels only** (see §5 for the exact set): GitHub Release assets + **PyPI publication of `pythinker-code` AND of every pinned sub-package (`pythinker-core`, `pythinker-host`, `pythinker-review`)**. Homebrew is **removed** from the gate (§5). On all-ready → `PATCH prerelease=false, make_latest=true`. `/releases/latest` now serves X.Y.Z; `pip install pythinker-code==X.Y.Z` resolves all transitive pins. Ticks the readiness-issue rows.
11. **Separate `needs: promote` job** mints the `pythinker-release-bot` token and fires `repository_dispatch sync-pythinker-products` to pythinker-home (best-effort; not part of the promote success signal).
12. **pythinker-home** `sync-upstream-products.yml` pulls `/releases/latest` + `raw@<tag>`, writes `pythinkerCodeRelease.ts` + `public/install.{sh,ps1}` + `public/version.json`, commits, pushes main → Dokploy build-from-source → `bun run server.ts` → **pythinker.com live at X.Y.Z**.
13. **Every channel live:** PyPI (pip), GitHub Release (curl/irm/updater), Homebrew tap (best-effort, reconciled), website (best-effort, reconciled), [Docker/Scoop/Nix P2].

### Failure path (fail-loud, never silent-stuck)

- **Local gate fails (Phase 3):** tool aborts, nothing pushed. Maintainer fixes locally.
- **Sub-package pin lags PyPI:** the new blocking check (§5, item 10 above) keeps the release in `PRERELEASE` until `pythinker-core/host/review` pins all return 200 on PyPI — `/releases/latest` keeps serving last-good and `pip install pythinker-code==X` is never advertised against an unresolvable pin. This converts today's silent race into a tracked bottleneck row.
- **CI build job crashes / asset missing:** promote's bounded poll (80×30s ≈ 40 min, justified by emulated-arm64 long pole) exhausts → **FAILED_STUCK**: release **stays prerelease** (so `/releases/latest` keeps serving last-good — never stale-but-looks-live; this is *current* behavior at `promote-release.yml:152`, retained deliberately), readiness issue gets the **exact per-channel bottleneck** comment, Slack red alert with issue link (reusing the existing `notify-failure` job), job exits 1 (red CI). **No demotion to draft** (draft hides the partial assets needed for re-run). Re-run: fix/re-run the failing build workflow, then re-run promote (`workflow_dispatch tag=vX.Y.Z`) — re-enters CHECKING; PATCH is idempotent.
- **Site dispatch fails (missing/empty minted token):** the separate dispatch job goes red with Slack "**site sync failed — release IS promoted, /releases/latest is correct, self-heals via drift reconcile / daily cron**" (does NOT contaminate the promote success signal). **Empty minted token fails loud (`exit 1`)** — the old silent `::notice; exit 0` (`promote-release.yml:172-174`) is removed in both files.
- **Site mirrors stale source (Mode B, the 0.24.0 class):** served `version.json` ≠ `/releases/latest` → drift reconcile detects, re-dispatches, and on persistent drift across N cycles escalates to red Slack. (The App migration alone would NOT catch this — see §5.)

---

## 3. Version Single-Source-of-Truth (kill F3 sprawl)

**Source:** `pyproject.toml:3` `[project].version`. The installed package reads `importlib.metadata.version("pythinker-code")` (`constant.py:14`) — there is no `__version__` constant, so this is genuinely the only authoritative store.

**The SSOT→site chain (proves distribution + site consume the orchestrator's source):**
```
pyproject.toml:3 ─(release.py rewrite)→ release PR ─(check_version_tag gate)→ merge
   → human tag vX.Y.Z ─(CI)→ GitHub Release ─→ /releases/latest.tag_name
   → site sync writes public/version.json {pythinkerCode: X.Y.Z}  AND  brew formula version "X.Y.Z"  AND  scoop manifest
```

**Three derivation mechanisms (collapses F3's ~41 refs to 1 field + 1 narrative):**
- **(A) reads SSOT at build/run time — never edited:** installed-package runtime (`constant.py`), web bundle (`web/vite.config.ts:9`), web strict-gate (`scripts/build_web.py`), CI release version (`${REF#v}` from tag), Homebrew/Scoop generators (poll the release tag), Nix (`lib.importTOML ./pyproject.toml`), PyPI version badge (shields.io live).
- **(B) templated from SSOT — never edited:** `packages/windows-installer/{installer.iss,versioninfo.txt}` (substituted by `build.ps1 -Version`).
- **(C) rewritten by `release.py` from SSOT:** `pyproject.toml:3`; `uv.lock` (regenerated via `uv lock`); sub-package pyprojects + root pins (atomic with `--bump-*`); `CHANGELOG.md` + `docs/.../changelog.md` + `breaking-changes.md` headings (body preserved, C5); `README.md` heading/snippet/asset-names; `packages/linux-installer/README.md`; `docs/en/guides/getting-started.md:47`.
- **Documented exception:** `--version 0.27.0` *flag examples* in install-script comments + `getting-started.md:34` are NOT rewritten (they teach flag syntax; scripts resolve latest at runtime). The lockstep test asserts they're valid-semver *shape*, not equality.

**The `pythinker-review` sub-package (critique item 2 — DECIDED, fold-in + freeze):**
`pythinker-review==0.1.0` is a pinned runtime dep (`pyproject.toml:48`), a workspace member (`pyproject.toml:89`), and a `tool.uv.sources` workspace source (`pyproject.toml:97`) — but it has **no release workflow** and is not covered by `check_pythinker_dependency_versions.py` (which checks only core+host at lines 66-67). It escapes the entire anti-sprawl mechanism today. Decision: **freeze it at 0.1.0 AND enforce the freeze in all three guards.**
- `check_pythinker_dependency_versions.py` gains a third tuple `("pythinker-review", args.pythinker_review_pyproject)` so the pin and `packages/pythinker-review` version must agree.
- `tests/test_version_lockstep.py` includes `pythinker-review` in its pin-vs-version assertion.
- The promote PyPI-existence check (§5) treats `pythinker-review` identically to core/host: its pinned version must resolve on PyPI before the flip.
- **No `--bump-review` flag.** Review has no release workflow, so a CLI bump would have nothing to publish it and would break `pip install`. If review ever needs to move, that is a future phase that first adds a release workflow; until then the guards make the freeze *enforced*, not aspirational. (Verified 2026-05-31: `pythinker-review/0.1.0`, `pythinker-core/1.1.1`, `pythinker-host/1.0.0` all return PyPI 200 — the freeze is currently consistent and there is no live `pip install` break.)
- **`pythinker-sdk` is correctly out of scope:** it is a workspace member but is **not** a pinned runtime dependency of `pythinker-code` (absent from `[project].dependencies`), so it cannot strand a `pip install`. No guard needed.

**Lockstep test** (`tests/test_version_lockstep.py`, stdlib+tomllib, runs in CI test matrix on every PR): semver shape; **core/host/review pins == sub-package versions**; README has `What's New in X` + `pythinker-code==X`; README + linux-README + getting-started.md asset names (`PythinkerSetup-(semver).exe`, `*_(semver)_amd64.deb`, `*-(semver).x86_64.rpm`, `/releases/download/v(semver)/`) all == VERSION; CHANGELOG has `## X (`; install-script flag-examples are valid semver shape. Tests only assert relationships true on **every** main commit (never "a tag exists").

**Tool label correction:** `scripts/release.py` is **stdlib + shells out to git/gh/uv** (not stdlib-only). C3 permits this (CI/release tooling exemption); the shipped agent gains zero runtime deps.

---

## 4. Auth Topology (org-migration-proof)

**Canonical App inventory (3 Apps, all org-owned):**

| App / credential | Scope | Permissions | Secrets | Status |
|---|---|---|---|---|
| `pythinker-tap-publisher` | `homebrew-pythinker` only | contents:write, metadata:read | `HOMEBREW_TAP_APP_ID/_PRIVATE_KEY` (**leave at repo level — moving = churn**) | exists, unchanged |
| `pythinker-release-bot` | `pythinker-home` only | contents:write, metadata:read | `PYTHINKER_RELEASE_BOT_APP_ID/_PRIVATE_KEY` (org-level) | **NEW (P0)** — one App for **both** dispatch sites |
| `pythinker-scoop-publisher` | `scoop-pythinker` only | contents:write, metadata:read | `SCOOP_BUCKET_APP_ID/_PRIVATE_KEY` | **NEW (P2)** |

**Same-repo / OIDC (no App needed):** PyPI+TestPyPI (OIDC trusted publishing), all GitHub Release asset uploads + promote flip (same-repo `GITHUB_TOKEN` contents:write), GHCR push P2 (`GITHUB_TOKEN` packages:write), site data pull (site's own `GITHUB_TOKEN`).

**Decision — dedicated `pythinker-release-bot`, not broadening the tap App:** `homebrew-pythinker` is **public**, `pythinker-home` is **private**. A single key spanning that trust boundary means one leak compromises both; a dedicated key contains each leak to one trust domain and keeps `git log`/audit honest. Marginal cost is two org secrets + one install click.

**PATs eliminated:**
- `PYTHINKER_HOME_REPO_DISPATCH_TOKEN` → `pythinker-release-bot` (replaces it in **both** `promote-release.yml:168` AND `dispatch-pythinker-home-sync.yml:28`). Delete only after both files migrate + one green cycle.
- `PYTHINKER_CORE_PAGES_TOKEN` → **retired**. Target `PythinkerAI/pythinker-core` is a genuine 404 post-migration (and `TechMatrix-labs/pythinker-core` is also 404 — core exists only as a monorepo sub-package). **Drop the pdoc gh-pages step entirely** (`release-pythinker-core.yml:99-127`, including the PAT-skip swallow at lines 104-105) — Auth Option A. The VitePress docs are the docs surface and nothing user-facing has rendered there since the migration. (Option B is rejected: pdoc runs on core tags but `docs-pages.yml` deploys only on push-to-main, so it would silently deploy nothing.)

**Residual blast radius (stated honestly):** `contents:write` is the floor for `POST /dispatches` (there is no narrower fine-grained permission). A leaked ~1h `pythinker-release-bot` token could push commits to the private site, not merely dispatch. Mitigated by single-repo install + ~1h TTL + per-run minting. Receiver-side defense: `sync-upstream-products.yml` adds a job-level `if:` gating on `client_payload.source_repo == 'TechMatrix-labs/pythinker-code'` (cron/manual carry no payload → allowed; the sync workflow currently has only `if: failure()` on notify and no payload gate — this is genuinely net-new); payload fields are **never** interpolated into a `run:` shell line (injection vector — the sync derives everything from the live API by repo name).

---

## 5. Fail-Loud Reliability State Machine

**What is ALREADY current behavior (critique item 3 — do not re-build):** `promote-release.yml` already has a `notify-failure` Slack job (lines 188-200) and its bare `exit 1` (line 152) already leaves the release as **prerelease** (it never demotes to draft). So "stays-prerelease + Slack + red CI" is *current behavior*. The genuine net-new in this section is **only**: (a) the sub-package PyPI-existence blocking check, (b) per-channel bottleneck detail inside the Slack message, (c) the `release-readiness` tracking issue, and (d) removing Homebrew from the gate.

**Terminal states:** `PROMOTED` (success), `FAILED_STUCK` (loud failure, release retained as prerelease, tracking issue open, red CI). `DEGRADED` is transient (promoted but best-effort channel reconciling) and **never un-promotes**.

```
tag push → PRERELEASE (/latest = last good)
   → CHECKING (poll BLOCKING set: GH assets + PyPI(pythinker-code) + PyPI(core,host,review pins))
   ├─ all blocking ready → PATCH prerelease=false, make_latest → PROMOTED (/latest = X.Y.Z; pip fully resolvable)
   │      └─ [separate needs:promote job] best-effort site dispatch → (site live) or → DEGRADED
   └─ budget exhausted → FAILED_STUCK (stays PRERELEASE; per-channel bottleneck → issue comment +
          Slack + step-summary; exit 1) → fix/re-run build (or wait on lagging sub-pkg publish)
          → re-run promote → back to CHECKING
   DEGRADED → daily drift reconcile (tap formula != latest OR served version.json != latest)
          → re-dispatch/re-run (idempotent) → PROMOTED ; persistent N cycles → red Slack
```

**Blocking vs best-effort — discriminator "does it feed `/releases/latest` or pip?":**
- **BLOCKING (gate the flip):** GitHub Release assets; PyPI publication of `pythinker-code`; **PyPI resolvability of every pinned sub-package — `pythinker-core` 1.1.1, `pythinker-host` 1.0.0, `pythinker-review` 0.1.0** (critique item 1 + item 2, unified into one uniform "all pinned sub-packages resolve" check via `GET pypi.org/pypi/<pkg>/<pinned>/json == 200`). Today the poll checks only `pythinker-code/${version}` (`promote-release.yml:95`), so a near-simultaneous tag push can flip `/releases/latest` to PROMOTED while `pip install pythinker-code==X` 500s on a lagging `pythinker-core`. This is the single largest reliability gap and it is closed here.
- **BEST-EFFORT (report, never block):** Homebrew tap, website, [Docker/Scoop P2].
- **Change:** Homebrew is **release-blocking today** (`promote-release.yml:126-129` `&& homebrew_ready`). **Remove it from the gate.** Justification is **blast-radius, not symmetry**: a cross-repo tap push failure should not strand `/releases/latest`. The tap is reliably reconciled (its own flag-safe re-run) — best-effort is correct.

**Why prerelease is the complete gate:** all four "latest" consumers honor it — `install-native.sh` + updater `native.py` + site sync use REST `/releases/latest` (prerelease-excluding by contract); `install.ps1` explicitly skips `$release.prerelease` (`scripts/install.ps1:152`). So a stuck prerelease leaves every consumer on **last-good** — the failure is silent-stuck, not consumer-breakage. **Terminal failure = KEEP-PRERELEASE, never draft.**

**The two 0.24.0 modes (ONE story across §4/§5/§7):**
- **Mode A — credential breaks** (PAT owner leaves org). Defense: org-owned App (no user dependency, ~1h tokens) **+ fail-loud on empty minted token**.
- **Mode B — source identity goes stale** (owner/org literal baked into a sync URL builder; `raw.githubusercontent` doesn't follow transfer redirects). **0.24.0 was Mode B.** The daily cron did NOT save it (re-ran the same wrong owner). Defense: per-product owner config (already present, §7) + a new lockstep assertion + fixing the one residual hardcoded literal **+ served `version.json` drift detection** that turns a silent freeze into a loud tracked DEGRADED + re-dispatch. The App migration alone would NOT have caught 0.24.0.

**Idempotent re-runs:** PATCH flip (no-op if already promoted), PyPI `skip-existing`, tap flag-safe diff, dispatch naturally idempotent (commit-on-diff), readiness issue **upsert by REST exact-title list** (not search API — search is async-indexed and races duplicates). Per-tag `concurrency` + `cancel-in-progress:false` serializes tag-push and manual re-promote. **Guard:** never re-run a build workflow against an already-promoted release (it re-marks prerelease=true); reconcile detects `latest==version && prerelease==true` and re-flips. Reconcile auto-closes stale `release-readiness` issues older than `/latest`.

**Observability = ONE artifact:** a per-release `release-readiness` GitHub issue (now a 6-row checklist: GH assets, PyPI code, PyPI sub-package pins, tap, site `version.json`, [docker P2]) is both the "is X.Y.Z fully live?" pane and the failure-tracking artifact. (`promote` job needs `issues:write`.)

**Installer robustness (minimal):** `install-native.sh` — exponential backoff (4→120s, ≈6m) on asset-wait; keep REST `/releases/latest` (no prerelease-skip added — over-correction). `install.ps1` — fix the genuine `per_page=20` pagination cliff (`scripts/install.ps1:144`): hit `/releases/latest` first, **preserve the existing `.exe` + `.sha256` asset-pair guard** (`scripts/install.ps1:158`) and the `$release.prerelease` skip (line 152), paginated scan only as fallback; add matching backoff. Both keep SHA-256 verification (the real "half-published unreachable" guarantee).

**Monotonic guard correction (Trigger §5.4):** strict `version >= committed` **breaks rollback** (a yanked release legitimately lowers `/latest`) and misses higher-but-wrong-repo values. Replace with: **valid-semver tag that exists as a published non-prerelease release**. The served `version.json` exact-match is what catches Mode B.

**Ordering constraint (critique item 6):** `release-readiness-reconcile.yml` (the new Homebrew backstop) **must land before or in the same change set as Homebrew-gate-removal**. Otherwise there is a window where the tap has neither a promote gate nor a reconcile backstop. This is a hard P0 sequencing rule.

---

## 6. Broadened Distribution Matrix

| Channel | Produced | Stored | Auto-updated | Auth | Block? |
|---|---|---|---|---|---|
| **PyPI/TestPyPI** | wheel/sdist (+ core/host/review sub-pkgs) | PyPI | tag CI | OIDC | **BLOCKING** (code + all pinned sub-pkgs resolve) |
| **GitHub Release** | PyInstaller ×5 + installers + .sha256 | repo releases | tag CI | GITHUB_TOKEN | **BLOCKING** |
| **Homebrew tap** | `generate-formula.py` polls onedir tarballs | homebrew-pythinker | `homebrew-tap.yml` poll | App tap-publisher | best-effort |
| **Website** | sync.ts pulls latest+raw@tag | pythinker.com (Dokploy) | dispatch + cron + reconcile | App release-bot | best-effort |
| **Docker (GHCR)** P2 | `python:3.14-slim` + `pip install pythinker-code==${V}` (reuses PyPI wheel, C3-safe), multi-arch native amd64+arm64, push-by-digest, imagetools stitch, **ancestor-check** before `:latest` (`fetch-depth:0` + refuse-on-unknown-:latest) | `ghcr.io/TechMatrix-labs/pythinker-code` | `push: tags: v*` | GITHUB_TOKEN packages:write (**zero new secrets, best auth fit**) | best-effort |
| **Scoop** P2 | NEW `packages/scoop-bucket/generate-manifest.py` points at the **EXISTING** `pythinker-{v}-x86_64-pc-windows-msvc-onedir.zip` + its `.sha256` (verified produced by `release-pythinker-cli.yml`); `bin: pythinker\pythinker.exe`. Generator polls the **windows zip specifically** (NOT a clone of generate-formula.py's mac/linux NATIVE_TARGETS) | `TechMatrix-labs/scoop-pythinker` (PUBLIC, **org-owned**) `bucket/pythinker-code.json` | `scoop-bucket.yml` poll | App scoop-publisher (**org-owned**) | best-effort |
| **Nix** P2 | flake builds via uv2nix with `packages.default = pythinker-code` (`flake.nix:129`) — **but there is NO `apps` stanza** (verified), so `apps.default` + `nix build .#default`/`nix run` CI check is genuine net-new; `nix run github:…` working is **UNVERIFIED** until `apps.default` exists; monthly `update-flake-lock` PR | git repo (no artifact store); version from `pyproject.toml` | flake.lock cron PR | none | build-time CI gate |
| **WinGet** P2-late | `wingetcreate update ... --submit` | `microsoft/winget-pkgs` fork | **MANUAL `workflow_dispatch` only** (hard gate) | fine-grained PAT `WINGET_SUBMIT_TOKEN` (isolated; can't be an App for external-repo PRs) | never |
| **AUR** | DEFER | — | — | SSH key (re-introduces non-App secret) | — |

**Required code change (don't ship non-self-updating channels without it):** `src/pythinker_code/ui/shell/update.py` — add a `PYTHINKER_MANAGED=<channel>` env read at the top of `_detect_upgrade_command()` (mirrors hermes `HERMES_MANAGED`); Docker/Nix set it, Scoop/WinGet manifests set it → channel-native upgrade hint. **Brew must NOT set `PYTHINKER_MANAGED`** (keep its existing path-sniff so behavior is unchanged); **mandatory regression test** that brew still maps to `['brew','upgrade','pythinker-code']` (the `.pythinker-native` marker means brew also trips `is_native_build()`; precedence is load-bearing). This change ships in P1 as prep so P2 channels are not released non-self-updating.

**C4 for new channels:** README install snippets MUST be **version-less** (`scoop install pythinker-code`, `docker run ghcr.io/techmatrix-labs/pythinker-code`, `nix run github:TechMatrix-labs/pythinker-code`) so they never enter the F3 sprawl set.

**Recommended adoption order:** **Docker (GHCR)** → **Scoop** → **Nix polish** → WinGet (manual) → defer AUR. Rationale: Docker = highest reach-per-fragility (OIDC auth, reuses wheel, self-protecting ancestor-check); Scoop = closes the Windows gap as a mechanical clone of the trusted tap pattern; Nix needs the `apps.default` net-new but the package build already works.

---

## 7. Cross-Repo Trigger + Site Coupling + Deploy

**Chosen model: hybrid (formalize the existing one — no churn).** Trigger and data source failed for different reasons, so they get different fixes:
- **Data source → pull (keep).** Site fetches with its own `GITHUB_TOKEN` (token-migration-safe). Do not push data via dispatch payload (would be a second source of truth + injection surface).
- **Trigger → dispatch, App-authed (finish migration).** Keep `repository_dispatch` fast-path; migrate auth PAT → `pythinker-release-bot` in **both** files. Fire from a separate `needs:promote` job (§5).
- **Backstop → daily cron 04:17 (keep)** + drift reconcile (§5).

**Dispatch `tag` semantics differ — handle both (critique item 5, RECONCILED):** the two dispatch sources send different `tag` values:
- `promote-release.yml:170` sends `vX.Y.Z` (the release tag).
- `dispatch-pythinker-home-sync.yml:30` sends `github.sha` (a 40-char commit SHA) on the install-script/README push path.

The discriminator that matters in `sync-upstream-products.ts`:
- **Raw README/script fetch** (`raw.githubusercontent.com/owner/repo/<ref>/path`) accepts **either** a `vX.Y.Z` tag **or** a 40-char SHA — so the SHA push-path is fine here. Pinning raw fetch to the dispatched `<ref>` (instead of `main`) ensures the served installer matches the source at that ref.
- **Release-asset download URLs** (`/releases/download/<tag>/...`, plus the deb/rpm/exe URLs + shas in `pythinkerCodeRelease.ts`) **must be built from the live API's `release.tag_name`, never from the payload ref** — a SHA there 404s. The sync already derives release data from `/releases/latest`; this codifies that the payload `tag` is used only for raw-source pinning and **never** for constructing asset URLs.

**Deploy chain (the commit-push IS the deploy trigger):**
```
release → promote → dispatch → sync-upstream-products.ts writes files → git push main
   → Dokploy build-from-source (nixpacks → bun run server.ts: serves dist/ + bun:sqlite install-counter) → pythinker.com
```

**Deploy resolution (F5):** **Canonical = Dokploy build-from-source.** GitHub Pages is **disqualified** — `server.ts` needs a runtime + SQLite + POST endpoint. GHCR+Watchtower path is **provably dead** (no image since `docker.yml` deleted; `deploy/.env.example` `SITE_IMAGE` points at the wrong org `mohamed-elkholy95`). **Retire** (after confirming the live host runs Dokploy, not compose): `docker-compose.yml`, `docker-compose.private-ghcr.yml`, `deploy/traefik/`, Watchtower + all GHCR refs, rewrite `deploy/README.md` around Dokploy. **Keep:** `Dockerfile` (documented single-container fallback), `nixpacks.toml`, `server.ts`. **State the dependency:** the deploy chain relies on `pythinker-home` main being unprotected (verified) so the workflow can push; if it's ever protected, exempt `github-actions[bot]` or the chain breaks.

**Install-script locations — distinguish code-repo sources from site mirrors (critique item 7):**
- **Code repo (KEEP — they are dispatch triggers):** `scripts/install.ps1` + `scripts/install-native.sh` are the **source** scripts; `dispatch-pythinker-home-sync.yml` watches them (`paths:` lines 16-17). Do **not** delete these.
- **Site repo (`git rm` the dead mirrors):** the canonical served pair is **`public/install.sh` + `public/install.ps1`** (the sole Vite-served dir, confirmed kept). The 3 dead, git-tracked mirrors — `scripts/install.ps1`, `web/public/install.ps1`, `docs/public/install.ps1` (all verified tracked + byte-identical) — get `git rm`'d and dropped from `installMirrors[].targetPaths`.

**0.24.0 root-cause fix (Mode B) — re-scoped to what is actually net-new (critique item 4):** the per-product `owner`/`repo` config block **already exists** in `sync-upstream-products.ts` (lines 82-83 for the AI product `owner:"mohamed-elkholy95", repo:"Pythinker-ai"`; lines 98-99 for `TechMatrix-labs/pythinker-code`). Do **NOT** "create the config block" (overstated) and do **NOT** collapse to a single `ORG` const (would break the AI product, owner `mohamed-elkholy95`, a different org from code's `TechMatrix-labs`). The real residual risk is two things the config block does not cover:
1. A **hardcoded literal at line 366**: `readme.replaceAll("github.com/mohamed-elkholy95/Pythinker/releases", "github.com/mohamed-elkholy95/Pythinker-ai/releases")` — bypasses the config block. **Fix:** derive both sides from the product's `owner`/`repo` config, or drop the rewrite if it's a migration vestige.
2. **No assertion** that each product's `owner`/`repo`/derived URLs/`brewCommand` agree. **Fix:** add a lockstep/typecheck assertion over the existing config so a stale literal fails loudly.

Add a **`.sha256` sidecar existence check** (right-sized: defense-in-depth for the cron-mid-upload race; promote already gates sidecars on the normal path). **Circular dependency is cosmetic** — `pythinker.com/install.sh` appears only in installer comments/fallback text; real downloads target `github.com/.../releases/latest/download`. Add a documented raw-GitHub `<tag>` fallback line to the installer headers.

---

## 8. OLD → NEW Replacement Table

| # | OLD mechanism | NEW / disposition |
|---|---|---|
| 1 | Manual ~18-file version bump (F3) | `scripts/release.py` rewrites all column-C files + `uv.lock` from `pyproject.toml:3` |
| 2 | Manual sub-package pin sequencing (core+host) | `--bump-core/--bump-host` write sub-pkg version + root pin atomically; gate verifies pre-push; tool prints sub-pkg-tags-first order |
| 3 | `pythinker-review==0.1.0` escapes dep-check/lockstep/promote (F3 hole) | Folded into all 3 guards + frozen at 0.1.0 (no `--bump-review`, no release workflow); sdk explicitly out of scope (unpinned) |
| 4 | No version-drift safety net | `tests/test_version_lockstep.py` (CI, every PR) + tomlkit + tomllib parse-back assertion |
| 5 | Manual "update_files" prose in release SKILL | Repoint `.agents/skills/release/SKILL.md` at `scripts/release.py` |
| 6 | Site-dispatch PAT in `promote-release.yml:168` + `dispatch-pythinker-home-sync.yml:28` (F2) | App `pythinker-release-bot`, per-run token, **both** files |
| 7 | Silent `::notice; exit 0` on missing token (0.24.0-Mode-A swallow, `promote-release.yml:172-174`) | Fail loud `exit 1` on empty minted token, both files |
| 8 | `PYTHINKER_CORE_PAGES_TOKEN` → 404 `PythinkerAI/pythinker-core` (`release-pythinker-core.yml:99-127`) | Retire step + delete PAT (VitePress is the docs surface) |
| 9 | promote PyPI poll checks only `pythinker-code/${version}` (`:95`) → sub-pkg publish race breaks `pip install` (F1) | BLOCKING check: core+host+review pinned versions all 200 on PyPI before flip |
| 10 | Homebrew as hard promote-gate member (`:126-129`, F1 blast radius) | Removed from gate → best-effort + drift reconcile (reconcile must land first, §5) |
| 11 | promote bottleneck framing | Slack `notify-failure` (`:188`) + prerelease-retention (`:152`) **already exist**; net-new = per-channel bottleneck detail + `release-readiness` issue + Homebrew-gate removal |
| 12 | Site dispatch as promote's last step (red = "promotion failed") | Separate `needs:promote` job; distinct "site sync failed, release promoted" Slack |
| 13 | "Daily cron is the only safety net" (implicit, F4) | Explicit `release-readiness-reconcile.yml` (drift detect + re-dispatch + alert + close issue) |
| 14 | Site mirrors README/scripts from `main` (can lead binaries) | Pin raw fetch to dispatched `<ref>` (tag OR sha); asset URLs always from API `tag_name` |
| 15 | 4 install.ps1 copies in site (3 dead, git-tracked) | `git rm` the 3 site mirrors; canonical `public/install.{sh,ps1}`. Code-repo `scripts/install.{ps1,sh}` KEPT (dispatch triggers) |
| 16 | Hardcoded `replaceAll(...mohamed-elkholy95/Pythinker/releases...)` at sync-TS:366 (0.24.0 Mode B) | Derive from existing per-product config (:82-99) + add lockstep assertion (config block already exists — not net-new) |
| 17 | No deterministic served-version signal | `public/version.json` emitted by sync; drift check exact-matches it |
| 18 | GHCR+Watchtower+Traefik compose (orphaned, wrong-org image) | Retire after host-confirm; canonical = Dokploy build-from-source |
| 19 | install.ps1 `per_page=20` pagination cliff (`:144`) | `/releases/latest`-first + asset-pair guard (`:158`) + prerelease skip (`:152`) + backoff |
| 20 | Flat 6×10s installer asset-wait | Exponential backoff (≈6m cap), both installers |
| 21 | Windows = manual .exe / irm\|iex only | + Scoop bucket (P2) pointing at existing onedir zip |
| 22 | No container/Nix/WinGet distribution; Nix has no `apps` stanza | + GHCR (P2), Nix `apps.default` net-new + CI (P2), WinGet manual (P2-late); AUR deferred |

---

## 9. Phased Migration Roadmap

### P0 — Quick wins (low risk, high value; fixes F2 + the F1 sub-package race + the real 0.24.0 class)
**Scope:** (a) Create org App `pythinker-release-bot` + org secrets; migrate **both** dispatch files to App token **and** fail-loud-on-empty (auth fix + fail-loud fix are the same edit). (b) Receiver `if:` source-repo gate in `sync-upstream-products.yml`. (c) Remove dead core-pages gh-pages step + delete `PYTHINKER_CORE_PAGES_TOKEN`. (d) promote-release: **add the sub-package PyPI-existence blocking check (core+host+review)**, drop Homebrew from gate, per-channel bottleneck detail in the existing Slack job, `issues:write` + `release-readiness` issue, dispatch as separate `needs:promote` job, asset URLs from API `tag_name` only. (e) **Mode-B fix**: `public/version.json` emit (pythinker-home) + lockstep assertion over the existing per-product config + fix the sync-TS:366 literal + pin raw fetch to dispatched ref (tolerate tag OR sha); `git rm` the 3 dead **site** install.ps1 mirrors (keep code-repo source scripts). (f) `release-readiness-reconcile.yml` (drift + alert + issue close) — **lands before/with the Homebrew-gate removal in (d)**. (g) Installer backoff + `install.ps1` pagination fix.
**Risk:** Low (CI/site only; no agent runtime change; no branch-protection change). **Reversibility:** High (keep PAT until both files green + one cycle; revert is a workflow revert). **Effort:** ~**3 days** across two repos + 3 PRs (code, code, home) — revised up from the optimistic ~1.5–2 day estimate, given the org App + 2 workflow rewrites + the new blocking check + receiver gate + `version.json` + reconcile workflow + per-product lockstep + 2 installer fixes.
*Note:* P0 fixes BOTH 0.24.0 modes and the `pip install` race only because (d)'s sub-pkg check and (e)'s `version.json`/literal fix are included — App migration alone (a) covers neither Mode B nor the publish race.

### P1 — Structural (release tool + single-source; finishes F3)
**Scope:** `scripts/release.py` (stdlib + git/gh/uv) with all 4 phases incl. `uv lock` regen + `uv sync --frozen` local gate + tomlkit + tomllib parse-back; `tests/test_version_lockstep.py` covering **core+host+review pins**; extend `check_pythinker_dependency_versions.py` with the review tuple; getting-started.md:47 into column-C + test; ensure `## Unreleased` anchors; repoint release SKILL; document the `release/*` + `chore(release)` contract with `changelog-entry-required.yml`. Add `PYTHINKER_MANAGED` env to `update.py` + brew-regression test (prep for P2 channels).
**Risk:** Low-medium (tool runs locally before any push; gates mirror CI; no workflow topology change). **Reversibility:** High (additive; manual bump still works if tool unused). **Effort:** ~2–3 days incl. tests + a dry-run release rehearsal.

### P2 — Breadth (new channels; broaden distribution)
**Scope, in order:** (1) Docker/GHCR (`Dockerfile` + `docker.yml`, ancestor-check, `GITHUB_TOKEN`); (2) Scoop (`scoop-pythinker` **org repo** + `pythinker-scoop-publisher` **org App** + `generate-manifest.py` polling the windows zip + `scoop-bucket.yml`); (3) Nix (`apps.default` net-new + `nix build .#default`/`nix run` CI + monthly `update-flake-lock` PR); (4) WinGet (manual `workflow_dispatch`, isolated PAT) — last; AUR deferred. Each new channel: version-less README snippet (C4), `PYTHINKER_MANAGED` set, best-effort (never gates promote).
**Risk:** Medium (new repos/Apps/secrets; all best-effort so they can't worsen F1). **Reversibility:** High (each channel is an independent additive workflow; delete to remove). **Effort:** Docker ~1 day, Scoop ~1.5 days, Nix ~0.5 day, WinGet ~0.5 day — adopt incrementally, one PR each.

**Cross-phase invariants:** every PR goes branch → PR → checks pass → CodeRabbit `success` (C2) → merge → (release PRs) tag (C1); no direct main push; no new agent runtime dep (C3); README/badges move with the bump (C4); authored CHANGELOG narrative preserved, contributor footer only as release-notes addendum (C5).

---

## Punch-list disposition (every critique item resolved)

| # | Critique item | Disposition |
|---|---|---|
| **1** | Sub-package→PyPI publish race unguarded | **FIXED** §2 step 10, §5 BLOCKING set, §6 table, §8 row 9, §9 P0(d) — new blocking check core+host+review resolve on PyPI before flip |
| **2** | `pythinker-review==0.1.0` escapes anti-sprawl | **FIXED + DECIDED** §3 — folded into all 3 guards + frozen (no `--bump-review`); sdk justified out of scope (unpinned) |
| **3** | F1 fail-loud net-new overstated | **REFRAMED** §5 + §8 row 11 — Slack (`:188`) + prerelease-retention (`:152`) already exist; net-new = bottleneck detail + issue + gate removal |
| **4** | Mode-B config block already exists | **RE-SCOPED** §7 + §8 row 16 — net-new is lockstep assertion + the line-366 literal, not "create config block" |
| **5** | Two dispatch sources send different `tag` (tag vs sha) | **RECONCILED** §7 — raw fetch tolerates both; asset URLs always from API `tag_name` |
| **6** | P0 sequencing hazard + optimistic estimate | **FIXED** §5 ordering rule (reconcile before gate-removal) + §9 P0 estimate → ~3 days |
| **7** | Code-repo source scripts vs site mirrors conflated | **FIXED** §7 + §8 row 15 — `git rm` only the 3 site mirrors; keep code-repo `scripts/install.{ps1,sh}` (dispatch triggers) |
| Nix | "Nix already works" overstated | **SOFTENED** §1 + §6 + §8 row 22 — `apps.default` net-new, `nix run` UNVERIFIED until added |

C1–C5 confirmed complete: C1 (release.py opens `release/X.Y.Z` PR, human tags post-merge); C2 (existing merge-gate hook); C3 (release.py is CI tooling, shipped agent gains zero deps); C4 (version-less new-channel snippets + lockstep-enforced README strings, bump in same change set); C5 (`## Unreleased`→`## X.Y.Z (DATE)` preserves body, contributor footer addendum only).

**Files referenced (absolute paths):**
- `/home/ai/Projects/pythinker-code-main/pyproject.toml` (SSOT `:3`; pins `:28` core, `:47` host, `:48` review; workspace `:89`; sources `:97`)
- `/home/ai/Projects/pythinker-code-main/scripts/check_pythinker_dependency_versions.py` (`:66-67` core+host only — extend for review)
- `/home/ai/Projects/pythinker-code-main/.github/workflows/promote-release.yml` (`:95` PyPI poll, `:126-129` homebrew gate, `:152` exit/prerelease, `:168-186` dispatch PAT, `:172-174` silent skip, `:188-200` Slack)
- `/home/ai/Projects/pythinker-code-main/.github/workflows/dispatch-pythinker-home-sync.yml` (`:16-17` watched paths, `:28` PAT, `:30` sends `github.sha`)
- `/home/ai/Projects/pythinker-code-main/.github/workflows/changelog-entry-required.yml` (`:54` title skip, `:57` branch skip)
- `/home/ai/Projects/pythinker-code-main/.github/workflows/release-pythinker-core.yml` (`:99-127` pdoc gh-pages step to retire)
- `/home/ai/Projects/pythinker-code-main/flake.nix` (`:129` `packages.default`; NO `apps` stanza)
- `/home/ai/Projects/pythinker-code-main/scripts/install.ps1` (`:144` per_page=20, `:152` prerelease skip, `:158` asset-pair guard)
- `/home/ai/Projects/pythinker-site/site/scripts/sync-upstream-products.ts` (`:82-83`/`:98-99` per-product owner config, `:366` hardcoded `replaceAll` literal)
