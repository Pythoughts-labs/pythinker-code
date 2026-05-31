# P0 — Quick Wins (Release Orchestration) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Migrate the cross-repo release auth to an org-owned GitHub App, make `promote-release.yml` fail loud (block the prerelease→latest flip until every pinned sub-package resolves on PyPI; drop Homebrew from the gate behind a new drift-reconcile backstop), and fix the site sync's 0.24.0-class Mode-B bugs (stale source literal, missing served-version signal, dead install-script mirrors), plus harden both native installers.

**Architecture:** Three pull-requests across two repos. **PR-code-1** carries the non-sequencing-entangled code-repo edits (dispatch-file App migration + fail-loud, retire the dead pdoc gh-pages step, installer backoff/pagination). **PR-code-2** carries `release-readiness-reconcile.yml` (NEW) *and* all `promote-release.yml` edits in the same change set, so the hard rule "reconcile lands before/with Homebrew-gate removal" (§5) is satisfied atomically. **PR-home-3** carries the pythinker-home site edits (receiver source-repo gate, `public/version.json` emit + drift, the line-366 literal fix, ref-pinned raw fetch, `git rm` of 3 dead mirrors, deploy retirement). The shipped agent gains zero runtime deps (C3); every change is branch→PR→CodeRabbit-success→merge (C1/C2).

**Tech Stack:** GitHub Actions (bash + `gh api` + `jq` + `curl`), `actions/create-github-app-token@v2.2.2` (the reference pattern at `homebrew-tap.yml:79-86`), TypeScript on Bun 1.3.x with the built-in `bun:test` runner (zero new JS deps), `actionlint` (workflow lint), `shellcheck` (bash lint), PowerShell `PSScriptAnalyzer` (manual).

---

## Prerequisites (manual / operator)

These touch admin/secrets/outward-facing services. They are **operator actions**, not code steps. Do them in this order; PR-code-1, PR-code-2 dispatch verification, and the PAT deletions depend on them.

- [ ] **OP-1 — Create the org-owned GitHub App `pythinker-release-bot`.** In the GitHub UI: `https://github.com/organizations/TechMatrix-labs/settings/apps/new`. Name `pythinker-release-bot`. Homepage URL `https://github.com/TechMatrix-labs/pythinker-code`. Uncheck "Webhook → Active". Repository permissions: **Contents: Read and write**, **Metadata: Read-only** (Metadata auto-selects). "Where can this GitHub App be installed?" → **Only on this account**. Create. On the App's page, **Generate a private key** (downloads a `.pem`) and note the numeric **App ID**.
  - *Why an App and not the PAT:* `homebrew-pythinker` is public, `pythinker-home` is private; a dedicated org App contains a leak to one trust domain, survives member/org changes, and mints ~1h tokens per run (§4).
- [ ] **OP-2 — Install the App on `pythinker-home` ONLY.** App page → **Install App** → TechMatrix-labs → **Only select repositories** → `pythinker-home` → Install. Verify it is NOT installed on any other repo.
- [ ] **OP-3 — Set the org secrets** (run from a shell where `gh auth status` shows an org-admin token):
  ```bash
  gh secret set PYTHINKER_RELEASE_BOT_APP_ID --org TechMatrix-labs --visibility all --body "<numeric-app-id-from-OP-1>"
  gh secret set PYTHINKER_RELEASE_BOT_APP_PRIVATE_KEY --org TechMatrix-labs --visibility all < /path/to/pythinker-release-bot.private-key.pem
  ```
  Expected: `✓ Set Organization secret PYTHINKER_RELEASE_BOT_APP_ID` (and `_PRIVATE_KEY`). Then `rm /path/to/pythinker-release-bot.private-key.pem` (the key lives only in the secret now).
- [ ] **OP-4 — Confirm the live site host runs Dokploy build-from-source, not the Docker-Compose/Watchtower stack.** Required before Task 14 (deploy retirement). Check the Dokploy dashboard / server: the site is built from source via nixpacks (`bun run server.ts`), and there is no running `watchtower`/`traefik` compose stack for it. If you cannot confirm, **skip Task 14** and log it under "Out of scope / deferred" — it is reversible (`git rm`) and not on the release path.
- [ ] **OP-5 — (DEFERRED, post-verification) Delete the retired PATs.** Do these only after the gated green cycle in "Phase verification":
  - `PYTHINKER_HOME_REPO_DISPATCH_TOKEN` — delete after **both** dispatch files are migrated (PR-code-1 + PR-code-2) **and** one green release cycle dispatches via the App. `gh secret delete PYTHINKER_HOME_REPO_DISPATCH_TOKEN --repo TechMatrix-labs/pythinker-code` (it is a repo secret today, per `promote-release.yml:168`).
  - `PYTHINKER_CORE_PAGES_TOKEN` — delete after PR-code-1 merges (the only consumer, `release-pythinker-core.yml:101`, is removed there). `gh secret delete PYTHINKER_CORE_PAGES_TOKEN --repo TechMatrix-labs/pythinker-code`.

**Local tooling the executor needs** (install once; none are repo deps):
```bash
go install github.com/rhysd/actionlint/cmd/actionlint@latest   # -> ~/go/bin/actionlint
sudo dnf install -y ShellCheck                                  # shellcheck on Fedora 44
# bun 1.3.13 already present (site TDD); PSScriptAnalyzer is Windows/manual only.
```
Expected: `actionlint --version` prints a version; `shellcheck --version` prints `version: 0.x`.

---

## File Structure

**pythinker-code repo** (`/home/ai/Projects/pythinker-code-main`):

| File | Change | Responsibility |
|---|---|---|
| `.github/workflows/dispatch-pythinker-home-sync.yml` | Modify | Mint `pythinker-release-bot` token (replace PAT); fail loud on empty token |
| `.github/workflows/release-pythinker-core.yml` | Modify | Remove the dead `docs` job's pdoc→gh-pages step (404 target) |
| `scripts/install-native.sh` | Modify | Exponential backoff (4→120s, ~6m cap) on the asset-wait loop |
| `scripts/install.ps1` | Modify | `/releases/latest`-first; paginated scan only as fallback (fix `per_page=20` cliff); add backoff |
| `.github/workflows/promote-release.yml` | Modify | Sub-package PyPI-existence blocking check; remove Homebrew gate; per-channel Slack detail; `issues:write` + release-readiness issue (rows ticked as channels go ready); separate App-authed `needs: promote` dispatch job; fail-loud token; asset URLs from API `tag_name` |
| `.github/workflows/release-readiness-reconcile.yml` | **Create** | Daily/dispatch drift detector + idempotent re-dispatch + persistent-drift Slack + stale-issue auto-close (the Homebrew backstop) |

**pythinker-home repo** (`/home/ai/Projects/pythinker-site/site`):

| File | Change | Responsibility |
|---|---|---|
| `scripts/sync-upstream-products.ts` | Modify | Export functions + guard entrypoint; emit `public/version.json`; fix the line-366 literal to derive from per-product config; pin raw fetch to dispatched ref; drop 3 dead mirror targets; add the foreign-owner lockstep assertion |
| `scripts/sync-upstream-products.test.ts` | **Create** | `bun:test` unit tests for the TS logic above |
| `.github/workflows/sync-upstream-products.yml` | Modify | Job-level receiver `if:` gating on `client_payload.source_repo`; pass dispatched ref via `env:` (never into a `run:` line) |
| `scripts/install.ps1`, `web/public/install.ps1`, `docs/public/install.ps1` | **Delete** (`git rm`) | The 3 dead, byte-identical tracked mirrors (canonical pair is `public/install.{sh,ps1}`) |
| `docker-compose.yml`, `docker-compose.private-ghcr.yml`, `deploy/traefik/`, `deploy/.env.example`, `deploy/README.md` | Delete/rewrite (Task 14, gated by OP-4) | Retire the orphaned GHCR+Watchtower+Traefik path; canonical deploy = Dokploy build-from-source |

**Deferred (out of P0 scope) — §7 right-sizing items, not on the release path:**
- *Installer raw-GitHub `<tag>` fallback header line* (a documented comment in `install-native.sh`/`install.ps1` headers pointing at `github.com/.../releases/latest/download` as the non-`pythinker.com` fallback). **Deferred:** cosmetic doc-only text; the real download already targets the raw GitHub URL, and the circular `pythinker.com` reference is only in comment/fallback prose (§7). No runtime behavior change.
- *`.sha256` sidecar existence check in the site sync* (defense-in-depth for a cron-mid-upload race). **Deferred:** promote already gates every `.sha256` sidecar on the normal release path (`promote-release.yml:67-94`), and the site sync derives asset URLs from the live API `tag_name`; this is belt-and-suspenders, not a fix for a live failure (§7).

---

## PR-code-1 — Dispatch App migration, dead-docs retirement, installer hardening

Branch: `release-orch/p0-dispatch-and-installers`. Touches `scripts/install*.{sh,ps1}` and `release-*.yml` → **requires a `## Unreleased` CHANGELOG bullet** (`changelog-entry-required.yml:82-88` matches these paths; the gate is a required check under branch protection). Add it as the first task so CI is green from the start.

### Task 1 — Add the CHANGELOG entry (unblock the required gate)

**Files:** Modify `CHANGELOG.md` (the `## Unreleased` block).

- [ ] 1.1 Create the branch:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main switch -c release-orch/p0-dispatch-and-installers
  ```
  Expected: `Switched to a new branch 'release-orch/p0-dispatch-and-installers'`.
- [ ] 1.2 Confirm the `## Unreleased` heading exists and view its current body:
  ```bash
  awk '/^## Unreleased/{f=1} f&&/^## [0-9]/{exit} f' /home/ai/Projects/pythinker-code-main/CHANGELOG.md
  ```
  Expected: prints the `## Unreleased` heading and any existing bullets (may be just the heading).
- [ ] 1.3 Add a bullet under `## Unreleased` (C5 — hand-authored, not `[skip changelog]`). Use Edit to insert directly after the `## Unreleased` line:
  ```
  - Release pipeline: migrate the pythinker-home website-sync dispatch to the org-owned `pythinker-release-bot` GitHub App and fail loud on an empty token; retire the dead pythinker-core API-docs gh-pages publish step; add exponential backoff to the native install scripts and fix the Windows installer's release-pagination cliff.
  ```
- [ ] 1.4 Approximate the gate locally (HONEST: this is an approximation, not the gate). The real `changelog-entry-required.yml` gate diffs the `## Unreleased` block against the PR base and requires ≥1 **added** non-blank line; only CI can run that diff-against-base. Locally, diff the working tree against `origin/main` and confirm the new bullet appears as an added line:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main fetch origin main
  git -C /home/ai/Projects/pythinker-code-main diff origin/main -- CHANGELOG.md | grep -E '^\+- ' | grep -c 'pythinker-release-bot'
  ```
  Expected: `1` (the bullet is a net-added line). This mirrors the gate's "added line" intent; the authoritative pass/fail is the `changelog` check on the PR.
- [ ] 1.5 Commit:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main add CHANGELOG.md
  git -C /home/ai/Projects/pythinker-code-main commit -m "docs(changelog): note P0 dispatch + installer changes"
  ```
  Expected: one file changed, one insertion.

### Task 2 — Migrate `dispatch-pythinker-home-sync.yml` to the App token + fail-loud

This is CI-wiring: verify with `actionlint` locally, then `gh workflow run` post-merge (the workflow does not run on `pull_request`). Copy the mint step verbatim from `homebrew-tap.yml:79-86`, swapping the secret names and `repositories`.

**Files:** Modify `.github/workflows/dispatch-pythinker-home-sync.yml:25-47`. Verify: `actionlint`.

- [ ] 2.1 Replace the `dispatch` job's `steps:` block (current lines 25-47, where the single `Trigger pythinker-home sync` step reads <code v-pre>DISPATCH_TOKEN: ${{ secrets.PYTHINKER_HOME_REPO_DISPATCH_TOKEN }}</code> and silently `exit 0` on empty) with a job-level `env:` + a mint step + a dispatch step. The exact replacement for lines 25-47:
  ```yaml
      env:
        DISPATCH_OWNER: TechMatrix-labs
        DISPATCH_REPO: pythinker-home
      steps:
        # Mint a short-lived installation token for the org-owned
        # pythinker-release-bot App (Contents: write on pythinker-home only).
        # Replaces a personal PAT: org-owned (survives member/org changes),
        # ~1h TTL, minted fresh each run, scoped to the single private site repo.
        - name: Mint GitHub App token for pythinker-home
          id: app-token
          uses: actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349 # v2.2.2
          with:
            app-id: ${{ secrets.PYTHINKER_RELEASE_BOT_APP_ID }}
            private-key: ${{ secrets.PYTHINKER_RELEASE_BOT_APP_PRIVATE_KEY }}
            owner: ${{ env.DISPATCH_OWNER }}
            repositories: ${{ env.DISPATCH_REPO }}

        - name: Trigger pythinker-home sync
          env:
            DISPATCH_TOKEN: ${{ steps.app-token.outputs.token }}
            SOURCE_REPO: ${{ github.repository }}
            RELEASE_TAG: ${{ github.sha }}
            DISPATCH_OWNER: ${{ env.DISPATCH_OWNER }}
            DISPATCH_REPO: ${{ env.DISPATCH_REPO }}
          run: |
            set -euo pipefail
            if [ -z "${DISPATCH_TOKEN:-}" ]; then
              echo "::error::No dispatch token: the pythinker-release-bot App token mint produced an empty value. Confirm PYTHINKER_RELEASE_BOT_APP_ID and PYTHINKER_RELEASE_BOT_APP_PRIVATE_KEY org secrets are set and the App is installed on ${DISPATCH_OWNER}/${DISPATCH_REPO} with Contents: Read and write." >&2
              exit 1
            fi
            payload=$(jq -n \
              --arg source_repo "$SOURCE_REPO" \
              --arg tag "$RELEASE_TAG" \
              '{"event_type":"sync-pythinker-products","client_payload":{"source_repo":$source_repo,"tag":$tag}}')
            curl --fail-with-body \
              -X POST \
              -H "Accept: application/vnd.github+json" \
              -H "Authorization: Bearer $DISPATCH_TOKEN" \
              "https://api.github.com/repos/${DISPATCH_OWNER}/${DISPATCH_REPO}/dispatches" \
              -d "$payload"
  ```
  Notes: the `permissions: contents: read` on the `dispatch` job (lines 23-24) stays (the App token does the cross-repo write, not `GITHUB_TOKEN`); the silent `exit 0`-on-empty is replaced by `exit 1` (Mode-A fail-loud, §5). `RELEASE_TAG` stays `github.sha` (this file's path-trigger sends a SHA, §7 — handled receiver-side in PR-home-3).
- [ ] 2.2 Lint the file:
  ```bash
  ~/go/bin/actionlint /home/ai/Projects/pythinker-code-main/.github/workflows/dispatch-pythinker-home-sync.yml
  ```
  Expected: prints nothing and exits 0 (`echo $?` → `0`).
- [ ] 2.3 Commit:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main add .github/workflows/dispatch-pythinker-home-sync.yml
  git -C /home/ai/Projects/pythinker-code-main commit -m "ci(dispatch): mint pythinker-release-bot App token, fail loud on empty"
  ```

### Task 3 — Retire the dead pythinker-core gh-pages docs step

The target `PythinkerAI/pythinker-core` is a confirmed 404 (§4, table row 8); the whole `docs` job exists only to publish pdoc there. Drop the entire `docs` job (lines 67-127) — without the publish step it would build docs and discard them.

**Files:** Modify `.github/workflows/release-pythinker-core.yml` (remove the `docs:` job, lines 67-127). Verify: `actionlint`.

- [ ] 3.1 Delete the `docs:` job block — everything from line 67 (`  docs:`) through line 127 (end of file; the last line is `          git -C "$PAGES_DIR" push origin gh-pages`). The file is 127 lines total. The remaining jobs are `validate` and `publish`. Use Edit to remove the block; confirm the file now ends after the `publish` job's `packages-dir: dist/pythinker-core` line.
- [ ] 3.2 Lint:
  ```bash
  ~/go/bin/actionlint /home/ai/Projects/pythinker-code-main/.github/workflows/release-pythinker-core.yml
  ```
  Expected: prints nothing and exits 0.
- [ ] 3.3 Confirm no lingering reference to the deleted secret in this file:
  ```bash
  grep -n PYTHINKER_CORE_PAGES_TOKEN /home/ai/Projects/pythinker-code-main/.github/workflows/release-pythinker-core.yml || echo "clean"
  ```
  Expected: `clean`.
- [ ] 3.4 Commit:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main add .github/workflows/release-pythinker-core.yml
  git -C /home/ai/Projects/pythinker-code-main commit -m "ci(core): drop dead pdoc gh-pages publish (404 target)"
  ```

### Task 4 — `install-native.sh`: exponential backoff on asset-wait

The current loop (lines 229-238) is flat 6×10s. Replace with exponential backoff capped at 120s, ~6m total budget. This is a bash logic change — verify with `shellcheck` + a local dry-run of the backoff arithmetic.

**Files:** Modify `scripts/install-native.sh:229-238`. Verify: `shellcheck` + local arithmetic check.

- [ ] 4.1 The current block to replace (lines 229-238):
  ```bash
  attempt=0
  until release_has_assets; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 6 ]; then
      fail "release assets for v${VERSION} are not available yet: ${tarball_url}
  The latest release may still be publishing. Try again shortly, or pin a known-good version with --version X.Y.Z"
    fi
    step "Waiting for v${VERSION} assets to finish publishing (attempt ${attempt}/6)"
    sleep 10
  done
  ```
  Replace with exponential backoff (4s → cap 120s, ~6m cumulative):
  ```bash
  # Exponential backoff: the GitHub Release can briefly advertise a version
  # whose assets are still uploading. Wait 4,8,16,...,120s (capped), ~6m total,
  # before giving up — long enough to ride out a slow multi-arch upload.
  attempt=0
  delay=4
  elapsed=0
  max_elapsed=360
  until release_has_assets; do
    attempt=$((attempt + 1))
    if [ "$elapsed" -ge "$max_elapsed" ]; then
      fail "release assets for v${VERSION} are not available after ~${max_elapsed}s: ${tarball_url}
  The latest release may still be publishing. Try again shortly, or pin a known-good version with --version X.Y.Z"
    fi
    step "Waiting for v${VERSION} assets to finish publishing (attempt ${attempt}, retry in ${delay}s)"
    sleep "$delay"
    elapsed=$((elapsed + delay))
    delay=$((delay * 2))
    [ "$delay" -gt 120 ] && delay=120
  done
  ```
- [ ] 4.2 Verify the backoff sequence and total budget with a standalone reproduction:
  ```bash
  delay=4; elapsed=0; max=360; seq="";
  while [ "$elapsed" -lt "$max" ]; do seq="$seq $delay"; elapsed=$((elapsed+delay)); delay=$((delay*2)); [ "$delay" -gt 120 ] && delay=120; done
  echo "delays:$seq  total:${elapsed}s"
  ```
  Expected: `delays: 4 8 16 32 64 120 120  total:364s` (7 retries, geometric early then 120s-capped; the loop stops once `elapsed >= 360`).
- [ ] 4.3 Lint the whole file and confirm it is clean:
  ```bash
  shellcheck /home/ai/Projects/pythinker-code-main/scripts/install-native.sh; echo "exit=$?"
  ```
  Expected: `exit=0` (no findings). If shellcheck reports pre-existing findings unrelated to lines 229-238, confirm none are newly introduced by the diff region (the new code uses only quoted POSIX arithmetic and already-defined helpers).
- [ ] 4.4 Commit:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main add scripts/install-native.sh
  git -C /home/ai/Projects/pythinker-code-main commit -m "fix(install): exponential backoff on native asset-wait"
  ```

### Task 5 — `install.ps1`: `/releases/latest`-first, paginated fallback, backoff

The current `Get-LatestVersion` (lines 136-164) scans `releases?per_page=20` and picks the first non-prerelease with the asset pair — a real cliff if the target release is page-2 (`scripts/install.ps1:144`). Fix: hit `/releases/latest` first (preserves the `$release.prerelease` skip at line 152 and the `.exe`+`.sha256` asset-pair guard at line 158 by re-applying both checks), use the paginated scan only as fallback, and add backoff. PowerShell can only be lint-checked with PSScriptAnalyzer on Windows — mark this **manual/CI-verified**.

**Files:** Modify `scripts/install.ps1:136-164` (`Get-LatestVersion`). Verify: PSScriptAnalyzer (manual) + post-merge real run.

- [ ] 5.1 Replace the `Get-LatestVersion` function (lines 136-164) with a `/releases/latest`-first resolver that preserves the prerelease skip and asset-pair guard, then falls back to a paginated scan, with backoff:
  ```powershell
  function Test-ReleaseHasInstaller($release) {
    if ($release.draft -or $release.prerelease) { return $null }
    $tag = [string]$release.tag_name
    if (-not $tag) { return $null }
    $candidate = $tag.TrimStart('v')
    $exe = "PythinkerSetup-$candidate.exe"
    $names = @($release.assets | ForEach-Object { [string]$_.name })
    if (($names -contains $exe) -and ($names -contains "$exe.sha256")) { return $candidate }
    return $null
  }

  function Get-LatestVersion {
    Step "Looking up latest Pythinker release"
    # /releases/latest is prerelease-excluding and not page-bound, so it is the
    # correct primary source (fixes the per_page=20 pagination cliff). The
    # GitHub Release can briefly advertise a version whose Windows installer is
    # still uploading, so retry with exponential backoff (~6m). A paginated
    # scan is only a fallback if /latest somehow lacks the asset pair.
    $latestApi = "https://api.github.com/repos/$Repo/releases/latest"
    $listApi   = "https://api.github.com/repos/$Repo/releases?per_page=100"
    $delay = 4
    $elapsed = 0
    $maxElapsed = 360
    while ($true) {
      try {
        $latest = Invoke-RestMethod -UseBasicParsing -Uri $latestApi
        $found = Test-ReleaseHasInstaller $latest
        if ($found) { OK "Latest version is $found"; return $found }
      } catch { }
      try {
        $releases = Invoke-RestMethod -UseBasicParsing -Uri $listApi
        foreach ($release in @($releases)) {
          $found = Test-ReleaseHasInstaller $release
          if ($found) { OK "Latest version is $found"; return $found }
        }
      } catch { }
      if ($elapsed -ge $maxElapsed) {
        Fail "no published release has a ready Windows installer asset after ~${maxElapsed}s; try again shortly or pin `$env:PYTHINKER_VERSION"
      }
      Step "Windows installer asset not ready yet; retry in ${delay}s"
      Start-Sleep -Seconds $delay
      $elapsed += $delay
      $delay = [Math]::Min($delay * 2, 120)
    }
  }
  ```
- [ ] 5.2 Static syntax check the file parses (no PSScriptAnalyzer on Linux, but PowerShell-on-Linux can tokenize it). If `pwsh` is available locally:
  ```bash
  command -v pwsh >/dev/null && pwsh -NoProfile -Command "[void][System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw '/home/ai/Projects/pythinker-code-main/scripts/install.ps1'), [ref]\$null); 'parsed OK'" || echo "pwsh not present — defer parse check to CI/Windows"
  ```
  Expected: `parsed OK` (if `pwsh` present) or `pwsh not present — defer parse check to CI/Windows`. If deferred, the real verification is the post-merge manual Windows run in Phase verification.
- [ ] 5.3 Confirm the two preserved guards are present in the new code:
  ```bash
  grep -nE '\$release\.prerelease|"\$exe\.sha256"' /home/ai/Projects/pythinker-code-main/scripts/install.ps1
  ```
  Expected: two matches — the `$release.draft -or $release.prerelease` skip and the `($names -contains "$exe.sha256")` asset-pair check, both inside `Test-ReleaseHasInstaller`.
- [ ] 5.4 Commit:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main add scripts/install.ps1
  git -C /home/ai/Projects/pythinker-code-main commit -m "fix(install): /releases/latest-first + paginated fallback + backoff on Windows"
  ```

### Task 6 — Open PR-code-1

- [ ] 6.1 Push and open the PR:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main push -u origin release-orch/p0-dispatch-and-installers
  gh pr create --repo TechMatrix-labs/pythinker-code --base main \
    --title "ci: dispatch App migration + retire dead docs step + installer hardening" \
    --body "P0 (1/2): migrate dispatch-pythinker-home-sync.yml to the pythinker-release-bot App token with fail-loud-on-empty; remove the dead pythinker-core pdoc gh-pages step (404 target); install-native.sh exponential backoff; install.ps1 /releases/latest-first with paginated fallback and backoff. No agent runtime deps. Sequencing note: promote-release.yml gate changes ship in PR-code-2 with the reconcile backstop."
  ```
  Expected: prints the new PR URL.
- [ ] 6.2 Wait for required checks (including `changelog`) to pass and CodeRabbit commit status on the head SHA to be `success` (C2). Verify before merge:
  ```bash
  gh pr checks --repo TechMatrix-labs/pythinker-code <PR#>
  gh api repos/TechMatrix-labs/pythinker-code/commits/$(gh pr view --repo TechMatrix-labs/pythinker-code <PR#> --json headRefOid -q .headRefOid)/status --jq '.statuses[] | select(.context=="CodeRabbit") | .state'
  ```
  Expected: all checks `pass`; the CodeRabbit line prints `success`. Do not merge until then (C2).
- [ ] 6.3 Merge (after CodeRabbit `success`):
  ```bash
  gh pr merge --repo TechMatrix-labs/pythinker-code <PR#> --squash
  ```
  Expected: `✓ Squashed and merged pull request #<PR#>`.
- [ ] 6.4 **Post-merge dispatch smoke test** (needs OP-1..OP-3 done): trigger the dispatch workflow manually and confirm the App-token path fires:
  ```bash
  gh workflow run dispatch-pythinker-home-sync.yml --repo TechMatrix-labs/pythinker-code
  gh run watch --repo TechMatrix-labs/pythinker-code $(gh run list --repo TechMatrix-labs/pythinker-code --workflow dispatch-pythinker-home-sync.yml -L1 --json databaseId -q '.[0].databaseId')
  ```
  Expected: the run is green; the "Mint GitHub App token" step succeeds and the dispatch POST returns 204. Then confirm pythinker-home received it:
  ```bash
  gh run list --repo TechMatrix-labs/pythinker-home --workflow sync-upstream-products.yml -L1
  ```
  Expected: a fresh `repository_dispatch` run is listed.

---

## PR-code-2 — promote-release fail-loud + reconcile backstop (one PR, hard sequencing)

Branch: `release-orch/p0-promote-reconcile`. Touches `promote-release.yml` and adds `release-readiness-reconcile.yml` (matches `release-*.yml` in `changelog-entry-required.yml:88`) → **requires a `## Unreleased` bullet**. Reconcile + Homebrew-gate-removal ship together so the §5 hard rule ("reconcile lands before/with gate removal") is satisfied with no window where the tap has neither gate nor backstop.

### Task 7 — CHANGELOG entry for PR-code-2

**Files:** Modify `CHANGELOG.md`.

- [ ] 7.1 Branch from fresh main:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main switch main && git -C /home/ai/Projects/pythinker-code-main pull --ff-only
  git -C /home/ai/Projects/pythinker-code-main switch -c release-orch/p0-promote-reconcile
  ```
  Expected: `Switched to a new branch 'release-orch/p0-promote-reconcile'`.
- [ ] 7.2 Add a bullet under `## Unreleased` (C5):
  ```
  - Release promotion: block the prerelease→latest flip until `pythinker-code` and every pinned sub-package (`pythinker-core`, `pythinker-host`, `pythinker-review`) resolve on PyPI; remove Homebrew from the promote gate (now backed by a new `release-readiness-reconcile.yml` drift backstop); add per-channel bottleneck detail to the failure Slack, a per-release `release-readiness` tracking issue whose rows tick as channels go ready, and a separate App-authed site-dispatch job that fails loud on an empty token.
  ```
- [ ] 7.3 Approximate the gate locally (HONEST: approximation only; the authoritative check is CI's diff-against-base):
  ```bash
  git -C /home/ai/Projects/pythinker-code-main diff origin/main -- CHANGELOG.md | grep -E '^\+- ' | grep -c 'release-readiness-reconcile'
  ```
  Expected: `1`.
- [ ] 7.4 Commit:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main add CHANGELOG.md
  git -C /home/ai/Projects/pythinker-code-main commit -m "docs(changelog): note promote fail-loud + reconcile backstop"
  ```

### Task 8 — promote-release: sub-package PyPI-existence blocking check + remove Homebrew gate

**Files:** Modify `.github/workflows/promote-release.yml`. The readiness step is lines 59-153. Verify: `actionlint` + post-merge `workflow_dispatch` rehearsal.

- [ ] 8.1 In the `Wait for install-channel readiness` step, replace the single PyPI URL (line 95) and the Homebrew formula URL (line 96) with a list of all four PyPI URLs that must return 200, deleting `homebrew_formula_url`. Replace lines 95-96 with:
  ```bash
          # BLOCKING set: /releases/latest and pip must both resolve before the flip.
          # pythinker-code AND every pinned sub-package must publish, else
          # `pip install pythinker-code==X` 500s on a lagging transitive pin.
          pypi_urls=(
            "https://pypi.org/pypi/pythinker-code/${version}/json"
            "https://pypi.org/pypi/pythinker-core/1.1.1/json"
            "https://pypi.org/pypi/pythinker-host/1.0.0/json"
            "https://pypi.org/pypi/pythinker-review/0.1.0/json"
          )
  ```
  (The sub-package pins are hardcoded here to the values frozen in `pyproject.toml` — core 1.1.1, host 1.0.0, review 0.1.0. P1 will source these from the dep-check; for P0 they are literals matching the SSOT.)
- [ ] 8.2 Replace the per-attempt PyPI/Homebrew readiness evaluation (lines 118-127) with a loop over `pypi_urls`, dropping the Homebrew block entirely:
  ```bash
            pypi_ready=true
            missing_pypi=()
            for u in "${pypi_urls[@]}"; do
              if ! curl -fsSL --retry 2 --retry-delay 2 -o /dev/null "$u"; then
                pypi_ready=false
                missing_pypi+=("$u")
              fi
            done
  ```
- [ ] 8.3 Replace the all-ready condition (line 129) — remove `&& "$homebrew_ready" == "true"`:
  ```bash
            if [[ "${#missing_assets[@]}" -eq 0 && "$pypi_ready" == "true" ]]; then
  ```
- [ ] 8.4 Replace the per-attempt diagnostics (lines 139-144) so each lagging channel is named, and remove the two Homebrew diagnostic lines:
  ```bash
            if [[ "$pypi_ready" != "true" ]]; then
              printf 'PyPI not serving yet: %s\n' "${missing_pypi[*]}"
            fi
  ```
  (This removes the old `homebrew_ready` "not at version yet" block at lines 142-144; line 137-138's `Missing release assets` block is kept unchanged.)
- [ ] 8.5 Give the readiness step `id: readiness_wait`. Build a local shell `bottleneck` variable, write it to `$GITHUB_OUTPUT` as a multi-line output named `bottleneck`, write a human-readable step summary, and (after the loop, when not ready) **tick the readiness issue rows** by PATCHing the issue body to reflect which channels are ready. Replace the final not-ready block (current lines 150-153) with:
  ```bash
          # Build the live-status checklist body from the loop's final flags so the
          # release-readiness issue is an accurate per-channel status pane (§5).
          assets_box="[ ]"; [[ "${#missing_assets[@]}" -eq 0 ]] && assets_box="[x]"
          pypi_code_box="[ ]"; pypi_subpkg_box="[ ]"
          if [[ "$pypi_ready" == "true" ]]; then
            pypi_code_box="[x]"; pypi_subpkg_box="[x]"
          else
            # Code resolves iff the code URL is not in the missing set.
            case " ${missing_pypi[*]} " in
              *"pythinker-code/${version}/json"*) ;;
              *) pypi_code_box="[x]" ;;
            esac
          fi
          issue_body="$(printf '%s\n' \
            "Tracking install-channel readiness for **${TAG}**." \
            "" \
            "- ${assets_box} GitHub Release assets" \
            "- ${pypi_code_box} PyPI: pythinker-code" \
            "- ${pypi_subpkg_box} PyPI: pinned sub-packages (core/host/review)" \
            "- [ ] Homebrew tap (best-effort)" \
            "- [ ] Site version.json (best-effort)")"
          gh api -X PATCH "repos/$REPO/issues/${{ steps.readiness.outputs.number }}" \
            -f body="$issue_body" >/dev/null

          bottleneck="$(
            if [[ "${#missing_assets[@]}" -gt 0 ]]; then printf 'Missing assets: %s\n' "${missing_assets[*]}"; fi
            if [[ "$pypi_ready" != "true" ]]; then printf 'PyPI not resolvable: %s\n' "${missing_pypi[*]}"; fi
          )"
          {
            echo "### Release readiness for ${TAG} — NOT READY"
            [[ -n "$bottleneck" ]] && printf '%s\n' "$bottleneck"
          } >> "$GITHUB_STEP_SUMMARY"
          {
            echo "bottleneck<<EOF"
            printf '%s\n' "$bottleneck"
            echo "EOF"
          } >> "$GITHUB_OUTPUT"
          gh issue comment "${{ steps.readiness.outputs.number }}" --repo "$REPO" \
            --body "$(printf 'Promotion stuck for %s after ~%dm.\n\n%s\n\nRe-run via `workflow_dispatch tag=%s` once the bottleneck clears.' "$TAG" "$budget_min" "${bottleneck:-unknown bottleneck}" "$TAG")"
          echo "::error::Install channels were not fully ready after ${budget_min} minutes"
          exit 1
  ```
  Notes: `bottleneck` is a **local shell variable** read in the same step that wrote it — it is NOT routed through `$GITHUB_ENV` (which only propagates to *later* steps and would always be empty here). Cross-job propagation to the Slack job uses the `$GITHUB_OUTPUT` `bottleneck` value exposed as a job output in Task 10.3. The issue-body PATCH ticks rows so the issue is a live status pane. The `Promote release` step (Task 9.4) ticks the remaining rows / closes the issue on success.
- [ ] 8.6 Lint + commit:
  ```bash
  ~/go/bin/actionlint /home/ai/Projects/pythinker-code-main/.github/workflows/promote-release.yml
  ```
  Expected: prints nothing, exits 0. Then:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main add .github/workflows/promote-release.yml
  git -C /home/ai/Projects/pythinker-code-main commit -m "ci(promote): block flip on all sub-pkg PyPI pins; drop Homebrew gate; tick readiness rows"
  ```

### Task 9 — promote-release: `issues:write` + release-readiness issue (upsert by exact title)

**Files:** Modify `.github/workflows/promote-release.yml` (`promote` job `permissions:` and a new step). Verify: `actionlint` + post-merge rehearsal.

- [ ] 9.1 Extend the `promote` job permissions (current lines 36-37 `permissions:` / `contents: write`) to add `issues: write`:
  ```yaml
      permissions:
        contents: write
        issues: write
  ```
- [ ] 9.2 Add a step **before** the readiness wait (between `Resolve and validate tag` and `Wait for install-channel readiness`) that upserts the per-release tracking issue by **exact-title REST list** (not the async search API, which races duplicates). Insert after the `tag` step (after current line 57):
  ```yaml
      - name: Upsert release-readiness issue
        id: readiness
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ steps.tag.outputs.tag }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail
          title="release-readiness: ${TAG}"
          # Exact-title match over ALL open issues (--paginate scans every page;
          # the search API is async-indexed and races duplicate creation).
          number=$(gh api --paginate "repos/$REPO/issues?state=open&per_page=100" \
            | jq -r --arg t "$title" '.[] | select(.title==$t) | .number' \
            | head -n1)
          body=$'Tracking install-channel readiness for **'"$TAG"$'**.\n\n- [ ] GitHub Release assets\n- [ ] PyPI: pythinker-code\n- [ ] PyPI: pinned sub-packages (core/host/review)\n- [ ] Homebrew tap (best-effort)\n- [ ] Site version.json (best-effort)'
          if [ -z "$number" ]; then
            number=$(gh api -X POST "repos/$REPO/issues" -f title="$title" -f body="$body" --jq '.number')
            echo "Created issue #$number"
          else
            echo "Reusing issue #$number"
          fi
          echo "number=$number" >> "$GITHUB_OUTPUT"
  ```
  Notes: `gh api --paginate ... | jq -r --arg t ...` — the exact-title filter is a **standalone `jq`** consuming the paginated `gh api` output. `gh api`'s own `--jq` takes only a jq-program string and rejects `--arg`, so the variable injection must be on the piped `jq`. `--paginate` ensures the match scans all open issues, not just page 1.
- [ ] 9.3 The stuck-failure issue comment is already emitted inside the readiness-wait step (Task 8.5, using the local `bottleneck` shell variable and `steps.readiness.outputs.number`). No separate step is needed; confirm the readiness-wait step's `env:` block carries <code v-pre>GH_TOKEN: ${{ github.token }}</code> and <code v-pre>REPO: ${{ github.repository }}</code> (it already does, current lines 60-63) so `gh issue comment` authenticates.
- [ ] 9.4 On **success**, tick all rows and close the issue. Append to the `Promote release` step (after the PATCH at current line 163-164):
  ```bash
          all_ready_body=$'Tracking install-channel readiness for **'"$TAG"$'**.\n\n- [x] GitHub Release assets\n- [x] PyPI: pythinker-code\n- [x] PyPI: pinned sub-packages (core/host/review)\n- [ ] Homebrew tap (best-effort)\n- [ ] Site version.json (best-effort)'
          gh api -X PATCH "repos/$REPO/issues/${{ steps.readiness.outputs.number }}" -f body="$all_ready_body" >/dev/null || true
          gh issue close "${{ steps.readiness.outputs.number }}" --repo "$REPO" \
            --comment "Promoted ${TAG}: prerelease=false, make_latest=true. All blocking channels ready (Homebrew/site reconcile best-effort)." || true
  ```
  (The two best-effort rows stay unticked at close time — they are reconciled asynchronously by `release-readiness-reconcile.yml`, not by promote.)
- [ ] 9.5 Lint + commit:
  ```bash
  ~/go/bin/actionlint /home/ai/Projects/pythinker-code-main/.github/workflows/promote-release.yml
  git -C /home/ai/Projects/pythinker-code-main add .github/workflows/promote-release.yml
  git -C /home/ai/Projects/pythinker-code-main commit -m "ci(promote): upsert release-readiness issue by exact title; close on success"
  ```
  Expected: actionlint prints nothing, exits 0.

### Task 10 — promote-release: separate App-authed `needs: promote` dispatch job + fail-loud + per-channel Slack

**Files:** Modify `.github/workflows/promote-release.yml`. Verify: `actionlint` + post-merge rehearsal.

- [ ] 10.1 **Remove** the `Trigger pythinker-home sync` step from the `promote` job (current lines 166-186, which use `secrets.PYTHINKER_HOME_REPO_DISPATCH_TOKEN` and the silent `::notice; exit 0`). The promote job now ends after the `Promote release` step (which closes the issue, Task 9.4).
- [ ] 10.2 Add a new top-level job `dispatch-site` with `needs: promote`, mirroring the Task 2 mint pattern, building the dispatch `tag` from the **promote job's live tag output** (not a payload ref), failing loud on empty token. Insert between the `promote` job and `notify-failure`:
  ```yaml
    dispatch-site:
      name: Dispatch pythinker-home sync
      runs-on: ubuntu-latest
      needs: promote
      permissions:
        contents: read
      env:
        DISPATCH_OWNER: TechMatrix-labs
        DISPATCH_REPO: pythinker-home
      steps:
        - name: Mint GitHub App token for pythinker-home
          id: app-token
          uses: actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349 # v2.2.2
          with:
            app-id: ${{ secrets.PYTHINKER_RELEASE_BOT_APP_ID }}
            private-key: ${{ secrets.PYTHINKER_RELEASE_BOT_APP_PRIVATE_KEY }}
            owner: ${{ env.DISPATCH_OWNER }}
            repositories: ${{ env.DISPATCH_REPO }}

        - name: Trigger pythinker-home sync
          env:
            DISPATCH_TOKEN: ${{ steps.app-token.outputs.token }}
            SOURCE_REPO: ${{ github.repository }}
            RELEASE_TAG: ${{ needs.promote.outputs.tag }}
            DISPATCH_OWNER: ${{ env.DISPATCH_OWNER }}
            DISPATCH_REPO: ${{ env.DISPATCH_REPO }}
          run: |
            set -euo pipefail
            if [ -z "${DISPATCH_TOKEN:-}" ]; then
              echo "::error::No dispatch token: pythinker-release-bot App mint produced an empty value. Site sync skipped, but the release IS promoted and /releases/latest is correct; it self-heals via drift reconcile / daily cron. Fix PYTHINKER_RELEASE_BOT_APP_* org secrets." >&2
              exit 1
            fi
            payload=$(jq -n \
              --arg source_repo "$SOURCE_REPO" \
              --arg tag "$RELEASE_TAG" \
              '{"event_type":"sync-pythinker-products","client_payload":{"source_repo":$source_repo,"tag":$tag}}')
            curl --fail-with-body \
              -X POST \
              -H "Accept: application/vnd.github+json" \
              -H "Authorization: Bearer $DISPATCH_TOKEN" \
              "https://api.github.com/repos/${DISPATCH_OWNER}/${DISPATCH_REPO}/dispatches" \
              -d "$payload"
  ```
  Notes: `RELEASE_TAG` is `needs.promote.outputs.tag` (a validated `vX.Y.Z` from the live API, §7) — never a raw payload ref. The receiver in PR-home-3 uses this tag only for raw-source pinning; asset URLs are always built from the live API `tag_name`.
- [ ] 10.3 Expose `tag` and `bottleneck` as `promote` job outputs so `dispatch-site` and `notify-failure` can read them. Add to the `promote` job after `runs-on: ubuntu-latest` (current line 34):
  ```yaml
      outputs:
        tag: ${{ steps.tag.outputs.tag }}
        bottleneck: ${{ steps.readiness_wait.outputs.bottleneck }}
  ```
  (`steps.tag` is the `Resolve and validate tag` step; `steps.readiness_wait` is the `Wait for install-channel readiness` step given `id: readiness_wait` in Task 8.5.)
- [ ] 10.4 Make `notify-failure` cover both jobs and add per-channel bottleneck detail. Change `needs: promote` (current line 191) to `needs: [promote, dispatch-site]`, extend the Slack step `env:`, and rebuild the payload `detail` from the two job results (do NOT replace the job — §5). Replace the `notify-failure` step's `env:` block (current lines 197-201) with:
  ```yaml
          env:
            SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
            RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
            REPO: ${{ github.repository }}
            TAG: ${{ inputs.tag || github.ref_name }}
            PROMOTE_RESULT: ${{ needs.promote.result }}
            DISPATCH_RESULT: ${{ needs.dispatch-site.result }}
            BOTTLENECK: ${{ needs.promote.outputs.bottleneck }}
  ```
  And replace the existing `payload=$(jq -n ...)` block (current lines 207-211) so the Slack message carries a `Detail` field with the named bottleneck:
  ```bash
          detail="promote=${PROMOTE_RESULT}, dispatch=${DISPATCH_RESULT}"
          if [ "$PROMOTE_RESULT" != "success" ]; then
            detail="$detail — release STUCK as prerelease; /releases/latest still last-good. Bottleneck: ${BOTTLENECK:-unknown}. See readiness issue."
          else
            detail="$detail — release PROMOTED; only site sync failed, self-heals via reconcile/cron."
          fi
          payload=$(jq -n \
            --arg run_url "$RUN_URL" --arg repo "$REPO" --arg tag "$TAG" --arg detail "$detail" \
            '{"text":":red_circle: *Release promotion failed*","attachments":[{"color":"danger","fields":[{"title":"Repo","value":$repo,"short":true},{"title":"Tag","value":$tag,"short":true},{"title":"Detail","value":$detail,"short":false},{"title":"Run","value":"<\($run_url)|View logs>","short":false}]}]}')
  ```
- [ ] 10.5 Lint + confirm no PAT reference remains:
  ```bash
  ~/go/bin/actionlint /home/ai/Projects/pythinker-code-main/.github/workflows/promote-release.yml
  grep -n PYTHINKER_HOME_REPO_DISPATCH_TOKEN /home/ai/Projects/pythinker-code-main/.github/workflows/promote-release.yml || echo "clean"
  ```
  Expected: actionlint prints nothing (exit 0); the grep prints `clean`.
- [ ] 10.6 Commit:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main add .github/workflows/promote-release.yml
  git -C /home/ai/Projects/pythinker-code-main commit -m "ci(promote): App-authed needs:promote dispatch job, fail-loud, per-channel Slack"
  ```

### Task 11 — Create `release-readiness-reconcile.yml` (the Homebrew backstop)

Detects drift (tap formula version != `/releases/latest` OR served `public/version.json` != `/releases/latest`), re-dispatches the site sync idempotently, alerts on drift, and auto-closes `release-readiness` issues for releases **older than** the current latest. This MUST be in the same PR as the gate removal (§5 hard rule — satisfied because both are in PR-code-2).

**Files:** Create `.github/workflows/release-readiness-reconcile.yml`. Verify: `actionlint` + post-merge `workflow_dispatch`.

- [ ] 11.1 Create the file:
  ```yaml
  name: Release readiness reconcile

  # Backstop for best-effort channels (Homebrew tap, website) now that Homebrew
  # is no longer a promote gate. Detects drift between /releases/latest and the
  # tap formula / served public/version.json, re-dispatches the site sync
  # idempotently, escalates to Slack on drift, and auto-closes release-readiness
  # issues for releases OLDER than the current latest (semver-ordered, so a newer
  # in-progress release's issue is left open).

  on:
    workflow_dispatch:
    schedule:
      - cron: "47 5 * * *"

  permissions:
    contents: read
    issues: write

  concurrency:
    group: release-readiness-reconcile
    cancel-in-progress: false

  env:
    DISPATCH_OWNER: TechMatrix-labs
    DISPATCH_REPO: pythinker-home

  jobs:
    reconcile:
      runs-on: ubuntu-latest
      outputs:
        drift: ${{ steps.detect.outputs.drift }}
        redispatched: ${{ steps.redispatch.outputs.redispatched }}
      steps:
        - name: Detect drift
          id: detect
          env:
            GH_TOKEN: ${{ github.token }}
            REPO: ${{ github.repository }}
          run: |
            set -euo pipefail
            latest_tag=$(gh api "repos/$REPO/releases/latest" --jq '.tag_name')
            latest="${latest_tag#v}"
            echo "Latest published release: $latest_tag ($latest)"
            drift=""
            tap_url="https://raw.githubusercontent.com/TechMatrix-labs/homebrew-pythinker/main/Formula/pythinker-code.rb"
            tap_text=$(curl -fsSL --retry 2 --retry-delay 2 "$tap_url" 2>/dev/null || true)
            if ! grep -qF "version \"${latest}\"" <<<"$tap_text"; then
              drift="$drift tap"
            fi
            ver_url="https://pythinker.com/version.json"
            served=$(curl -fsSL --retry 2 --retry-delay 2 "$ver_url" 2>/dev/null | jq -r '.pythinkerCode // empty' || true)
            if [ "$served" != "$latest" ]; then
              drift="$drift site($served)"
            fi
            echo "drift=$drift" >> "$GITHUB_OUTPUT"
            echo "latest=$latest" >> "$GITHUB_OUTPUT"
            echo "latest_tag=$latest_tag" >> "$GITHUB_OUTPUT"
            if [ -n "$drift" ]; then echo "::warning::Drift detected:$drift"; else echo "No drift."; fi

        - name: Auto-close stale (older-than-latest) release-readiness issues
          env:
            GH_TOKEN: ${{ github.token }}
            REPO: ${{ github.repository }}
            LATEST_TAG: ${{ steps.detect.outputs.latest_tag }}
          run: |
            set -euo pipefail
            # Close an open release-readiness issue ONLY if its tag is OLDER than
            # the current latest (semver). A NEWER in-progress release's issue
            # must stay open (§5 — do not close a release that hasn't promoted
            # yet). sort -V puts the older tag first; we close only when this
            # issue's tag is the older one AND differs from latest.
            gh api --paginate "repos/$REPO/issues?state=open&per_page=100" \
              --jq '.[] | select(.title|startswith("release-readiness: ")) | "\(.number)\t\(.title)"' \
            | while IFS=$'\t' read -r num title; do
                tag="${title#release-readiness: }"
                [ "$tag" = "$LATEST_TAG" ] && continue
                older=$(printf '%s\n%s\n' "$tag" "$LATEST_TAG" | sort -V | head -n1)
                if [ "$older" = "$tag" ]; then
                  gh issue close "$num" --repo "$REPO" --comment "Auto-closed: superseded by newer published release ${LATEST_TAG}." || true
                else
                  echo "Leaving #$num ($tag) open: newer than latest ${LATEST_TAG} (in-progress release)."
                fi
              done

        - name: Mint GitHub App token for pythinker-home
          if: steps.detect.outputs.drift != ''
          id: app-token
          uses: actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349 # v2.2.2
          with:
            app-id: ${{ secrets.PYTHINKER_RELEASE_BOT_APP_ID }}
            private-key: ${{ secrets.PYTHINKER_RELEASE_BOT_APP_PRIVATE_KEY }}
            owner: ${{ env.DISPATCH_OWNER }}
            repositories: ${{ env.DISPATCH_REPO }}

        - name: Re-dispatch site sync on drift
          id: redispatch
          if: steps.detect.outputs.drift != ''
          env:
            DISPATCH_TOKEN: ${{ steps.app-token.outputs.token }}
            SOURCE_REPO: ${{ github.repository }}
            RELEASE_TAG: ${{ steps.detect.outputs.latest_tag }}
            DISPATCH_OWNER: ${{ env.DISPATCH_OWNER }}
            DISPATCH_REPO: ${{ env.DISPATCH_REPO }}
          run: |
            set -euo pipefail
            if [ -z "${DISPATCH_TOKEN:-}" ]; then
              echo "::error::Empty App token during drift re-dispatch." >&2
              exit 1
            fi
            payload=$(jq -n --arg source_repo "$SOURCE_REPO" --arg tag "$RELEASE_TAG" \
              '{"event_type":"sync-pythinker-products","client_payload":{"source_repo":$source_repo,"tag":$tag}}')
            curl --fail-with-body -X POST \
              -H "Accept: application/vnd.github+json" \
              -H "Authorization: Bearer $DISPATCH_TOKEN" \
              "https://api.github.com/repos/${DISPATCH_OWNER}/${DISPATCH_REPO}/dispatches" \
              -d "$payload"
            echo "redispatched=true" >> "$GITHUB_OUTPUT"

    notify-drift:
      name: Notify on persistent drift
      runs-on: ubuntu-latest
      needs: reconcile
      # Only page when this run did NOT itself re-dispatch — i.e. drift on a
      # workflow_dispatch re-check after a prior cycle already re-dispatched. A
      # normal release that re-dispatches this cycle will NOT page (the next
      # scheduled run re-checks; if still drifted it has not re-dispatched and
      # pages). This approximates the §5 "persistent across cycles" rule without
      # a stored counter — accepted deviation, documented below.
      if: needs.reconcile.outputs.drift != '' && needs.reconcile.outputs.redispatched != 'true'
      permissions:
        contents: read
      steps:
        - name: Post Slack alert
          env:
            SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
            RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
            DRIFT: ${{ needs.reconcile.outputs.drift }}
          run: |
            set -euo pipefail
            if [ -z "${SLACK_WEBHOOK_URL:-}" ]; then exit 0; fi
            payload=$(jq -n --arg run_url "$RUN_URL" --arg drift "$DRIFT" \
              '{"text":":warning: *Release channel drift persisting*","attachments":[{"color":"warning","fields":[{"title":"Drifted channels","value":$drift,"short":false},{"title":"Action","value":"Drift was NOT re-dispatched this run (prior cycle already re-dispatched and it did not converge). Investigate the tap/site workflow.","short":false},{"title":"Run","value":"<\($run_url)|View logs>","short":false}]}]}')
            curl --fail-with-body -X POST -H "Content-Type: application/json" -d "$payload" "$SLACK_WEBHOOK_URL"
  ```
  Notes: **Accepted deviation from §5 "persistent across N cycles":** there is no stored per-channel cycle counter (a counter is logged as a P0.1 refinement — YAGNI for the quick-win phase). Instead, the Slack alert is suppressed on the same run that re-dispatched (`redispatched=true`), so a normal release does not page; it only pages on a *later* run that still sees drift it did not just re-dispatch — i.e. drift that prior re-dispatch failed to converge. The `Auto-close` step uses `--paginate` to scan all open issues and `sort -V` semver ordering so only releases **older** than latest are closed (a newer in-progress release's issue is left open). `re-dispatch` reuses the App token (cron/manual carry no `client_payload`, so the receiver gate in PR-home-3 lets it through).
- [ ] 11.2 Lint:
  ```bash
  ~/go/bin/actionlint /home/ai/Projects/pythinker-code-main/.github/workflows/release-readiness-reconcile.yml
  ```
  Expected: prints nothing, exits 0.
- [ ] 11.3 Verify the semver close-logic with a standalone reproduction (older closes, newer stays):
  ```bash
  LATEST_TAG=v0.27.0
  for tag in v0.26.0 v0.27.0 v0.28.0; do
    older=$(printf '%s\n%s\n' "$tag" "$LATEST_TAG" | sort -V | head -n1)
    if [ "$tag" != "$LATEST_TAG" ] && [ "$older" = "$tag" ]; then echo "$tag -> CLOSE"; else echo "$tag -> keep"; fi
  done
  ```
  Expected: `v0.26.0 -> CLOSE`, `v0.27.0 -> keep`, `v0.28.0 -> keep` (the newer in-progress tag is left open).
- [ ] 11.4 Commit:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main add .github/workflows/release-readiness-reconcile.yml
  git -C /home/ai/Projects/pythinker-code-main commit -m "ci: add release-readiness-reconcile backstop for best-effort channels"
  ```

### Task 11b — Open PR-code-2

- [ ] 11b.1 Push + PR:
  ```bash
  git -C /home/ai/Projects/pythinker-code-main push -u origin release-orch/p0-promote-reconcile
  gh pr create --repo TechMatrix-labs/pythinker-code --base main \
    --title "ci(promote): fail-loud sub-pkg PyPI gate + drift reconcile backstop" \
    --body "P0 (2/2): block prerelease->latest until all pinned sub-packages resolve on PyPI; remove Homebrew from the gate; per-channel bottleneck Slack; release-readiness issue (issues:write) whose rows tick as channels go ready; separate App-authed needs:promote dispatch job with fail-loud token; asset URLs from API tag_name. Ships release-readiness-reconcile.yml in the SAME PR so the §5 sequencing rule (reconcile before/with gate removal) holds; reconcile auto-closes only OLDER-than-latest readiness issues (semver). Depends on PR-code-1 (dispatch App migration) for the full PAT retirement."
  ```
  Expected: prints the new PR URL.
- [ ] 11b.2 Wait for checks + CodeRabbit `success` on the head SHA (C2), as in Task 6.2:
  ```bash
  gh pr checks --repo TechMatrix-labs/pythinker-code <PR#>
  gh api repos/TechMatrix-labs/pythinker-code/commits/$(gh pr view --repo TechMatrix-labs/pythinker-code <PR#> --json headRefOid -q .headRefOid)/status --jq '.statuses[] | select(.context=="CodeRabbit") | .state'
  ```
  Expected: all checks `pass`; CodeRabbit `success`. Merge with `gh pr merge --repo TechMatrix-labs/pythinker-code <PR#> --squash` only after `success`.

---

## PR-home-3 — Site: receiver gate, version.json, Mode-B fix, dead mirrors, deploy

Branch: `release-orch/p0-site`, in `/home/ai/Projects/pythinker-site/site`. This repo has **no JS test runner and is not subject to `changelog-entry-required.yml`** (different repo). Use the built-in `bun:test` runner (zero new deps). The TS module currently runs `await main()` at top level (line 390) and exports nothing — so the first task makes it importable, which is a hard prerequisite for every TS TDD step.

### Task 12 — Make the TS importable, then TDD the version.json emit + ref-pin + line-366 fix

**Files:** Modify `scripts/sync-upstream-products.ts`; Create `scripts/sync-upstream-products.test.ts`. Verify: `bun test` (real failing-first).

- [ ] 12.1 Branch:
  ```bash
  git -C /home/ai/Projects/pythinker-site/site switch -c release-orch/p0-site
  ```
  Expected: `Switched to a new branch 'release-orch/p0-site'`.
- [ ] 12.2 **Refactor for testability (prerequisite).** Change the top-level entrypoint (line 390 `await main();`) to guard it, and export the functions under test. Replace line 390 with:
  ```ts
  if (import.meta.main) {
    await main();
  }

  export {
    products,
    buildMetadata,
    renderReadme,
    resolveRawRef,
    buildVersionJson,
  };
  ```
  (`renderReadme`, `resolveRawRef`, `buildVersionJson` are added in 12.5-12.6.)
- [ ] 12.3 Write the **failing** test file `scripts/sync-upstream-products.test.ts` first. This includes the §7 item-2 config lockstep that asserts each product's `brewCommand` and derived release URL AGREE with its `owner`/`repo` (not just `repo != "Pythinker"`):
  ```ts
  import { describe, expect, test } from "bun:test";
  import {
    products,
    buildMetadata,
    renderReadme,
    resolveRawRef,
    buildVersionJson,
  } from "./sync-upstream-products.ts";

  const codeRelease = {
    tag_name: "v0.27.0",
    html_url: "https://github.com/TechMatrix-labs/pythinker-code/releases/tag/v0.27.0",
    assets: [
      { name: "PythinkerSetup-0.27.0.exe", browser_download_url: "" },
      { name: "PythinkerSetup-0.27.0.exe.sha256", browser_download_url: "" },
      { name: "pythinker-code_0.27.0_amd64.deb", browser_download_url: "" },
      { name: "pythinker-code_0.27.0_arm64.deb", browser_download_url: "" },
      { name: "pythinker-code-0.27.0.x86_64.rpm", browser_download_url: "" },
      { name: "pythinker-code-0.27.0.aarch64.rpm", browser_download_url: "" },
    ],
  };

  const aiProduct = products.find((p) => p.key === "ai")!;
  const codeProduct = products.find((p) => p.key === "code")!;

  describe("buildVersionJson", () => {
    test("emits pythinkerCode + tag from the code release", () => {
      const meta = buildMetadata(codeProduct, codeRelease);
      expect(buildVersionJson(meta)).toEqual({
        pythinkerCode: "0.27.0",
        tag: "v0.27.0",
      });
    });
  });

  describe("resolveRawRef", () => {
    test("accepts a vX.Y.Z tag", () => {
      expect(resolveRawRef("v0.27.0", "main")).toBe("v0.27.0");
    });
    test("accepts a 40-char sha", () => {
      const sha = "0".repeat(40);
      expect(resolveRawRef(sha, "main")).toBe(sha);
    });
    test("falls back to branch on garbage", () => {
      expect(resolveRawRef("not-a-ref; rm -rf /", "main")).toBe("main");
    });
    test("falls back to branch on empty", () => {
      expect(resolveRawRef("", "main")).toBe("main");
    });
  });

  describe("renderReadme (line-366 literal fix)", () => {
    test("AI rewrite derives destination from product owner/repo config", () => {
      const src = "see github.com/mohamed-elkholy95/Pythinker/releases for downloads";
      const out = renderReadme(aiProduct, src);
      expect(out).toContain(`github.com/${aiProduct.owner}/${aiProduct.repo}/releases`);
      expect(out).not.toContain("mohamed-elkholy95/Pythinker/releases");
    });
    test("code README passes through unchanged", () => {
      const src = "pip install pythinker-code\n";
      expect(renderReadme(codeProduct, src)).toBe(src);
    });
  });

  describe("config integrity (Mode-B lockstep, §7 item 2)", () => {
    test("no product config carries the stale pre-migration slug", () => {
      for (const p of products) {
        expect(p.owner.length).toBeGreaterThan(0);
        expect(p.repo.length).toBeGreaterThan(0);
        expect(p.repo).not.toBe("Pythinker");
      }
    });
    test("each product's brewCommand agrees with its product key", () => {
      // brew formula name = pythinker-<key>; a stale slug would diverge.
      for (const p of products) {
        expect(p.brewCommand).toContain(`pythinker-${p.key}`);
      }
    });
    test("derived release URLs are built from the product owner/repo", () => {
      for (const p of products) {
        const meta = buildMetadata(p, {
          tag_name: "v0.27.0",
          html_url: `https://github.com/${p.owner}/${p.repo}/releases/tag/v0.27.0`,
          assets: codeRelease.assets,
        });
        const releaseRepo = p.releaseRepo ?? p.repo;
        const expectedBase = `https://github.com/${p.owner}/${releaseRepo}/releases`;
        expect(meta.latestReleaseUrl).toContain(expectedBase);
        expect(meta.releaseDownloadBaseUrl).toContain(`${expectedBase}/latest/download`);
        expect(meta.releaseDownloadBaseUrl).toContain(p.owner);
      }
    });
  });
  ```
  (The third config test reuses `codeRelease.assets`, whose asset names match the `pythinker-code`/`pythinker-ai` patterns `buildMetadata` requires; both products' asset regexes accept the `pythinker-<pkg>_0.27.0_*` / `PythinkerSetup-*` names present in that fixture.)
- [ ] 12.4 Run the test and watch it **fail** (functions not exported / not defined):
  ```bash
  cd /home/ai/Projects/pythinker-site/site && bun test scripts/sync-upstream-products.test.ts
  ```
  Expected: failures — `resolveRawRef`/`buildVersionJson`/`renderReadme` are not exported (import errors or "is not a function").
- [ ] 12.5 Implement `renderReadme` (replaces the inline ternary at lines 365-367). Add the function near `buildMetadata`:
  ```ts
  // The AI README still carries the pre-migration "Pythinker" repo slug in its
  // release links (an old repo name that is NOT in any product config). Rewrite
  // it to the configured owner/repo so the served README never points at the
  // dead repo. Destination is DERIVED from config (not a second hardcoded
  // literal) so a future owner/repo change can't reintroduce the 0.24.0 drift.
  function renderReadme(product: ProductConfig, readme: string): string {
    if (product.key !== "ai") return readme;
    const legacy = "github.com/mohamed-elkholy95/Pythinker/releases";
    const dest = `github.com/${product.owner}/${product.repo}/releases`;
    return readme.replaceAll(legacy, dest);
  }
  ```
- [ ] 12.6 Implement `resolveRawRef` and `buildVersionJson`. Add near the top-level helpers (e.g. after `rawUrl`):
  ```ts
  // The dispatched ref is either a release tag (vX.Y.Z) or a 40-char commit SHA
  // (the install-script/README push path sends github.sha). Validate strictly —
  // it is interpolated into a raw.githubusercontent URL — and fall back to the
  // product branch on anything else. NEVER used to build release-asset URLs
  // (those always come from the live API tag_name).
  function resolveRawRef(ref: string | undefined, branch: string): string {
    if (ref && /^(v\d+\.\d+\.\d+|[0-9a-f]{40})$/.test(ref)) return ref;
    return branch;
  }

  function buildVersionJson(meta: ProductMetadata): { pythinkerCode: string; tag: string } {
    return { pythinkerCode: meta.version, tag: meta.tag };
  }
  ```
- [ ] 12.7 Wire the ref-pin into `rawUrl`/`syncProduct`, replace the line-366 call site with `renderReadme`, and emit `version.json` in `main`. Change `rawUrl` (line 184) to accept a ref:
  ```ts
  function rawUrl(product: ProductConfig, sourcePath: string, ref: string): string {
    return `https://raw.githubusercontent.com/${product.owner}/${product.repo}/${ref}/${sourcePath}`;
  }
  ```
  Replace `syncProduct` (lines 359-382) so it computes the ref once and threads it through both raw fetches and uses `renderReadme`:
  ```ts
  async function syncProduct(product: ProductConfig): Promise<ProductMetadata> {
    const ref = resolveRawRef(process.env.SYNC_SOURCE_REF, product.branch);
    const [release, readme] = await Promise.all([
      fetchJson<ReleaseResponse>(apiLatestReleaseUrl(product)),
      fetchText(rawUrl(product, product.readmeSourcePath, ref)),
    ]);
    const readmeContents = renderReadme(product, readme);
    writeTextFile(product.readmeTargetPath, readmeContents);
    for (const mirror of product.installMirrors ?? []) {
      const installSource = await fetchText(rawUrl(product, mirror.sourcePath, ref));
      validateMirrorSource(installSource, mirror.validators);
      for (const targetPath of mirror.targetPaths) {
        writeTextFile(targetPath, installSource);
      }
    }
    const metadata = buildMetadata(product, release);
    writeTextFile(product.metadataPath, renderMetadataModule(product.metadataConstName, metadata));
    return metadata;
  }
  ```
  Replace `main` (lines 384-388) to emit `public/version.json` from the code product:
  ```ts
  async function main(): Promise<void> {
    const ai = await syncProduct(products[0]);
    const code = await syncProduct(products[1]);
    updateLlmsText(ai, code);
    writeTextFile("public/version.json", `${JSON.stringify(buildVersionJson(code), null, 2)}\n`);
  }
  ```
- [ ] 12.8 Run the test and watch it **pass**:
  ```bash
  cd /home/ai/Projects/pythinker-site/site && bun test scripts/sync-upstream-products.test.ts
  ```
  Expected: all tests pass (e.g. `11 pass, 0 fail`). This is the real gate for the TS changes (it imports and exercises the edited module).
- [ ] 12.9 Commit (NOTE: do NOT rely on `bun run typecheck` here — `site/tsconfig.json`'s `include` is `["src/**/*", "src/**/*.vue", "env.d.ts"]`, so `vue-tsc` never sees `scripts/`; the `bun test` in 12.8 is the authoritative verification for this file):
  ```bash
  git -C /home/ai/Projects/pythinker-site/site add scripts/sync-upstream-products.ts scripts/sync-upstream-products.test.ts
  git -C /home/ai/Projects/pythinker-site/site commit -m "feat(sync): version.json emit, ref-pinned raw fetch, config-derived README rewrite + tests"
  ```

### Task 13 — Receiver source-repo gate + `git rm` dead mirrors

**Files:** Modify `.github/workflows/sync-upstream-products.yml`; Modify `scripts/sync-upstream-products.ts` (drop dead mirror targets); `git rm` 3 files. Verify: `actionlint` + `bun test`.

- [ ] 13.1 Add the job-level receiver gate to `sync-upstream-products.yml`. The gate must let cron/manual through (no payload) and only restrict `repository_dispatch`. Add to the `sync` job after `runs-on: ubuntu-latest` (current line 20):
  ```yaml
      if: github.event_name != 'repository_dispatch' || github.event.client_payload.source_repo == 'TechMatrix-labs/pythinker-code'
  ```
- [ ] 13.2 Thread the dispatched ref into the sync via `env:` (NEVER into a `run:` line — injection, §4). Edit the `Sync public upstream products` step (current lines 30-33):
  ```yaml
        - name: Sync public upstream products
          env:
            GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
            SYNC_SOURCE_REF: ${{ github.event.client_payload.tag }}
          run: bun run sync:products
  ```
  (The TS validates `SYNC_SOURCE_REF` via `resolveRawRef` before any use; an empty/garbage value falls back to `branch`. For cron/manual there is no payload, so `SYNC_SOURCE_REF` is empty → branch fallback.)
- [ ] 13.3 Lint:
  ```bash
  ~/go/bin/actionlint /home/ai/Projects/pythinker-site/site/.github/workflows/sync-upstream-products.yml
  ```
  Expected: prints nothing, exits 0.
- [ ] 13.4 Drop the 3 dead mirror target paths from the TS config (lines 123-129). Edit the `scripts/install.ps1` mirror's `targetPaths` to keep only the canonical served copy:
  ```ts
          targetPaths: [
            "public/install.ps1",
          ],
  ```
  (`scripts/install.ps1`, `web/public/install.ps1`, `docs/public/install.ps1` are removed — they are byte-identical dead mirrors; canonical served pair is `public/install.{sh,ps1}`, §7.)
- [ ] 13.5 `git rm` the 3 tracked dead mirrors:
  ```bash
  git -C /home/ai/Projects/pythinker-site/site rm scripts/install.ps1 web/public/install.ps1 docs/public/install.ps1
  ```
  Expected: `rm 'scripts/install.ps1'`, `rm 'web/public/install.ps1'`, `rm 'docs/public/install.ps1'`.
- [ ] 13.6 Re-run the TS tests (config change must not break them):
  ```bash
  cd /home/ai/Projects/pythinker-site/site && bun test scripts/sync-upstream-products.test.ts
  ```
  Expected: all tests still pass (e.g. `11 pass, 0 fail`).
- [ ] 13.7 Commit:
  ```bash
  git -C /home/ai/Projects/pythinker-site/site add .github/workflows/sync-upstream-products.yml scripts/sync-upstream-products.ts
  git -C /home/ai/Projects/pythinker-site/site commit -m "ci(sync): receiver source-repo gate, ref via env; git rm 3 dead install.ps1 mirrors"
  ```

### Task 14 — Retire orphaned GHCR+Watchtower+Traefik deploy (GATED by OP-4)

Only do this if **OP-4** confirmed the live host runs Dokploy build-from-source. Otherwise skip and log under "Out of scope". This is reversible (`git rm`).

**Files:** `git rm` `docker-compose.yml`, `docker-compose.private-ghcr.yml`, `deploy/traefik/` (recursive), `deploy/.env.example`; rewrite `deploy/README.md`. Verify: visual + grep for dead refs.

- [ ] 14.1 Remove the dead compose + traefik + env files:
  ```bash
  git -C /home/ai/Projects/pythinker-site/site rm docker-compose.yml docker-compose.private-ghcr.yml deploy/.env.example
  git -C /home/ai/Projects/pythinker-site/site rm -r deploy/traefik
  ```
  Expected: `rm 'docker-compose.yml'` etc. (If any path is already absent, confirm with OP-4's host findings and adjust the list to only the tracked files; `git ls-files docker-compose.yml docker-compose.private-ghcr.yml deploy/.env.example deploy/traefik` lists what is actually tracked.)
- [ ] 14.2 Rewrite `deploy/README.md` around Dokploy build-from-source (keep `Dockerfile`/`nixpacks.toml`/`server.ts` as documented). Replace the whole file:
  ```markdown
  # Deployment

  The Pythinker landing site deploys via **Dokploy build-from-source**: Dokploy
  builds the repo with nixpacks (`nixpacks.toml`) and runs `bun run server.ts`,
  which serves the built `dist/` and a `bun:sqlite` install-counter behind a
  POST endpoint. The website-sync workflow's `git push` to `main` is the deploy
  trigger.

  ## What runs
  - `server.ts` — Bun server: static `dist/` + `/api` install-copy counter (SQLite at `/app/.data`).
  - `Dockerfile` + `nixpacks.toml` — single-container build inputs (Dokploy uses nixpacks; `Dockerfile` is a documented fallback for Railway/Render/Coolify-style hosts).

  Persist `/app/.data` across redeploys or the SQLite counter resets.

  ## Counter environment variables
  ```env
  INSTALL_COPY_COUNTER_HOME_INITIAL_VALUE=0
  INSTALL_COPY_COUNTER_AI_INITIAL_VALUE=0
  ```
  `HOME` is the root page (`/`); `AI` is `/ai`. Stored values only increase.

  ## Deploy dependency
  This chain relies on `pythinker-home`'s `main` being unprotected so the sync
  workflow can push. If `main` is ever protected, exempt `github-actions[bot]`
  or the deploy chain breaks.

  > The previous GHCR image + Watchtower + Traefik compose stack was retired
  > (no image was published after `docker.yml` was deleted, and the GHCR ref
  > pointed at a stale org). Canonical deploy is Dokploy build-from-source.
  ```
- [ ] 14.3 Confirm no remaining references to the retired stack in tracked files:
  ```bash
  cd /home/ai/Projects/pythinker-site/site && git grep -nE 'watchtower|traefik|SITE_IMAGE|private-ghcr' -- . ':!deploy/README.md' || echo "clean"
  ```
  Expected: `clean` (the only `traefik`/`watchtower` mentions remaining, if any, are the historical note inside `deploy/README.md`, which is excluded).
- [ ] 14.4 Commit:
  ```bash
  git -C /home/ai/Projects/pythinker-site/site add -A
  git -C /home/ai/Projects/pythinker-site/site commit -m "chore(deploy): retire orphaned GHCR+Watchtower+Traefik; canonical = Dokploy build-from-source"
  ```

### Task 15 — Open PR-home-3

- [ ] 15.1 Push + PR:
  ```bash
  git -C /home/ai/Projects/pythinker-site/site push -u origin release-orch/p0-site
  gh pr create --repo TechMatrix-labs/pythinker-home --base main \
    --title "P0: receiver source-repo gate, version.json, Mode-B fix, dead mirrors, deploy retire" \
    --body "P0 site half: job-level receiver if: on client_payload.source_repo (cron/manual carry no payload -> allowed); ref passed via env, validated in TS, never into a run: shell; emit public/version.json {pythinkerCode,tag}; fix the line-366 hardcoded literal to derive from per-product owner/repo config; pin raw-source fetch to the dispatched ref (tag or 40-char sha) while asset URLs stay from API tag_name; git rm the 3 dead tracked install.ps1 mirrors (canonical = public/install.{sh,ps1}); retire orphaned GHCR+Watchtower+Traefik compose (Dokploy build-from-source is canonical). New bun:test unit tests (incl. §7 config lockstep) for the TS logic."
  ```
  Expected: prints the new PR URL.
- [ ] 15.2 Wait for checks + CodeRabbit `success` on the head SHA (C2):
  ```bash
  gh pr checks --repo TechMatrix-labs/pythinker-home <PR#>
  gh api repos/TechMatrix-labs/pythinker-home/commits/$(gh pr view --repo TechMatrix-labs/pythinker-home <PR#> --json headRefOid -q .headRefOid)/status --jq '.statuses[] | select(.context=="CodeRabbit") | .state'
  ```
  Expected: checks `pass`; CodeRabbit `success`. Merge `--squash` only after `success`. (pythinker-home `main` must stay unprotected for the deploy chain — do not enable protection.)

---

## Phase verification

**Done = all three PRs merged (each past CodeRabbit `success`, C2), the App fully replaces both PAT dispatch sites, the next release flips only when every pinned sub-package resolves on PyPI, the readiness issue ticks rows then closes on success, and the site serves a correct `public/version.json` with the reconcile backstop live.** Prove it with one rehearsal + one real cycle:

1. **App dispatch (post PR-code-1):** `gh workflow run dispatch-pythinker-home-sync.yml --repo TechMatrix-labs/pythinker-code` → `gh run watch` green; the mint step succeeds; pythinker-home shows a fresh `repository_dispatch` sync run that **passes the receiver gate** (source_repo matches). This proves the App token + receiver gate end-to-end. (Confirms OP-1..OP-3.)

2. **Reconcile dry-run (post PR-code-2 + PR-home-3):** `gh workflow run release-readiness-reconcile.yml --repo TechMatrix-labs/pythinker-code` → `gh run watch`. With the site already at latest, expect **no drift** (`drift=` empty), the stale-issue close step runs cleanly (closing only older-than-latest issues, leaving any newer in-progress issue open), `notify-drift` does NOT run. To prove the drift path, the run's "Detect drift" log shows the served `pythinkerCode` vs latest comparison; the `notify-drift` job's `if:` (drift present AND not re-dispatched this run) confirms a normal re-dispatch run does not page.

3. **promote rehearsal (no real tag):** after a real release tag exists, `gh workflow run promote-release.yml --repo TechMatrix-labs/pythinker-code -f tag=v<latest>` re-enters CHECKING; with all four PyPI URLs already 200 and assets present, it PROMOTES idempotently (PATCH is a no-op), the `release-readiness` issue is upserted, its rows ticked, then closed, and the `dispatch-site` job mints the App token and fires. The Slack `notify-failure` job does NOT run (no failure). This exercises the new blocking-PyPI check and the separated dispatch job without waiting on a fresh build.

4. **First real release** (the true end-to-end): maintainer tags `vX.Y.Z`; `promote-release` waits for assets + all four PyPI pins; on ready it flips `prerelease=false, make_latest=true`, ticks+closes the readiness issue, and the `needs: promote` dispatch job updates pythinker-home → Dokploy redeploys → `https://pythinker.com/version.json` returns `{"pythinkerCode":"X.Y.Z","tag":"vX.Y.Z"}`. Confirm:
   ```bash
   curl -fsSL https://pythinker.com/version.json
   gh release view vX.Y.Z --repo TechMatrix-labs/pythinker-code --json isLatest,isPrerelease
   pip index versions pythinker-code   # or: pip install pythinker-code==X.Y.Z --dry-run
   ```
   Expected: `version.json` == X.Y.Z; release `isLatest=true, isPrerelease=false`; `pip install` resolves all transitive pins (no 500 on a lagging sub-package).

5. **Retire the PATs (OP-5):** after step 4's green cycle, delete `PYTHINKER_HOME_REPO_DISPATCH_TOKEN` and `PYTHINKER_CORE_PAGES_TOKEN`. Re-run step 1's dispatch once more to confirm nothing depended on the deleted PAT (still green via the App).

**Negative-path checks (must hold):** if a sub-package PyPI pin lags, the promote run stays in CHECKING and on budget-exhaust **keeps the release as prerelease** (so `/releases/latest` serves last-good), PATCHes the readiness issue body with the unticked sub-package row, comments the per-channel bottleneck on the issue, posts the red Slack with the `Detail` field carrying the named bottleneck (via `needs.promote.outputs.bottleneck`), and exits 1 — never flips to a half-resolvable `pip install`. If the `dispatch-site` job fails (empty/missing App token), it exits 1 loud with the "release IS promoted, self-heals via reconcile/cron" Slack detail and does NOT contaminate the promote success signal. The readiness-issue auto-close must NEVER close a release-readiness issue whose tag is semver-newer than `/releases/latest` (Task 11.3 reproduction proves the `sort -V` guard).
