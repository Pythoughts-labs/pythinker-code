# Tasks

## Active

Branch `refactor/agent-contract-and-tool-metadata` — landing step 1 of
`tasks/design-adoption-blueprint.md` (agent-logic/coding-flow cleanup):

- [x] Task 1: FetchURL untrusted-envelope fix — DONE (ceeeeb78; 3 TDD tests,
      spec + quality review approved). Deferred: add `await
      builder.spill_to_disk()` at the trafilatura + fetch-service sites for
      event-loop hygiene (pre-existing asymmetry; no output difference).
      Original: `tools/web/fetch.py:232,277,338`
      write pre-rendered `UntrustedData(...).render_for_prompt()` into the
      builder, so truncation can cut the closing envelope tag and break
      `strip_untrusted_envelope` (endswith). Switch to raw write +
      `builder.mark_untrusted()` (idiom: `tools/web/search.py:174-177`).
      → verify: new TDD test reproducing tag truncation fails before / passes
      after; `tests/utils` untrusted-wrapping suite green.
- [x] Task 2: Public `turn()` contract on PythinkerSoul — DONE (7e96dfb8;
      thin delegate keeps `_turn` as the test patch point; 3 call sites
      migrated, suppressions removed; contract docstring distinguishes
      framed vs unframed callers; spec + quality review approved).
- [x] Task 3: Declarative tool metadata for the dispatch/permission gates —
      DONE (eaa96d6e; `external_side_effect_tool` ClassVar on the 3 adapters,
      `emits_tool_execution_started_after_approval` pinned on 8 classes,
      both string-match consumers rewritten; spec review, quality review,
      and security review (SAFE TO MERGE) all passed).

Review: branch `refactor/agent-contract-and-tool-metadata` (3 commits on top
of bff54f94) final-reviewed READY TO MERGE. Full `make test-pythinker-code`:
5279 passed, 1 failed — the failure is
`tests/e2e/test_shell_pty_e2e.py::test_shell_cancel_running_command_kills_process_and_recovers`,
verified PRE-EXISTING and machine-local: fails identically in isolation on
main (bff54f94) and on 7caeca33 / d51ef649 / 2904de00, all of which merged
with green CI. It is the ONLY test that sends ESC, so the local ESC-interrupt
PTY path has no corroborating coverage. Needs its own debugging session
(suspect ESC flush timing in the local macOS/Python 3.14 PTY environment).

Out of scope this PR (logged): pricing display move out of core, the
`extract_key_argument` name→spec registry, larger soul/toolset splits
(blueprint P1a/P2a/P2b).

### Deferred from this branch's reviews
- `await builder.spill_to_disk()` missing at FetchURL trafilatura +
  fetch-service sites (pre-existing; sync-spill fallback is correct, just
  blocks the event loop briefly).
- No structural enforcement that FUTURE external adapters declare
  `external_side_effect_tool` (pin tests cover the current three only);
  consider an `__init_subclass__` check or lint rule.
- MCPTool fires ToolExecutionStarted before its approval dialog resolves
  (no `emits_tool_execution_started_after_approval`); pre-existing event
  ordering inconsistency vs Shell/WriteFile — decide deliberately.

Done: `mythos-enhancements` PR #118 merged (d51ef649).

### Deferred (documented, not silently dropped)

- Read-only MCP doc-lookup carve-out for offline roles — today ALL MCP tools
  are fail-closed below the implement profile (deliberate); reviewer specs
  route doc needs to the parent/`scout` instead. Revisit only with a real
  allowlist mechanism design.
- Per-profile shell timeout caps: rejected — long `pythinker review`/`secscan`
  runs are legitimate; spec-level timeout discipline shipped instead.
- Codename polish: a background RunAgents child can show a name codename AND a
  different task-id codename (each distinctive, mildly redundant); aligning
  them needs a preferred-suffix param through `manager.launch_agent_task`.
- Narrow race: a subagent launched while the parent's background MCP connect is
  still in flight misses shared MCP tools (map populated later) — needs a
  re-bind or wait at subagent build.
- Test-design debt: test_learn_slash mocks soul._turn; test_soul_status_cost
  asserts an import — black-boxing them is its own task.
- From the review-safety plan: full ShellReadPolicy allowlist (would deny every
  unclassified command — needs maintainer call); ReviewCapabilityRegistry +
  scanner ladder (no external scanner subsystem exists yet); Phase 5
  heartbeats/token budgets (own PR); Phase 6 full TaskEventStore renderer
  rewrite (own PR); OS-level sandboxing (Seatbelt/Landlock).
- Non-interactive Rich Live path forces `live.update(refresh=True)` on every
  wire message in `_live_view.py`, bypassing its 10fps clock — separate
  flicker contributor in that mode.
- Provider compat: 400 "enable_thinking restricted to True" lives in
  pythinker_core openai_legacy (external); Bugsink keeps reporting it (4xx
  stays unexpected) until fixed upstream — desired.
- Infra: edge OTLP collector accepts any bearer token; SigNoz SMTP may need
  configuring for alert email delivery.

## Recently completed

Completed-work logs through 2026-06-11 (agent robustness arc, statusline v2,
review-safety hardening, telemetry sync, CodeRabbit triage) were trimmed on
repush of PR #118 — see git history of this file for the full record.
