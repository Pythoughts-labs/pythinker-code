---
name: pr-walkthrough
description: Produce a concise reviewer-friendly walkthrough of a PR or diff, including changed areas, behavior, tests, and risks.
---

# PR Walkthrough

Use when the user asks for a walkthrough, summary, reviewer guide, or explanation of a PR/diff/branch.

## Workflow

1. Inspect the diff and changed file list.
2. Group changes by feature area or responsibility.
3. Explain what changed, why it matters, and how the pieces fit together.
4. Identify behavior changes, migrations, compatibility concerns, and user-visible impact.
5. Summarize tests or verification evidence if available.

## Rules

- Do not perform a deep code review unless asked; this is explanatory.
- Do not claim intent beyond what the diff, specs, or commits support.
- Call out uncertainty and missing verification plainly.
- Keep it useful for reviewers: paths, components, and reading order.

## Output

```text
SUMMARY
CHANGED AREAS
READING ORDER
BEHAVIOR CHANGES
TESTS / VERIFICATION
RISKS / OPEN QUESTIONS
```
