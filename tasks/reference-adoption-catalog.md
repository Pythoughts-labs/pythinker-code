# Reference Adoption Catalog — best practices from the blackbox agent-harness reference

## Execution status (branch `feat/reference-adoption`, off `main`)

- **Waves 1–3 DONE** (10 items, 11 commits, all TDD + clean-code-guard; Wave 2 items
  security-reviewed SAFE TO MERGE; `make check-pythinker-code` green, 2151 tests passing):
  - W1: `system-prompt` cmd · shell-timeout drift-guard · memory freshness caveat ·
    bounded fan-out cap · per-session spend ceiling.
  - W2: dangerous-host deny-set (`EDIT_DANGEROUS`) · accept-edits tier (`/accept-edits`).
  - W3: `TurnOutcome.produced_answer` (observable) · required-MCP spawn gate · UserPromptSubmit
    `additionalContext` injection.
- **Wave 4 RESOLVED** (#11 DONE, #13 DONE, #12 architectural no-go — AGENTS.md kept in the system prompt):
  - **#11 read-before-write file-state cache. DONE** (`38eb98d1`; extended to StrReplaceFile via the
    shared `overwrite_is_stale` helper in `eb9773f9`). Adapted to stale-detection only (full
    read-before-write would break pythinker's "write without prior read" contract). Technique (from the reference
    `utils/file_state_cache.py`): a session-scoped path→read-mtime cache; ReadFile records the
    mtime at read; WriteFile-overwrite and StrReplaceFile then require the path to have been read
    AND reject if the on-disk mtime is newer ("File has been modified since read"). Scope to
    EXISTING-file overwrites only (new files exempt). Edge cases that must be right: the tool's own
    successful write updates the cache (so the agent can immediately re-edit); a partial-view inject
    (truncated AGENTS.md/MEMORY.md) should still require an explicit read. Cache owner on
    Runtime/Session; touches `tools/file/{read,write,replace}.py`. Tool-semantics change → CHANGELOG
    + security review required. This is invasive (the core edit path) — best executed in a focused
    session.
  - **#12 project/env context as a separate `<system-reminder>` user message. ARCHITECTURAL NO-GO —
    not implemented.** The user approved the minimal version (move only the merged AGENTS.md out of
    `system.md` §11 into a session-start `<system-reminder>`); on implementation it proved infeasible
    without forbidden speculative infra. AGENTS.md must survive compaction AND not truncate (≤32 KiB).
    The system prompt (`context._system_prompt`, stored separately from messages) is the only home that
    satisfies both — it is never summarized and carries its own 32 KiB budget. A **seed user message**
    is lossily summarized at the first compaction: `compaction.py` `prepare()` walks history backward
    and preserves only the last `max_preserved_messages`=2 user/assistant messages verbatim, so a
    leading AGENTS.md lands in `to_compact` → `_build_compact_message` summarizes it, degrading the
    project's NON-NEGOTIABLE rules (fail-closed approvals, trust boundaries, no co-author trailers) into
    a summary. A **dynamic injection** is hard-capped at `injection_ceiling_tokens`=2048 by
    `collect_within_budget` (`pythinkersoul.py:592-617`) — it would truncate AGENTS.md; no unbudgeted
    path exists. Both non-system-prompt variants need NEW load-bearing machinery (compaction-pin a
    verbatim head message, or an unbudgeted large-injection special case), which the project's
    MVC / no-speculative-abstractions / root-cause-robust rules forbid, for marginal NON-reference cache
    value (the reference itself bakes env into the system array — the separate-message technique was a
    scout misattribution). AGENTS.md is the single worst field to move (large + must-not-degrade);
    moving only the small volatile bits (`PYTHINKER_NOW`, `PYTHINKER_WORK_DIR_LS`) is the original
    marginal-value catalog #12 and is not pursued. Verdict: keep AGENTS.md in the system prompt; the
    `agent.py:66` TODO is a documented no-go in pythinker's compaction+budget architecture.
  - **#13 max-output-token escalation ladder. DONE** (`67fca31c` pythinker-core surfaces
    `GenerateResult.truncated`; `1af5eec8` soul-side bounded continuation nudge). Shipped the bounded
    resume-nudge (capped by `loop_control.max_truncation_recoveries`, default 3 / 0 disables); the
    per-step `max_output_tokens` escalation was intentionally dropped as higher-risk / lower-value than
    the continuation nudge. Original blocked-on-truncation-signal plan kept below for provenance.
    Reverse-engineered executable plan (cross-package; tests in BOTH `pythinker-core` and
    `pythinker-code`):
    1. `chat_provider/pythinker.py` `PythinkerStreamedMessage` captures `_id`/`_usage` but NOT
       `finish_reason`. Add `self._finish_reason: str | None = None`, set it from
       `choices[0].finish_reason` in both `_convert_stream_response` and
       `_convert_non_stream_response` (openai-compatible; `"length"` == truncated), and expose a
       `finish_reason` property (mirror the `id`/`usage` properties ~lines 400-410).
    2. `_generate.py`: after building the message (line ~91), read `stream.finish_reason` and set a
       new `GenerateResult.truncated: bool = False` (line 98 dataclass) — true when finish_reason is
       `"length"` (the visible-text-then-cap case the existing think-only guard at :81-89 misses).
       A `usage.output >= provider max_tokens` heuristic is the imprecise fallback if a provider
       lacks finish_reason.
    3. `soul/pythinkersoul.py` `_step` (where `usage`/`_session_cost_usd` are read, ~line 1666): on
       `result.truncated`, escalate the per-step max_output_tokens once (new `LoopControl` field),
       then append a bounded number of PARAPHRASED resume-nudges ("resume mid-thought, no recap,
       break remaining work into smaller pieces" — never copy the reference's literal string), then
       surface. Per-step max_output_tokens override plumbing through `llm.py` (`gen_kwargs["max_tokens"]`,
       :215) is also needed. Safety net today: the blind `APIEmptyResponseError` retry
       (`pythinkersoul.py:2295`) already prevents a hard crash, so this is an improvement, not a fix.
- **Deferred follow-ups (low):** item-8 print exit-code gating; item-10 PostToolUse
  additionalContext (await the fire-and-forget trigger gated on has_hooks_for); deny-set symlink-dir
  + Shell-write limitations; accept-edits in `dynamic_injections/permissions_state.py`.

---

Source: a 25-agent gap-analysis scout (2026-06-14) comparing the current pythinker CLI against a
cleanly-layered reverse-engineered agent-harness reference (Python port, local clone under
`blackbox/`, gitignored). Each candidate was scouted with a hard verdict, then adversarially
verified (liveness / genuinely-missing / architecture-fit). Recommendations are worded generically;
the reference's verbatim model-facing prompt text is treated as REFERENCE-ONLY (provenance) — we adopt
technique, never literal strings — and the current `soul/` loop is NOT swapped (discrete behaviors only).

## Honest summary

The honest read: the reference is overwhelmingly already-present or stubbed, not a trove of adoptable code. Of ~75 candidates across 13 subsystems, only 13 survive as actionable (1 adopt-now, 12 adapt) — roughly 47 are already-have (pythinker implements them in its own kimi-derived soul idiom, frequently MORE robustly than the reference, e.g. abort tool_result pairing, single-flight dedup, the typed wire union, fail-closed PreToolUse blocks, the lazy skill index, and the shimmer/theme TUI), and the rest are stub-only/rewrite-defer/anti-pattern. Most of the reference's load-bearing subsystems (real model calls, compaction, stop-hook executor, token budget, skills discovery, memory injection, MCP/LSP, the agent loop trampoline, the permission gate interior) are explicit '# TODO(port:' no-op skeletons, so their value is design-reference only. The genuinely adoptable items are small, additive, and safe: one read-only prompt-dump command, plus narrow hardening around resource-bounding (parallel fan-out cap, USD spend ceiling), permission safety (dangerous-dotfile re-confirm then accept-edits tier), prompt cache-stability (separate-reminder context), hook steering (additionalContext injection), file-edit safety (read-before-write cache), and a couple of telemetry/observability caveats. The single largest item (max-output-token escalation) is blocked on a pythinker-core precondition (core captures no finish_reason, so truncation is silently accepted today) and is therefore last and partly cross-package.

**Gap stats:** adopt-now: 1, adapt: 12, already-have: 47, stub-only: 4, rewrite-defer: 5, anti-pattern: 8

## Recommended waves

### Wave 1: Low-risk additive hardening (no behavior change to existing happy paths)  _(est. risk: low)_

- **Items:** `dump-system-prompt-entrypoint`, `shell-timeout-literals-not-interpolated`, `per-memory-freshness-disclaimer`, `bounded-parallel-fanout-cap`, `max-budget-usd-loop-stop`
- **Rationale:** All single-file or near-single-file, OFF-by-default or observational, no tool-semantics change. Dump-prompt and shell-timeout are pure additions/drift-guards; per-memory-freshness adds one consolidated caveat; bounded-fanout adds a semaphore inside the existing gate; max-budget adds an opt-in ceiling reusing already-imported estimate_cost_usd. Highest value-per-risk, ships first.

### Wave 2: Permission safety (ordered: deny-set is the prerequisite for the accept-edits tier)  _(est. risk: medium)_

- **Items:** `dangerous-dotfile-deny-set`, `accept-edits-mode-tier`
- **Rationale:** dangerous-dotfile-deny-set closes a verified yolo/accept-edits backdoor (a ~/.zshrc or .git/hooks write is auto-approved today) and MUST land first, because accept-edits-mode-tier auto-approves plain FileActions.EDIT — which a host dotfile classifies as until the deny-set reclassifies it. Landing the deny-set first is what makes the new edit-only auto-approve tier safe. Both touch the approval/classify_edit_action seam, so they are coherent and cheap to land together in order.

### Wave 3: Loop/terminal quality + hook steering (observational-first, gated fast paths)  _(est. risk: medium)_

- **Items:** `terminal-quality-success-predicate`, `required-mcp-spawn-gate`, `posttooluse-context-feedback-injection`
- **Rationale:** terminal-quality-predicate ships as a telemetry attribute before gating exit codes (avoids false-positives on tool-only-then-stop turns). required-mcp-spawn-gate must distinguish 'MCP still loading' from 'absent' to avoid spurious spawn rejections. posttooluse injection ships its clean UserPromptSubmit half first; the PostToolUse half stays gated on has_hooks_for so the no-hooks fast path is untouched. Each needs tuning against real behavior, so they sit after the mechanical wins.

### Wave 4: Heavier / cross-package / blocked  _(est. risk: medium)_

- **Items:** `read-before-write-file-state-cache`, `project-context-as-separate-user-reminder`, `max-output-token-escalation-ladder`
- **Rationale:** read-before-write is a tool-semantics change (new FileState cache, must scope to existing-file overwrites only, needs CHANGELOG + tests). project-context-reminder is a clean refactor through heavily test-pinned system.md and the AGENTS.md fence/budget + subagent work-dir override paths. max-output-token-ladder is gated on a pythinker-core precondition that does not exist today (core surfaces no finish_reason/truncation signal), so it is genuinely cross-package and last. Highest effort, lowest urgency.

## Actionable items (full detail)

### Adopt-now

#### `dump-system-prompt-entrypoint` — Read-only inspection entrypoint that renders and prints the fully-assembled system prompt for a given agent

- **Area / subsystem:** prompt / prompt-assembly
- **Verdict bucket:** ADOPT-NOW · risk **low** · confidence **high** · current status **missing**
- **What:** A small CLI subcommand that builds the system prompt exactly as the live path would and prints it, so maintainers can eyeball/diff the assembled prompt without running a session. Invaluable for reviewing the heavily test-pinned prompt diffs and debugging placeholder/section regressions.
- **Reference evidence:** blackbox/.../entrypoints/dump_system_prompt.py:14-31 (imports get_system_prompt, awaits it, prints '\n'.join(prompt)); get_system_prompt (prompts.py:418-520) runs end-to-end; the entrypoint is real harness code, carries no proprietary model-facing strings
- **Current evidence:** grep of src/pythinker_code/cli/ and __main__.py for dump_system_prompt/--dump/--show-prompt/system_prompt/render-prompt returns zero hits (verified); info.py surfaces no rendered prompt; render path already returns the exact string: load_agent -> _load_system_prompt (soul/agent.py:469-625) and Agent.system_prompt is a plain field (agent.py:458)
- **Reference liveness:** live
- **Adoption sketch:** Add a read-only subcommand that builds a Runtime (reuse app.py's path), calls load_agent(DEFAULT_AGENT_FILE, runtime, mcp_configs=[]) and prints agent.system_prompt (a thin wrapper over the already-rendered string at agent.py:458). NAME COLLISION: `pythinker debug` is ALREADY an alias to pythinker_review's debug app (verified: cli/debug.py sets `cli = upstream_debug.app`), so do NOT add it as a `debug` subcommand — use a non-colliding command (e.g. `pythinker info system-prompt` or a dedicated command). Keep it read-only and out of the model-facing surface; optionally also dump the would-be startup injections so the full effective context is inspectable. Low risk, high maintainer value.
- **Surgical scope:** a new read-only CLI command (non-colliding with the existing `debug` alias) wrapping load_agent; S

### Adapt (surgical, into the existing architecture)

#### `max-output-token-escalation-ladder` — Max-output-token recovery escalation ladder (capped to escalated to per-attempt nudge to surface)

- **Area / subsystem:** loop / loop-core
- **Verdict bucket:** ADAPT · risk **medium** · confidence **high** · current status **partial**
- **What:** When the model hits its output-token cap mid-response, escalate the cap once, then issue a bounded number of paraphrased 'resume mid-thought, break work into smaller pieces' meta-nudges, surfacing the error only after the recovery budget is exhausted. Today truncated output is silently accepted as complete because core captures no finish_reason.
- **Reference evidence:** blackbox/.../query/loop.py:806-867 (escalate to ESCALATED_MAX_TOKENS, then MAX_OUTPUT_TOKENS_RECOVERY_LIMIT=3 nudges, then surface); deps.py:209-216 (_isWithheldMaxOutputTokens predicate); pythinker.py:1093-1108 (sets api_error='max_output_tokens' on stop_reason=='max_tokens')
- **Current evidence:** packages/pythinker-core/src/pythinker_core/_generate.py:74-91 raises APIEmptyResponseError only on fully-empty (74-75) or think-only (83-89) responses; the COMMON truncation case (visible text then cap) returns at line 91 with no error; grep for finish_reason/stop_reason across packages/pythinker-core returns EMPTY, so the loop cannot detect truncation; _is_retryable_error blindly retries APIEmptyResponseError (pythinkersoul.py:2295-2296)
- **Reference liveness:** live
- **Adoption sketch:** Two-step cross-package change, blocked on a precondition. STEP 1 (pythinker-core): have _generate.py:74-91 surface a typed truncation/length finish signal (e.g. a MaxOutputTokensError subclass or a `truncated` flag on GenerateResult) instead of collapsing the cap case into a silent normal return / generic APIEmptyResponseError. STEP 2 (soul): add LoopControl.max_output_recovery_attempts (config.py near max_steps_per_turn); in _step, on the truncation signal, escalate the per-step max_output_tokens once then append a system_reminder meta-nudge (PARAPHRASE: 'resume mid-thought, no recap, break remaining work into smaller pieces' — never copy the reference literal string) and continue, bounded by the new budget before giving up. Per-step max_output_tokens override plumbing is also needed. Safety net today: the blind APIEmptyResponseError retry already prevents a hard crash, so this is an improvement not a fix.
- **Surgical scope:** packages/pythinker-core/_generate.py (truncation signal) then src/pythinker_code/soul/pythinkersoul.py _step + config.py LoopControl; M-L

#### `bounded-parallel-fanout-cap` — Bounded concurrency cap on parallel-safe tool fan-out

- **Area / subsystem:** loop / loop-tools
- **Verdict bucket:** ADAPT · risk **low** · confidence **high** · current status **partial**
- **What:** Run concurrency-safe tool calls in parallel but cap live fan-out at a configurable limit (default ~10) so a turn emitting many parallel-safe reads (e.g. 20 FetchURL) does not open unbounded sockets/file handles at once. This is resource-bounding, distinct from the already-landed reader/writer ordering policy.
- **Reference evidence:** tool_orchestration.py:48-56 (_get_max_tool_use_concurrency, default 10), :215 (all(generators, cap)); utils/generators.py all() is a live asyncio.wait(FIRST_COMPLETED) refill loop, not a stub
- **Current evidence:** src/pythinker_code/soul/toolset.py:377-387 _ReadWriteGate.shared() bumps _active_readers under the writer lock then yields with NO semaphore; :553-555 _gated_call routes supports_parallel tools through shared(); :872 handle() spawns asyncio.create_task(_call()) per call; unbounded proven by packages/pythinker-core/__init__.py:88 (toolset.handle per streamed call) + :113 (gather over all step tasks). grep for Semaphore/concurrency cap across soul/ + pythinker-core/src is clean.
- **Reference liveness:** live
- **Adoption sketch:** src/pythinker_code/soul/toolset.py ONLY. Construct _ReadWriteGate with a bound N (config/env, default ~10). Inside _ReadWriteGate.shared() acquire an asyncio.Semaphore(N) BEFORE the `async with self._writer_lock` / _active_readers bump and release in finally, so the cap throttles parallel readers without affecting writer draining. Deadlock-safe only if acquired before the counter bump: a reader queued on the semaphore has not incremented _active_readers so it does not hold _readers_drained open; writers never touch the semaphore. Do NOT import the reference's all(gens,cap) generator — reshape the cap into the existing gate. Add a focused test asserting concurrent shared() bodies never exceed N.
- **Surgical scope:** src/pythinker_code/soul/toolset.py (semaphore field + acquire in shared()); optional 1-line config/env read; S

#### `max-budget-usd-loop-stop` — Per-session USD spend ceiling enforced as a loop stop condition

- **Area / subsystem:** loop / loop-engine
- **Verdict bucket:** ADAPT · risk **low** · confidence **high** · current status **partial**
- **What:** After each model step, check accumulated session cost against a configured ceiling and halt the turn with a budget-exhausted stop reason instead of running until token/step limits. Caps runaway spend (subagent fan-outs, ralph loops) deterministically rather than only after the bill lands. Today cost is accumulated and displayed but never enforced.
- **Reference evidence:** query_engine.py:656 (if cfg.max_budget_usd is not None and _get_total_cost() >= cfg.max_budget_usd: return) — live stop-check control flow (the reference cost FEED is itself a P3 stub, irrelevant: wire to pythinker's own live feed)
- **Current evidence:** src/pythinker_code/config.py:891 cost_budget is a StatusLine footer field, display-only (ui/shell/slash.py:1444, ui/shell/statusline.py:246); pythinkersoul.py:378 _session_cost_usd accumulates at :1666 and :2141 and flows only to the statusline; LoopControl (config.py:554) caps max_steps_per_turn/max_consecutive_failures but has no spend ceiling; estimate_cost_usd already imported at pythinkersoul.py:103
- **Reference liveness:** live
- **Adoption sketch:** Add an optional max_session_cost_usd to LoopControl (config.py near max_steps_per_turn). In _agent_loop after the per-step usage accumulation (pythinkersoul.py ~1666 where _session_cost_usd updates), if the ceiling is set and _session_cost_usd >= ceiling, stop the loop the way the degenerate-loop backstop does: emit a concise budget-exhausted assistant message (mirror _stuck_summary_message) and return with a new stop_reason 'budget_exhausted' (extend StepStopReason at pythinkersoul.py:190). Print mode maps it like the stuck path. Keep OFF by default (None). Reuse the already-imported estimate_cost_usd; do NOT import the reference SDK result-message machinery. Cost degrades to 0.0 for unpriced models (subagents/usage.py:38,49), so the ceiling is best-effort: fail-open on unknown pricing, never block silently, and document this.
- **Surgical scope:** src/pythinker_code/soul/pythinkersoul.py (_agent_loop step boundary, StepStopReason) + config.py (LoopControl field); focused test; S/M

#### `terminal-quality-success-predicate` — Terminal-message quality predicate distinguishing a real completion from a degenerate stop

- **Area / subsystem:** loop / loop-engine
- **Verdict bucket:** ADAPT · risk **medium** · confidence **medium** · current status **partial**
- **What:** Inspect the final assistant/user message: a usable terminal requires actual text/thinking content (or an all-tool-result user message). A turn that 'stopped' without producing a usable terminal answer should be flagged as degenerate rather than reported as clean success. Today print mode exits 0 on any non-exception completion, including a stuck or empty terminal.
- **Reference evidence:** query_engine.py:227-256 (_is_result_successful, docstring 'ported, not stubbed True' at line 234); 712-732 (consumed to emit error_during_execution)
- **Current evidence:** src/pythinker_code/soul/pythinkersoul.py:190 StepStopReason classifies WHY it stopped (no_tool_calls/tool_rejected/stuck) but TurnOutcome (:338) carries no success/failure quality bit; grep for is_result_successful/result_successful/error_during_execution/degenerate_terminal in src/ returns nothing; ui/print/__init__.py:83,88 returns SUCCESS on any clean completion, FAILURE only from exceptions at :440-451 — a stuck/empty terminal still exits 0
- **Reference liveness:** live
- **Adoption sketch:** Add a boolean degenerate_terminal to TurnOutcome (pythinkersoul.py:338) computed at the no_tool_calls exit (~:1828/:1920) from the final assistant_message content emptiness against pythinker's Message/TextPart model (NOT the reference content-block dicts; reconstruct, never copy the literal edge_diagnostic string). Keep it OBSERVATIONAL first: emit a telemetry attribute on the turn span (pythinkersoul.py:1187) before gating exit codes, to avoid false-positives on legitimate tool-only-then-stop turns. Once tuned, ui/print/__init__.py (~:448) can map an empty terminal to a non-zero exit / distinct error_type. Medium risk because the empty-terminal definition must be tuned against real tool-only completions.
- **Surgical scope:** src/pythinker_code/soul/pythinkersoul.py (TurnOutcome + terminal classification) + ui/print/__init__.py (exit-code mapping); focused test; M

#### `project-context-as-separate-user-reminder` — Project/env context injected as a separate <system-reminder> user message rather than baked into the immutable system array

- **Area / subsystem:** prompt / prompt-assembly
- **Verdict bucket:** ADAPT · risk **medium** · confidence **medium** · current status **partial**
- **What:** Keep the volatile work-dir listing, merged AGENTS.md, and additional-dirs OUT of the immutable system.md so the system message stays byte-stable across turns for prompt-cache hits; inject them as a single startup <system-reminder> user message. Pythinker's own code self-flags this (agent.py:66 TODO). Justification rests on cache-stability + the self-documented TODO, NOT on the reference structure (the reference actually keeps env IN the system array).
- **Reference evidence:** blackbox/.../constants/prompts.py:466-475,726-750 bake env INTO the system array as a section (counter-evidence: NOT the separate-user-message technique the scout cited; blackbox/.../context.py is empty)
- **Current evidence:** src/pythinker_code/soul/agent.py:64-69 (PYTHINKER_WORK_DIR_LS/PYTHINKER_AGENTS_MD/PYTHINKER_ADDITIONAL_DIRS_INFO in BuiltinSystemPromptArgs) with explicit '# TODO: move to first message from system prompt' at agent.py:66; system.md §10 (lines 220-247) and §11 (lines 249-262) render the volatile listing inside the system message; primitives already exist: soul/message.py:23 (system_reminder), pythinkersoul.py:406 + 503 (DynamicInjectionProvider registry / add_injection_provider)
- **Reference liveness:** live
- **Adoption sketch:** Add a one-shot StartupContextInjectionProvider (or fold into an existing root-only provider via add_injection_provider at pythinkersoul.py:503) that emits work-dir listing + merged AGENTS.md + additional-dirs as a single system_reminder() user message at session start, and trim system.md §10/§11 to durable guidance only (the rules about HOW to treat AGENTS.md/env, not the volatile listing). Risk is medium: system.md content is heavily test-pinned (tests/core/test_default_agent.py, test_load_agent.py) and the AGENTS.md fence/budget logic (agent.py:85,107-178) plus the subagent work-dir override flowing through builtin_args must be preserved when relocated. Clean refactor, not a bug; defer if not explicitly prioritized.
- **Surgical scope:** agent.py (move builtin_args context out), system.md (trim §10/§11), new startup injection provider; M

#### `shell-timeout-literals-not-interpolated` — Interpolate enforced limits into the tool description from the same constant the code enforces (Shell timeout drift guard)

- **Area / subsystem:** prompt / prompt-tools
- **Verdict bucket:** ADAPT · risk **low** · confidence **high** · current status **partial**
- **What:** Derive the Shell description's foreground/background timeout numerals from the MAX_FOREGROUND_TIMEOUT/MAX_BACKGROUND_TIMEOUT constants the schema and validator already enforce, instead of restating literal 300/86400 by hand — closing the one place pythinker's own ReadFile-style interpolation idiom is not applied. HONEST CAVEAT: no current behavioral delta (300==5*60, 86400==24*60*60), so the rendered description is byte-identical today; the sole deliverable is a regression guard against future divergence.
- **Reference evidence:** blackbox/.../tools/bash_tool/prompt.py:275 (live f-string interpolating get_max_timeout_ms/get_default_timeout_ms helpers, not stubbed)
- **Current evidence:** src/pythinker_code/tools/shell/__init__.py:30-31 define MAX_FOREGROUND_TIMEOUT=5*60 (300) and MAX_BACKGROUND_TIMEOUT=24*60*60 (86400), enforced at schema line 60 (le=MAX_BACKGROUND_TIMEOUT) and validator line 80; load_desc called at :96-100 with only {"SHELL": ...}; bash.md/powershell.md hardcode literals 300/86400. Precedent: read.md:13,15,17 interpolate ${MAX_LINES}/${MAX_LINE_LENGTH} fed by read.py:70-77 — the exact template.
- **Reference liveness:** live
- **Adoption sketch:** In src/pythinker_code/tools/shell/__init__.py:96-100 extend the load_desc context dict to also pass {"MAX_FOREGROUND_TIMEOUT": MAX_FOREGROUND_TIMEOUT, "MAX_BACKGROUND_TIMEOUT": MAX_BACKGROUND_TIMEOUT}. In bash.md (the line holding both literals, plus the foreground-only line) and powershell.md (same two spots) replace 300 -> ${MAX_FOREGROUND_TIMEOUT} and 86400 -> ${MAX_BACKGROUND_TIMEOUT}. Add ONE focused test asserting the rendered Shell description contains str(MAX_FOREGROUND_TIMEOUT) DYNAMICALLY (reference the constant, not the literal '300' — a literal assertion is a tautology that cannot catch drift). Existing tests already import these constants (tests/tools/test_shell_bash.py:249). Verify with make check-pythinker-code && make test-pythinker-code.
- **Surgical scope:** src/pythinker_code/tools/shell/__init__.py (context dict) + bash.md + powershell.md + 1 drift-guard test; S

#### `read-before-write-file-state-cache` — Shared file-state cache enforcing read-before-write and stale-read detection

- **Area / subsystem:** design / design-tool-contract
- **Verdict bucket:** ADAPT · risk **medium** · confidence **high** · current status **missing**
- **What:** A per-session path-keyed cache records, on each read, file content + mtime + offset/limit + is_partial_view. Edit/overwrite tools reject when the path has no recorded read ('read it first') or when the file's mtime advanced past the recorded read ('modified since read'), with a full-read content-equality fallback to avoid false positives. Catches blind overwrites of unread files and concurrent external/linter modifications that exact-string matching alone misses.
- **Reference evidence:** blackbox/.../utils/file_state_cache.py:43-92 (dict-backed path-normalizing cache; only TODO is cosmetic P3 LRU); tools/file_read_tool.py:813-820,1016-1022 (read sets FileState with floor(st_mtime*1000)); tools/file_edit_tool.py:313-345 (validate_input rejects 'not been read'/'modified since read'), :516-523 (re-set post-write)
- **Current evidence:** src/pythinker_code/tools/file/write.py:185-189 overwrites unconditionally (no read/mtime gate); replace.py:423-444 guards only by exact old-string match + CRLF/fuzzy relaxation (cannot catch a blind overwrite of an unread file, nor an external edit where the old string still matches); read.py:66 declares only supports_parallel and records no FileState; grep of src/pythinker_code/tools/ + soul/ for FileStateCache/read_file_state/is_partial_view/'modified since'/st_mtime found no relevant hits
- **Reference liveness:** live
- **Adoption sketch:** Add a small path-normalizing FileState cache (content, mtime_ms, offset, limit, is_partial_view) hung off Runtime/session (tools receive Runtime via DI; no ToolUseContext analog). Populate it in tools/file/read.py after a successful read (record offset/limit; set is_partial_view when served bytes differ from disk, e.g. injected MEMORY.md). Gate in write.py (overwrite mode) and replace.py: before mutating, look up the normalized path; return a ToolError 'read it first' when absent/partial and 'changed on disk since you read it' when getmtime > recorded mtime (full-read content-equality fallback for cloud-sync/AV false positives). Re-set the cache after a successful write so a same-turn follow-up edit is not falsely flagged. CRITICAL SCOPE: gate EXISTING-file overwrites only — new-file creation has nothing to read and MUST stay allowed (mirror the reference). This is a tool-SEMANTICS change: needs a CHANGELOG ## Unreleased entry and focused tests (edit-without-read rejected, edit-after-external-mtime-bump rejected, edit-after-read allowed, partial-read does not satisfy the gate). Frame in generic terms; do not import reference code/strings.
- **Surgical scope:** src/pythinker_code/tools/file/{read,write,replace}.py + one new cache module + cache owner on Runtime/session; tests + CHANGELOG; M

#### `accept-edits-mode-tier` — Middle auto-approve tier: auto-allow reversible in-workspace file edits while still prompting Shell/destructive/out-of-workspace actions

- **Area / subsystem:** design / design-permissions
- **Verdict bucket:** ADAPT · risk **medium** · confidence **high** · current status **missing**
- **What:** A distinct permission tier between per-call prompting and full yolo: auto-approve WriteFile/StrReplaceFile inside the working directory (reversible, restore-point-backed) while Shell, destructive, and out-of-workspace actions take the normal approval path. Lets a user accept all edits without over-approving shell and destructive commands.
- **Reference evidence:** blackbox/.../utils/permissions/filesystem.py:1074-1083 (acceptEdits mode auto-allows in-working-dir writes, after deny/internal/session/safety/ask gates run first — live, no TODO in body); :749-773 (generate_suggestions proposes setMode acceptEdits)
- **Current evidence:** src/pythinker_code/soul/approval.py:141-178 ApprovalState exposes yolo/auto/runtime_auto/safe_mode/auto_approve_actions but no edit-only tier; is_auto_approve() (:230-241) gates ALL tool calls uniformly; the only file carve-out is exclusion of reversible file tools from the destructive-deliberation classifier (permission.py:1486-1492), NOT a positive auto-approve scope; grep for accept_edits/acceptEdits/permission_mode in non-test src returned nothing
- **Reference liveness:** live
- **Adoption sketch:** Add an accept_edits: bool flag to ApprovalState (approval.py:141) and a setter on Approval. In request() before the general is_auto_approve() branch (~:519), add: if accept_edits AND the action is FileActions.EDIT (so EDIT_OUTSIDE and EDIT_CONFIG are excluded by construction — no new classifier), return approved; leave Shell/destructive/out-of-workspace on the existing path. Wire a /accept-edits or /mode toggle through the same surface that sets yolo. Do NOT introduce the reference's literal mode-enum strings; model as a pythinker auto-approve scope. SAFETY DEPENDENCY: this tier keys on plain EDIT, so it must land AFTER dangerous-dotfile-deny-set — otherwise it would auto-approve a ~/.zshrc or .git/hooks write that classifies as plain EDIT today.
- **Surgical scope:** src/pythinker_code/soul/approval.py (flag + request() branch) + a /accept-edits slash toggle; focused approval tests; M

#### `dangerous-dotfile-deny-set` — Always-re-confirm precedence for dangerous host dotfiles and structural dirs (shell-rc, git-config, .git/, .vscode/) independent of pythinker's own config surface

- **Area / subsystem:** design / design-permissions
- **Verdict bucket:** ADAPT · risk **medium** · confidence **high** · current status **partial**
- **What:** Treat writes to a fixed set of host dotfiles (.bashrc/.zshrc/.zprofile/.gitconfig/.gitmodules/.mcp.json) and structural dirs (.git/.vscode/.idea) as always requiring manual approval even under yolo/accept-edits, because a rewritten shell-rc or git hook is a persistent backdoor. Pythinker re-confirms only its OWN behavioral config today, leaving these surfaces auto-approvable.
- **Reference evidence:** blackbox/.../utils/permissions/filesystem.py:93-111 (DANGEROUS_FILES/DANGEROUS_DIRECTORIES); :345-379 (_is_dangerous_file_path_to_auto_edit, real segment+basename scan with a .pythinker/worktrees carve-out); :441-461 (forces ask — live, no TODO in body)
- **Current evidence:** src/pythinker_code/utils/path.py:141-182 is_config_surface_path covers ONLY agents.md/.pythinker/config.toml/agent specs — NOT .zshrc/.bashrc/.gitconfig/.git/; utils/sensitive.py covers .env/SSH/cloud creds but is wired into READ filtering, not WRITE re-confirm; classify_edit_action (tools/file/__init__.py:22-39) yields EDIT_OUTSIDE/EDIT_CONFIG/EDIT and only EDIT_CONFIG re-confirms under yolo. Verified backdoor: under interactive yolo a ~/.zshrc write classifies EDIT_OUTSIDE, _unattended_denial_feedback short-circuits (approval.py:287 'or self._state.yolo'), then approval.py:519 auto-approves with no re-confirm; an in-repo .git/hooks/pre-commit write classifies plain EDIT and is likewise auto-approved
- **Reference liveness:** live
- **Adoption sketch:** Add a generic dangerous-dotfile predicate (a small frozenset of basenames .bashrc/.zshrc/.zprofile/.profile/.gitconfig/.gitmodules/.ripgreprc/.mcp.json plus a .git//.vscode//.idea/ path-segment check on the canonicalized path, mirroring filesystem.py:93-111). CRITICAL ORDERING: wire it into classify_edit_action (tools/file/__init__.py) BEFORE the is_within_workspace branch (~:35) — wired after, out-of-workspace dotfiles stay EDIT_OUTSIDE and the yolo backdoor stays open. Map matches to the always-re-confirm channel (EDIT_CONFIG or a sibling) so _is_config_edit/_is_session_approvable already exclude them. Keep it pure-path like is_config_surface_path. DROP .pythinker from the ported DANGEROUS_DIRECTORIES set — pythinker deliberately allows plan/scratch artifacts there. This is the prerequisite that makes accept-edits-mode-tier safe.
- **Surgical scope:** src/pythinker_code/utils/path.py (predicate) + classify_edit_action wiring (tools/file/__init__.py before the workspace branch); tests; S/M

#### `posttooluse-context-feedback-injection` — Hook additionalContext as a first-class non-block feedback channel injected back into the model (UserPromptSubmit + PostToolUse)

- **Area / subsystem:** design / design-hooks
- **Verdict bucket:** ADAPT · risk **medium** · confidence **high** · current status **partial**
- **What:** Beyond allow/block, a hook can return additionalContext text appended into the conversation so the model sees it next step (e.g. a UserPromptSubmit guidance line, a PostToolUse linter summary). Turns hooks into a steering channel, not just a gate. The runner already extracts additional_context for every event, but injection happens ONLY at compaction time; UserPromptSubmit additional_context is dropped and PostToolUse is fire-and-forget with output discarded.
- **Reference evidence:** blackbox/.../src/types/hooks.ts:77,81,101-106 (additionalContext on PreToolUse/UserPromptSubmit/PostToolUse), aggregated :285 — DESIGN-ONLY: the Python port's PostToolUse path is a no-op stub (services/tools/tool_execution.py:526 'TODO(port: P3) runPostToolUseHooks')
- **Current evidence:** src/pythinker_code/hooks/runner.py:82,97,112-118 already extracts additional_context for every event; sole injection site is the compaction path (pythinkersoul.py:2195-2200) via build_hook_context_message (compaction_restore.py:161, whose body text is compaction-specific 'restored after compaction'); UserPromptSubmit reads only result.action=='block' and discards additional_context (pythinkersoul.py:974-982, verified); PostToolUse fire-and-forget with output discarded (toolset.py:848-860); fast-path gate helper available: engine.py:227 has_hooks_for; trust wrapper available: utils/trust.py:51 mark_untrusted
- **Reference liveness:** stub
- **Adoption sketch:** SPLIT into two pieces of different risk. (1) UserPromptSubmit (clean, low-risk, ship first): in pythinkersoul.py after the block check (~:974), collect non-empty result.additional_context from the same hook_results and, if any, append a system_reminder user message BEFORE wire_send(TurnBegin), mirroring the compact-time pattern. Do NOT reuse build_hook_context_message verbatim — its body says 'restored after compaction' which would mislead the model; use a generically-framed builder (or parameterize the header). Wrap hook stdout in mark_untrusted (it is external content per AGENTS.md). (2) PostToolUse (the genuine adaptation, defer/gate): converting the fire-and-forget call (toolset.py:849) to await-and-inject changes per-turn latency/ordering and MUST be gated on engine.has_hooks_for('PostToolUse') so the no-hooks fast path stays fire-and-forget; route returned additional_context into the tool_result via _append_reminder_to_return_value (toolset.py:865-868). Keep additional_context strictly non-authoritative. Focused tests under tests/hooks/ and tests/core/ for both; never block the turn on PostToolUse latency.
- **Surgical scope:** src/pythinker_code/soul/pythinkersoul.py (UserPromptSubmit) + soul/toolset.py (PostToolUse, gated) + a non-compaction-framed context builder; tests; M

#### `per-memory-freshness-disclaimer` — Point-in-time staleness caveat attached to injected memory blocks

- **Area / subsystem:** design / design-context-skills-memory
- **Verdict bucket:** ADAPT · risk **low** · confidence **high** · current status **missing**
- **What:** Attach a single consolidated plain-text caveat to injected durable-memory content telling the model that file:line citations and code-behavior claims recorded in old memory may be stale and must be re-verified against current code before asserting as fact. Pythinker's existing recall caveat is about AUTHORITY ('don't act on past context'), a different failure mode from factual STALENESS ('citations may have moved').
- **Reference evidence:** blackbox/.../memdir/memory_age.py:11-48 (memory_age_days/memory_freshness_text/memory_freshness_note — live mtime->note math). Reference WIRING is NOT portable: reference memory injection is stubbed (memdir/memdir.py:2 'Phase 1: no memory section') and the only live call site is FileReadTool output (file_read_tool.py:290-294), not an injected block — adopt the mtime->note TECHNIQUE only; the literal string at memory_age.py:35-38 is reference-only.
- **Current evidence:** LIVE injection path is RecallInjectionProvider (registered app.py:381-385) rendering via memory/recall.py:build_recall_block (:129-169); existing caveat (recall.py:141-143) is authority/actionability NOT freshness; durable snapshot header (project_memory.py:460-465) calls memory 'durable facts' with no staleness note; recency only affects RANKING (retriever.py:84-85), never a model-facing note; grep for freshness/stale/point-in-time/verify-against found no per-block caveat
- **Reference liveness:** live
- **Adoption sketch:** Add a tiny pure helper (memory/freshness.py with freshness_note(mtime_epoch) returning '' for <=1 day old else a generic pythinker-worded caveat — DO NOT copy the reference literal string). CRITICAL CORRECTION to the naive sketch: durable-tier blocks (MEMORY.md/USER.md/JOURNAL.md) are injected with created_at_epoch=now (recall.py:254-263), so keying the caveat off per-block created_at_epoch would NEVER fire for the file:line citations that motivate it. Drive the durable-tier staleness note off the FILE mtime already computed by RecallInjectionProvider._memory_files_mtime() (recall.py:293-309); reserve per-block created_at_epoch for the scratch tier (recall.py:241). Append ONE consolidated caveat (not per-line noise) to respect the injection token budget. Verify with a focused test asserting the caveat appears for an aged file and is absent for a fresh one.
- **Surgical scope:** src/pythinker_code/memory/recall.py (build_recall_block) + small memory/freshness.py helper + optionally project_memory.py snapshot header; focused test; S

#### `required-mcp-spawn-gate` — Declarative required-MCP-servers capability on the agent-type definition, gating spawn when servers are absent

- **Area / subsystem:** design / design-agents-subagents
- **Verdict bucket:** ADAPT · risk **low** · confidence **medium** · current status **missing**
- **What:** An agent type can declare MCP server name patterns it requires; the spawn is rejected with an actionable message (pointing to `pythinker mcp`) when no connected server matches. Prevents an agent that depends on an MCP tool from silently running tool-less. Ports the matcher+gate DESIGN wired into pythinker's live discovery (the reference field is never populated end-to-end — its FS agent-dir discovery is P5-stubbed).
- **Reference evidence:** blackbox/.../tools/agent_tool/load_agents_dir.py:277-293 (has_required_mcp_servers pure matcher), :169 (required_mcp_servers field); agent_tool.py:251-277 (spawn-time gate with /mcp guidance — live pure code)
- **Current evidence:** grep of required_mcp/requires across subagents/, tools/agent/, agents/, agentspec.py returns nothing; AgentTypeDefinition (subagents/models.py:27-36) carries only tool_policy/default_model/supports_background/when_to_use; mcp_tools keyed mcp__<server>__<tool> (soul/agent.py:202-203); MCP tools load deferred/background (soul/agent.py:588-590)
- **Reference liveness:** live
- **Adoption sketch:** Add an optional required_mcp_servers: tuple[str,...] = () to AgentTypeDefinition (subagents/models.py:27-36); populate from the subagent spec when registering builtin types (soul/agent.py:510-520) and from markdown frontmatter in discovery.py (parse_markdown_agent). Add a small pure matcher (case-insensitive substring against runtime.mcp_tools server names, which are keyed mcp__<server>__<tool>) and call it at spawn time in ForegroundSubagentRunner._prepare_instance (subagents/runner.py:472-514, ToolError available at runner.py:12) and the background equivalent, raising a ToolError that names the missing pattern. NON-TRIVIAL TIMING ADAPTATION (keeps this adapt not adopt-now): MCP tools load deferred (soul/agent.py:588-590), so a naive fail-closed-at-spawn gate rejects SPURIOUSLY during the load window — the gate must distinguish 'still loading' from 'absent' (wait-for / treat loading distinctly) before rejecting. Skip the reference's permission_mode/max_turns/isolation fields (isolation/background already exist; per-type permission_mode duplicates the approval/tool-policy layer).
- **Surgical scope:** src/pythinker_code/subagents/models.py (field) + soul/agent.py + discovery.py (populate) + subagents/runner.py (spawn gate w/ loading-vs-absent distinction); tests; S/M

## Already-have (pythinker already does this — do NOT re-adopt)

The bulk of the reference is already present in pythinker's own idiom, frequently more robustly.

- **closed-terminal-stop-set** — Closed enumerated set of terminal/stop reasons  
  _current:_ soul/pythinkersoul.py:190 StepStopReason Literal{no_tool_calls,tool_rejected,stuck} + typed exceptions (MaxStepsReached:1396, CancelledError:1771, propagated provider exc:1499); every reference TerminalReason maps to a pythinker equivalent
- **abort-tool-result-pairing** — On abort, synthesize a matching cancel/error tool_result for EVERY tool_use (dedup of loop-core + loop-tools)  
  _current:_ soul/pythinkersoul.py:1771-1793 builds a ToolResult for every tc (completed keep real output, pending get ToolRuntimeError), then shields the _grow_context write; pythinker-core/__init__.py:108-114,154-158 cancels+gathers futures on abort — stronger than the reference's uniform-error fill
- **needs-follow-up-independent-of-stop-reason** — Tool-use detection independent of provider stop_reason  
  _current:_ soul/pythinkersoul.py:1872 drives continuation off result.tool_calls; 1693-1697 pythinker-core's StepResult deliberately has no finish_reason, so the loop cannot key on stop_reason — correct by construction; intent-nudge at :1900 is a pythinker superset
- **prompt-cache-input-immutability** — Never mutate API-bound tool_use input in place (clone for observers)  
  _current:_ Already-have by construction: system prompt frozen for cache hits (pythinkersoul.py:1676); no display-enrichment of API-bound tool_call input exists (the only .function.arguments= mutation is a display-only accumulator at ui/shell/visualize/_blocks.py:739, never the context message)
- **withheld-recoverable-error-handling** — Withhold a recoverable API error until recovery is known, surface only once if unrecovered  
  _current:_ soul/pythinkersoul.py:1481-1499 catches context_overflow before any error reaches the user, retries via _recover_from_context_overflow:1966, re-raises once at :1499 if unrecovered — the exception-driven flow withholds by construction (no stream-loop double-emit risk)
- **ordered-result-reassembly** — Ordered tool_result reassembly in tool_use emission order  
  _current:_ packages/pythinker-core/__init__.py:148-153 StepResult.tool_results() iterates self.tool_calls in order awaiting each id's future, independent of completion order
- **per-tool-concurrency-classification** — Per-tool concurrency-safety classification (read-parallel vs write-serial, conservative default)  
  _current:_ soul/toolset.py:553 getattr(tool,'supports_parallel',False) default exclusive; declared True only on read-shaped tools (read/glob/grep/fetch/search/think/recall/mcp_resource); MCPTool.supports_parallel returns False; mutating tools omit it -> serialize. Do NOT adopt the reference input-aware is_concurrency_safe (its read-only-bash payoff is its own stub)
- **single-flight-dedup-identical-calls** — Single-flight / dedup of identical concurrent (and repeated) tool calls  
  _current:_ soul/toolset.py:652-672 same-step coalescing; :674-694 cross-step dup detection with 3/5/8 escalating system-reminders; :337-339 canonical-args key — the reference orchestration has NO dedup, pythinker exceeds it
- **finalize-in-same-task-cancellation** — Cancellation contract: finalize tool work in the same task that runs it  
  _current:_ soul/toolset.py:872-874 returns asyncio.create_task(_call()) (the tool task itself, no orphaning wrapper); :813-818 closes the OTel span in-task so the context token detaches synchronously
- **unknown-tool-and-validation-result-synthesis** — Synthesize an error tool_result for unknown-tool / parse / validation failures  
  _current:_ soul/toolset.py:620-631 unknown tool -> ToolNotFoundError with difflib close-match suggestion; :636-644 JSON parse -> ToolParseError; per-tool validation -> ToolRuntimeError captured at :762-812 — adds a fuzzy name suggestion the reference lacks
- **stop-hook-continuation-protocol** — Stop-hook continuation protocol: blocking stop hook feeds its reason back as a user message forcing one more turn  
  _current:_ soul/pythinkersoul.py:1009-1024 (trigger 'Stop'; block result with reason -> await self._turn(Message(role='user', content=result.reason))); reference _execute_stop_hooks is a no-op stub
- **stop-hook-active-reentry-guard** — stop_hook_active re-entry guard capping continuation at one extra turn  
  _current:_ soul/pythinkersoul.py:429 (_stop_hook_active=False), :1008 (gate), :1019/:1023 (set/reset around the single re-trigger); comment names 'max 1 re-trigger to prevent infinite loop'
- **stop-hook-blocking-errors-as-user-messages** — Hook blocking errors converted to model-visible user messages at the boundary  
  _current:_ soul/pythinkersoul.py:1018-1021 (reason -> user Message -> _turn); hooks/engine.py:386-399 aggregates block+reason; hooks/runner.py:75-86 maps exit-2/permissionDecision=deny to action='block'
- **skip-stop-hooks-on-api-error** — Skip end-of-turn stop hooks when the turn ended on an API error  
  _current:_ soul/pythinkersoul.py:1485-1499 fires StopFailure on the API-error path and re-raises before the :1007 Stop block can run — exception-driven separation is the trampoline equivalent of the reference's explicit branch
- **per-turn-usage-cost-accounting** — Per-turn token-usage and USD-cost accumulation  
  _current:_ soul/pythinkersoul.py:1663-1666 accumulate_usage + _session_cost_usd; 832-847 StatusSnapshot exposes session_cost_usd/tokens; subagents/usage.py:27-67 per-child roll-up — covers the reference cost_tracker ground without process globals
- **memoized-dynamic-section-registry** — Memoized dynamic-section registry: volatile prompt content recomputed only when inputs change, separate from the cached static prompt  
  _current:_ soul/dynamic_injection.py:138-182 (DynamicInjectionProvider per-provider throttle + on_context_compacted reset); dynamic_injections/permissions_state.py:39-50 (fingerprint memoization); pythinkersoul.py:406-427 (registry of 7 providers) — fingerprint-diff replaces the reference's name-keyed cache-clear
- **offline-prompt-fidelity-harness** — Offline prompt-fidelity: render the full prompt and assert required invariants without a live model call  
  _current:_ soul/agent.py:615-630 StrictUndefined+SandboxedEnvironment fails loud on a dropped/renamed placeholder; tests/core/test_load_agent.py:28-165,254-261 and test_default_agent.py:15-62 render the real system.md and pin required phrases — the reference's verbatim-fragment gate is a TS->Py porting tool pythinker does not need
- **composable-section-builders** — Prompt assembled from small per-section units  
  _current:_ agents/default/system.md (single Jinja template, 12 numbered sections, ${...} slots + {% if %} conditional inclusion); the reference's builder explosion exists to weave external build-time dead-code-elimination gates — a porting artifact pythinker has no equivalent of
- **tiny-system-prompt-mechanics-in-code** — Tiny-system-prompt philosophy: mechanics in tools/code, judgment in the prompt  
  _current:_ system.md §5 is judgment-level (when to parallelize/which subagent/MCP policy); per-tool mechanics live in tool descriptions snapshot-tested at test_default_agent.py:338; toolset.py owns mechanics. Tool names are stable compatibility-pinned surface, so static names are intentional not drift
- **per-tool-description-file** — Each tool owns a dedicated code-adjacent file for its model-facing description  
  _current:_ tools/file/{grep,read,write}.md, shell/{bash,powershell}.md, web/fetch.md loaded via load_desc() (tools/utils.py:25-37); 25+ tools use the convention — structural equivalent of the reference per-tool prompt.py, with original (non-proprietary) text
- **limits-interpolated-from-enforced-constants** — Interpolate enforced limits into the description from the same constant the code enforces  
  _current:_ tools/file/read.py:17-19 MAX_LINES/MAX_LINE_LENGTH/MAX_BYTES threaded into Field.description + read.md ${...} (read.py:70-77) + enforcement (:224,229) + truncation msg (:248-258) — strictly more than the reference, which only centralized TOOL_SUMMARY_MAX_LENGTH (the Shell tool is the one un-applied spot, tracked separately)
- **truncation-message-names-next-action** — Truncation/limit-hit messages always name the next concrete action  
  _current:_ tools/file/grep_local.py:1026-1029 ('Use offset=... to see more'); read.py:256-258 ('continue with line_offset='); tools/utils.py:283-288 spill hint ('Recover it with ReadFile(...)') — more thorough than the reference (adds disk-spill recovery + subagent delegation)
- **pydantic-input-model-async-call** — Typed pydantic input model with async call/description on a Tool base  
  _current:_ packages/pythinker-core/tooling/__init__.py:232-316 CallableTool2[Params: BaseModel] (parameters from model_json_schema, async call validates with model_validate then dispatches typed); WriteFile/StrReplaceFile are CallableTool2 subclasses
- **declarative-concurrency-and-side-effect-metadata** — Declarative capability flags (concurrency-safe, side-effect, lifecycle) instead of duck-typing  
  _current:_ soul/toolset.py:553 reads supports_parallel; :1248 external_side_effect_tool ClassVar; :1258 emits_tool_execution_started_after_approval ClassVar — the already-landed P3a declarative-metadata work named in the exclusion filter
- **agent-capability-render-in-tool-prompt** — Render per-type capability metadata (tools, model, background, when-to-use) into the spawn tool description  
  _current:_ tools/agent/__init__.py:196-212 _builtin_type_lines renders name/description/Tools/Model/Background/when-to-use from labor_market.builtin_types; :218-224 _tool_summary derives from tool_policy
- **in-process-nested-loop** — Subagents run as an in-process nested agent loop sharing the parent engine  
  _current:_ subagents/runner.py:302-470 (ForegroundSubagentRunner.run); core.py:119-173 (prepare_soul builds in-process PythinkerSoul); background/agent_runner.py:205 (background variant in-process) — reference run_agent is the explicit P4 stub 'not yet reachable at runtime'
- **sync-shares-async-isolates** — Sync subagents share parent app-state/abort; async/background subagents isolated  
  _current:_ soul/agent.py:391-450 copy_for_subagent (per-child DenwaRenji, approval.share(), shares session/labor_market/mcp_tools/approval_runtime by reference); runner.py:99-121 own asyncio.Event abort per run; filter_history_for_fork (core.py:71-97) is the fork-at-spawn analogue — reference createSubagentContext is documented as NOT ported
- **gate-spine-decision-flow** — abort -> force -> inner -> allow/deny/ask flow with deny-on-ask in non-interactive contexts  
  _current:_ soul/approval.py:491-503 deliberation_gate (force-deliberate ahead of yolo); :509-518 _unattended_denial_feedback (deny-on-ask when no user); :519-527 auto-approve — same decision flow in pythinker's idiom; reference interactive/coordinator handlers are TODO(port) stubs
- **plan-bypass-mode-mapping** — Permission modes plan/default/bypass (3 of 4 map; acceptEdits tracked separately)  
  _current:_ plan: permission.py:293-298 plan_mode profile; bypass: approval.py:237-241 is_yolo; default ask: normal Approval.request — pythinker's PermissionProfile + ApprovalState split is the equivalent of the mode enum
- **internal-path-carveouts** — Read/write carve-outs for harness-internal paths so the agent never re-prompts for its own scratch space  
  _current:_ internal artifacts (memory/plans/subagent state) written via dedicated tools/runtime paths that bypass the user-facing file-write approval; plan-file carve-out via is_plan_artifact (soul/permission.py:334-348)
- **hook-event-taxonomy** — Lifecycle hook-event taxonomy  
  _current:_ hooks/config.py:5-19 HookEventType Literal of 13 events (strict superset of the reference's portable set) + per-event payload builders hooks/events.py:12-194; reference taxonomy is design-only (its executor is a stub)
- **pretooluse-fail-closed-block** — Fail-closed PreToolUse block vs fail-open everywhere else  
  _current:_ soul/toolset.py:717-739 (block -> ToolError, never executes); engine.py:316-326 keeps the block-detect track() OUTSIDE the fail-open try so telemetry failure cannot bypass a block; runner.py:65-73 maps exit-2/deny to block — the AGENTS.md 'block result never discarded' invariant; reference never ported the executor
- **hooks-must-not-throw** — Must-not-throw hook engine (errors/timeouts isolated, fail-open)  
  _current:_ hooks/engine.py:305-314 (try/except -> report_handled_error + fail-open + return []); runner.py:31,45-59 (subprocess timeout/exception -> allow); engine.py:158-188 fire_and_forget keeps a strong task ref — reference contract is design-only (no executor)
- **stop-subagentstop-reentry** — Stop/SubagentStop hook with bounded single re-trigger  
  _current:_ soul/pythinkersoul.py:1007-1024 (_stop_hook_active guards single re-turn); subagents/runner.py:407-414 fires SubagentStop via fire_and_forget_trigger
- **client-side-wire-hooks** — Client-forwarded (wire) hook subscriptions alongside local shell hooks  
  _current:_ hooks/engine.py:92-128 (WireHookSubscription/WireHookHandle), :374-381,425-460 (_dispatch_wire_hook round-trip with wait_for timeout -> fail-open); wire/server.py:477-544 — exceeds the reference (in-process callbacks only)
- **closed-event-hook-union-spec** — Closed discriminated event/request unions with exhaustiveness + runtime guards  
  _current:_ wire/types.py closed unions (type Event/Request/WireMessage :690-693), flatten_union exhaustiveness :697-699, runtime TypeGuards :702-714, name-keyed envelope registry :717-751; hook events are typed BaseModels :137-183 — strictly more rigorous than the reference's Mapping[str,Any] fallbacks
- **layered-cwd-session-runtime-factory** — Layered construction: cwd-bound state -> session -> runtime factory (no process globals)  
  _current:_ app.py:163 PythinkerCLI.create(session, ...) takes explicit Session, builds Runtime, wires cwd=str(session.work_dir) (:398); session id is session.id — explicit objects vs the reference's module-global latches (anti-pattern)
- **lazy-skill-index** — Lazy skill index: surface name+description, load SKILL.md body on demand  
  _current:_ skill/__init__.py resolve_skills_roots:184, discover_skills_from_roots:323, index_skills:318, format_skills_for_prompt:354-389 (name+path+description only), body via read_skill_text:392-402; wired soul/agent.py:257-268 — reference is a no-op stub
- **memdir-design-layout** — Per-project memory-dir layout with project-key resolution and write carve-outs  
  _current:_ project_memory.py:100-163 ProjectMemoryStore (MEMORY.md+USER.md per-project share dir); injection via RecallInjectionProvider (recall.py:280); strict reads + multi-instance mtime visibility (recall.py:293-309) — reference path resolver is a conservative prefix-only stub
- **diagnostics-returned-as-data** — Subsystem diagnostics returned as structured data, not thrown  
  _current:_ soul/toolset.py:913 builds MCPServerSnapshot with a Literal status union, surfaces failures as status='failed' (:1134) into MCPStatusSnapshot on the wire (wire/types.py:199-216), consumed by ui/shell/mcp_status.py — reference LSP/diagnostic services are fully stubbed
- **async-once-conversation-memoized-context** — Per-conversation memoization of context blocks with explicit cache-clear seam  
  _current:_ project_memory.py:515-538 + memory/recall.py:280-380 once-per-session injection via _injected flag + on_context_compacted re-arm + rearm(key) — the same compute-once/invalidate-on-compaction contract; reference _AsyncOnce caches stubbed git/memory loaders
- **shimmer-spinner-system** — Theme-token-driven per-character shimmer sweep + animated activity spinner  
  _current:_ ui/shell/motion.py:138-211 (bidirectional sweep w/ settle beats, cosine-falloff truecolor blend, discrete ramp fallback, reduced-motion pin, shared Rich+prompt_toolkit path); glyphs.py:20-39; spinner_words.py:208-222 — strictly richer than the reference (whose driver is a P6 stub)
- **theme-token-palette** — Named-token color palette resolved per render with renderer-agnostic mapping  
  _current:_ ui/theme.py TuiTokens dataclass (activity_verb*/activity_spinner/thinking_text/usage_*), tui_rich_style()/get_tui_tokens() per render, dark+light palettes w/ set/get_active_theme; design_system.py:61-69 shell_style maps ShellTone to tokens
- **ghostty-sparkle-substitution** — Terminal-specific glyph substitution  
  _current:_ Current TUI never renders the offset-prone sparkle codepoint; the only sparkle used is the glyph the reference treats as terminal-safe (ui/shell/glyphs.py:54); per-glyph ASCII/Windows/dumb-term fallbacks already exist (glyphs.py:20-66) — a Ghostty branch would be speculative dead code

## Stub-only in the reference (design-reference only; nothing live to port)

- **fallback-model-retry-on-overload** — In-loop fallback-model retry on provider overload: verify REFUTED liveness: the handler at loop.py:628-674 is real but its trigger FallbackTriggeredError has ZERO raise sites (defined once at with_retry.py:90), and the overload-classification-and-raise logic lives in the deferred multi-attempt loop (with_retry.py docstring: 'model-fallback decision is infra-bound, TODO(port: P3)'). The handler can never execute. Gap is genuinely missing in pythinker (no in-loop overload->fallback concept; _step retries the same model via tenacity) but there is no live behavior to port — design only.
- **cost-state-restore-on-resume** — Restore accumulated cost/usage when resuming a session: verify REFUTED liveness (AND-gate): the durable cross-resume continuity unit is exactly the reference's TODO(port:P3) stub — cost_tracker.py:209-215 _project_config is in-memory only ('round trips WITHIN a process'), save writes to a dict not disk, so nothing survives a real process restart. Genuinely missing in pythinker (context.py persists only token_count; cost/usage are fresh per run) but no reference code to port — extend-the-_usage-journal design is reference-able, low priority.
- **token-budget-continuation-nudge** — Per-turn token-budget continuation nudge + diminishing-returns early stop + completion telemetry: Double-stubbed in the reference (feature('TOKEN_BUDGET')=False AND get_turn_output_tokens hardwired to return 0). Pythinker's structural intent is already served by bounded _run_goal_continuations (goal.max_continuations), the one-shot intent-nudge, and the consecutive-failure 'stuck' backstop. Adopting the token-budget algorithm needs new per-turn output-token telemetry pythinker does not track at turn granularity — a new feature, not a port. (Covers diminishing-returns-early-stop and budget-completion-telemetry siblings.)
- **static-dynamic-cache-boundary-marker** — Static/dynamic prompt-cache-scope boundary sentinel: Only meaningful with cross-organization/global prompt-cache scopes (the reference's should_use_global_cache_scope, a vendor-specific beta). Pythinker is multi-provider and does not segment prompt caching by org scope, so the marker would be inert. Pythinker already gets the equivalent win for free: dynamic content lives in user-role <system-reminder> messages after the byte-stable system.md. Revisit only if a provider-level global cache scope is introduced.
- **render-tool-hooks** — Per-tool UI render hooks (tool-use message, result, activity description): Reference hooks are explicit P6 no-op stubs returning None. Pythinker has its own render layer (ToolReturnValue.display/BriefDisplayBlock, wire ToolExecutionStarted events, extract_key_argument feeding TUI/ACP) — nothing live to port.

## Rewrite-defer (would require a loop swap / large structural rewrite — out of scope)

- **graduated-stall-ramp** — Stall severity as a continuous color ramp toward an error hue: verify confirmed=false (the task gate drops unconfirmed candidates out of adapt; the stray final_verdict:adapt in the data is inconsistent and not honored). The reference interpolation math is live and the blend primitives already exist and drive the shimmer ramp, but the current ActivitySnapshot.stalled field is DEAD scaffolding never set by any producer (both construction sites rely on the default False; git log -S confirms it was born unused and the consumer branch motion.py:301-302 is unreachable). There is no stall-detection infra at all. Adopting the ramp therefore requires BUILDING a stall-detection signal first (a new feature), not porting a pattern — out of scope for a polish pass.
- **unified-can-use-tool-seam** — Single can_use_tool decision seam returning {allow|deny|ask}: Even the scout's '80/20' sliver only relocates the deny-or-pass profile gate; Approval.request remains a separate seam with a different return type (ApprovalResult vs ToolError|None). Folding both into one decision object is a structural rewrite of the approval subsystem, already tracked as blueprint P2b. The reference seam interior is itself hollow (auto-mode classifier/acceptEdits/bypass fast-paths + ask-handler all TODO(port) stubbed), so it does not even prove the payoff.
- **declarative-allow-deny-rule-config** — User-configurable source-precedence allow/deny/ask rule strings: The session-allow sub-capability is already-have (signature-keyed session approval, approval.py:535/623). What remains — user-authored persistent rule files with user/project/local/cli/session source precedence, a rule-string parser, a wildcard matcher, persistence, and a config UI — is a new subsystem, exactly the broad-infrastructure-for-edge-cases the AGENTS.md simplicity rules forbid building speculatively. The shell classifier the rules would gate is itself a P3 stub in the reference.
- **structured-output-retry-cap** — Structured-output mode with a bounded retry counter via tool-call counting: Pythinker has no headless json_schema/output-contract mode, so there is nothing to bound — adding a StructuredOutput tool + schema-validated result mode is a feature, not a gap-fill. If a `--output-schema` headless mode is ever added, the retry-cap-via-tool-call-counting technique is the right pattern to adopt then, implemented over pythinker's Message.tool_calls.
- **user-configurable-keybindings** — User-configurable keybinding system (closed action/context vocabulary + JSON config + resolver): A user-facing feature (config schema, parser, context-aware resolver, public config key + docs/tests per compatibility rules), not theme/spinner polish. The reference default_bindings carry a TODO(port) stub. If user-rebindable keys are ever prioritized, scope it as its own task touching config.py + a new keybindings module + keyboard.py dispatch.

## Anti-patterns in the reference (do NOT import)

- **heterogeneous-attr-or-key-message-switch** — Stringly-typed attr-or-key discriminator dispatch over mixed dict/dataclass messages: The reference's _mtype/_msubtype/_attr switch exists only because it reconstructed message types from an absent src/types/message.ts and mixes dicts with dataclasses. Pythinker already has a typed wire protocol + typed TurnOutcome dataclass; adopting the stringly-typed discriminator would be a regression.
- **to-auto-classifier-input** — Per-tool compact rendering feeding an LLM-driven auto-mode security classifier: No consumer exists: pythinker auto-approval is a deterministic allowlist + token classifier, not an LLM security-classifier transcript. The hook only pays off after building that whole classifier subsystem — out of scope for the tool base contract.
- **swarm-teammate-coordinator-machinery** — Multi-agent swarm / in-process teammate / coordinator-mode spawn paths and external build gating: Reverse-engineered multi-agent/remote features, almost entirely stubbed (NotImplementedError / dead external-build-gated and feature-flag-gated branches carrying leaked external-internal symbol names). Importing any of it adds a large speculative spawn surface with no live behavior and would surface external product names. Pythinker's fan-out is already served by launching multiple foreground/background subagents.
- **agent-source-precedence-merge** — Agent-definition source-precedence merge (project overrides builtin): Refuted: pythinker already registers project markdown agents with NEW names; the only behavior the merge changes is the collision case, where today builtin wins by deliberate skip-and-warn. agents/default/agent.yaml:40-72 shows ALL ~12 builtins are core role agents, so there is no 'non-protected builtin' to safely override — adopting it would let a project silently CLOBBER a fixed core role agent. Keep the skip-and-warn inverse design.
- **module-global-mutable-state-budget** — Module-global mutable accumulators for turn/token accounting: Would break pythinker's multi-instance/ContextVar invariants. Pythinker already carries this state on session-scoped objects surfaced via the typed wire StatusUpdate; the reference's free-function globals (get_turn_output_tokens hardwired to 0) are a stubbed anti-pattern.
- **cwd-memoized-style-cache** — Memoize the resolved output-style set keyed on cwd: A cwd-keyed global cache is justified only by per-build re-resolution across multiple on-disk sources; pythinker resolves the prompt once at agent-load, so it adds a global mutable plus a stale-style invalidation bug for zero benefit.
- **verbatim-proprietary-prompt-text** — Byte-for-byte verbatim model-facing description strings + external build/user-type gates: The reference prompt files are reverse-engineered proprietary text with external-product build gates; copying the literal wording or the external-gate/internal-user-type/fidelity-verifier machinery is forbidden. Pythinker's own original .md descriptions are the correct compliant approach.
- **stringly-typed-hook-event-bus** — Stringly-typed event/regex-matcher hook dispatch: The matcher is inherent to the user-facing hook config contract (a public compatibility surface) and is already defensively handled (invalid regex fails closed-to-non-match with a warning). Do not 'improve' it into a typed matcher DSL — that breaks the documented config.toml hook schema for zero correctness gain.
