---
name: create-pr
description: Prepare a pull request by summarizing changes, verification, risks, and reviewer guidance without adding AI footers.
---

# Create PR

Use when the user asks to prepare or draft a pull request, PR description, or review-ready summary.

## Workflow

1. Inspect the branch diff and recent commits.
2. Identify user-visible changes, tests run, and risks.
3. Draft a concise PR title and body using the repository's PR template when available.
4. Include exact verification commands and results.
5. Call out screenshots/videos needed for user-visible changes.

## Rules

- Do not add AI-generated footers or co-author trailers.
- Do not push, open, or publish a PR unless explicitly asked.
- Do not claim tests passed unless they were run.
- Keep changelog entries aligned with repository conventions.

## Output

```text
TITLE
SUMMARY
TEST PLAN
RISKS
PR BODY
```
