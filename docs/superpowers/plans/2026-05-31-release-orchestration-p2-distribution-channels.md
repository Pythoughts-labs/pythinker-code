# P2 — Broadened Distribution (Docker/GHCR, Scoop, Nix, WinGet) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Ship four best-effort distribution channels (Docker/GHCR, Scoop, Nix `apps.default`, manual WinGet) that all set `PYTHINKER_MANAGED` for channel-native upgrades, never gate `promote-release`, and carry version-less README snippets so they never enter the version-sprawl set.

**Architecture:** All four channels are additive workflows in `pythinker-code` (the source of truth). Docker builds a thin `python:3.14-slim` image that `pip install`s the already-published wheel (zero new runtime deps, C3), built multi-arch native (amd64 + ubuntu-24.04-arm), pushed by digest, stitched with `buildx imagetools`, `:latest` advanced only for a promoted (non-prerelease) release with an ancestor-check. Scoop mirrors the trusted Homebrew tap pattern exactly: a generator (`packages/scoop-bucket/generate-manifest.py`) polls the EXISTING Windows onedir zip from the release, and `scoop-bucket.yml` (in pythinker-code) mints the `pythinker-scoop-publisher` App token and git-pushes the manifest to the org repo `Pythoughts-labs/scoop-pythinker`. Nix gains an `apps.default` plus a `PYTHINKER_MANAGED=nix` wrapper env and a monthly `update-flake-lock` PR. WinGet is a manual `workflow_dispatch` using an isolated fine-grained PAT.

**Tech Stack:** GitHub Actions, `docker/build-push-action` + `buildx imagetools` (GHCR), `actions/create-github-app-token` (Scoop App), stdlib Python generator (`urllib`, mirrors `generate-formula.py`), `uv run pytest` (generator test), Nix flakes (`uv2nix`), `wingetcreate`.

---

## Cross-phase dependency (READ FIRST)

This phase **depends on P1** for the `PYTHINKER_MANAGED=<channel>` env read at the top of `_detect_upgrade_command()` in `src/pythinker_code/ui/shell/update.py`, and on the **P0 App-token pattern** (`actions/create-github-app-token`, copied from `.github/workflows/homebrew-tap.yml:79-86`).

- **Do not implement or unit-test the `PYTHINKER_MANAGED` env read here** — that code + its pytest belong to P1. P2 only *sets* the variable per channel and verifies it is set via integration checks (Docker `env`, Nix `result/bin` wrapper grep, manifest env block). If P1 has not merged when you start, surface it and either (a) wait, or (b) land P2 channels and open a follow-up that adds the `PYTHINKER_MANAGED=...` settings once P1 merges. The channels work without it (they just show the generic upgrade hint); the env read is what makes the hint channel-native.
- Only **one** task in this phase has a real failing-test-first pytest: Task 2.2 (`generate-manifest.py`). Every other task is CI-wiring (workflow YAML, App tokens, cross-repo push, Nix build) and is verified by `actionlint` + a documented dry-run on a throwaway tag, honestly marked CI-vs-local.

**Hard sequencing within P2 (from spec §6 recommended order):** Docker → Scoop → Nix → WinGet. WinGet is last and gated to manual dispatch only.

**Deviation from the literal contract phrasing (stated up front — DISCLOSED + JUSTIFIED; confirm with the contract owner):** the contract says scoop-pythinker has "its own `.github/workflows/scoop-bucket.yml`". Implemented as the Homebrew mirror instead: **`scoop-bucket.yml` lives in `pythinker-code`** and git-pushes the manifest into `scoop-pythinker`. Rationale: if the workflow ran *inside* scoop-pythinker committing to itself, the `pythinker-scoop-publisher` App would never be exercised (a same-repo `GITHUB_TOKEN` would suffice), contradicting the App's reason to exist. Running it in pythinker-code and pushing cross-repo is the only design where the App token is actually used — exactly as `homebrew-tap.yml` uses `pythinker-tap-publisher` (verified against `homebrew-tap.yml:79-145`). This is the sole disclosure of the deviation; it is not a blocker, but the contract owner should ratify it.

---

## Prerequisites (manual / operator)

These touch org admin, secrets, and an external repo — they are **operator actions**, not code steps. Do them before the Scoop/WinGet tasks. Verify each with the `gh` command shown.

### OP-1 — Create the public org repo `Pythoughts-labs/scoop-pythinker`
```bash
gh repo create Pythoughts-labs/scoop-pythinker \
  --public \
  --description "Scoop bucket for Pythinker Code. Auto-updated by pythinker-code/.github/workflows/scoop-bucket.yml on every semver release tag. Do not hand-edit bucket/*." \
  --disable-wiki
# Verify:
gh repo view Pythoughts-labs/scoop-pythinker --json visibility,name -q '.name + " " + .visibility'
# Expected: scoop-pythinker public
```
Leave it empty — `scoop-bucket.yml`'s first run initializes `main` exactly like `homebrew-tap.yml:98-145` does for the empty tap.

### OP-2 — Create + install the `pythinker-scoop-publisher` GitHub App
In the org **Settings → Developer settings → GitHub Apps → New GitHub App** (UI; cannot be scripted):
- **Name:** `pythinker-scoop-publisher`
- **Homepage URL:** `https://github.com/Pythoughts-labs/scoop-pythinker`
- **Webhook:** uncheck Active.
- **Repository permissions:** `Contents: Read and write`, `Metadata: Read-only` (mandatory). Nothing else.
- Create, then **Generate a private key** (downloads a `.pem`). Note the **App ID**.
- **Install App** → choose **Only select repositories** → select **only** `Pythoughts-labs/scoop-pythinker`.

Verify the installation is scoped to exactly one repo:
```bash
gh api /orgs/Pythoughts-labs/installations --jq '.installations[] | select(.app_slug=="pythinker-scoop-publisher") | {app_id, repository_selection}'
# Expected: repository_selection "selected"
```

### OP-3 — Add the App credentials as ORG secrets (visible to pythinker-code)
```bash
# App ID (numeric, from OP-2):
gh secret set SCOOP_BUCKET_APP_ID --org Pythoughts-labs --visibility selected --repos pythinker-code --body "<APP_ID>"
# Private key (the .pem downloaded in OP-2):
gh secret set SCOOP_BUCKET_APP_PRIVATE_KEY --org Pythoughts-labs --visibility selected --repos pythinker-code < /path/to/pythinker-scoop-publisher.private-key.pem
# Verify both exist:
gh secret list --org Pythoughts-labs | grep SCOOP_BUCKET_APP
# Expected: SCOOP_BUCKET_APP_ID  and  SCOOP_BUCKET_APP_PRIVATE_KEY listed
```

### OP-4 — (WinGet, Task 4.1 only) Create the isolated fine-grained PAT `WINGET_SUBMIT_TOKEN`
A GitHub App **cannot** open PRs against the external `microsoft/winget-pkgs`, so WinGet needs a classic/fine-grained PAT on a fork. Create a fine-grained PAT (UI: **Settings → Developer settings → Fine-grained tokens**) scoped to your `microsoft/winget-pkgs` fork with `Contents: Read and write` + `Pull requests: Read and write`, short expiry. Then:
```bash
gh secret set WINGET_SUBMIT_TOKEN --repo Pythoughts-labs/pythinker-code --body "<PAT>"
gh secret list --repo Pythoughts-labs/pythinker-code | grep WINGET_SUBMIT_TOKEN
# Expected: WINGET_SUBMIT_TOKEN listed
```

### OP-5 — Confirm GHCR is enabled for the org
GHCR (`ghcr.io`) needs no secret (uses `GITHUB_TOKEN` + `packages: write`), but the org must allow Actions to create packages. Verify after the first Docker run that the package exists:
```bash
gh api /orgs/Pythoughts-labs/packages?package_type=container --jq '.[].name'
# After first successful docker.yml run, expect: pythinker-code
```

---

## File Structure

| Action | Path | Responsibility |
|---|---|---|
| Create | `Dockerfile` | Thin `python:3.14-slim` image; `pip install pythinker-code==${V}` from PyPI; sets `PYTHINKER_MANAGED=docker`; entrypoint `pythinker`. |
| Create | `.dockerignore` | Keep the build context tiny (the wheel comes from PyPI, not the repo). |
| Create | `.github/workflows/docker.yml` | On semver release tags (`v+([0-9]).+([0-9]).+([0-9])`): wait-for-PyPI, build amd64 + arm64 by digest, stitch manifest to `ghcr.io/pythoughts-labs/pythinker-code:<version>`, advance `:latest` only when the release is promoted (non-prerelease) + ancestor-check. Best-effort. |
| Create | `packages/scoop-bucket/generate-manifest.py` | Stdlib generator: poll the release, read the EXISTING Windows onedir zip + `.sha256`, render `bucket/pythinker-code.json`. Mirrors `packages/homebrew-tap/generate-formula.py`. |
| Create | `packages/scoop-bucket/pythinker-code.json.tmpl` | Scoop manifest template with `__VERSION__`/`__URL__`/`__SHA256__` placeholders; `bin: pythinker\pythinker.exe`; `env_set: PYTHINKER_MANAGED=scoop`; version-less `autoupdate`. |
| Create | `.github/workflows/scoop-bucket.yml` | On semver release tags (`v+([0-9]).+([0-9]).+([0-9])`) + `workflow_dispatch`: generate the manifest, mint `pythinker-scoop-publisher` token, git-push `bucket/pythinker-code.json` into `scoop-pythinker`. Mirrors `homebrew-tap.yml`. |
| Create | `tests/test_scoop_manifest.py` | Failing-test-first pytest for `generate-manifest.py` (mirrors `tests/test_homebrew_formula.py`). |
| Modify | `flake.nix` | Add `apps.default` (`type=app`, `program=.../bin/pythinker`); add `--set PYTHINKER_MANAGED "nix"` to the `makeWrapper` installPhase. |
| Modify | `.github/workflows/ci-pythinker-cli.yml` | Extend the existing `nix-test` job to also run `nix run .#default -- --version` (the `apps.default` smoke check). |
| Create | `.github/workflows/update-flake-lock.yml` | Monthly cron: `nix flake update` → open a PR. |
| Create | `.github/workflows/winget.yml` | Manual `workflow_dispatch(version)` only: `wingetcreate update --submit` via the isolated PAT. |
| Modify | `README.md` | Add version-less Docker / Scoop / Nix install snippets (C4). |

---

## TASK 1 — Docker / GHCR

### Task 1.1 — Thin Dockerfile + .dockerignore

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Verify: local `docker build` (buildah-backed) — CI does the multi-arch push.

**Steps:**

- [ ] 1. Create `Dockerfile`. The image installs the already-published wheel (zero new runtime deps, C3-safe) and sets `PYTHINKER_MANAGED=docker` so the in-app updater shows a docker-native hint. `PYTHINKER_VERSION` is a build arg supplied by `docker.yml`.

```dockerfile
# syntax=docker/dockerfile:1
# Thin Pythinker Code image: installs the published wheel from PyPI so the
# container ships the exact same artifact users get from `pip install`. No
# source build, no new runtime deps (C3). The version is pinned at build time
# by docker.yml AFTER the wheel is confirmed live on PyPI.
FROM python:3.14-slim

# Build-time pin. docker.yml passes --build-arg PYTHINKER_VERSION=<X.Y.Z>.
ARG PYTHINKER_VERSION
RUN test -n "$PYTHINKER_VERSION" || (echo "PYTHINKER_VERSION build-arg is required" >&2; exit 1)

# ripgrep is the one external binary the agent shells out to; install it so the
# container is self-contained (matches the Nix wrapper's --prefix PATH ripgrep).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "pythinker-code==${PYTHINKER_VERSION}"

# Channel marker: the in-app updater (P1) reads this and prints a docker-native
# upgrade hint instead of trying to pip-upgrade inside an immutable image.
ENV PYTHINKER_MANAGED=docker

ENTRYPOINT ["pythinker"]
CMD ["--help"]
```

- [ ] 2. Create `.dockerignore` so the build context stays tiny (the wheel comes from PyPI; nothing from the repo is copied in).

```
*
!Dockerfile
```

- [ ] 3. Local sanity build (buildah is the local docker shim; this proves the Dockerfile parses and the wheel installs). Use a real published version to avoid a 404:

```bash
docker build --build-arg PYTHINKER_VERSION=0.27.0 -t pythinker-docker-test:local /home/ai/Projects/pythinker-code-main
```
Expected tail: `Successfully tagged ... pythinker-docker-test:local` (buildah: `COMMIT`). If buildah rejects `--build-arg`, run with `dangerouslyDisableSandbox` is NOT needed — instead skip local and rely on the CI dry-run in Task 1.3; note that in the commit message.

- [ ] 4. Verify the channel marker is baked in:
```bash
docker run --rm pythinker-docker-test:local env | grep PYTHINKER_MANAGED
```
Expected: `PYTHINKER_MANAGED=docker`

- [ ] 5. Commit on a feature branch (C1 — no direct main):
```bash
git switch -c feat/p2-docker-ghcr
git add Dockerfile .dockerignore
git commit -m "feat(docker): thin python:3.14-slim image installing the published wheel"
```

### Task 1.2 — docker.yml multi-arch GHCR workflow

**Files:**
- Create: `.github/workflows/docker.yml`
- Verify: `actionlint` (CI-wiring, no local pytest possible) + a throwaway-tag dry-run (Task 1.3).

**Steps:**

- [ ] 1. Create `.github/workflows/docker.yml`. Topology mirrors h-agent's `docker-publish.yml` (build-amd64 / build-arm64 / merge / move-latest), with three pythinker-specific changes the advisor flagged: (a) GHCR login with `GITHUB_TOKEN` (not Docker Hub); (b) a **wait-for-PyPI** pre-check before buildx (the wheel publishes in a parallel job and may 404); (c) `:latest` advances **only when the release is non-prerelease** (promote has flipped it) AND the ancestor-check passes. Lowercase image name is mandatory for GHCR.

> **Runbook note — `:latest` does NOT auto-advance after promotion.** `docker.yml` triggers only on semver release tags (`v+([0-9]).+([0-9]).+([0-9])`) and `workflow_dispatch` — there is **no `release:` trigger**. At tag-push time the GitHub Release is still a prerelease (created prerelease by `release-pythinker-cli.yml`), so the `move-latest` gate evaluates `isPrerelease == true` and **skips** — `:latest` is intentionally NOT moved. `promote-release.yml` later flips the release to non-prerelease via a release *edit*, which does **not** re-fire `docker.yml`. Therefore a maintainer MUST manually re-dispatch after promotion to advance `:latest`:
> ```bash
> gh workflow run docker.yml -f version=X.Y.Z   # run AFTER promote flips vX.Y.Z to non-prerelease
> ```
> On that post-promotion dispatch the gate sees `isPrerelease == false`, the ancestor-check passes, and `:latest` advances to `X.Y.Z`. This manual step is the accepted design (it keeps `:latest` from ever leading `/releases/latest`); it is repeated in Phase-verification step 4. If hands-off advancement is ever wanted, add `release: {types: [released]}` to `docker.yml` and re-verify the gate — explicitly out of scope here.

```yaml
name: Docker (GHCR)

on:
  push:
    tags:
      - "v+([0-9]).+([0-9]).+([0-9])"
  workflow_dispatch:
    inputs:
      version:
        description: "Version to (re)build (e.g. 0.27.0)"
        required: true
        type: string

permissions:
  contents: read
  packages: write

env:
  IMAGE_NAME: ghcr.io/pythoughts-labs/pythinker-code
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"

# One run per tag; never cancel a tag/dispatch run (each must publish its digest).
concurrency:
  group: docker-${{ github.ref }}
  cancel-in-progress: false

jobs:
  resolve:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.ver.outputs.version }}
    steps:
      - name: Resolve version
        id: ver
        env:
          GITHUB_REF: ${{ github.ref }}
          INPUT_VERSION: ${{ inputs.version }}
        run: |
          set -euo pipefail
          if [[ "$GITHUB_REF" =~ ^refs/tags/v([0-9]+\.[0-9]+\.[0-9]+)$ ]]; then
            version="${BASH_REMATCH[1]}"
          elif [[ -n "${INPUT_VERSION:-}" ]]; then
            version="$INPUT_VERSION"
          else
            echo "::error::No version source available" >&2
            exit 1
          fi
          echo "version=${version}" >> "$GITHUB_OUTPUT"

      # The wheel publishes in release-pythinker-cli.yml's parallel publish-python
      # job; a tag-triggered docker build can outrun it and 404. Mirror
      # homebrew-tap.yml's bounded poll (lines 58-69): wait up to 30m for the
      # PyPI version JSON to return 200 before any arch builds.
      - name: Wait for the wheel on PyPI
        env:
          PKG_VERSION: ${{ steps.ver.outputs.version }}
        run: |
          set -euo pipefail
          deadline=$(( $(date +%s) + 30 * 60 ))
          url="https://pypi.org/pypi/pythinker-code/${PKG_VERSION}/json"
          until [ "$(curl -s -o /dev/null -w '%{http_code}' "$url")" = "200" ]; do
            if [ "$(date +%s)" -gt "$deadline" ]; then
              echo "::error::pythinker-code==${PKG_VERSION} not on PyPI within 30 minutes" >&2
              exit 1
            fi
            echo "pythinker-code==${PKG_VERSION} not on PyPI yet; sleeping 30s"
            sleep 30
          done
          echo "pythinker-code==${PKG_VERSION} is live on PyPI"

  build-amd64:
    needs: resolve
    runs-on: ubuntu-latest
    timeout-minutes: 45
    outputs:
      digest: ${{ steps.push.outputs.digest }}
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Push amd64 by digest
        id: push
        uses: docker/build-push-action@v6
        with:
          context: .
          file: Dockerfile
          platforms: linux/amd64
          build-args: |
            PYTHINKER_VERSION=${{ needs.resolve.outputs.version }}
          labels: |
            org.opencontainers.image.revision=${{ github.sha }}
            org.opencontainers.image.version=${{ needs.resolve.outputs.version }}
          outputs: type=image,name=${{ env.IMAGE_NAME }},push-by-digest=true,name-canonical=true,push=true
          cache-from: type=gha,scope=docker-amd64
          cache-to: type=gha,mode=max,scope=docker-amd64
      - name: Export digest
        run: |
          mkdir -p /tmp/digests
          digest="${{ steps.push.outputs.digest }}"
          touch "/tmp/digests/${digest#sha256:}"
      - name: Upload digest artifact
        uses: actions/upload-artifact@v4
        with:
          name: digest-amd64
          path: /tmp/digests/*
          if-no-files-found: error
          retention-days: 1

  build-arm64:
    needs: resolve
    runs-on: ubuntu-24.04-arm
    timeout-minutes: 45
    outputs:
      digest: ${{ steps.push.outputs.digest }}
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Push arm64 by digest
        id: push
        uses: docker/build-push-action@v6
        with:
          context: .
          file: Dockerfile
          platforms: linux/arm64
          build-args: |
            PYTHINKER_VERSION=${{ needs.resolve.outputs.version }}
          labels: |
            org.opencontainers.image.revision=${{ github.sha }}
            org.opencontainers.image.version=${{ needs.resolve.outputs.version }}
          outputs: type=image,name=${{ env.IMAGE_NAME }},push-by-digest=true,name-canonical=true,push=true
          cache-from: type=gha,scope=docker-arm64
          cache-to: type=gha,mode=max,scope=docker-arm64
      - name: Export digest
        run: |
          mkdir -p /tmp/digests
          digest="${{ steps.push.outputs.digest }}"
          touch "/tmp/digests/${digest#sha256:}"
      - name: Upload digest artifact
        uses: actions/upload-artifact@v4
        with:
          name: digest-arm64
          path: /tmp/digests/*
          if-no-files-found: error
          retention-days: 1

  merge:
    needs: [resolve, build-amd64, build-arm64]
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Download digests
        uses: actions/download-artifact@v4
        with:
          path: /tmp/digests
          pattern: digest-*
          merge-multiple: true
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      # Stitch both per-arch digests into the version-tagged manifest list.
      - name: Create version manifest and push
        working-directory: /tmp/digests
        env:
          IMAGE_NAME: ${{ env.IMAGE_NAME }}
          TAG: ${{ needs.resolve.outputs.version }}
        run: |
          set -euo pipefail
          args=()
          for digest_file in *; do
            args+=("${IMAGE_NAME}@sha256:${digest_file}")
          done
          docker buildx imagetools create -t "${IMAGE_NAME}:${TAG}" "${args[@]}"
          docker buildx imagetools inspect "${IMAGE_NAME}:${TAG}"

  move-latest:
    needs: [resolve, merge]
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      packages: write
    concurrency:
      group: docker-move-latest
      cancel-in-progress: false
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      # Gate :latest on the GH release being PROMOTED (non-prerelease). At
      # tag-push time the release is still prerelease until promote-release.yml
      # flips it; advancing :latest to an unpromoted release would publish a
      # "latest" ahead of /releases/latest. Best-effort: if the release isn't
      # promoted yet, skip cleanly (the version tag is already pushed; a later
      # docker workflow_dispatch re-run after promotion advances :latest).
      - name: Decide whether to move :latest
        id: gate
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          VERSION: ${{ needs.resolve.outputs.version }}
        run: |
          set -euo pipefail
          is_pre=$(gh release view "v${VERSION}" \
            --repo "${GITHUB_REPOSITORY}" --json isPrerelease -q '.isPrerelease' 2>/dev/null || echo "true")
          if [ "$is_pre" != "false" ]; then
            echo "Release v${VERSION} is still prerelease (or missing); not advancing :latest."
            echo "move=false" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          # Ancestor-check (defense-in-depth, mirrors h-agent move-latest):
          # only advance if our commit descends from the current :latest.
          image_json=$(docker buildx imagetools inspect "${IMAGE_NAME}:latest" \
            --format '{{ json (index .Image "linux/amd64") }}' 2>/dev/null || true)
          if [ -z "${image_json}" ]; then
            echo "move=true" >> "$GITHUB_OUTPUT"; exit 0
          fi
          current_sha=$(printf '%s' "${image_json}" | jq -r '.config.Labels."org.opencontainers.image.revision" // ""')
          if [ -z "${current_sha}" ] || [ "${current_sha}" = "${GITHUB_SHA}" ]; then
            echo "move=true" >> "$GITHUB_OUTPUT"; exit 0
          fi
          if ! git cat-file -e "${current_sha}^{commit}" 2>/dev/null; then
            git fetch --no-tags --prune origin "+refs/heads/main:refs/remotes/origin/main" || true
          fi
          if ! git cat-file -e "${current_sha}^{commit}" 2>/dev/null; then
            echo "Registry :latest points at an unknown commit; refusing to overwrite."
            echo "move=false" >> "$GITHUB_OUTPUT"; exit 0
          fi
          if git merge-base --is-ancestor "${current_sha}" "${GITHUB_SHA}"; then
            echo "move=true" >> "$GITHUB_OUTPUT"
          else
            echo "Existing :latest is newer (likely a backport); leaving it alone."
            echo "move=false" >> "$GITHUB_OUTPUT"
          fi
      - name: Move :latest
        if: steps.gate.outputs.move == 'true'
        env:
          IMAGE_NAME: ${{ env.IMAGE_NAME }}
          VERSION: ${{ needs.resolve.outputs.version }}
        run: |
          set -euo pipefail
          docker buildx imagetools create --tag "${IMAGE_NAME}:latest" "${IMAGE_NAME}:${VERSION}"
          docker buildx imagetools inspect "${IMAGE_NAME}:latest"
```

- [ ] 2. Lint the workflow (actionlint is NOT on this machine's PATH — run it pinned via Docker so the check is real, not claimed):
```bash
docker run --rm -v /home/ai/Projects/pythinker-code-main:/repo -w /repo rhysd/actionlint:latest -color .github/workflows/docker.yml
```
Expected: no output, exit 0. (If the buildah shim cannot run this image, fall back to `gh workflow view` after push and rely on the Task 1.3 dry-run; say which you used.)

- [ ] 3. Commit:
```bash
git add .github/workflows/docker.yml
git commit -m "feat(docker): multi-arch GHCR workflow with PyPI-wait and promoted-only :latest"
```

### Task 1.3 — Docker PR + CI dry-run verification

**Files:** none (verification + merge).

**Steps:**

- [ ] 1. Push the branch and open the PR (C1):
```bash
git push -u origin feat/p2-docker-ghcr
gh pr create --base main --title "feat(docker): GHCR distribution channel" \
  --body "P2 Docker/GHCR channel. Thin python:3.14-slim image installing the published wheel; multi-arch (amd64 + ubuntu-24.04-arm); push-by-digest + imagetools manifest; :latest only for promoted releases. Best-effort, never gates promote. Sets PYTHINKER_MANAGED=docker (consumed by the P1 updater hook)."
```

- [ ] 2. CI dry-run (this is the **only** way to verify the multi-arch push end-to-end — there is no local pytest for this). Run the workflow manually against an already-published, already-promoted version:
```bash
gh workflow run docker.yml --ref feat/p2-docker-ghcr -f version=0.27.0
gh run watch "$(gh run list --workflow=docker.yml --limit 1 --json databaseId -q '.[0].databaseId')"
```
Expected observable result: `resolve` passes the PyPI-wait (0.27.0 is already live), `build-amd64` + `build-arm64` push digests, `merge` creates `ghcr.io/pythoughts-labs/pythinker-code:0.27.0`. **`move-latest` reports `move=true` and DOES advance `:latest` to `0.27.0`.** The gate keys on the GitHub Release's `isPrerelease` field, **not** on the branch the dispatch ran from: `v0.27.0` is an already-promoted (non-prerelease) release, so `is_pre=false` and (on a first run with no existing `:latest`) `move=true`. This is benign — `0.27.0` is the current released version, so `:latest` is simply re-pointed at the artifact it already represents; the wheel installed is the published PyPI artifact regardless of which branch built the image. The `move=false` skip path is exercised only against a still-prerelease tag (see Phase-verification step 5), which is the real tag-push behavior. Confirm the image:
```bash
docker buildx imagetools inspect ghcr.io/pythoughts-labs/pythinker-code:0.27.0
```
Expected: a manifest list with `linux/amd64` and `linux/arm64`.

- [ ] 3. Confirm the channel marker survives into the published image:
```bash
docker run --rm ghcr.io/pythoughts-labs/pythinker-code:0.27.0 env | grep PYTHINKER_MANAGED
```
Expected: `PYTHINKER_MANAGED=docker` (verified in CI/locally against the pulled image — NOT a pytest; this is an integration check).

- [ ] 4. **CodeRabbit gate (C2):** confirm the `CodeRabbit` commit status on the PR head SHA is `success` before merging:
```bash
gh pr view --json statusCheckRollup,commits -q '.commits[-1].oid'
gh api "/repos/Pythoughts-labs/pythinker-code/commits/<HEAD_SHA>/status" --jq '.statuses[] | select(.context=="CodeRabbit") | .state'
```
Expected: `success`. Read its summary + any "Actionable comments posted: N" before merging. Then merge via the UI/`gh pr merge --squash` only after green.

---

## TASK 2 — Scoop

### Task 2.1 — Scoop manifest template

**Files:**
- Create: `packages/scoop-bucket/pythinker-code.json.tmpl`
- Verify: read by the generator test in Task 2.2.

**Steps:**

- [ ] 1. Create `packages/scoop-bucket/pythinker-code.json.tmpl`. Placeholders mirror the Homebrew template's `__NAME__` convention. `bin` is `pythinker\pythinker.exe`: the onedir zip roots every file under a single `pythinker/` directory (`release-pythinker-cli.yml:476` builds `arcname = f"pythinker/{...}"`, same single-root layout the Homebrew formula chdirs into), and **no `extract_dir` is set** — so Scoop extracts the zip as-is, the natural `pythinker/` root is preserved, and `bin` resolves to `$dir\pythinker\pythinker.exe`. Setting `extract_dir: "pythinker"` would promote that subdirectory's *contents* to `$dir`, leaving the exe at `$dir\pythinker.exe`, after which `bin: pythinker\pythinker.exe` would double-nest to a non-existent `$dir\pythinker\pythinker.exe` and `scoop install` would fail to create the shim — do NOT re-add it. `env_set.PYTHINKER_MANAGED=scoop` is what the P1 updater reads. `autoupdate.url` is version-less (Scoop substitutes `$version` itself), which keeps the manifest out of the sprawl set.

```json
{
  "version": "__VERSION__",
  "description": "Pythinker Code is your next CLI agent.",
  "homepage": "https://pythinker.com",
  "license": "Apache-2.0",
  "architecture": {
    "64bit": {
      "url": "__URL__",
      "hash": "__SHA256__"
    }
  },
  "bin": "pythinker\\pythinker.exe",
  "env_set": {
    "PYTHINKER_MANAGED": "scoop"
  },
  "checkver": {
    "github": "https://github.com/Pythoughts-labs/pythinker-code"
  },
  "autoupdate": {
    "architecture": {
      "64bit": {
        "url": "https://github.com/Pythoughts-labs/pythinker-code/releases/download/v$version/pythinker-$version-x86_64-pc-windows-msvc-onedir.zip"
      }
    },
    "hash": {
      "url": "$url.sha256"
    }
  }
}
```

- [ ] 2. Validate it is well-formed JSON before relying on it as a template fixture:
```bash
uv run python -c "import json,pathlib; json.loads(pathlib.Path('packages/scoop-bucket/pythinker-code.json.tmpl').read_text())"
```
Expected: no output, exit 0 (the `__VERSION__` etc. are valid JSON string values, so it parses as-is).

- [ ] 3. Commit on a new branch:
```bash
git switch main && git pull
git switch -c feat/p2-scoop
git add packages/scoop-bucket/pythinker-code.json.tmpl
git commit -m "feat(scoop): manifest template pointing at the windows onedir zip"
```

### Task 2.2 — generate-manifest.py (TDD — real failing test first)

**Files:**
- Create: `tests/test_scoop_manifest.py` (write FIRST)
- Create: `packages/scoop-bucket/generate-manifest.py`
- Test runner: `uv run pytest tests/test_scoop_manifest.py -vv`

**Steps:**

- [ ] 1. Write the failing test FIRST. It mirrors `tests/test_homebrew_formula.py` exactly: `importlib`-load the generator, build a fake single-asset map for the Windows zip, render, and assert the manifest JSON. The asset name is the EXACT one produced by `release-pythinker-cli.yml:470` (`pythinker-{tag}-x86_64-pc-windows-msvc-onedir.zip`).

```python
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "packages" / "scoop-bucket" / "generate-manifest.py"
TEMPLATE = ROOT / "packages" / "scoop-bucket" / "pythinker-code.json.tmpl"


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scoop_generate_manifest", GENERATOR)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_assets(generator: ModuleType, version: str) -> dict[str, dict[str, str]]:
    name = generator.windows_zip_asset_name(version)
    return {
        name: {
            "browser_download_url": f"https://example.invalid/{name}",
            "digest": "sha256:" + ("a" * 64),
        }
    }


def test_scoop_manifest_renders_windows_zip() -> None:
    generator = load_generator()
    version = "1.2.3"
    assets = _fake_assets(generator, version)

    manifest_text = generator.render_manifest(
        TEMPLATE.read_text(encoding="utf-8"), generator.manifest_replacements(version, assets)
    )
    manifest = json.loads(manifest_text)

    assert manifest["version"] == "1.2.3"
    assert (
        manifest["architecture"]["64bit"]["url"]
        == "https://example.invalid/pythinker-1.2.3-x86_64-pc-windows-msvc-onedir.zip"
    )
    assert manifest["architecture"]["64bit"]["hash"] == "a" * 64
    assert manifest["bin"] == "pythinker\\pythinker.exe"
    assert manifest["env_set"]["PYTHINKER_MANAGED"] == "scoop"


def test_scoop_manifest_fails_when_asset_missing() -> None:
    generator = load_generator()
    with pytest.raises(RuntimeError, match="release asset missing"):
        generator.manifest_replacements("1.2.3", {})


def test_windows_zip_asset_name_matches_release_workflow() -> None:
    generator = load_generator()
    # Exact shape produced by release-pythinker-cli.yml's onedir packaging step.
    assert (
        generator.windows_zip_asset_name("0.27.0")
        == "pythinker-0.27.0-x86_64-pc-windows-msvc-onedir.zip"
    )
```

- [ ] 2. Run it and watch it fail for the right reason (the generator does not exist yet):
```bash
uv run pytest tests/test_scoop_manifest.py -vv
```
Expected: collection/import error — `FileNotFoundError`/`spec is None` because `packages/scoop-bucket/generate-manifest.py` does not exist. (Red.)

- [ ] 3. Write the minimal generator. It reuses the Homebrew generator's verified helper shapes (`_fetch_json`, `_fetch_text`, `_parse_sha256_text`, `_asset_digest_sha256`, `fetch_release_assets`) but polls the **single Windows zip** instead of the four mac/linux NATIVE_TARGETS (per spec §6 Scoop row). Full code:

```python
"""Generate the Scoop manifest for pythinker-code from GitHub Releases.

Runs in scoop-bucket.yml after the Windows onedir zip is attached to the
Pythinker GitHub Release. Points at the EXISTING
pythinker-{version}-x86_64-pc-windows-msvc-onedir.zip asset produced by
release-pythinker-cli.yml — it does NOT clone the Homebrew generator's
mac/linux NATIVE_TARGETS (Scoop is Windows-only).

Usage:
    python generate-manifest.py \
        --version 0.27.0 \
        --template packages/scoop-bucket/pythinker-code.json.tmpl \
        --output bucket/pythinker-code.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

GITHUB_REPO = "Pythoughts-labs/pythinker-code"
GITHUB_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/v{{version}}"


def windows_zip_asset_name(version: str) -> str:
    """Exact Windows onedir zip name from release-pythinker-cli.yml."""
    return f"pythinker-{version}-x86_64-pc-windows-msvc-onedir.zip"


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as resp:
        data = json.load(resp)
    if not isinstance(data, dict):
        raise RuntimeError(f"unexpected JSON payload from {url}")
    return data


def _fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_sha256_text(text: str) -> str | None:
    match = re.search(r"(?i)\b([a-f0-9]{64})\b", text)
    return match.group(1).lower() if match else None


def _asset_digest_sha256(asset: dict[str, Any]) -> str | None:
    digest = asset.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return None
    sha = digest[len("sha256:") :].lower()
    return sha if re.fullmatch(r"[a-f0-9]{64}", sha) else None


def fetch_release_assets(version: str) -> dict[str, dict[str, Any]]:
    release = _fetch_json(GITHUB_RELEASE_API.format(version=version))
    tag_name = release.get("tag_name")
    if tag_name != f"v{version}":
        raise RuntimeError(f"release tag mismatch: expected v{version}, got {tag_name!r}")
    assets: dict[str, dict[str, Any]] = {}
    for asset in release.get("assets", []):
        if isinstance(asset, dict) and isinstance(asset.get("name"), str):
            assets[asset["name"]] = asset
    return assets


def _asset_url_and_sha(assets: dict[str, dict[str, Any]], asset_name: str) -> tuple[str, str]:
    asset = assets.get(asset_name)
    if asset is None:
        raise RuntimeError(f"release asset missing: {asset_name}")
    url = asset.get("browser_download_url")
    if not isinstance(url, str) or not url:
        raise RuntimeError(f"release asset {asset_name} has no browser_download_url")
    sha = _asset_digest_sha256(asset)
    if sha is not None:
        return url, sha
    sha_asset = assets.get(asset_name + ".sha256")
    if sha_asset is None:
        raise RuntimeError(f"release asset checksum missing: {asset_name}.sha256")
    sha_url = sha_asset.get("browser_download_url")
    if not isinstance(sha_url, str) or not sha_url:
        raise RuntimeError(f"release asset checksum {asset_name}.sha256 has no download URL")
    sha = _parse_sha256_text(_fetch_text(sha_url))
    if sha is None:
        raise RuntimeError(f"could not parse SHA-256 for {asset_name}")
    return url, sha


def manifest_replacements(version: str, assets: dict[str, dict[str, Any]]) -> dict[str, str]:
    url, sha = _asset_url_and_sha(assets, windows_zip_asset_name(version))
    return {"__VERSION__": version, "__URL__": url, "__SHA256__": sha}


def render_manifest(template: str, replacements: dict[str, str]) -> str:
    manifest = template
    for placeholder, value in replacements.items():
        manifest = manifest.replace(placeholder, value)
    leftovers = sorted(set(re.findall(r"__[A-Z0-9_]+__", manifest)))
    if leftovers:
        raise RuntimeError(f"unresolved template placeholders: {', '.join(leftovers)}")
    # Parse-back assertion: the rendered manifest must be valid JSON.
    json.loads(manifest)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    assets = fetch_release_assets(args.version)
    replacements = manifest_replacements(args.version, assets)
    manifest = render_manifest(args.template.read_text(encoding="utf-8"), replacements)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(manifest, encoding="utf-8")

    digest = hashlib.sha256(manifest.encode("utf-8")).hexdigest()
    print(f"manifest written to {args.output}")
    print(f"version     : {args.version}")
    print(f"manifest sha: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] 4. Run the test and watch it pass (Green):
```bash
uv run pytest tests/test_scoop_manifest.py -vv
```
Expected: `3 passed`.

- [ ] 5. Run the repo lint on the new files so the PR's `check` job will be green (matches `make check-pythinker-code`):
```bash
uv run ruff check tests/test_scoop_manifest.py
```
Expected: `All checks passed!` (the generator lives under `packages/scoop-bucket/` which is generator code; if ruff flags it, match the homebrew generator's style — it passes today.)

- [ ] 6. Commit:
```bash
git add packages/scoop-bucket/generate-manifest.py tests/test_scoop_manifest.py
git commit -m "feat(scoop): manifest generator polling the windows onedir zip"
```

### Task 2.3 — scoop-bucket.yml (mirror homebrew-tap.yml, App-authed cross-repo push)

**Files:**
- Create: `.github/workflows/scoop-bucket.yml`
- Verify: `actionlint` + dry-run on a throwaway version (Task 2.4).

**Steps:**

- [ ] 1. Create `.github/workflows/scoop-bucket.yml`. This is `homebrew-tap.yml` with the generator/template/output/target swapped and the App swapped to `pythinker-scoop-publisher`. The token-mint step is the literal contract reference pattern (`actions/create-github-app-token`, pinned SHA copied from `homebrew-tap.yml:81`). The empty-repo first-run git dance and the empty-token fail-loud guard are copied verbatim (they are load-bearing).

```yaml
name: Update Scoop bucket

on:
  push:
    tags:
      - "v+([0-9]).+([0-9]).+([0-9])"
  workflow_dispatch:
    inputs:
      version:
        description: "Version to push to the Scoop bucket (e.g. 0.27.0)"
        required: true
        type: string

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"

jobs:
  update:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    env:
      BUCKET_OWNER: Pythoughts-labs
      BUCKET_REPO: scoop-pythinker
    steps:
      - name: Checkout source repo
        uses: actions/checkout@v4

      - name: Resolve version
        id: ver
        env:
          GITHUB_REF: ${{ github.ref }}
          INPUT_VERSION: ${{ inputs.version }}
        run: |
          set -euo pipefail
          if [[ "$GITHUB_REF" =~ ^refs/tags/v([0-9]+\.[0-9]+\.[0-9]+)$ ]]; then
            version="${BASH_REMATCH[1]}"
          elif [[ -n "${INPUT_VERSION:-}" ]]; then
            version="$INPUT_VERSION"
          else
            echo "::error::No version source available" >&2
            exit 1
          fi
          echo "version=${version}" >> "$GITHUB_OUTPUT"

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Generate Scoop manifest
        env:
          PKG_VERSION: ${{ steps.ver.outputs.version }}
        run: |
          set -euxo pipefail
          mkdir -p out/bucket
          deadline=$(( $(date +%s) + 30 * 60 ))
          until python packages/scoop-bucket/generate-manifest.py \
            --version "$PKG_VERSION" \
            --template packages/scoop-bucket/pythinker-code.json.tmpl \
            --output out/bucket/pythinker-code.json; do
            if [ "$(date +%s)" -gt "$deadline" ]; then
              echo "::error::Windows onedir zip for ${PKG_VERSION} was not ready within 30 minutes" >&2
              exit 1
            fi
            echo "Windows zip not ready for ${PKG_VERSION}; sleeping 30s"
            sleep 30
          done
          echo "--- generated manifest ---"
          cat out/bucket/pythinker-code.json

      # Mint a short-lived installation token for the org-owned
      # pythinker-scoop-publisher App (Contents: Read and write on
      # scoop-pythinker only). Same pattern as homebrew-tap.yml's tap-publisher.
      - name: Mint GitHub App token for the bucket repo
        id: app-token
        uses: actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349 # v2.2.2
        with:
          app-id: ${{ secrets.SCOOP_BUCKET_APP_ID }}
          private-key: ${{ secrets.SCOOP_BUCKET_APP_PRIVATE_KEY }}
          owner: ${{ env.BUCKET_OWNER }}
          repositories: ${{ env.BUCKET_REPO }}

      - name: Sync manifest into bucket repo (handles empty repo on first run)
        env:
          PKG_VERSION: ${{ steps.ver.outputs.version }}
          BUCKET_TOKEN: ${{ steps.app-token.outputs.token }}
        run: |
          set -euxo pipefail
          if [ -z "${BUCKET_TOKEN:-}" ]; then
            echo "::error::No bucket token available — the GitHub App token mint produced an empty value. Confirm SCOOP_BUCKET_APP_ID and SCOOP_BUCKET_APP_PRIVATE_KEY are set and the App is installed on ${BUCKET_OWNER}/${BUCKET_REPO} with Contents: Read and write, then re-run." >&2
            exit 1
          fi
          rm -rf bucket-repo
          mkdir bucket-repo
          cd bucket-repo
          git init -q -b main
          git remote add origin \
            "https://x-access-token:${BUCKET_TOKEN}@github.com/${BUCKET_OWNER}/${BUCKET_REPO}.git"
          if git ls-remote --exit-code --heads origin main >/dev/null 2>&1; then
            git fetch --depth 1 origin main
            git reset --hard FETCH_HEAD
          fi

          mkdir -p bucket
          cp ../out/bucket/pythinker-code.json bucket/pythinker-code.json

          if [ ! -f README.md ]; then
            cat > README.md <<EOF
          # scoop-pythinker

          Scoop bucket for [Pythinker Code](https://github.com/Pythoughts-labs/pythinker-code).

          \`\`\`pwsh
          scoop bucket add pythinker https://github.com/Pythoughts-labs/scoop-pythinker
          scoop install pythinker-code
          \`\`\`

          This bucket is auto-updated by the
          [scoop-bucket.yml](https://github.com/Pythoughts-labs/pythinker-code/blob/main/.github/workflows/scoop-bucket.yml)
          workflow on every semver release tag. Do not hand-edit \`bucket/*\` — your
          edits will be overwritten on the next release.
          EOF
          fi

          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

          git add bucket/pythinker-code.json README.md
          if git diff --cached --quiet; then
            echo "Manifest already up to date for ${PKG_VERSION}; nothing to push."
            exit 0
          fi
          git commit -m "pythinker-code ${PKG_VERSION}" \
                     -m "Auto-updated by pythinker-code/.github/workflows/scoop-bucket.yml"
          git push -u origin HEAD:main
```

- [ ] 2. Lint:
```bash
docker run --rm -v /home/ai/Projects/pythinker-code-main:/repo -w /repo rhysd/actionlint:latest -color .github/workflows/scoop-bucket.yml
```
Expected: no output, exit 0.

- [ ] 3. Commit:
```bash
git add .github/workflows/scoop-bucket.yml
git commit -m "feat(scoop): publish workflow mirroring the homebrew tap App pattern"
```

### Task 2.4 — Scoop PR + cross-repo dry-run

**Files:** none (verification + merge).

**Steps:**

- [ ] 1. Push + PR (C1). Requires OP-1..OP-3 done first:
```bash
git push -u origin feat/p2-scoop
gh pr create --base main --title "feat(scoop): Windows Scoop bucket channel" \
  --body "P2 Scoop channel. Generator polls the existing windows onedir zip; scoop-bucket.yml mints the pythinker-scoop-publisher App token and pushes bucket/pythinker-code.json into Pythoughts-labs/scoop-pythinker (mirrors homebrew-tap.yml). Best-effort, never gates promote. Sets PYTHINKER_MANAGED=scoop via manifest env_set."
```

- [ ] 2. Cross-repo dry-run against an already-released version (verifies the App token actually writes to scoop-pythinker — CI-only, no local equivalent):
```bash
gh workflow run scoop-bucket.yml --ref feat/p2-scoop -f version=0.27.0
gh run watch "$(gh run list --workflow=scoop-bucket.yml --limit 1 --json databaseId -q '.[0].databaseId')"
```
Expected: green run; the `Sync manifest` step ends with `git push -u origin HEAD:main` (first run) or "nothing to push". Confirm the manifest landed in the org repo:
```bash
gh api /repos/Pythoughts-labs/scoop-pythinker/contents/bucket/pythinker-code.json --jq '.path'
```
Expected: `bucket/pythinker-code.json`. Spot-check its `version` and `env_set`:
```bash
gh api /repos/Pythoughts-labs/scoop-pythinker/contents/bucket/pythinker-code.json --jq '.content' | base64 -d | python3 -c "import json,sys; m=json.load(sys.stdin); print(m['version'], m['env_set'])"
```
Expected: `0.27.0 {'PYTHINKER_MANAGED': 'scoop'}`.

> **Honesty note — what is and is NOT test-verified.** The Task 2.2 pytest only asserts the manifest *shape* (`bin`, `env_set`, url, hash), and this dry-run only confirms the manifest *file lands* in scoop-pythinker with the right `version`/`env_set`. Neither runs `scoop install` on a Windows host, so true shim/install correctness (that `bin: pythinker\pythinker.exe` resolves against the extracted `pythinker/` root and Scoop creates a working `pythinker` shim) is **outside this plan's automated checks**. It is therefore NOT claimed as test-verified — only the manifest shape and the cross-repo publish are. Real install verification requires a Windows host running `scoop bucket add pythinker https://github.com/Pythoughts-labs/scoop-pythinker && scoop install pythinker-code`; do that once manually after the first publish.

- [ ] 3. CodeRabbit gate (C2) as in Task 1.3 step 4, then merge.

---

## TASK 3 — Nix (apps.default + PYTHINKER_MANAGED + CI smoke + monthly flake.lock PR)

### Task 3.1 — apps.default + PYTHINKER_MANAGED wrapper env in flake.nix

**Files:**
- Modify: `flake.nix` (installPhase ~lines 99-108; add `apps` after `packages`/`formatter` ~line 131-132)
- Verify: CI `nix-test` job (Nix is NOT on this machine — verification is CI-only; say so).

**Steps:**

- [ ] 1. Branch:
```bash
git switch main && git pull
git switch -c feat/p2-nix
```

- [ ] 2. Add the `PYTHINKER_MANAGED=nix` channel marker to the `makeWrapper` call so the P1 updater shows a nix-native hint. The current installPhase (flake.nix:99-108) ends the `makeWrapper` with `--set PYTHINKER_CLI_NO_AUTO_UPDATE "1"`. Add one more `--set` line. Before:
```nix
                makeWrapper ${pythinkerCodePackage}/bin/pythinker $out/bin/pythinker \
                  --prefix PATH : ${lib.makeBinPath [ ripgrep ]} \
                  --set PYTHINKER_CLI_NO_AUTO_UPDATE "1"
```
After:
```nix
                makeWrapper ${pythinkerCodePackage}/bin/pythinker $out/bin/pythinker \
                  --prefix PATH : ${lib.makeBinPath [ ripgrep ]} \
                  --set PYTHINKER_CLI_NO_AUTO_UPDATE "1" \
                  --set PYTHINKER_MANAGED "nix"
```

- [ ] 3. Add the `apps` output. The flake has `packages` (line 47) and `formatter` (line 132) but **no `apps` stanza** (the contract net-new). Add `apps` using the same `forAllSystems` helper. Insert directly after the `formatter = ...;` line (line 132), before the closing `};` of the outputs attrset (line 133). New block:
```nix
      apps = forAllSystems (
        { system, ... }:
        {
          default = {
            type = "app";
            program = "${self.packages.${system}.default}/bin/pythinker";
          };
        }
      );
```
> `self` is already in scope (bound in the outputs lambda, line 24). `nix run .` works today via `meta.mainProgram` (proven by `ci-pythinker-cli.yml:328`); this makes `nix run .#default` explicit and is the canonical app entry the spec requires.

- [ ] 4. Validate the flake parses (Nix is unavailable locally — do a Nix-free syntax sanity check, then rely on CI for the real evaluation). At minimum confirm the braces balance and `nixfmt` would accept it by eye; the authoritative check is the CI `nix-test` job (Task 3.2). State in the commit that flake evaluation is verified in CI.

- [ ] 5. Commit:
```bash
git add flake.nix
git commit -m "feat(nix): add apps.default and PYTHINKER_MANAGED=nix wrapper env"
```

### Task 3.2 — Extend the existing nix-test CI job (do NOT add a new workflow)

**Files:**
- Modify: `.github/workflows/ci-pythinker-cli.yml` (the `nix-test` job, line 327-328)
- Verify: the job itself in CI on the PR.

**Steps:**

- [ ] 1. The advisor confirmed: `nix-test` (lines 305-328) ALREADY runs `nix run .#pythinker-code` and `nix run .`. Adding a whole new "nix build/run CI check" workflow would duplicate it. Extend the existing final step instead. Before (lines 327-328):
```yaml
      - name: Run nix package
        run: nix run .#pythinker-code -- --version && nix run . -- --help
```
After:
```yaml
      - name: Run nix package
        run: nix run .#pythinker-code -- --version && nix run . -- --help

      - name: Run nix app (apps.default) and assert PYTHINKER_MANAGED
        run: |
          set -euo pipefail
          nix run .#default -- --version
          nix build .#default
          grep -q 'PYTHINKER_MANAGED' result/bin/pythinker
          echo "apps.default runs and the wrapper sets PYTHINKER_MANAGED"
```
> The `grep` on `result/bin/pythinker` is the integration check that `PYTHINKER_MANAGED` is set by the wrapper (the makeWrapper-generated launcher is a shell script that `export`s its `--set` vars). This verifies the channel marker in CI — NOT a pytest.

- [ ] 2. Lint:
```bash
docker run --rm -v /home/ai/Projects/pythinker-code-main:/repo -w /repo rhysd/actionlint:latest -color .github/workflows/ci-pythinker-cli.yml
```
Expected: no output, exit 0.

- [ ] 3. Commit:
```bash
git add .github/workflows/ci-pythinker-cli.yml
git commit -m "test(nix): smoke nix run .#default and assert PYTHINKER_MANAGED in nix-test"
```

### Task 3.3 — Monthly update-flake-lock PR workflow

**Files:**
- Create: `.github/workflows/update-flake-lock.yml`
- Verify: `actionlint` + a manual `workflow_dispatch`.

**Steps:**

- [ ] 1. Create `.github/workflows/update-flake-lock.yml`. Monthly cron + manual dispatch; uses `DeterminateSystems/update-flake-lock` which opens a PR. **C1 gotcha (advisor item 5):** a PR opened with the default `GITHUB_TOKEN` does NOT trigger required status checks, so under branch protection it can never satisfy the merge gate. Options: (a) pass an App/PAT token so the PR triggers checks, or (b) document that the operator must close+reopen (or push an empty commit to) the PR to fire checks. This plan uses (b) — no new long-lived secret — and the workflow body says so. If the org later wants hands-off merges, swap `token:` to a fine-grained PAT in a follow-up.

```yaml
name: Update flake.lock

on:
  schedule:
    # 06:00 UTC on the 1st of each month.
    - cron: "0 6 1 * *"
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  update-lock:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install Nix
        uses: DeterminateSystems/nix-installer-action@main

      - name: Update flake.lock and open PR
        uses: DeterminateSystems/update-flake-lock@main
        with:
          pr-title: "chore(nix): monthly flake.lock update"
          pr-labels: dependencies
          # NOTE: this PR is opened with the default GITHUB_TOKEN, which does
          # NOT trigger required status checks. Under main branch protection
          # (enforce_admins=true) the maintainer must push an empty commit or
          # close+reopen the PR to fire CI before it can merge. To make this
          # hands-off, replace this with a fine-grained PAT/App token in a
          # follow-up. Branch prefix is the action default (update_flake_lock_action).
          branch: update-flake-lock
```

- [ ] 2. Lint:
```bash
docker run --rm -v /home/ai/Projects/pythinker-code-main:/repo -w /repo rhysd/actionlint:latest -color .github/workflows/update-flake-lock.yml
```
Expected: no output, exit 0.

- [ ] 3. Commit:
```bash
git add .github/workflows/update-flake-lock.yml
git commit -m "chore(nix): monthly update-flake-lock PR workflow"
```

### Task 3.4 — Nix PR + CI verification

**Files:** none (verification + merge).

**Steps:**

- [ ] 1. Push + PR (C1):
```bash
git push -u origin feat/p2-nix
gh pr create --base main --title "feat(nix): apps.default + channel marker + monthly lock PR" \
  --body "P2 Nix polish. Adds apps.default (nix run .#default), sets PYTHINKER_MANAGED=nix in the wrapper, extends nix-test to smoke the app + assert the marker, adds a monthly update-flake-lock PR. Nix evaluation verified in the nix-test CI job (Nix unavailable locally)."
```

- [ ] 2. Verify in CI (the only place Nix runs): on the PR, the `nix-test` job's new step must pass on all three platforms:
```bash
gh run watch "$(gh run list --workflow=ci-pythinker-cli.yml --branch feat/p2-nix --limit 1 --json databaseId -q '.[0].databaseId')"
```
Expected: `nix-test` green; step log shows `apps.default runs and the wrapper sets PYTHINKER_MANAGED`.

- [ ] 3. Dry-run the lock workflow manually (proves it opens a PR; no tag needed):
```bash
gh workflow run update-flake-lock.yml --ref feat/p2-nix
gh run watch "$(gh run list --workflow=update-flake-lock.yml --limit 1 --json databaseId -q '.[0].databaseId')"
```
Expected: green; a `chore(nix): monthly flake.lock update` PR appears (or "No changes" if the lock is already current). Close that bot PR after confirming — it is just a dry-run artifact.

- [ ] 4. CodeRabbit gate (C2), then merge.

---

## TASK 4 — WinGet (manual workflow_dispatch only)

### Task 4.1 — winget.yml manual submit workflow

**Files:**
- Create: `.github/workflows/winget.yml`
- Verify: `actionlint` + (real submit deferred — it opens a PR against microsoft/winget-pkgs; do that only on a real release).

**Steps:**

- [ ] 1. Requires OP-4 (`WINGET_SUBMIT_TOKEN`). Create `.github/workflows/winget.yml`. It is **manual only** (`workflow_dispatch`, no `push` trigger) — the hard gate from spec §6. It uses `vedantmgoyal9/winget-releaser` (the maintained wingetcreate wrapper) or a direct `wingetcreate update --submit`. This plan uses a direct `wingetcreate` call for transparency.

```yaml
name: Submit to WinGet

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Released version to submit to winget-pkgs (e.g. 0.27.0)"
        required: true
        type: string

permissions:
  contents: read

jobs:
  submit:
    # WinGet manifests can only be submitted from Windows (wingetcreate is a
    # Windows tool). Manual-only by design: a human runs this AFTER a release is
    # fully promoted, so it never gates promote and never auto-fires on a tag.
    runs-on: windows-latest
    steps:
      - name: Verify the release is published and non-prerelease
        shell: bash
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          VERSION: ${{ inputs.version }}
        run: |
          set -euo pipefail
          is_pre=$(gh release view "v${VERSION}" --repo "${GITHUB_REPOSITORY}" --json isPrerelease -q '.isPrerelease')
          if [ "$is_pre" != "false" ]; then
            echo "::error::Release v${VERSION} is not a promoted (non-prerelease) release; refusing to submit to WinGet." >&2
            exit 1
          fi

      - name: Submit manifest update with wingetcreate
        shell: pwsh
        env:
          WINGET_TOKEN: ${{ secrets.WINGET_SUBMIT_TOKEN }}
          VERSION: ${{ inputs.version }}
        run: |
          $ErrorActionPreference = "Stop"
          $installerUrl = "https://github.com/Pythoughts-labs/pythinker-code/releases/download/v$env:VERSION/PythinkerSetup-$env:VERSION.exe"
          Invoke-WebRequest -Uri "https://aka.ms/wingetcreate/latest" -OutFile wingetcreate.exe
          # PackageIdentifier must match the existing winget-pkgs entry; create it
          # once manually via `wingetcreate new` before the first automated update.
          .\wingetcreate.exe update PythoughtsLabs.PythinkerCode `
            --version $env:VERSION `
            --urls "$installerUrl" `
            --submit `
            --token $env:WINGET_TOKEN
```
> The installer asset is `PythinkerSetup-<version>.exe` — confirmed by `native_installer_asset_name()` in `src/pythinker_code/native.py:48` and the README at `README.md:151`.

> **WinGet does NOT set `PYTHINKER_MANAGED` — accepted limitation, not an oversight.** Unlike Docker (`ENV`), Scoop (`env_set`), and Nix (`makeWrapper --set`), WinGet installs the *identical* `PythinkerSetup-<version>.exe` that a direct `/releases/download` grab installs, and a WinGet manifest has **no `env_set` equivalent** to inject a process env var. So a WinGet install is byte-for-byte a native install and the in-app updater cannot distinguish the two. This is fine: that installer drops the `.pythinker-native` sentinel (`src/pythinker_code/native.py:17`), so `is_native_build()` returns `True` and `_detect_upgrade_command()` (`src/pythinker_code/ui/shell/update.py:100`) routes WinGet users to the **native-installer upgrade hint** — a correct, if not WinGet-specific, message. A genuinely WinGet-native upgrade hint would require a marker or wrapper that does not exist today; that is a documented **follow-up**, deliberately out of P2 scope. (The contract's "Scoop/WinGet manifests set it" is honored for Scoop; for WinGet there is no manifest mechanism to honor it, hence the documented fallback.)

> **WinGet README snippet is intentionally DEFERRED (see Task 5.1).** No version-less WinGet row is added to the README in this phase. The `PythoughtsLabs.PythinkerCode` PackageIdentifier does not exist in `microsoft/winget-pkgs` until a human runs this workflow on a real release (and a maintainer first creates it via `wingetcreate new`). Advertising `winget install PythoughtsLabs.PythinkerCode` before that manifest is merged would point users at a non-existent package. The README row is therefore added only after the first WinGet manifest is live — tracked as a follow-up, not a silent omission.

- [ ] 2. Lint:
```bash
docker run --rm -v /home/ai/Projects/pythinker-code-main:/repo -w /repo rhysd/actionlint:latest -color .github/workflows/winget.yml
```
Expected: no output, exit 0.

- [ ] 3. Branch + commit:
```bash
git switch main && git pull
git switch -c feat/p2-winget
git add .github/workflows/winget.yml
git commit -m "feat(winget): manual workflow_dispatch submit via isolated PAT"
```

- [ ] 4. Push + PR (C1):
```bash
git push -u origin feat/p2-winget
gh pr create --base main --title "feat(winget): manual WinGet submit workflow" \
  --body "P2 WinGet (last, manual only). workflow_dispatch-only submit to microsoft/winget-pkgs via the isolated WINGET_SUBMIT_TOKEN PAT; guarded to non-prerelease releases. Never auto-fires on a tag; never gates promote. First-ever PackageIdentifier must be created manually with 'wingetcreate new'."
```
> Do NOT do a live `--submit` dry-run — it opens a real PR against microsoft/winget-pkgs. The first real submission happens on the next genuine release by a human running this workflow. Verification here is `actionlint` green + CodeRabbit; the live behavior is exercised on a real release.

- [ ] 5. CodeRabbit gate (C2), then merge.

---

## TASK 5 — README version-less snippets (C4)

### Task 5.1 — Add Docker / Scoop / Nix install rows

**Files:**
- Modify: `README.md` (the platform install table ~lines 151-155; the install detail section ~lines 210-227)
- Verify: `tests/test_version_lockstep.py` (P1) must still pass — these snippets are version-less so they add NO version-bearing strings.

**Steps:**

- [ ] 1. Branch (this can ride with any one channel PR, but a standalone doc PR is cleanest):
```bash
git switch main && git pull
git switch -c docs/p2-install-snippets
```

- [ ] 2. Add three **version-less** rows to the platform install table. After the Homebrew row (`README.md:153`), insert:
```markdown
| **🐳 Docker** | `docker run --rm -it ghcr.io/pythoughts-labs/pythinker-code` | GHCR multi-arch image |
| **🪟 Windows — Scoop** | `scoop bucket add pythinker https://github.com/Pythoughts-labs/scoop-pythinker && scoop install pythinker-code` | auto-published Scoop bucket |
| **❄️ Nix** | `nix run github:Pythoughts-labs/pythinker-code` | flake `apps.default` |
```
> Every command is version-less (`scoop install pythinker-code`, `docker run ghcr.io/...`, `nix run github:...`) per spec §6 "C4 for new channels" — they never enter the F3 sprawl set, so the lockstep test (which only asserts version-bearing strings) is unaffected.
>
> **WinGet row is intentionally omitted here (deferral, not oversight).** Three rows are added — Docker, Scoop, Nix — and **no** WinGet row. The `PythoughtsLabs.PythinkerCode` PackageIdentifier does not exist in `microsoft/winget-pkgs` until the manual `winget.yml` workflow (Task 4.1) submits it on a real release, so advertising `winget install PythoughtsLabs.PythinkerCode` now would point users at an unpublished package. Add the version-less WinGet row (`winget install PythoughtsLabs.PythinkerCode`) in a follow-up once the first manifest is merged upstream. This deferral is also recorded in Task 4.1.

- [ ] 3. Sanity check that you introduced no `==<version>` or `PythinkerSetup-<version>` strings (would break the P1 lockstep test):
```bash
git diff README.md | grep -E '^\+' | grep -E '==[0-9]+\.[0-9]+\.[0-9]+|PythinkerSetup-[0-9]' && echo "FOUND VERSIONED STRING — FIX" || echo "OK: no versioned strings added"
```
Expected: `OK: no versioned strings added`.

- [ ] 4. If P1 is merged, run the lockstep test to prove the README edits didn't break it:
```bash
uv run pytest tests/test_version_lockstep.py -vv
```
Expected: `passed` (only run if P1's test exists; if P1 isn't merged yet, skip and note it).

- [ ] 5. Commit, push, PR (C1):
```bash
git add README.md
git commit -m "docs(p2): add version-less Docker, Scoop, and Nix install snippets"
git push -u origin docs/p2-install-snippets
gh pr create --base main --title "docs(p2): version-less install snippets for new channels" \
  --body "C4-compliant version-less install commands for the P2 channels (Docker/GHCR, Scoop, Nix). No version-bearing strings added, so the lockstep test is unaffected."
```

- [ ] 6. CodeRabbit gate (C2), then merge.

---

## Phase verification (prove the WHOLE phase works end-to-end)

**Done means:** the next real `vX.Y.Z` tag publishes all four channels best-effort, none of them gate `promote-release`, and each non-self-updating channel sets `PYTHINKER_MANAGED`.

1. **Pre-flight (before the next real release):** all four PRs merged; OP-1..OP-5 confirmed (`gh secret list --org Pythoughts-labs | grep SCOOP_BUCKET_APP` shows both; `gh repo view Pythoughts-labs/scoop-pythinker` is public). P1 merged (the `PYTHINKER_MANAGED` env read exists in `update.py`) — otherwise the markers are set but unread.

2. **First real release rehearsal:** on the next maintainer release, after the human pushes `vX.Y.Z`, watch the four channel workflows fire from the tag:
```bash
for wf in docker.yml scoop-bucket.yml homebrew-tap.yml; do
  echo "== $wf =="; gh run list --workflow=$wf --limit 1 --json status,conclusion,headBranch
done
```
Expected: `docker.yml` and `scoop-bucket.yml` complete (green) **independently of** `promote-release.yml`. `winget.yml` does NOT appear (manual-only, correct).

3. **Prove promote is NOT gated by P2:** confirm `promote-release.yml`'s blocking set contains only PyPI(code+core+host+review) + GH assets — NOT Docker/Scoop/Nix (this is P0's edit; here we only assert P2 channels are absent from the gate). Inspect:
```bash
grep -n "docker\|scoop\|ghcr\|nix" .github/workflows/promote-release.yml || echo "GOOD: no P2 channel referenced in promote gate"
```
Expected: `GOOD: no P2 channel referenced in promote gate`.

4. **Channel-live checks after the release:**
   - Docker: `docker run --rm ghcr.io/pythoughts-labs/pythinker-code:<X.Y.Z> --version` prints `X.Y.Z`; `docker run --rm ... env | grep PYTHINKER_MANAGED` → `docker`. **`:latest` does NOT auto-advance** — `docker.yml` has no `release:` trigger and promote flips the prerelease flag via a release edit that does not re-fire it (see Task 1.2 runbook note). After promotion the maintainer MUST run `gh workflow run docker.yml -f version=X.Y.Z`; only after that re-dispatch does `:latest` resolve to `X.Y.Z` (verify with `docker buildx imagetools inspect ghcr.io/pythoughts-labs/pythinker-code:latest`).
   - Scoop: `gh api /repos/Pythoughts-labs/scoop-pythinker/contents/bucket/pythinker-code.json` shows `version == X.Y.Z` and `env_set.PYTHINKER_MANAGED == scoop`.
   - Nix: the `nix-test` CI job on main is green and its log shows the `PYTHINKER_MANAGED` assertion passing; `nix run github:Pythoughts-labs/pythinker-code -- --version` (on a Nix host) prints `X.Y.Z`.
   - WinGet: a human runs `gh workflow run winget.yml -f version=X.Y.Z` only after promotion; it opens a PR on the winget-pkgs fork.

5. **Best-effort proof:** intentionally re-run `docker.yml` against a still-prerelease tag (e.g. immediately after a tag, before promote flips it) — `move-latest` must report `move=false` and skip, while the version tag still publishes. This proves a channel failure/lag can never advance `:latest` ahead of `/releases/latest` and can never block the release.

**If anything is red:** the channel is best-effort, so a single red channel workflow must NOT be treated as a release failure — fix-and-rerun the channel workflow with `gh workflow run <wf> -f version=X.Y.Z`. Only `promote-release` (P0) failing is a release failure.

---

## Finalize notes (review punch-list applied)

This plan is the finalized deliverable; the review punch-list has been folded into the body. For traceability:

- **Scoop `extract_dir` (stale BLOCKING item — dropped, NOT a live defect).** An earlier draft's punch-list claimed the Scoop manifest set both `extract_dir: "pythinker"` and `bin: "pythinker\pythinker.exe"` (double-nest). The current Task 2.1 template (the JSON block) has **no `extract_dir` key**, and the Task 2.1 prose explains why adding one would double-nest the shim. Bin resolution is correct as written: the Windows onedir zip roots all files under a single `pythinker/` directory (`release-pythinker-cli.yml` builds `arcname = f"pythinker/{...}"`), so with no `extract_dir` the natural `pythinker/` root is preserved and `bin` resolves to `$dir\pythinker\pythinker.exe`. **Do NOT re-add `extract_dir`.**
- **Docker Task 1.3 step 2 (fixed).** The dry-run rationale now matches the gate's actual `isPrerelease` logic: dispatching `version=0.27.0` yields `move=true` (benign, re-points `:latest` at the current release), and the `move=false` skip is exercised only against a still-prerelease tag (Phase-verification step 5).
- **Docker `:latest` post-promotion (fixed).** Task 1.2 runbook note + Phase-verification step 4 now state `:latest` does NOT auto-advance after promotion and require the maintainer to run `gh workflow run docker.yml -f version=X.Y.Z` after promote flips the prerelease flag.
- **WinGet `PYTHINKER_MANAGED` (acknowledged).** Task 4.1 documents that WinGet installs the identical native `.exe`, has no `env_set` mechanism, and therefore falls back to the native-installer hint via `is_native_build()`/`.pythinker-native` — an accepted limitation with a documented follow-up.
- **WinGet README row (deferred explicitly).** Tasks 4.1 and 5.1 state the version-less WinGet row is deferred until the first manifest is live in `microsoft/winget-pkgs` (don't advertise an unpublished PackageIdentifier).
- **Scoop install verification honesty (added).** Task 2.4 notes that true shim/install correctness needs a Windows host running `scoop install`; the automated checks verify only manifest shape + cross-repo publish.
- **`scoop-bucket.yml` location (disclosed deviation, confirm with contract owner).** Recorded at the top of the plan: the workflow lives in `pythinker-code` (not `scoop-pythinker`) and pushes cross-repo via the `pythinker-scoop-publisher` App — the only design that actually exercises the App, mirroring `homebrew-tap.yml`.
- **C1/C2/C3/C5 verified.** Every task is branch→PR→CodeRabbit(C2)→merge (C1); the Dockerfile's apt packages are container system deps, not pyproject runtime deps (C3); no task touches CHANGELOG (C5). Local-vs-CI honesty holds: Task 2.2 is the only real failing-test-first pytest; all workflow/Nix/cross-repo steps are marked CI-verified.
