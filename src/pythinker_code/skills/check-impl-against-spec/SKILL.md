---
name: check-impl-against-spec
description: Compare an implementation against a product or technical spec and report gaps with evidence.
---

# Check Implementation Against Spec

Use after implementation or during review when there is a spec, issue plan, acceptance criteria, or design document.

## Workflow

1. Read the spec or acceptance criteria and extract each required behavior.
2. Read the changed implementation and relevant tests.
3. Map each requirement to code and verification evidence.
4. Identify missing, partial, over-scoped, or conflicting behavior.
5. Recommend the smallest follow-up fixes.

## Rules

- Treat the spec as the source of truth unless it conflicts with explicit user instructions.
- Do not invent requirements not present in the spec.
- Cite concrete files, functions, tests, or command output for each claim.
- Separate implementation gaps from test/documentation gaps.

## Output

```text
SUMMARY
SPEC CHECKLIST
- [pass|partial|missing|conflict] requirement — evidence
GAPS
RECOMMENDED FIXES
VERIFICATION
```
