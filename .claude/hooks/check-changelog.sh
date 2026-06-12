#!/usr/bin/env bash
# Pre-hook: block `gh pr create` when shipped-code paths are changed but
# CHANGELOG.md has nothing under ## Unreleased.
# Mirrors the logic in .github/workflows/changelog-entry-required.yml so the
# gate fires locally before CI does.

set -uo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')

# Only intercept gh pr create invocations.
if ! printf '%s' "$cmd" | grep -q 'gh pr create'; then
  exit 0
fi

# Skip release-prep branches and titles (they consume ## Unreleased).
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
case "$branch" in
  release/*) exit 0 ;;
esac
if printf '%s' "$cmd" | grep -qF 'chore(release)'; then
  exit 0
fi
# [skip changelog] anywhere in the command body is also an escape hatch.
if printf '%s' "$cmd" | grep -qiF '[skip changelog]'; then
  exit 0
fi

# Determine which files changed vs the merge-base with origin/main.
base=$(git merge-base HEAD origin/main 2>/dev/null || echo "")
if [ -z "$base" ]; then
  # Can't determine base — don't block.
  exit 0
fi
changed=$(git diff --name-only "$base" HEAD 2>/dev/null || echo "")

# Check for shipped-code paths (matches the CI workflow exactly).
touched=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  case "$f" in
    src/*|packages/*) touched=1; break ;;
    scripts/install*.sh|scripts/install*.ps1) touched=1; break ;;
    pythinker.spec) touched=1; break ;;
    .github/workflows/linux-installer.yml|\
    .github/workflows/windows-installer.yml|\
    .github/workflows/homebrew-tap.yml|\
    .github/workflows/release-*.yml|\
    .github/workflows/promote-release.yml) touched=1; break ;;
  esac
done <<< "$changed"

[ "$touched" -eq 0 ] && exit 0

# Pass if ## Unreleased has at least one non-blank line.
# Checked inside awk (no pipe): `| grep -q` exits at the first match, and
# under pipefail the resulting SIGPIPE to awk reads as failure once the
# block outgrows the pipe buffer — denying exactly when the changelog is
# at its fullest.
if awk '
  /^## Unreleased[[:space:]]*$/ { inblk=1; next }
  inblk && /^## /               { inblk=0 }
  inblk && /[^[:space:]]/       { found=1; exit }
  END                           { exit !found }
' CHANGELOG.md 2>/dev/null; then
  exit 0
fi

# Block and tell the author exactly what to do.
printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"CHANGELOG gate: this branch touches shipped code but ## Unreleased in CHANGELOG.md is empty.\n\nAdd a bullet under ## Unreleased before opening the PR, for example:\n  - **Your change.** Brief description.\n\nEscape hatches:\n  - Add [skip changelog] in the PR body\n  - Use branch name release/* or title chore(release)*"}}'
