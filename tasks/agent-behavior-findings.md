# Agent behaviour review — `.pythinker` + `.pythinker-review`

Diagnosis from runtime artifacts (review run `20260522015318-650c6d67`, scratch
sessions May 27–28). Evidence-based; root causes confirmed in source.

## Status (applied 2026-05-28)
- **R1 — applied** (`reviewers/common.py`): retry now relays the concrete
  validation error + an explicit title-length nudge. Tests:
  `test_retry_prompt_surfaces_previous_validation_error`.
- **R2 — applied** (`reviewers/schema.py`): `title` is truncated (≤80, ellipsis)
  via a before-validator instead of hard-failing the whole `ReviewerOutput`.
  Tests: `test_reviewer_output_truncates_overlong_title`,
  `test_overlong_title_is_truncated_not_dropped`.
- **S1 — applied** (`scratchpad.py` + `cli/__init__.py`): `append_scratch_event_sync`
  gained an idempotent `dedup_signature`; the CLI passes `source:<src>` so a
  relaunch no longer appends a duplicate "session start". Tests:
  `test_session_start_event_is_idempotent_per_signature`.
- **R4 — applied** (`reviewers/prompts/*.system.md`): the `evidence_snippet`
  placeholder now demands VERBATIM, character-for-character copying (no
  paraphrase/ellipses) across all four reviewer prompts, so the model's output
  passes the containment validator instead of being dropped per-finding.
- **S2 — applied** (`scratchpad.py`): labels now collapse by key —
  single-valued keys (`session/workspace/ui/source/scope`) keep the latest
  value, multi-valued keys (`kind`) keep the unique set. Kills
  `source:startup | source:resume` noise while retaining `kind:todo | kind:agent`.
  Tests: `test_session_labels_collapse_single_valued_keys`. (Note: the original
  delimiter-injection worry was already mitigated by `_clean_event_text`, which
  strips `|`/`\r`/`\n`; this change addresses the residual duplicate-key noise.)
- **R3 — deliberately NOT applied.** Gating the run when a chunk is unreviewable
  (`malformed_output`) is *correct* fail-closed behaviour for a security tool;
  making it non-gating would let a file pass review unreviewed. R1+R2+R4 instead
  cut the failure *rate* so runs pass legitimately.
- **S3 — deliberately NOT applied.** Auto-pruning scratch files conflicts with
  the module's documented design (`scratchpad.py` header: retained as history
  "unless the user explicitly asks for cleanup"). S1 already removes the main
  growth driver (duplicate session-starts); broader retention is a product
  decision for the user, not a silent change.

Original findings below.

## Review subsystem (the background review subagent) — highest impact

### R1 [High] Retry never relays the real validation error → systematic schema misses lose the whole chunk
`reviewers/common.py:69-92`. On a parse/validation failure the harness retries
once, but `_RETRY_SUFFIX` (common.py:15) only says *"your response was not valid
JSON … reply with strict JSON only."* The captured Pydantic error (`last_error`,
common.py:87) is **never fed back to the model**. So when the failure is a
*content* violation (e.g. a title > 80 chars — valid JSON, invalid schema), the
retry message is actively misleading and the model has no reason to change. Both
attempts fail → `ok=False` → **every finding in that chunk is discarded.**
- Evidence: meta `chunk_failures` — `tests/ui_and_conv/test_prompt_tips.py`
  failed with *4* `String should have at most 80 characters` errors; the whole
  chunk's findings were lost.
- Fix direction: append `last_error` to the retry prompt so the model can
  self-correct.

### R2 [High] No field-level coercion at ingest; one bad field nukes the chunk
`reviewers/schema.py:16` `title: str = Field(max_length=80)`. `ReviewerOutput`
is parsed all-or-nothing via `model_validate_json` (common.py:84), so a single
over-long title (or any one out-of-range field) fails the *entire* output and
drops all sibling findings in the chunk. Smaller models (run model: MiniMax
M2.7) hit the 80-char cap routinely.
- Fix direction: soft-coerce on ingest (truncate title to 80 with ellipsis)
  instead of hard-failing; or parse findings individually so one bad finding
  doesn't take the rest down.

### R3 [Med] Model-formatting noise gates the entire run
`engine/runner.py:163` `failed=(not allow_partial) and bool(real_failures)`, and
`real_failures` excludes `validation_error` but **includes** `malformed_output`
(runner.py:156). Result: 2 of 54 chunks failing on model-formatting (long title,
truncated JSON) flipped the whole run to `status: "failed"` despite 42 valid
findings delivered. `malformed_output` is a model-quality issue like
`validation_error`, not a runtime failure (timeout/llm_error/worker_error).
- Fix direction: treat `malformed_output` as non-gating (like validation_error),
  or add a distinct "delivered with model-output gaps" status.

### R4 [Low / mostly positive] Evidence-snippet validation is graceful but mismatch rate is high
`reviewers/validation.py:_snippet_matches` already falls back rendered-diff →
whitespace-compacted → on-disk slice → compacted file (good; these drop
**per-finding**, not per-chunk — runner.py:101-115). But 7 findings still failed
evidence match, i.e. the model paraphrases snippets beyond whitespace.
- Fix direction: emphasise verbatim copying in the reviewer prompt, or add a
  token-overlap fuzzy match as a last-resort tier.

## Scratchpad / session memory (`.pythinker/scratch`)

### S1 [Med] "session start" journaling is not idempotent
`cli/__init__.py:761-781` emits a `session start` event unconditionally on every
CLI init for the session, with no guard against an existing start block for the
same session id.
- Evidence: session `7f7a8039` has **4** `session start / source: startup`
  entries in 3 min; `06ba6c38`, `7c6a9676`, `f42f6caa` each have duplicate
  same-minute startups. Defeats the file's stated "compact" purpose.
- Fix direction: skip if the last event for the session id is already a
  session-start within N seconds, or only emit once per genuine create/resume.

### S2 [Med] Label line: duplicate keys unmerged + unsanitised free text → parse/injection risk
The `labels:` line is `key:value` joined by ` | `.
- Duplicate keys are appended, not merged: `source:startup | source:resume`,
  multiple `kind:` values (`kind:todo | kind:agent-batch | kind:agent`). Recall
  on labels sees conflicting values.
- The raw session title is embedded as a scope label:
  `scope:Goal: perform a deep code scan analysis of the…` — contains a colon,
  spaces, an ellipsis, and could contain `|` or a newline from an arbitrary
  title, corrupting any `:`/`|` splitter.
- Evidence: session `b241579b` labels line.
- Fix direction: dedupe/merge by key; slugify or escape the title before using
  it as a label value (or store title separately, not as a label).

### S3 [Low] Unbounded scratch growth; no-op sessions persist boilerplate
Most `untitled` files are 558 bytes = header + a single session-start (sessions
that did nothing). Combined with S1, the dir grows unbounded with low-value
files; no pruning/retention observed.
- Fix direction: lazy-create the file on first substantive event, and/or prune
  near-empty session files on a retention policy.

## Positive — validates the enhancement direction
Background agent-batch + todo journaling is coherent. Session `b241579b`:
4 background agents (`review`, `security-reviewer`, `explore`, `verifier`)
tracked start→completed, todo progressing 0→6 done, agent-type captured
(`7c6a9676`: `agent-type:code-reviewer`, `agent started / mode: foreground`).
The SetTodoList + background-subagent foundation being enhanced is sound; the
gaps above are in the *journaling* and *review-output* layers, not the
orchestration itself.
