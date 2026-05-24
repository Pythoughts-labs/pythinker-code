---
name: resolve-merge-conflicts
description: Resolve git merge/rebase conflicts safely by preserving both sides' intent and validating the result.
---

# Resolve Merge Conflicts

Use when files contain conflict markers or the user asks to resolve merge, rebase, or cherry-pick conflicts.

## Workflow

1. Inspect `git status` and list conflicted files.
2. Read each conflict with surrounding context.
3. Understand the intent of both sides before editing.
4. Resolve the conflict with the smallest combined change that preserves behavior.
5. Run formatters/tests relevant to the resolved files when practical.
6. Report any conflicts that need human product judgment.

## Rules

- Never choose one side blindly.
- Do not run destructive git commands unless explicitly confirmed.
- Do not stage, commit, continue rebase, or continue merge unless the user asks.
- Remove all conflict markers from resolved files.

## Output

```text
SUMMARY
RESOLVED FILES
DECISIONS
VERIFICATION
BLOCKERS
```
