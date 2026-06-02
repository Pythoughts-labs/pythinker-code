#!/usr/bin/env bash
#
# coderabbit-merge-gate.sh
#
# PreToolUse(Bash) hook. Gates `gh pr merge` on CodeRabbit having FINISHED its
# review of the PR's head commit ("review-complete" gate):
#
#   - CodeRabbit commit status on head == success  -> allow (surface findings)
#   - status == pending                            -> BLOCK (still reviewing)
#   - status == failure/error                      -> BLOCK (problem)
#   - status absent / cannot verify                -> BLOCK (not reviewed yet)
#
# A finished review lets the merge proceed even if it has actionable comments
# (that is the "resolve-all-issues" gate, deliberately not enabled here). The
# count is surfaced so it is not silently ignored. Every failure path fails
# SAFE to BLOCK -- it never silently allows a merge it could not verify.
#
# Blocking uses permissionDecision:"deny" rather than "ask" on purpose: this
# environment runs defaultMode:auto + skipAutoPermissionPrompt, which silently
# auto-approves "ask", making it a no-op. "deny" is a hard block. To override
# (e.g. CodeRabbit is down), edit/remove this hook in .claude/settings.local.json
# or run the merge yourself outside the agent.
#
# Authoritative signal is the `CodeRabbit` commit status (set by commit_status:
# true in .coderabbit.yaml): pending while reviewing, success when complete. A
# new push resets it to pending, so this is inherently staleness-proof.
#
# Reads the hook payload on stdin, emits a PreToolUse decision as JSON on stdout.

set -o pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // ""' 2>/dev/null)"

# Fast path: only act when `gh pr merge` is an actual command, not a substring.
# Anchor it to a command boundary (line start, &&, ;, |, then, do) so it still
# catches compound forms (`cd x && gh pr merge 9`) but NOT mentions inside
# `echo "... gh pr merge ..."`, `git commit -m "... gh pr merge ..."`, or
# `rg "gh pr merge"`. Anything else passes untouched.
if ! printf '%s' "$cmd" | grep -qE '(^|&&|;|\||\bthen\b|\bdo\b)[[:space:]]*gh[[:space:]]+pr[[:space:]]+merge([[:space:]]|$)'; then
  exit 0
fi

# Emit a hard "deny" decision (blocks the merge) and exit.
block() {
  jq -nc --arg r "$1" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}

# Inject context for the model but do not block (normal permission flow continues).
note() {
  jq -nc --arg c "$1" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$c}}'
  exit 0
}

command -v gh >/dev/null 2>&1 || block "CodeRabbit gate: 'gh' not found — cannot verify CodeRabbit review. Confirm manually before merging."
command -v jq >/dev/null 2>&1 || exit 0  # jq missing: cannot build payload; do not block.

# Target repo: honor -R/--repo on the merge command, else the current repo.
repo="$(printf '%s' "$cmd" | grep -oE '(-R|--repo)[ =]+[^ ]+' | head -1 | sed -E 's/^(-R|--repo)[ =]+//')"
repo_args=()
[ -n "$repo" ] && repo_args=(--repo "$repo")

# PR number: prefer pull/<n> from a URL, then a bare integer argument, else the
# current branch's PR. (A bare-digit token avoids grabbing digits inside an
# owner name such as ".../mohamed-elkholy95/...".)
args="$(printf '%s' "$cmd" | sed -E 's/.*gh[[:space:]]+pr[[:space:]]+merge//')"
pr="$(printf '%s' "$args" | grep -oE 'pull/[0-9]+' | head -1 | grep -oE '[0-9]+')"
if [ -z "$pr" ]; then
  pr="$(printf '%s' "$args" | tr ' ' '\n' | grep -xE '[0-9]+' | head -1)"
fi
if [ -z "$pr" ]; then
  pr="$(gh pr view "${repo_args[@]}" --json number --jq '.number' 2>/dev/null)"
fi
[ -n "$pr" ] || block "CodeRabbit gate: could not determine the PR for this merge. Confirm CodeRabbit reviewed it, then merge."

# owner/repo for the commit-status API.
nwo="$repo"
[ -n "$nwo" ] || nwo="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null)"
[ -n "$nwo" ] || block "CodeRabbit gate: could not resolve the repository for PR #$pr. Confirm CodeRabbit review, then merge."

# Head commit of the PR.
sha="$(gh pr view "$pr" "${repo_args[@]}" --json commits --jq '.commits[-1].oid' 2>/dev/null)"
[ -n "$sha" ] || block "CodeRabbit gate: could not read PR #$pr head commit. Confirm CodeRabbit review, then merge."

# CodeRabbit commit status on the head commit.
cr_state="$(gh api "repos/$nwo/commits/$sha/status" \
  --jq '.statuses[] | select(.context=="CodeRabbit") | .state' 2>/dev/null | head -1)"

# Latest "Actionable comments posted: N" from CodeRabbit's completion comment.
actionable="$(gh pr view "$pr" "${repo_args[@]}" --json comments --jq '
  [ .comments[]
    | select(.author.login=="coderabbitai")
    | select(.body | contains("coderabbit-review-completion-marker"))
    | (.body | capture("Actionable comments posted: (?<n>[0-9]+)").n)
  ] | last // "unknown"' 2>/dev/null)"

case "$cr_state" in
  success)
    if [ "$actionable" = "0" ] || [ "$actionable" = "unknown" ] || [ -z "$actionable" ]; then
      note "CodeRabbit review complete on PR #$pr (no actionable comments). Proceeding."
    else
      note "CodeRabbit review complete on PR #$pr with $actionable actionable comment(s). Review-complete gate allows the merge — confirm those were addressed/resolved before merging."
    fi
    ;;
  pending)
    block "CodeRabbit is still reviewing the latest commit on PR #$pr (status: pending). Wait for the review to finish before merging."
    ;;
  failure|error)
    block "CodeRabbit commit status on PR #$pr is '$cr_state'. Investigate and resolve before merging."
    ;;
  *)
    block "No CodeRabbit review found on PR #$pr's head commit ($sha). CodeRabbit may not have reviewed this push yet (or is not enabled here). Confirm before merging."
    ;;
esac
