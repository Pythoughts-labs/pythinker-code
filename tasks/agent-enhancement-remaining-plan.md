# Pythinker Agent Enhancement — Robust Remaining-Work Plan

**Date:** 2026-06-08
**Builds on:** `tasks/pythinker-agent-enhancement-plan.md` (the comprehensive 37-gap / 32-item
plan, committed on `feat/agent-phase0-enhancements`) and `tasks/_gap_actionable.md`
(per-item GAP/ACTION/FILES analysis). This document does **not** re-derive those — it adds the
**execution layer** they lack: verified done-state, a file→item collision matrix, collision-aware
workstream sequencing, cross-plan dependencies, and branch strategy.

**Purpose.** Turn "~20 items remain" into a plan that survives contact with reality — i.e. one where
concurrent PRs do not collide on the same hot files, the L-effort items are scoped honestly, and the
work is resumable across sessions.

---

## 0. Ground truth (verified against the branch diff, not the recap)

Reconciliation anchored on `git diff main...feat/agent-phase0-enhancements` mapped onto each gap ID's
`FILES:` line + test presence — **not** the prior session's summary, which overclaimed.

### Done (verified — source landed; test coverage noted per row)
| ID | What | Evidence (✅ = test present, ⚠️ = source only, no test) |
|---|---|---|
| injdef-1 | `<untrusted_data>` declared to model | `system.md` + `test_default_agent.py` |
| tooldesc-1 | 7 stub tool descriptions filled | all 7 `.md` files modified |
| mode-3 / subagent-3 | effort/anti-sprawl rubric | `agent/description.md`, `system.md` |
| planning-1 | plan must include verification section | ⚠️ `plan/enter.py`, `dynamic_injections/plan_mode.py` — **no test** (add a reminder-text snapshot test) |
| planning-2 | `cancelled` todo state | `session_state.py`, `todo/*`, `display.py`, `tool_renderers/todo.py` |
| obs-eval-2 | cache-token + finish-reason telemetry (both halves landed) | ⚠️ `telemetry/metrics.py`, `pythinkersoul.py` — **no test** (add an InMemoryMetricReader assertion on cache_read/creation counters) |
| subagent-1 | plan-mode inheritance to subagents **(Critical)** | `permission.py` + `test_permission_profiles.py` |
| permgate-1 | per-command approval key + destructive backstop | `approval.py`, `permission.py`, shell/write/replace |
| injdef-3 | invisible-unicode strip on tool ingress | `utils/trust.py`, `project_memory.py` |
| permgate-3 | sibling approval de-duplication | `soul/approval.py` (not `runtime.py` as gap doc guessed) |
| permgate-2 / injdef-4 | config-surface edit protection + ingestion scan | `permission.py`, `write.py`, `replace.py`, `approval.py`, `file/__init__.py` |
| (display) | hide `<untrusted_data>` wrapper from TUI | ✅ `visualize/_blocks.py`, `test_untrusted_display.py` |

> **Test backfill (tracked, not blocking):** `planning-1` and `obs-eval-2` shipped source-only.
> Add a plan-mode reminder-text snapshot test and a telemetry counter assertion respectively — the
> obs-eval-2 test also de-risks the silent cache-keying regression it was meant to catch. All other
> DONE rows carry tests (verified: `mode-3`/`subagent-3` are snapshot-tested in
> `test_tool_descriptions.py` + `test_default_agent.py`).

### Partial (must finish — counted in remaining)
| ID | Done | Still missing |
|---|---|---|
| **injdef-2** | Shell stdout + WebSearch content wrapped (`tools/utils.py` `mark_untrusted`) | **Grep output** — `grep_local.py` has **zero** trust-wrapping. Finish this. |

### Remaining (the real scope of this plan — 22 work items)
Two were mislabeled "Phase 0 done" but **never landed** (no `config.py` / `tools/progress/` on branch):
- **memory-2** — flip durable-memory defaults (posture decision)
- **uxsteer-1** — wire a `ProgressNote` producer

Plus the original Phases 2–5 (20 items). Full list in §2.

---

## 1. The robustness lever: file → remaining-item collision matrix

The naive failure mode is "just do the remaining 20" in any order → merge-conflict hell, because the
remaining items pile onto a few hot files. Inverting every `FILES:` line for **remaining** items:

| Hot file | Remaining items that touch it | Risk |
|---|---|---|
| **`soul/toolset.py`** | tooldesc-2, obs-eval-1, mcpext-1, mcpext-2, mcpext-3 | **5 — highest** |
| **`soul/pythinkersoul.py`** | sysprompt-1, sysprompt-2, ctxmgmt-2, obs-eval-5, uxsteer-3 | 5 (subagent-2 does **not** touch it — see below) |
| **`agents/default/agent.yaml`** | memory-1/ctxmgmt-3, mcpext-1, uxsteer-1, uxsteer-2 | 4 (additive registration surface) |
| **`memory/recall.py`** | memory-1/ctxmgmt-3, memory-2, memory-3 | 3 (one feature) |
| **`config.py`** | ctxmgmt-1, ctxmgmt-2, memory-2 | 3 **+ live uncommitted theme-branch edits** |
| **`soul/permission.py`** | memory-1/ctxmgmt-3, mcpext-1 | 2 — **crosses WS-RECALL ⨯ WS-TOOLSET** (additive allow-list) |
| **`soul/agent.py`** | memory-1/ctxmgmt-3, uxsteer-1 | 2 — **crosses WS-RECALL ⨯ WS-UX** (registration) |
| **`agents/default/system.md`** | sysprompt-1, mode-1 | 2 |
| **`acp/session.py`** | uxsteer-1, uxsteer-3 | 2 |
| **`wire/types.py` / `visualize/_interactive.py`** | uxsteer-2, uxsteer-3 | 2 |
| **`llm.py`** | sysprompt-1, obs-eval-3 | 2 |
| `soul/__init__.py` (StatusSnapshot) | subagent-2 | 1 — single-touch, **parallel-safe** |

**Rule:** items sharing a hot file are **serialized into one workstream (one owner, sequential PRs)**;
items with disjoint file-sets run as **parallel workstreams**.

**The Recall tool (`memory-1`/`ctxmgmt-3`) is the collision hub.** Its file set
(`recall.py` + `agent.yaml` + `permission.py` + `soul/agent.py`) means WS-RECALL is **not** disjoint
from WS-TOOLSET (`permission.py`) or WS-UX (`soul/agent.py`). These touches are *additive*
(a new tool's allow-list entry + tool registration), so they merge cleanly **if landed sequentially** —
see the "registration surface" rule in §2. They are **not** "disjoint by construction."

---

## 2. Workstream decomposition (collision-aware resequencing)

The original plan's "Phase 2/3/4/5" are *priority bands*. The execution unit is the **workstream**,
chosen so two open PRs never touch the same hot file. Priority within/across streams still follows the
original impact×effort order.

### WS-FINISH — close the partials (do first, tiny, unblocks nothing-blocked)
1. **injdef-2-grep** · S · wrap `grep_local.py` joined output via `UntrustedData` (mirror shell path). Disjoint file. ✅ parallel-safe.

### WS-SOUL — `pythinkersoul.py` owner (strictly serial; the god-object)
Single owner, sequential PRs, rebase each on the prior. Ordered by impact:
1. **obs-eval-5** · M · stuck-loop / failure-threshold escalation
2. **sysprompt-2** · M · graceful max-steps handoff turn
3. **ctxmgmt-2** · **L** · graduated stale-tool-output pruning (also `compaction.py`, `context.py`, `config.py`)
4. **sysprompt-1** · M · model-defense injection provider (also `system.md`, `llm.py`, new `dynamic_injections/model_defense.py`)

⚠️ **uxsteer-3** also edits `pythinkersoul.py` but belongs to WS-UX — see cross-stream note below.
⚠️ **ctxmgmt-2 ↔ A7, sysprompt-1 ↔ A3, uxsteer-3 ↔ A4** all collide with the God-Object
Decomposition plan — see §3.

### WS-TOOLSET — `soul/toolset.py` owner (serial)
1. **tooldesc-2 / ctxmgmt-1** · M · tool-output overflow → disk spill + recovery hint (merged item; also `tools/utils.py`, `shell`, `read`, `config.py`)
2. **obs-eval-1** · M · connected `execute_tool` span + GenAI semconv naming (also `telemetry/otel.py`)
3. **mcpext-1** · M · MCP resources & prompts (also `permission.py`, `agent.yaml`)
4. **mcpext-2** · M · live MCP reconnect / tools-changed (also `ui/shell/slash.py`, `cli/__init__.py`)
5. **mcpext-3** · S · stdio MCP descendant-process / `--rm` hygiene (also `cli/mcp.py`)

### WS-RECALL — `memory/recall.py` + `tools/recall/` owner (serial; one feature)
1. **memory-2** · S · flip durable-memory defaults — **posture/privacy decision** (also `config.py`)
2. **memory-1 / ctxmgmt-3** · M · model-invokable cross-session `Recall` tool (merged; also `agent.yaml`, `permission.py`, `soul/agent.py`)
3. **memory-3** · M · re-arm recall on working-set/topic shift (also `memory/retriever.py`)

### WS-UX — uxsteer cluster owner (serial)
1. **uxsteer-1** · S · `ProgressNote` producer (also `agent.yaml`, `soul/agent.py`, `acp/session.py`, `ui/print/visualize.py`)
2. **uxsteer-2** · M · non-blocking suggestion affordance (also `wire/types.py`, `agent.yaml`, `_interactive.py`)
3. **uxsteer-3** · M · ACP question consistency + steer-cancels-question (also `acp/session.py`, `_interactive.py`, `wire/types.py`, **`pythinkersoul.py`**)

### WS-STANDALONE — disjoint file-sets (fully parallel-safe)
- **subagent-2** · M · child→parent token/cost roll-up (`subagents/runner.py`, `background/agent_runner.py`, `soul/__init__.py` StatusSnapshot, `tools/agent/__init__.py`) — **moved out of WS-SOUL: it does not touch `pythinkersoul.py` and is decomposition-disjoint**
- **skills-1** · M · skill bundled-resource manifest (`tools/skill/__init__.py`, `skill/__init__.py`)
- **skills-2** · M · `customize-pythinker` config skill (new `SKILL.md` only — zero code)
- **mode-1** · M · `agent-creator` meta-skill (`slash.py`, `agentspec.py`, `discovery.py`, `system.md`)
- **obs-eval-3** · **L** · record-replay LLM cassettes (`llm.py`, `tests_e2e/`)
- **obs-eval-4** · **L** · trajectory/efficiency eval scoring + versioned cases (`tests_ai/`)

### Cross-stream contention to manage explicitly
- **Registration surface** — `agents/default/agent.yaml`, `soul/agent.py` (tool/producer wiring), and
  `soul/permission.py` (allow-lists) are each touched by **every new-tool item** across streams:
  Recall (`memory-1`/`ctxmgmt-3`, WS-RECALL), `mcpext-1` (WS-TOOLSET), `uxsteer-1` + `uxsteer-2` (WS-UX).
  These edits are **additive** (new registration / allow-list block) but land in the *same region*, so
  they are **not** conflict-free in parallel. **Rule: serialize the registration-surface touches** —
  at most one open PR at a time editing `agent.yaml` / `soul/agent.py` / `soul/permission.py`; land
  Recall first (it is the hub), then rebase `mcpext-1` and the uxsteer items onto it. This converts the
  two §1 cross-stream collisions (`permission.py`, `soul/agent.py`) into trivial sequential merges.
- `config.py` is touched by WS-TOOLSET (ctxmgmt-1), WS-SOUL (ctxmgmt-2), WS-RECALL (memory-2) **and**
  the live theme branch (§4). Serialize all `config.py` additions and rebase on theme-branch merge.
- **uxsteer-3** is the one true bridge: it edits both WS-UX files and `pythinkersoul.py` (WS-SOUL).
  Schedule it **after WS-SOUL's queue drains** (or have the SOUL owner land it) to avoid a 2-stream race.
- `system.md` (sysprompt-1 in WS-SOUL, mode-1 in WS-STANDALONE) and `llm.py` (sysprompt-1 in WS-SOUL,
  obs-eval-3 in WS-STANDALONE): additive sections / disjoint functions — low risk, note for rebase.

---

## 3. Cross-plan dependency: God-Object Decomposition (`decomposition-plan.md`)

`tasks/decomposition-plan.md` Phase A extracts collaborators **out of** `pythinkersoul.py`. **This is
live, not theoretical: A1 (`FlowRunner`) already landed (PR #84, commit `575bf06a`)** — so the line
ranges in `decomposition-plan.md` are now stale and A2–A7 seams should be re-confirmed before use.

Three remaining enhancement items collide with specific Phase A extractions (not "6 items head-on" — the
collisions are surgical and per-PR):

| Enhancement item | Collides with | Why | Handling |
|---|---|---|---|
| **ctxmgmt-2** (graduated pruning) | **A7** `ContextCompactor` (`_grow_context`/`compact_context`/`_harvest_before_compaction` → `compaction.py`+`context.py`) | full 3-file overlap; the unique deep collision | A7-first, then build the prune helper on the seam |
| **sysprompt-1** (model-defense injection) | **A3** `InjectionManager` (`add_injection_provider`/`_collect_injections`) | new provider registers against the exact methods A3 extracts | A3-first (register against extracted manager), or sequence sysprompt-1 ahead and let A3 chase |
| **uxsteer-3** (steer-cancels-question) | **A4** `SteerQueue` (`steer`/`_consume_pending_steers`/`_inject_steer`) | edits the exact steer methods A4 extracts | A4-first, or co-own A4 + uxsteer-3 |

The other WS-SOUL items are **not** decomposition-entangled: `subagent-2` doesn't touch
`pythinkersoul.py` at all (→ `soul/__init__.py`); `obs-eval-5` and `sysprompt-2` touch the **retained**
core loop (`run`/`_step`), which A7 explicitly keeps in the host.

**Decision required (see §7):** either
- **(a) Freeze decomposition Phase A until WS-SOUL drains** — simplest; enhancements add behavior the
  decomposition would otherwise have to chase; **or**
- **(b) Extract-first per collision** — do A7 before ctxmgmt-2, A3 before sysprompt-1, A4 before
  uxsteer-3, so each feature lands in a focused collaborator instead of the 84k-line host.

Recommendation: **(b), with one caveat for ctxmgmt-2** — A7-first gives its prune helper + tiering a
clean home in `compaction.py`, but ctxmgmt-2's *trigger* edit is the `should_auto_compact` branch in
`_step` (`pythinkersoul.py:1252-1272`), which A7 **retains in the host**. So that trigger footprint
still lives in the retained loop and must still be serialized with `obs-eval-5`/`sysprompt-2` in the
WS-SOUL queue. A7-first removes the compaction-module half of the collision, not the trigger half.

---

## 4. config.py cross-branch collision (the live hazard)

The current working tree (`feat/tui-codex-theme`) has **uncommitted `config.py` edits** (theme tokens).
Three remaining items (ctxmgmt-1, ctxmgmt-2, memory-2) also add `config.py` fields. If both streams edit
`config.py` independently they will conflict.

**Containment:**
1. The theme branch's `config.py` change should land (merge to main) **before** any agent-enhancement
   `config.py` edit, or be explicitly rebased.
2. All three agent-enhancement `config.py` additions are **append-only new settings** — concentrate them
   in one section and land them in a single early "config scaffolding" PR if the theme work is still open,
   to minimize the conflict surface to one rebase.
3. **Do agent-enhancement work on `feat/agent-phase0-enhancements`, never in this theme tree.**

---

## 5. Branch & PR strategy

- **Continue on `feat/agent-phase0-enhancements`** (where Phases 0–1 live). Do **not** mix with the
  theme branch.
- **One PR per work item** (the original plan's "reviewable diffs" invariant). Within a serial
  workstream, stack/rebase PRs in the listed order.
- Parallel workstreams (WS-RECALL, WS-UX, WS-STANDALONE, WS-TOOLSET) can have **one open PR each**
  concurrently — they own disjoint hot files **except the shared registration surface**
  (`agent.yaml`, `soul/agent.py`, `soul/permission.py`), which is serialized per the §2 rule
  (land Recall first, rebase the rest). They are not disjoint "by construction."
- WS-SOUL keeps **exactly one open PR at a time** (shared god-object).
- Each PR: `make check` (ruff + pyright) clean + full `uv run pytest` green (pass-count ≥ baseline).

---

## 6. Verification strategy (per workstream)

Every item already carries a `Verify.` line in the source plan; the workstream-level gates:

- **WS-FINISH / WS-SOUL security-adjacent:** extend `tests/tools/test_untrusted_wrapping.py` (grep
  channel); for subagent-2/obs-eval-5/sysprompt-2 add behavior tests on a fixed scripted transcript
  (assert roll-up totals, escalation trigger, max-steps handoff text — without re-hitting the ceiling).
- **WS-TOOLSET:** overflow spill test (full output recoverable via `ReadFile(line_offset=…)`); span-tree
  test asserting `execute_tool` is a child of the LLM span (GenAI semconv); MCP resource round-trip.
- **WS-RECALL:** session-exit→resume test (JOURNAL written, recall surfaces it, growth bounded);
  Recall-tool search+read with sanitizer applied to historical transcript.
- **WS-UX:** `ProgressNote` renders in shell + print + ACP; suggestion is non-blocking; steer cancels a
  pending ACP question.
- **WS-STANDALONE L-items:** obs-eval-3 cassette determinism (same inputs → byte-stable replay);
  obs-eval-4 trajectory/token/tool-error scores emitted per scenario with a versioned case schema.

---

## 7. Decisions for you (gate before execution)

1. **Scope:** all 22 remaining, or a prioritized cut? The 3 **L-effort** items (ctxmgmt-2 graduated
   pruning, obs-eval-3 record-replay, obs-eval-4 eval harness) are each >1 week and the lowest-urgency.
   A high-value cut = WS-FINISH + WS-SOUL(S/M only) + WS-RECALL + WS-UX + cheap WS-STANDALONE, deferring
   the 3 L items.
2. **Decomposition coordination (§3):** freeze decomposition Phase A while WS-SOUL runs, or
   extract-first per collision (A7→ctxmgmt-2, A3→sysprompt-1, A4→uxsteer-3)? (Recommend: extract-first,
   noting ctxmgmt-2's trigger half stays in the retained loop regardless.) Either way, re-confirm A2–A7
   seams first — A1 already landed (PR #84), so the plan's line ranges are stale.
3. **memory-2 posture (§0/WS-RECALL):** flip `harvest_on_compaction` + `journal_recaps` to default-on
   (accept the disk/privacy tradeoff), or ship a "durable memory" opt-in profile instead?
4. **Start now?** If yes, I begin with WS-FINISH (injdef-2-grep) + the first WS-SOUL item, on
   `feat/agent-phase0-enhancements`.

---

## 7b. Decisions made (2026-06-08)

1. **Scope:** ✅ **All 22 items** (including the 3 L-effort: ctxmgmt-2, obs-eval-3, obs-eval-4). Multi-session.
2. **Decomposition coordination:** ✅ **Extract-first per collision** — A7→ctxmgmt-2, A3→sysprompt-1,
   A4→uxsteer-3. Re-confirm A2–A7 seams first (A1 landed in PR #84, line ranges stale).
3. **memory-2 posture:** ✅ **Opt-in "durable memory" profile** — do *not* flip defaults; ship a
   documented profile that enables harvest+journal. Reversible, no default privacy change.
4. **Execution:** ✅ **Start now**, on `feat/agent-phase0-enhancements`, in an isolated git worktree
   (the current tree has uncommitted `feat/tui-codex-theme` work that must not be disturbed).

**Execution order:** WS-FINISH (`injdef-2-grep`) → WS-SOUL non-collision items (`obs-eval-5`,
`sysprompt-2`) → then per-collision extract-first (A7→ctxmgmt-2, A3→sysprompt-1) → parallel
workstreams (WS-TOOLSET, WS-RECALL, WS-UX, WS-STANDALONE) honoring the §2 registration-surface rule.
One PR-sized, tested change at a time; `make check` + `uv run pytest` green per item.

---

## 7c. Progress log

| Date | Item | Status | Commits |
|---|---|---|---|
| 2026-06-08 | (gate) pre-existing pyright/format errors in Phase-1 security tests | ✅ fixed | `67a42404` |
| 2026-06-08 | **injdef-2-grep** (WS-FINISH) — wrap Grep content as untrusted | ✅ done | `127b3bbb` |
| 2026-06-08 | **obs-eval-5** (WS-SOUL #1) — stuck-loop failure-threshold escalation | ✅ done | `d8bc2832` |
| 2026-06-08 | **sysprompt-2** (WS-SOUL #2) — graceful max-steps handoff summary (tools-disabled, reuses btw mechanism; shell + print wired; wire/acp protocols untouched) | ✅ done | `df1a1728` |
| 2026-06-08 | (your change) "Did you mean?" tool-name suggestion on unknown tool calls | ✅ done | `c5d7c1c3` |
| 2026-06-08 | **ctxmgmt-2** (WS-SOUL #3) — graduated stale-tool-output pruning tier before full compaction | ✅ done | (this batch) |

**Decision update (§3 / §7b):** ctxmgmt-2 did **not** require the standalone A7
extraction. The pruning algorithm landed in the existing `compaction.py` (which
already hosts `SimpleCompaction`/`should_auto_compact`), satisfying extract-first's
*intent* (focused home, no host-algorithm bloat) without an out-of-order god-object
extraction (the decomposition plan orders A7 last). A7 remains available later for
moving the compaction *orchestration* (`_grow_context`/`compact_context`) out of the
host, but is no longer a prerequisite for any enhancement item.

**Next:** `sysprompt-1` (A3 collision — model-defense injection; same call: land in
existing injection bus without forcing the A3 extraction) or a parallel
WS-STANDALONE item. Remaining: 18 items.

---

## 8. Reference

- Detailed per-item ACTION/BASE_REC/FILES: `tasks/_gap_actionable.md` (37 items) and
  `tasks/pythinker-agent-enhancement-plan.md` §6 (work-item detail), §7 (rejected Kilo patterns —
  do **not** build per-provider prompt swaps, `priority` todo field, IDE/webview affordances).
- Done-state ledger: §0 above (re-verify against the diff if resuming in a later session).
