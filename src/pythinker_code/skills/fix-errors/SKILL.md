---
name: fix-errors
description: Fix concrete errors from logs, failing commands, exceptions, or diagnostics with root-cause-first discipline.
---

# Fix Errors

Use when the user provides an error message, stack trace, failing command, type diagnostic, lint failure, or runtime exception.

## Workflow

1. Capture the exact error text, command, affected file, and line if available.
2. Reproduce or inspect the smallest relevant code path.
3. State the root cause before editing.
4. Make the smallest change that fixes the root cause.
5. Rerun the focused failing command or a targeted equivalent.

## Rules

- Do not make random fixes hoping one works.
- Do not suppress diagnostics unless the code is intentionally invalid and the test requires it.
- Do not broaden scope into unrelated cleanup.
- If the error is environmental or cannot be reproduced, report what was verified and what is blocked.

## Output

```text
SUMMARY
ROOT CAUSE
CHANGES
VERIFICATION
REMAINING ISSUES
```
