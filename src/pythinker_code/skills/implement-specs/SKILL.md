---
name: implement-specs
description: Implement one or more checked-in specs using scout-plan-implement-verify workflow.
---

# Implement Specs

Use when the task is to implement existing spec files, issue plans, or acceptance criteria.

## Workflow

1. Locate and read the requested spec files.
2. Extract required behavior, constraints, non-goals, and verification gates.
3. Scout the existing code and tests before editing.
4. Produce a concise plan tied to spec requirements.
5. Implement the smallest viable change.
6. Run focused tests or checks.
7. Compare final behavior against the spec.

## Rules

- Keep changes tied directly to spec requirements.
- Ask or stop if specs conflict or are underspecified in a way that changes architecture.
- Preserve public compatibility unless the spec explicitly changes it.
- Add tests when behavior changes and a matching test layer exists.

## Output

```text
SUMMARY
IMPLEMENTED REQUIREMENTS
CHANGES
VERIFICATION
SPEC GAPS OR FOLLOW-UPS
```
