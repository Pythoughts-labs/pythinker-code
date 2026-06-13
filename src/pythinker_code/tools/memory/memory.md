Save durable, declarative facts to persistent per-project memory that survives
across sessions and is injected into future wakeups. Keep entries compact.

WRITE FACTS, NOT INSTRUCTIONS:
- "Project uses pytest with xdist" ✓ — "Run tests with pytest -n 4" ✗
- "User prefers concise answers" ✓ — "Always respond concisely" ✗

AUTHORITATIVE FILES FIRST:
If a fact would change how you already behave according to a file you read (AGENTS.md, a
protocol/spec/config), EDIT that file — do not store it here. Memory does not change files
you follow, so the change would be silently lost. Rephrasing a correction as a preference
("set the limit to 100" → "user prefers a 100-word limit") does NOT turn a file edit into a
memory fact. When the user corrects a rule, find and edit the file that governs it first.

CONFIRMATION ON FLAGGED WRITES:
An add/replace whose content looks like a rule or a value/limit, or that names a project
file, is shown to the user for confirmation before it is stored. If they decline (or no
user is available), the entry is NOT saved and the tool tells you so — treat that as a
signal to edit the governing file instead, not as an error to retry. Plain durable facts
save without a prompt.

TWO TARGETS:
- `memory`: project facts — conventions, architecture notes, gotchas, key file locations.
- `user`: how the user likes to work in this repo — preferences, style, do/don't.

DO NOT store: task progress, session outcomes, "fixed bug X / merged PR Y /
Phase N done", PR/issue numbers, commit SHAs, file counts, or anything stale
within a week. Those are transient and belong in the session journal, not memory.
Store only non-obvious facts — deviations, gotchas, conventions — not baseline
behavior any agent would assume. Store rules the user actually stated, never ones
you inferred from conversation fragments. NEVER store secrets, tokens, or credentials.

ACTIONS:
- `add`: append a new entry (requires `content`).
- `replace`: update an entry — identify it by `index` or `old_text`; `content` = new text.
- `remove`: delete an entry — identify it by `index` or `old_text`.
- `list`: show current entries, each with its `[index]`, size, and how much room is free (read-only).

IDENTIFYING AN ENTRY: prefer `index` (the `[N]` shown by `list`) — it is exact. Use `old_text`
(a unique substring) only when you are sure of the literal stored text. If a remove/replace
fails to match, run `list` and retry with the `index` rather than guessing the substring again.

WHEN A WRITE IS REJECTED FOR SPACE:
The error reports the exact free budget and lists existing entries. Do NOT retry the
same write with a slightly shorter entry — instead `remove` or `replace` a stale or
redundant entry to free room, or consolidate two entries into one. Use `list` first if
unsure what is stored.

Memory writes are best-effort housekeeping: if room cannot be freed in one or two
steps, drop the write and continue the user's actual task. Never loop on a rejected
memory write.
