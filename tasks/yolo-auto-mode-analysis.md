# YOLO + Auto Mode: Hypotheses, Behavior, and Test Plan

**Question:** What happens when *YOLO mode* is combined with *auto mode* in pythinker, and what bugs/issues can appear?

**Scope:** Analysis of `feat/auto-mode-tui-rendering`. Every claim cites `file:line`.

> **Update (2026-06-02): B1, B2, B3 (a/b/c) fixed in this branch; B4 resolved as correct-as-designed.** See §7.

---

## 0. The two flags (definitions)

| Flag | Identifier | Meaning | Persisted? |
|---|---|---|---|
| **YOLO** | `ApprovalState.yolo` (`soul/approval.py:145`) | "Dangerously skip permission approvals." Explicit opt-in. | Yes — `session_state.py:16` |
| **Auto** | `ApprovalState.auto` / `runtime_auto` (`soul/approval.py`; `is_auto()` at `approval.py:244`) | "No user is present at the terminal." | `auto` yes (`session_state.py:17`); `runtime_auto` no (`--print` only) |

Key compound: `is_auto_approve()` (`approval.py:223-234`):

```python
if yolo:        return True      # YOLO overrides everything below
if safe_mode:   return False     # untrusted workspace blocks auto (but NOT yolo)
return is_auto()
```

---

## 1. TL;DR — what the combination actually does

With **both** flags on, the agent is in the **most permissive state the system can reach**: every tool call is auto-approved with no human in the loop, the agent cannot pause to ask the user, and it can both *enter and exit plan mode by itself* — defeating the plan checkpoint.

**The single most important finding:** the only destructive-action backstop, the *deliberation gate*, is **OFF by default** (`auto_deliberate_destructive_actions` defaults to `False`, `config.py:381-382`; the gate requires it at `approval.py:302`). It is turned **on** only by the purpose-built `autonomous_coding` profile (`config.py:492-493`). Therefore:

> The **obvious** way to run unsupervised — typing `--yolo --auto` with a default config — is **strictly more dangerous** than the purpose-built `autonomous_coding` profile, because the manual path leaves the deliberation gate disabled. In that state `rm -rf /tmp/x`, `git reset --hard`, `git push --force` all auto-approve with **zero friction**.

---

## 2. How you realistically end up here (activation paths)

This is not a contrived combination:

1. **`autonomous_coding` profile + `--auto`/`--print`** — the profile sets `default_yolo=True` (`config.py:487-488`) and `auto_deliberate=True` (`config.py:492-493`) and `ask_user_question_policy="never"` (`config.py:489-491`). Add auto/print and both flags are on. *This is the intended combination and it has the deliberation backstop.*
2. **Manual `--yolo --auto`** (default config) — both flags on, **deliberation gate off**. *The dangerous one.*
3. **Resume** — both `yolo` and `auto` persist to `state.json`; on resume `effective_yolo = yolo or session.state.approval.yolo` (`agent.py:282`) and `auto = session.state.approval.auto` (`agent.py:300`). A session toggled into `/yolo` + `/auto` once **silently resumes fully unsupervised** with no re-confirmation, and there is no CLI flag to force it *off*.
4. **`--print` + config `default_yolo`** — one-shot non-interactive run, fully unsupervised, no checkpoint, can't ask.

---

## 3. Combined behavior, by action (default config, yolo+auto)

| Action | Result | Why |
|---|---|---|
| WriteFile / StrReplaceFile (in workspace) | auto-approved | `is_auto_approve→True` (`approval.py:230`); file tools not in destructive registry |
| WriteFile **outside** workspace (`~/.bashrc`, `~/.ssh/`) | auto-approved | YOLO makes `_unattended_denial_feedback→None` (`approval.py:258`), bypassing the outside-workspace guard (`approval.py:260`) |
| `rm -rf`, `git reset --hard`, `git push --force` | **auto-approved, no bounce** (default) | deliberation gate needs `auto_deliberate=True` (`approval.py:302`), default False |
| same, under `autonomous_coding` | bounced **once**, then runs | gate on; one-shot per (context, generation) (`approval.py:329-344`) |
| `rm -r dir` (no `-f`), `find -delete`, `: > file` | **auto-approved, never bounced** | classifier requires *both* `-r` and `-f` (`permission.py:538-540`); other forms unclassified |
| AskUserQuestion | auto-dismissed ("no user present") | bound to `is_auto` (`pythinkersoul.py:553`); auto path dismisses |
| EnterPlanMode | auto-approved | bound to `is_auto_approve` (`pythinkersoul.py:544`) |
| ExitPlanMode | auto-approved | bound to `is_auto` (`pythinkersoul.py:532`) → **plan checkpoint defeated** |

---

## 4. Hypotheses

Split into **BUGS** (genuine defects/inconsistencies worth fixing) and **RISKS** (correct-as-coded, but the combination removes supervision). Each is falsifiable with the test given. Harness patterns: unit = `Approval(state=ApprovalState(...))` (see `tests/core/test_approval_safe_mode.py`); integration = `Runtime.create(...)` (see `tests/core/test_runtime_auto_state.py`).

### BUGS

**B1 — The obvious manual combo is more dangerous than the profile. [HIGH]**
`auto_deliberate_destructive_actions` defaults `False` (`config.py:382`); the gate requires it (`approval.py:302`). So `--yolo --auto` with a default config auto-approves every destructive shell command with no bounce, while the purpose-built `autonomous_coding` profile (`config.py:492-493`) is *safer*. The safe path is the obscure one.
- **Test (unit):** build a `Shell` `ToolCall` for `rm -rf /tmp/x`.
  - `Approval(ApprovalState(yolo=True, auto=True, auto_deliberate=False))` → `deliberation_gate(call) is None` and `await request(...)` returns `approved=True` (no bounce).
  - flip `auto_deliberate=True` → first `request` returns `approved=False, deliberation=True`; re-issue in a later deliberation generation returns `approved=True`.
  - **Assertion that documents the defect:** default-config yolo+auto never bounces a destructive command.

**B2 — Plan-mode checkpoint defeated via Enter/Exit binding asymmetry. [MED-HIGH]**
`EnterPlanMode` is bound to `is_auto_approve` (`pythinkersoul.py:544`); `ExitPlanMode` to `is_auto` (`pythinkersoul.py:532`) — different predicates. Under yolo+auto both are true, so the agent enters *and* approves its own plan exit; the human-review checkpoint is nullified. The asymmetry is independently wrong: in **yolo-only** (interactive, not auto) you slip into plan mode silently (`is_auto_approve=True`) but must click to leave (`is_auto=False`).
- **Test (unit):** `ApprovalState(yolo=True, auto=False)` → `is_auto_approve()` True but `is_auto()` False → assert the two plan tools would resolve differently (the bug). 
- **Test (integration):** `Runtime.create(yolo=True)` with persisted `auto=True`; enter plan mode; invoke `ExitPlanMode`; assert it returns auto-approved *without* creating a `QuestionRequest`.

**B3 — Dangerous state persists and silently resumes; no force-off; `--yolo` rewrites trust. [MED]**
`yolo` + `auto` both persist (`session_state.py:16-17`) and re-apply on resume (`agent.py:282,300`) with no re-confirmation, and no CLI flag disables a persisted yolo. **Related:** a raw `--yolo` invocation sets `effective_safe_mode = False` (`agent.py:285`) and `_on_approval_change` writes `session.state.trust.safe_mode = False` back to disk (`agent.py:295`) — so one `--yolo` run silently downgrades the workspace's persisted trust posture (gated on the raw CLI flag, not persisted/config yolo).
- **Test (integration):** set `session.state.approval.yolo=True, .auto=True`; `Runtime.create(..., yolo=False)` → assert resulting `approval.is_yolo()` and `is_auto()` both True (state silently resumed).
- **Test (integration):** `Runtime.create(..., yolo=True)`, trigger a state change (`set_auto(True)`) → assert `session.state.trust.safe_mode is False` persisted.

**B4 — `autonomous_coding` sets `ask_user_question_policy="never"`, dismissing AskUserQuestion even in interactive sessions. [LOW-MED]**
`config.py:489-491`: policy `"never"` dismisses regardless of `is_auto`. With profile yolo but no auto (user present), the agent still can never ask them. Tangential to yolo+auto; flag as related.
- **Test (tool unit):** policy `"never"`, `is_auto=False` → AskUserQuestion still returns the auto-dismiss note.

### RISKS (correct-as-coded; the combination is the hazard)

**R1 — Full unsupervised auto-approve, no checkpoint anywhere. [HIGH]**
`is_auto_approve→True` (`approval.py:230`) + `_unattended_denial_feedback→None` (`approval.py:258`). No tool call ever surfaces to a human.
- **Test (unit):** yolo+auto → `is_auto_approve()` True; `request()` for WriteFile and benign Shell both `approved=True`.

**R2 — The deliberation gate (when on) is narrow, one-shot, self-supervised. [HIGH]**
(a) covers **only `Shell`** (`permission.py:510-512`); (b) misses `rm -r` without `-f` (`permission.py:538-540`), `> file` truncation, `find -delete`, `curl … | bash`, `mv` overwrite, `chmod -R`, glob/var-hidden `rm -rf`; (c) one-shot — the model "deliberates" for one generation, then re-issues and it runs, with **no human veto** in auto mode.
- **Test (unit):** `shell_destructive_reason("rm -r /tmp/x") is None`; `"find . -delete" is None`; `": > important.db" is None` → all auto-approve under yolo+auto. Documents the gaps.
- **Test (unit):** one-shot generation behavior — bounce → pass (next gen) → bounce again (fingerprint deleted, 3rd gen is a fresh first-sighting). Drive `_current_deliberation_scope` contextvar.

**R3 — AskUserQuestion auto-dismissed → no escalation at forks. [MED]**
`pythinkersoul.py:553` binds `is_auto`; auto path returns "no user present, make your own decision." The agent cannot escalate a genuinely ambiguous/irreversible decision. Under `auto_deliberate` policy it self-decides via `blind_advisor_verdict` (`deliberation.py:52-92`), which **never raises** — advisor failures silently fall back to the agent deciding alone.
- **Test (tool unit):** yolo+auto, policy `ask_except_auto` → AskUserQuestion returns the dismiss note, non-blocking.

**R4 — Runaway / cost: no auto-exit, ≤1000 steps/turn + ralph loop, every step auto-approved. [MED]**
Auto mode has no auto-exit; `max_steps_per_turn` default 1000 (`MaxStepsReached`, `pythinkersoul.py:1227`); ralph loop up to `max_ralph_iterations`. YOLO removes all approval friction, so a looping/hallucinating model can execute ~1000 auto-approved (and within R2's gaps, destructive) tool calls per turn unsupervised.
- **Test (property/limit):** assert the only per-turn stop is `max_steps_per_turn`; assert no auto-mode-specific de-escalation exists.

**R5 — Trust-gate bypass in untrusted workspaces. [HIGH]**
Auto-alone fails closed under `safe_mode` (`is_auto_approve→False` at `approval.py:232`; denial at `approval.py:262`). **YOLO bypasses both** (`approval.py:230,258`). So a cloned/untrusted repo opened with config `default_yolo` (or persisted yolo) + auto gets full auto-approve in a workspace never trusted. Only explicit `/trust off` clears yolo (`ui/shell/slash.py:1415`).
- **Test (unit):** `ApprovalState(yolo=True, auto=True, safe_mode=True)` → `is_auto_approve()` True and `_unattended_denial_feedback(safe_mode_action) is None`. Compare `ApprovalState(auto=True, safe_mode=True)` (no yolo) → `is_auto_approve()` False, feedback returned. Precise asymmetry.

**R6 — Outside-workspace writes proceed; "reversible" is operationally meaningless unattended. [MED]**
YOLO bypasses the `_EDIT_OUTSIDE_ACTION` guard (`approval.py:258,260`) → writes to `~/.bashrc`, `~/.ssh/authorized_keys`, etc. auto-approve. **Credit where due:** WriteFile/StrReplaceFile *do* create a content restore point unconditionally (`file_restore.py`; `write.py:165`, `replace.py:280`) that works for *any* path including untracked/gitignored/outside-workspace — so the file content is mechanically recoverable and this is **not** a data-loss bug. **But:** (a) no human is present to invoke `/restore`; (b) side effects already fired (a modified shell rc, an added SSH key); (c) restore points are session-scoped and lost with the session. So the trust boundary is bypassed even though content is technically restorable; file tools are also not in the deliberation registry, so there is no bounce either.
- **Test (unit):** yolo+auto → `request(action=_EDIT_OUTSIDE_ACTION)` returns `approved=True`. Compare auto-only (no yolo) → `approved=False` with `_OUTSIDE_WORKSPACE_UNATTENDED_FEEDBACK`.

---

## 4b. Verification status (tests run 2026-06-02)

| Hypothesis | Status | Evidence |
|---|---|---|
| B1 | **Fixed** (new tests) | `tests/core/test_runtime_auto_state.py::test_default_config_yolo_auto_deliberates_destructive_actions` — default config + yolo+auto now bounces destructive shell calls for deliberation |
| B2 | **Fixed** (new test) | `tests/core/test_plan_mode_auto_approval.py` — Enter/Exit plan-mode tools now use the same unattended predicate |
| B3 | **Fixed** (new tests) | `tests/core/test_resume_safety_notice.py`; `tests/core/test_runtime_auto_state.py::test_yolo_runtime_does_not_persist_safe_mode_downgrade`; `test_no_yolo_forces_yolo_off_over_persisted_state` |
| R2 (one-shot/narrow gate) | **Already covered** | `test_approval_auto.py::test_destructive_action_deliberates_once_then_proceeds_under_auto`, `test_same_generation_duplicate...`, `test_subagent_identical_call...`, `test_unscoped_destructive_calls_always_bounce_fail_closed` |
| R5 (yolo bypasses safe_mode) | **Already covered** | `test_approval_safe_mode.py::test_yolo_overrides_safe_mode`; `test_runtime_auto_state.py::test_unattended_runtime_in_default_safe_mode_denies_without_waiting` (the no-yolo contrast) |
| R6 (outside-workspace) | **Already covered** | `test_approval_auto.py::test_trusted_auto_denies_outside_workspace_write_without_yolo` + `test_explicit_yolo_allows_outside_workspace_auto_write_boundary` |

Production fixes and regression tests were added for B1, B2, and B3. Focused approval/runtime tests pass; `ruff check` + `ruff format --check` are clean.

## 5. Severity summary

| ID | Kind | Severity | One-line |
|---|---|---|---|
| B1 | Bug | HIGH | Manual `--yolo --auto` is more dangerous than the profile (gate off by default) |
| R1 | Risk | HIGH | Full unsupervised auto-approve, no checkpoint |
| R2 | Risk | HIGH | Backstop is narrow, one-shot, self-supervised |
| R5 | Risk | HIGH | YOLO bypasses untrusted-workspace safe_mode |
| B2 | Bug | MED-HIGH | Plan checkpoint defeated; Enter/Exit binding asymmetry |
| B3 | Bug | MED | Dangerous state persists & silently resumes; `--yolo` rewrites trust |
| R3 | Risk | MED | AskUserQuestion dismissed → no escalation |
| R4 | Risk | MED | Runaway: 1000 steps/turn, no auto-exit |
| R6 | Risk | MED | Outside-workspace writes; reversibility moot unattended |
| B4 | Bug | LOW-MED | `autonomous_coding` policy "never" dismisses asks even interactively |

---

## 6. Suggested guardrails (if any of the bugs are confirmed actionable)

- **B1:** when `yolo and auto` are both set, default `auto_deliberate` to `True` (or warn loudly at startup that the destructive backstop is off).
- **B2:** bind both plan tools to the *same* predicate; require an explicit non-auto confirmation to *exit* plan mode, or document the defeat.
- **B3:** print a one-line banner on resume when yolo/auto are restored from disk; add a `--no-yolo` force-off flag; do not persist a `--yolo`-derived `safe_mode=False` beyond the run.
- **R5:** make YOLO respect `safe_mode` for *untrusted* workspaces (require `/trust` first), or warn.

*Note: items in §6 are suggestions; what was actually implemented is in §7.*

---

## 7. Fixes implemented (2026-06-02)

Decided with the user: **B1 = "all unsupervised" scope**; ship **B1 + B2 + B3**. **B4** is resolved as correct-as-designed.

### B1 — destructive backstop now holds whenever unattended

`soul/approval.py` `deliberation_gate`: the early-return changed from
`if not self._state.auto_deliberate` to `if not (self._state.auto_deliberate or self.is_auto())`.
A destructive auto-approved action is now bounced once for deliberation whenever **no user
is present** (`is_auto`), regardless of the config flag. The `auto_deliberate` flag now only
*extends* deliberation to the interactive-yolo case (user present, approvals skipped).

- Consistency: `soul/dynamic_injections/auto_mode.py` now always injects the
  destructive-deliberation guidance under auto (the bare `_AUTO_PROMPT` was removed as
  orphaned — it could no longer be selected).
- Effect: plain `--auto` (trusted) and manual `--yolo --auto` now match the
  `autonomous_coding` profile instead of being more dangerous than it.

### B2 — plan-mode checkpoint preserved under interactive yolo

`soul/pythinkersoul.py`: `EnterPlanMode` is now bound to `self._approval.is_auto` (was
`is_auto_approve`), matching `ExitPlanMode`. Interactive `--yolo` no longer silently slips
into plan mode and then blocks the exit; both transitions self-approve only when truly
unattended (`is_auto`).

### B3 — persisted-state footguns (all three implemented)

- **B3a (trust corruption — the real bug):** `agent.py` no longer forces
  `effective_safe_mode = False` under `--yolo`. Yolo already bypasses safe mode in the
  decision path (`is_auto_approve` / `_unattended_denial_feedback` short-circuit on yolo
  before reading `safe_mode`), so there was no deadlock to avoid — and the forced `False`
  was being persisted back to `session.state.trust.safe_mode`, silently downgrading the
  workspace's trust posture. Now `effective_safe_mode = session.state.trust.safe_mode`.
- **B3b (resume notice):** `app.py` `run_shell` adds a WARN welcome-banner item
  (`_resumed_unsupervised_notice`) when a resumed session is running yolo and/or auto, so
  it is never silently restored from disk. (yolo/auto also already show in the status bar.)
- **B3c (`--no-yolo`):** new CLI flag plumbed cli → `PythinkerCLI.create` → `Runtime.create`;
  `effective_yolo = (yolo or persisted) and not no_yolo`, overriding the flag, config
  `default_yolo`, and persisted/resumed state. `--no-yolo` beats `--yolo` if both are passed.

### B4 — resolved as correct-as-designed (no change)

`autonomous_coding` keeps `ask_user_question_policy="never"`. Switching to `ask_except_auto`
is a **no-op** in every headless context the profile is for (auto/`--print`/`runtime_auto`
→ `is_auto` → both dismiss) and would *contradict* the profile's purpose interactively (an
"autonomous" session would block for input). `"never"` is the deliberate, correct choice.

### Tests (all RED→GREEN)

- New: `tests/core/test_plan_mode_auto_approval.py` (B2 binding);
  `tests/core/test_resume_safety_notice.py` (B3b).
- `test_runtime_auto_state.py`: B1 backstop + B3a (yolo doesn't corrupt persisted
  `safe_mode`) + B3c (`--no-yolo` forces off over persisted yolo).
- `test_approval_auto.py`: gate conditions, flag role, default-auto background-shell
  deliberation. `test_auto_injection.py`: prompt selection. The obsolete
  `test_plan_mode_enter_exit_predicate_asymmetry` (asserted the *buggy* asymmetry) was
  removed — superseded by the binding test.
