Save durable, declarative facts to persistent per-project memory that survives
across sessions and is injected into future wakeups. Keep entries compact.

WRITE FACTS, NOT INSTRUCTIONS:
- "Project uses pytest with xdist" ✓ — "Run tests with pytest -n 4" ✗
- "User prefers concise answers" ✓ — "Always respond concisely" ✗

TWO TARGETS:
- `memory`: project facts — conventions, architecture notes, gotchas, key file locations.
- `user`: how the user likes to work in this repo — preferences, style, do/don't.

DO NOT store: task progress, session outcomes, "fixed bug X / merged PR Y /
Phase N done", PR/issue numbers, commit SHAs, file counts, or anything stale
within a week. Those are transient and belong in the session journal, not memory.
NEVER store secrets, tokens, or credentials.

ACTIONS:
- `add`: append a new entry (requires `content`).
- `replace`: update an entry (`old_text` = a unique substring of the target entry; `content` = new text).
- `remove`: delete an entry (`old_text` = a unique substring of the target entry).
- `list`: show current entries with their sizes and how much room is free (read-only).

WHEN A WRITE IS REJECTED FOR SPACE:
The error reports the exact free budget and lists existing entries. Do NOT retry the
same write with a slightly shorter entry — instead `remove` or `replace` a stale or
redundant entry to free room, or consolidate two entries into one. Use `list` first if
unsure what is stored.

Memory writes are best-effort housekeeping: if room cannot be freed in one or two
steps, drop the write and continue the user's actual task. Never loop on a rejected
memory write.
