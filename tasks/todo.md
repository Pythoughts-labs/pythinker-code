# Tasks

## Active

- [ ] Open the `mythos-enhancements` PR; CodeRabbit gate before merge.

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

### 2026-06-11 — Agent robustness arc (`mythos-enhancements`): spec/profile truth, jail hardening, orchestration discipline, codename task ids

Source: live assessment of a review session (reviewers' mandated Context7/web
freshness check was dead code under their own permission profiles) + verified
triage of the follow-up deep-scan session ace53ad5.

Decisions: reviewer-class agents (review/code-reviewer/security-reviewer,
judge, verifier, debugger, explore) stay OFFLINE — untrusted-diff exfiltration
posture wins; specs rewritten offline-honest with a structured
`needs verification — <library> <version>: <claim>` RISKS contract for the
parent to resolve (directly or via `scout`). `scout` was accidentally offline
(unmapped → read_only): now `scout → ask` in `_SUBAGENT_PROFILES`. No MCP
carve-out (fail-closed stands); dead `mcp__context7__*`/`mcp__tavily__*` and
SearchWeb/FetchURL entries removed from non-implement specs; plan/scout route
docs work through live web tools. verifier/planner/ask/debug/coder/implementer
audited — already consistent, untouched.

Landed (all TDD red→green):

- Specs: code_reviewer/security_reviewer/review offline rewrite (+ timeout
  discipline: narrow scope on timeout, never re-run bigger; decomposition
  hint in when_to_use); judge → offline external-claims gate; debugger →
  installed-source-first; explore offline text; plan/scout web-first routing.
- system.md §5 "Review fan-out & finding verification": scope measured at the
  merge base (committed + worktree — never the uncommitted-only stat);
  >~1,500 lines / 25 files → one reviewer per subsystem + dedup; adversarial
  verification (re-read cited lines, re-derive failure; drop or reject —
  never severity-launder); re-anchor + recount; verify only third-party
  needs-verification claims against live docs; query hygiene at the
  network-holding layer. §8: findings reports are judge-gate triggers; child
  severities reported as scored, never silently re-graded. `scout` added to
  the §5 role enumeration. deep-scan.md playbook updated to match.
- permission.py: `scout → ask`; escape denials name the workspace root;
  workspace-jail bypass family closed — `$VAR`/backtick path args rejected
  fail-closed (patterns/program args unaffected — extractors never emit them
  as paths), glob args checked by literal prefix (`rg x /etc/*`, `ls ../*`,
  glob-then-`..` denied; in-workspace globs + `cat /etc/*` parity preserved),
  `cd`/`pushd` tracked across segments via effective_dir
  (`check_shell_path_argument` gains `base_dir`; `resolve_shell_path`
  helper); `popd`/`cd -`/bare `cd`/`(`/`{` grouping rejected as untrackable.
- config.py: `tui.statusline.{enabled,segments,command_timeout_ms}` join
  `command` in SCOPE_LOCKED_PATHS (cosmetics stay project-scope);
  `command_timeout_ms` bounded `le=60_000`.
- subprocess_env.py: scrub adds exact PRIVATE_KEY/JWT/COOKIE/BEARER +
  `_JWT`/`_COOKIE`/`_BEARER` suffixes (CSRF_TOKEN already via `_TOKEN`).
- shell: retry hard-stop keys on whitespace-normalized command
  (`_failure_key`) so padding can't mint a fresh counter.
- TaskOutput wait discipline (cffe7da6 follow-up): timeout hint reordered to
  notification-first; consecutive blocking timeouts escalate via
  `note_blocking_timeout` ("STOP waiting" at #2); a timed-out blocking
  attempt no longer resets the non-blocking "STOP polling" streak
  (deliberate contract change, test rewritten).
- Background agent task ids are codenames (`agent-tidal-wren`): the task id is
  the visible handle in TaskOutput/TaskStop headers, TaskList, and
  notifications, and single background launches never got a codename.
  `generate_task_id` mints codename ids unique against the store
  (length-guarded vs `_VALID_TASK_ID`, random fallback); bash ids unchanged
  but collision-checked.
- Docs: agents.md tool table + offline-by-design note. CHANGELOG: 11 bullets.

Deep-scan ace53ad5 triage verdicts (adversarially verified against code):
$VAR jail bypass REAL for search/traversal (cat example was design-permitted
ReadFile parity) — fixed above with the additionally-discovered absolute-glob
gap; cd bypass REAL — fixed; statusline scope gap REAL (low) — fixed;
timeout bound REAL — fixed; scrub gaps PARTIAL (overstated) — fixed; retry
normalization by-design-nit — fixed. FALSE POSITIVES rejected: usage.py fence
parsing (documented deliberate behavior, usage.py:123-126) and notification
output_path "disclosure" (the documented resume contract). Orchestration
gaps in that session (wrong scope measurement → no decomposition; no
adversarial verify; silent re-scoring; judge skipped; double-block 300s)
addressed via the §5/§8 prompt hardening + the TaskOutput contract above.

Verified: full tests/ 5201 passed / 7 skipped / 1 xfailed + tests_e2e 65
passed + make check-pythinker-code "All checks passed!" after the spec arc;
post-hardening suites green per-slice (permission 56, config 77,
subprocess_env 7, background tools+pkg 116, agent suites 100); final full
gate re-run before commit (see session log). Memory + lessons.md updated
(spec/profile consistency invariant; identity-surface triage).

### 2026-06-11 — Deep-scan report validation + robust nitpicks (parallel pass)

Validated .pythinker/reports/mythos-enhancements-deep-scan.md against the
already-fixed working tree: High $VAR + Medium cd bypass already closed;
statusline/timeout findings already locked; fence-parsing "fix" would regress
the aggregator (by-design). Locked the two tightenings with extra tests:
tests/tools/test_shell_retry_guard.py (4 tests — key normalization +
_record_failed_attempt dedup) alongside the existing scrub false-positive
guards. Verified: 35 passed (shell_bash + retry_guard + subprocess_env).

### 2026-06-11 — TUI streaming polish (parallel sessions)

- Transient red `<invalid>` flash on streaming tool calls: while args stream,
  partial-JSON repair turns key-without-value into `null` and card renderers
  flashed `<invalid>`. Central fix in `_blocks.py:_compose_card`: drop
  None-valued keys while args are incomplete so renderers show their pending
  state; finished calls with invalid args still show `<invalid>`.
  Tests: test_tool_call_block.py char-by-char streaming guards (red→green).
- Streaming redraw smoothness (macOS terminals): DEC mode 2026 synchronized
  updates — `ui/shell/sync_output.py` brackets every frame in
  `\x1b[?2026h…l` via a patched session-output flush (renderer frames +
  patch_stdout prints), gated by
  `terminal_capabilities.synchronized_output_enabled()` (TERM=dumb off;
  kill switch `PYTHINKER_NO_SYNC_OUTPUT=1`). 8 new tests; ui_and_conv 1752
  passed; PTY smoke shows BSU/ESU marks.

### 2026-06-11 — Live-session follow-ups

TaskOutput blocking-timeout retry-loop investigation (fix shipped in the
robustness arc above); distinctive RunAgents instance codenames
(subagents/codenames.py); slash-command inline ghost completion + Tab accept
(SlashCommandAutoSuggest in ui/shell/prompt.py + theme styles + key binding).

### 2026-06-11 — CodeRabbit review triage (16 findings)

Fixed (7): RunMeta.requested_base_ref → `str | None`; constant.py catches
TOMLDecodeError; prompt.py CwdLostError re-raises caught instance; prompt.py
shortstat bare-except now debug-logs; otel.py error-log sink one-shot
breadcrumb; usage.py `none observed` placeholders (+ regression test); symlink
test skips when unsupported.

Declined as false positives (evidence): 4× "subagents: null → []/{}"
(agentspec.py:60 types `dict|None|Inherit`, :128 resolves `or {}`; bare
`subagents:` is the uniform 15-spec convention; `[]` would fail pydantic);
agent.py add_shared_tools ordering (toolset.py:981 registers every connected
MCP tool on the primary toolset anyway — proposed move is a no-op); CHANGELOG
duplicate bullets (title-level scan finds zero).

### 2026-06-11 — Agent review safety + TUI hardening (`mythos-enhancements`)

Plan: docs/superpowers/plans/2026-06-11-agent-review-safety-tui-hardening-plan.md.
Landed: workspace jail for shell path args (`check_shell_path_argument` +
`shell_workspace_escape_reason` wired into `check_shell_command_allowed`,
fg+bg shared); declarative profiles (`allow_network` on PermissionProfile,
SearchWeb/FetchURL hidden AND execution-denied for review/verify/read-only,
yolo non-escalation locked by tests); secret env scrubbing for
restricted-profile shell (incl. background via TaskSpec.scrub_secrets);
bounded retry (verbatim command after 2 failures ⇒ hard denial,
review-scoped); ResolvedDiff/RunMeta `requested_base_ref`/`fallback_reason`
(loud origin/main fallback); subagent todos normalized to single in_progress;
monotonic _ToolCallBlock guards. Key decisions: jail mirrors file-tool
semantics (Glob/Grep full jail; ReadFile parity) so Shell is never stricter
than first-class tools; `_SUBAGENT_PROFILES` stays the single profile
registry. Verified then: make check ✓, review pkg 170 ✓, tests/ 5170 ✓,
tests_e2e 65 ✓; clean-code-guard pass deduplicated Shell failure-count
increment (`_record_failed_attempt`) and todo note-rebuild.

### 2026-06-11 — Default best-practices adoption (`feat/agentic-orchestration`)

`prompts/best_practices.md` upgraded to the enhanced 15-section profile (`/bp`
section parsing intact) + condensed always-on `## Default Best Practices`
baked into agents/default/system.md (inherited by all roles). Pins updated
(test_best_practices_slash.py, test_default_agent.py); docs + CHANGELOG.
Verified: targeted 46 passed, e2e wire snapshot + parity 5 passed, make check
clean. Placement after `## Engineering Discipline`; condensed bullets cover
only the delta; inline-comments rule deliberately excluded (would conflict
with system.md code-quality defaults).

### 2026-06-11 — Agentic UX enhancements (`feat/agentic-orchestration`)

`4302f457` /statusline customizable status bar (StatusLineConfig +
ui/shell/statusline.py + card-footer wiring + slash command + docs);
`fe165e59` concurrent foreground RunAgents fan-out (bounded by
background.max_running_tasks; ordering preserved; sibling-failure isolation)
+ batch_risks/batch_blockers roll-up in subagents/usage.py. Verified: full
suite 5005, tests_e2e 65, make check green. Deviations: interactive picker
deferred in favor of subcommands; customization applies to the card-footer
style. Out of scope: DAG/workflow engine; maintainer deferrals (mcpext-2(a),
obs-eval-3/4 live wiring, `lexical_recall`).

### 2026-06-11 — Clean-code-guard scan of feat/agentic-orchestration (full branch)

Scope: `git diff main` against the worktree (committed + uncommitted), ~3000
lines across 51 files. Fixed three bugs: (1) `_extract_section` stripped a
leading `-`/`*` from NON-bulleted finding lines, mangling bare `--force`/`*args`
findings — now only `- `/`* ` bullet markers strip (usage.py); (2) `/statusline`
verb parsing used `startswith`, so `/statusline commands` persisted external
command `"s"` and reloaded — now exact-verb `partition` match (ui/shell/slash.py);
(3) capped-output `proc.kill()` in `StatusLineCommandRunner._run_command` was
the only kill not wrapped in `suppress(ProcessLookupError)` — race logged as a
spurious refresh failure (statusline.py). Plus a docstring drift fix in
`_intercept_shell_command`. Regression tests added for (1) and (2). Verified
non-issues: `is_terminal_status` includes "recoverable" deliberately;
`ToolReturnValue.output` isinstance guard is real; `_rich_escape` is a local
helper; RunAgents gather doesn't swallow CancelledError. Verified: full unit
suite 5059 passed, make check-pythinker-code green.

### 2026-06-11 — Deep-scan report triage (statusline runner + findings roll-up)

Confirmed & fixed (statusline.py): refresh-loop exception guard, explicit
interval clamped to a positive floor, bounded 64KiB stdout read replaces
communicate(), sync cancel() also kills a live child process, _warn_once
dedupes per message. usage.py: _extract_section now skips fenced code blocks.
Rejected as not-issues: mid-task /statusline Reload (caught by
_run_slash_command_during_task), self-configured command exec+shlex (by
design), child output unwrapped (same-tier LLM content), BaseException
passthrough (correct). Regression tests added for every fix.

### 2026-06-11 — Per-command during-task availability for shell slash commands

`SlashCommand.available_during_task` flag; task-safe read-only commands
(/statusline, /usage, /help, /version, /agents, /changelog, /context, /tools)
run immediately mid-task via `_intercept_shell_command()` +
`shell_command_runner` hook; the rest toast "disabled while a task is in
progress". `Shell._run_slash_command_during_task` swallows Reload/Switch
mid-turn with a "saved, applies later" notice. Bare `/statusline` opens a
dismissable settings-list menu at the idle prompt; completion popup annotates
blocked-mid-run commands. Tests: test_btw.py, test_statusline_slash.py,
test_slash_completer.py; full ui_and_conv, core, utils, tests_e2e green.

### 2026-06-11 — Port upstream tool-call dedup (kimi-cli #2242 + #2372)

soul/toolset.py: canonical args, same-step result sharing, cross-step sparse
reminders (streak 3/5/8), dedup telemetry. soul/pythinkersoul.py: per-turn
reset, `begin_step` inside the step-retry wrapper, `end_step` after tool
results, D-Mail revert clears the dedup seed. 9 upstream dedup tests ported
(25 total green). Verified: full suite minus PTY e2e 4852 passed; make check
green. Skipped #2372 drive-bys (promo banner, /clear→/new alias).

### Dropped: `pythinker-cli` → `pythinker-code` rename plan (2026-05-07)

Obsolete — the rename is already fully realized: root `pyproject.toml` is
`name = "pythinker-code"`, the module is `src/pythinker_code/`, and zero
`pythinker_cli` references remain in source.

### 2026-06-11 — Bugsink noise: suppress expected user-environment errors

Triaged all 16 open issues on errors.pythinker.com (raw events archived in
tasks/bugsink_issues.json + tasks/bugsink_raw_events.json). telemetry/errors.py
gains `is_expected_error()` (cause-chain walk; 401/403/408/429/5xx, timeouts,
connection/DNS errors, OAuthError, McpError METHOD_NOT_FOUND);
`report_handled_error()` tags OTel `expected=` and skips Sentry capture for
expected ones. telemetry/crash.py asyncio handler applies the same gate;
sys.excepthook deliberately NOT gated. grep_local.py rg exec OSError (wrong
arch) now falls back to `_python_grep`. Tests: expected-error matrix,
crash-gate, rg-exec fallback. Verified: full suite 5018 passed; checks clean.
Out of scope: 400 "enable_thinking" is upstream pythinker_core compat.

### 2026-06-11 — Telemetry release sync + SigNoz pipeline & dashboard setup

constant.py `get_version()` prefers live pyproject.toml in source checkouts;
telemetry/config.py `detect_environment()` wired into sentry AND otel resource.
Infra: otel.pythinker.com had no Traefik route (404) — all client OTLP dropped
since launch; fixed with collector labels (port 4318) + redeploy, verified
end-to-end. SigNoz: product dashboard (12 panels), 5 saved views, 3 alert
rules → pythinker-admin-email. Out of scope: edge collector bearer validation;
SMTP for alert delivery.

### 2026-06-11 — Bugsink release sync (seamless)

Bugsink project renamed pythinker-cli → pythinker-code; junk releases deleted.
release workflow gains `register-bugsink-release` job POSTing
`pythinker-code@<version>` at tag time (idempotent; failures are warnings).
Secret `BUGSINK_RELEASES_TOKEN` set on the repo.

### 2026-06-11 — system.md harmonization + deep-scan fixes (`feat/agentic-orchestration`)

system.md condensing pass reviewed and harmonized (one stale cross-reference
fixed; two prompt pins updated). High fixes: `("tui","statusline","command")`
scope-locked; OTel error-log forwarding now site-only (no message body) per
the privacy posture. Medium finding already resolved by 68fb92d0. make-check
cleanup of pre-existing statusline-commit failures (import order, format
drift, pyright in test files). Final: make check exit 0; full tests/ 5142
passed. "code-reviewr" in specs is a real CLI name, not a typo.
