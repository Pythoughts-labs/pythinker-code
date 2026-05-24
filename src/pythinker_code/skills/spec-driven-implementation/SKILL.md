---
name: spec-driven-implementation
description: Implement a feature or fix from product/technical specs while checking the final code against the stated requirements.
---

# Spec-Driven Implementation

Use when the task references a product spec, tech spec, design doc, issue plan, or explicit acceptance criteria.

## Workflow

1. Read the relevant spec files or acceptance criteria.
2. Extract required behavior, non-goals, constraints, and verification gates.
3. Map the existing implementation and tests before editing.
4. Produce a short implementation plan tied to the spec.
5. Make surgical changes only for the requested behavior.
6. Check the implementation against each requirement.
7. Run the smallest meaningful verification gate and report any skipped gate.

## Rules

- Do not implement unstated nice-to-haves.
- If the spec conflicts with existing code or another spec, stop and surface the conflict.
- Preserve public compatibility unless the spec explicitly changes it.
- Add or update tests when behavior changes and the project has relevant tests.

## Output

Return:

```text
SUMMARY
SPEC REQUIREMENTS
CHANGES
SPEC CHECK
VERIFICATION
RISKS
```
