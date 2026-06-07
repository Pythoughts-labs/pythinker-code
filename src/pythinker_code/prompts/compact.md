
---

The above is a list of messages in an agent conversation. Compact it into a stable handoff summary that lets the agent continue without rereading the dropped history.

Output exactly the Markdown structure shown below. Keep section names and order unchanged. Use terse bullets, not prose paragraphs. Preserve exact file paths, commands, error strings, identifiers, user constraints, and verification results when known. Do not mention the summary process or that context was compacted.

## Goal

- [single-sentence summary of the user's current objective]

## Constraints & Preferences

- [user constraints, project rules, style preferences, approvals/trust boundaries, or "(none)"]

## Progress

### Done

- [completed work and verified outcomes, or "(none)"]

### In Progress

- [current partial work, active branch/session state, or "(none)"]

### Blocked

- [blockers, missing info, unavailable tools, or "(none)"]

## Key Decisions

- [decision and why it was chosen, or "(none)"]

## Next Steps

- [ordered next actions with acceptance/verification where known, or "(none)"]

## Critical Context

- [important technical facts, errors and resolutions, risks, assumptions, or "(none)"]

## Relevant Files

- [path: why it matters and latest known state, or "(none)"]

Rules:
- Keep every section even when empty.
- Preserve only final working code state; remove redundant attempts while keeping lessons from failures.
- For code snippets, keep full snippets only when short; otherwise keep signatures, changed symbols, and key logic.
- For errors, keep the exact error text and the final or next diagnostic action.
- If prior summaries are present, merge still-true details and remove stale details.
