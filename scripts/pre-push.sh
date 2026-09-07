#!/usr/bin/env bash
# Pre-push gate: catches classes of CI failure locally before they burn a CI run.
# Cheapest/most-certain checks run first and fail fast.
#
# Escape hatch: SKIP_HOOKS=1 git push   (or git push --no-verify)
set -euo pipefail

if [[ "${SKIP_HOOKS:-0}" == "1" ]]; then
  echo "[pre-push] SKIP_HOOKS=1 set, skipping all checks."
  exit 0
fi

cd "$(git rev-parse --show-toplevel)"

start_ts=$(date +%s)

# git's pre-push protocol feeds "<local ref> <local oid> <remote ref> <remote oid>"
# lines on stdin. Capture once so any sub-check that needs it (the AI
# co-authorship scan) can reuse it.
stdin_file="$(mktemp)"
trap 'rm -f "$stdin_file"' EXIT
cat > "$stdin_file"

fail() {
  local job="$1" msg="$2"
  local elapsed=$(( $(date +%s) - start_ts ))
  echo "❌ pre-push: would fail CI job \`${job}\` — ${msg}" >&2
  echo "   Escape hatch: SKIP_HOOKS=1 git push   (or git push --no-verify)" >&2
  echo "[pre-push] failed after ${elapsed}s" >&2
  exit 1
}

step() {
  local name="$1"
  shift
  echo "[pre-push] running: ${name}"
  "$@"
}

# What's already on the remote — used to scope diff-based checks (nix hash,
# changed-package typecheck, changed-test selection). Bootstrap-safe: falls
# back to origin/HEAD, then to skipping those checks entirely.
resolve_base_ref() {
  local upstream
  upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)
  if [[ -n "$upstream" ]] && git rev-parse --verify --quiet "$upstream" >/dev/null 2>&1; then
    echo "$upstream"
    return 0
  fi
  if git show-ref --verify --quiet refs/remotes/origin/HEAD; then
    echo "origin/HEAD"
    return 0
  fi
  return 1
}
base_ref="$(resolve_base_ref || true)"

# 1. AI co-authorship attribution — sub-second, blocks known-bad commits outright.
step "no-ai-coauthorship" bash scripts/git-hooks/pre-push-no-ai-coauthorship.sh < "$stdin_file" ||
  fail "pre-push-no-ai-coauthorship" "a commit contains forbidden AI agent attribution"

# 2. sherif — monorepo dependency-version skew (CI: `pnpm run sherif`).
step "sherif" pnpm run sherif || fail "sherif" "monorepo dependency versions are out of sync"

# 3. oxlint (CI: `pnpm run lint`).
step "lint" pnpm run lint || fail "lint" "oxlint reported errors"

# 4. Committed web bundle freshness. apps/pythinker-code/dist-web is generated
#    from apps/pythinker-web and read by no other gate, so a web source edit
#    without a rebuild ships a stale embedded UI with nothing red to show for it.
step "web-bundle-freshness" node apps/pythinker-code/scripts/check-web-assets.mjs ||
  fail "build" "apps/pythinker-web changed without restaging dist-web (run 'pnpm run build:web')"

# 5. Nix fetchPnpmDeps hash freshness (CI: nix build).
step "nix-hash-freshness" node scripts/check-nix-hash-fresh.mjs ||
  fail "nix build (flake.nix)" "could not verify flake.nix's pnpmDeps hash (see Nix output above)"

# 6. Typecheck, scoped to packages changed since $base_ref (CI: `pnpm run
#    typecheck`). Full typecheck builds every package first and takes
#    minutes — not affordable pre-push, so this narrows to what pnpm's own
#    dependency graph says was actually touched.
if [[ -n "$base_ref" ]]; then
  step "typecheck (changed packages)" pnpm -r --filter "...[${base_ref}]" --if-present run typecheck ||
    fail "typecheck" "type errors in a package changed on this branch"
else
  echo "[pre-push] no base ref (new branch, no origin/HEAD) — skipping scoped typecheck."
  echo "[pre-push] run 'pnpm run typecheck' manually before pushing if you touched types."
fi

# 7. Tests, scoped via vitest's own changed-file impact analysis (CI: `pnpm test`).
if [[ -n "$base_ref" ]]; then
  step "test (changed)" pnpm exec vitest run --changed "$base_ref" --passWithNoTests ||
    fail "test" "tests affected by changed files are failing"
else
  echo "[pre-push] no base ref — skipping scoped tests."
  echo "[pre-push] run 'pnpm test' manually before pushing if you touched behavior."
fi

elapsed=$(( $(date +%s) - start_ts ))
echo "[pre-push] all checks passed in ${elapsed}s"
