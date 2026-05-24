---
name: write-tech-spec
description: Draft a technical implementation spec from product requirements and codebase evidence.
---

# Write Tech Spec

Use when the user asks for a technical spec, implementation plan, architecture note, or product-spec-to-engineering breakdown.

## Workflow

1. Read the product requirements or issue context.
2. Scout the relevant code paths, APIs, tests, and constraints.
3. Propose the smallest architecture that satisfies the requirements.
4. Identify data model, API, UI, migration, compatibility, and security implications.
5. Define implementation phases and verification gates.

## Rules

- Ground the spec in existing code evidence; cite paths where possible.
- Prefer incremental, reversible changes.
- Do not over-design speculative extension points.
- Surface open questions and risky trade-offs explicitly.

## Output

```text
# Technical Spec: <title>

## Context
## Existing Code Evidence
## Proposed Design
## Implementation Plan
## Testing / Verification
## Migration / Compatibility
## Security / Privacy
## Risks
## Open Questions
```
