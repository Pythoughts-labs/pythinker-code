The user ran `/learn`. Review this session and extract reusable lessons worth persisting, then save them. {focus}

## What to extract

Look for, in priority order:

1. **Corrections** — anywhere the user corrected you or rejected an approach. These are the highest-value lessons.
2. **Error resolutions** — a non-obvious root cause and what actually fixed it.
3. **Workarounds** — library quirks, API limitations, version-specific or environment-specific fixes.
4. **Project conventions discovered the hard way** — invariants, test pins, or tooling behavior that surprised you.

## Quality bar (apply strictly)

- Extract the PATTERN, not the instance. Phrase every lesson as a trigger rule: "when X, do Y" — so it fires the next time the situation occurs.
- One pattern per lesson. Do not bundle.
- Skip trivial fixes (typos, simple syntax errors) and one-time issues (a specific outage, a transient flake).
- Skip anything the repository already records (AGENTS.md, code comments, git history, existing memory entries). If asked to remember one of those, distill what was non-obvious about it instead.
- A lesson that would not change your behavior in a future session is decoration — drop it.

## How to persist

- Save each lesson with the Memory tool (`action=add`, `target=memory`). The memory store has a small total budget, so keep each entry to one or two terse sentences.
- Before adding, check the existing memory entries injected into your context: if a related entry exists, use `action=replace` to sharpen it into one stronger rule instead of adding a near-duplicate.
- Use `target=user` only for durable facts about the user themselves (preferences, workflow), never for code or project facts.
- If the repository keeps a lessons file (e.g. `tasks/lessons.md`), longer repo-specific rules belong there as well — append, never rewrite others' entries.

## Finish

Report each saved lesson verbatim and where it was saved. If nothing in the session meets the bar, say exactly that and save nothing — an empty result is a valid result.
