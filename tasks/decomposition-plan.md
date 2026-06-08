# God-Object Decomposition Plan

Staged, one-collaborator-per-PR decomposition of the two largest behavioral
classes. **Invariant for every PR: public API frozen, behavior identical,
full test suite green before and after.** Each PR extracts a collaborator that
the host class *delegates to* — no logic rewrites, just relocation behind a
narrow interface.

Guiding rules:
- Characterize before cutting: confirm the seam is covered by existing tests
  *before* moving code. If a seam is thin on tests, add characterization tests
  in a separate prior PR.
- One collaborator per PR. Reviewable diffs over big-bang.
- No new abstractions that don't reduce the host class's surface. A 400-line
  helper with one caller is the same code in a new file — only worth it if it
  is independently testable and shrinks the host's responsibility count.
- Delegation, not duplication: the host keeps thin forwarding methods where the
  public API requires them.

---

## Phase A — PythinkerSoul (`src/pythinker_code/soul/pythinkersoul.py`, 2209 lines)

Seams identified by responsibility cluster (line ranges approximate, current main):

| PR  | Collaborator            | Methods to extract (from PythinkerSoul)                                                                                                            | Lines      | Risk |
|-----|-------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|------------|------|
| A0  | (characterization only) | Add tests for any thin-covered seam below before moving it (esp. compaction, connection recovery).                                                 | n/a        | none |
| A1  | `FlowRunner` → own module | Already a *separate class* in this file (lines ~2033-end). Move verbatim to `soul/flow_runner.py`, fix imports. Pure relocation.                  | ~180       | low  |
| A2  | `PlanModeController`     | `_bind_plan_mode_tools`, `_ensure_plan_session_id`, `_set_plan_mode`, `get_plan_file_path`, `read_current_plan`, `clear_current_plan`, `toggle_plan_mode*`, `set_plan_mode_from_manual`, `schedule_plan_activation_reminder`, `consume_pending_plan_activation_injection`, `plan_mode` property | ~160       | med  |
| A3  | `InjectionManager`      | `add_injection_provider`, `rearm_injection`, `_collect_injections`, `_notify_injection_providers_compacted`, `consume_pending_plan_activation_injection` glue | ~70        | med  |
| A4  | `SteerQueue`            | `steer`, `_consume_pending_steers`, `_inject_steer` + the pending-steer buffer state                                                               | ~40        | low  |
| A5  | `SlashCommandRegistry`  | `available_slash_commands`, `_build_slash_commands`, `_index_slash_commands`, `_find_slash_command`, `_make_prompt_template_runner`, `_make_skill_runner`, `_record_invoked_skill` | ~140       | med  |
| A6  | `ConnectionRecovery`    | `_is_retryable_error`, `_run_with_connection_recovery`, `_retry_log`, `_emit_step_retry`                                                            | ~130       | med  |
| A7  | `ContextCompactor`      | `_grow_context`, `compact_context`, `_harvest_before_compaction`, `_context_usage`                                                                  | ~240       | high |

After A1–A7, the host retains its identity: lifecycle/state (`__init__`,
status, model/agent/runtime/context accessors) and the core loop (`run`,
`_turn`, `_agent_loop`, `_step`) — the irreducible "soul". Target: host class
drops from ~2200 to roughly ~1100 lines.

**Sequencing rationale:** A1 first (zero-risk warm-up, proves the import-move
mechanics). Then ascending risk. A7 (compaction) last — it is the most
state-entangled (touches context, harvesting, injection-notify) and benefits
from A3 already being extracted.

**Per-PR verification:**
1. `make check` (ruff + pyright) clean.
2. Full `uv run pytest` green (diff the pass count vs. main — must be ≥).
3. For A7 specifically: add an explicit before/after compaction behavior test
   asserting message-count and context-usage parity on a fixed transcript.

---

## Phase B — Shell trio (needs its own seam-discovery pass first)

`ui/shell/prompt.py` (3591), `ui/shell/__init__.py` (2107), `ui/shell/slash.py`
(1881) are collectively larger than PythinkerSoul and are the bigger target —
but I have **not** yet mapped their seams. Do a discovery PR (read-only,
produces a seam table like Phase A) before committing to extraction PRs. Do not
start Phase B until Phase A lands and stabilizes.

---

## Out of scope (logged, not fixed here)
- `models_dev.py:65` — `ty` flags `"@" in model_id` (`model_id` typed `object`).
  Confirmed `ty` false positive (JSON dict key, always `str`; pyright is fine).
  Left as-is; documents why `ty` stays advisory.
