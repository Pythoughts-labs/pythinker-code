---
name: diagnose-ci-failures
description: Diagnose failing CI, lint, typecheck, build, or test logs and propose or implement the smallest verified fix.
---

# Diagnose CI Failures

Use when a CI job, local test, lint, typecheck, or build gate fails.

## Workflow

1. Capture the failing command, exit code, and the first actionable error.
2. Identify whether the failure is deterministic, flaky, environmental, or caused by recent code.
3. Reproduce with the narrowest local command when practical.
4. Name the root cause before editing.
5. Make the smallest fix that addresses the root cause.
6. Rerun the focused failing gate and report the result.

## Rules

- Do not skip hooks or weaken tests to make CI pass.
- Do not hide unrelated failures; separate them from the fixed failure.
- Prefer targeted tests over full-suite runs until the focused failure is fixed.
- If a gate cannot run because of missing tools or credentials, report that clearly.

## Output

Return:

```text
SUMMARY
ROOT CAUSE
CHANGES
VERIFICATION
REMAINING RISKS
```
