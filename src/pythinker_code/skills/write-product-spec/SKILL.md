---
name: write-product-spec
description: Draft a product spec from a user request, issue, or bug report with goals, non-goals, requirements, and acceptance criteria.
---

# Write Product Spec

Use when the user asks for a product spec, feature brief, issue-to-spec conversion, or acceptance criteria.

## Workflow

1. Restate the user problem and target users.
2. Define goals and non-goals.
3. Specify user-facing behavior and edge cases.
4. Add acceptance criteria that can be verified.
5. Note dependencies, rollout concerns, telemetry/observability needs, and open questions.

## Rules

- Do not prescribe implementation details unless they affect product behavior.
- Separate confirmed requirements from assumptions.
- Keep acceptance criteria testable and specific.
- Ask the parent/user for missing product decisions rather than inventing them.

## Output

```text
# Product Spec: <title>

## Problem
## Goals
## Non-goals
## User Stories
## Requirements
## Acceptance Criteria
## Rollout / Risks
## Open Questions
```
