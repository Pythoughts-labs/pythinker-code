# Tasks

## Active

### Default best-practices adoption — branch `feat/agentic-orchestration`

Make the engineering best-practices profile a default, not just `/bp` opt-in:
upgrade `prompts/best_practices.md` to the enhanced 15-section profile and bake
a condensed always-on summary into `agents/default/system.md` (inherited by all
roles incl. coder). All framing generic (no external product names).

- [x] Rewrite `prompts/best_practices.md` to the enhanced profile (keep `/bp`
      section parsing + pythinker tool names) — acceptance: section filter and
      heading listing still work (15 sections; verified via
      `_best_practices_section`/`_best_practices_headings`).
- [x] Add condensed `## Default Best Practices` section to
      `agents/default/system.md` (no `${...}`/template syntax) — acceptance:
      delta-focused, no duplication of Non-Negotiables/Discipline/DoD.
- [x] Update pins: `tests/core/test_best_practices_slash.py` headings+wording;
      add pins in `tests/core/test_default_agent.py` for the new section.
- [x] Docs (`slash-commands.md` `/best-practices`) + CHANGELOG entry.
- [x] Verify: targeted pytest (46 passed), e2e wire snapshot + parity (5
      passed), `make check-pythinker-code` (ruff/format/pyright clean), typos
      clean.

Review: condensed profile placed after `## Engineering Discipline` so every
role (root + coder/implementer/etc. via shared system.md) inherits it; the
condensed bullets cover only the delta vs. existing prompt sections. The
inline-comments rule stays out of the condensed set (system.md's code-quality
defaults already govern commenting and would conflict).

### Agentic UX enhancements — branch `feat/agentic-orchestration`

Scope confirmed: customizable status bar + two safe, net-new subagent extras.
The planned loop/orchestration/subagent roadmap items are already merged; this
branch adds only net-new, non-conflicting work. No DAG engine. All framing
generic (no external product names in code/comments/commits/PR/docs).
Design: `docs/superpowers/specs/2026-06-11-statusline-and-agentic-extras-design.md`.

- [x] **Slice 1 — `/statusline` customizable status bar**
  - [x] `StatusLineConfig` under `TUIConfig` (config.py) + `PYTHINKER_STATUSLINE` env
        — acceptance: defaults reproduce today's footer exactly; round-trip + unknown-id
        drop tested.
  - [x] `ui/shell/statusline.py` — `resolve_segments()` (pure) + lifecycle-managed
        async `StatusLineCommandRunner` (shlex argv, timeout, fail-closed, cached line).
  - [x] Wire into both `bottom_toolbar` render paths via shared resolver (no drift);
        `enabled=False` ⇒ byte-identical legacy footer.
  - [x] `/statusline` command (show / interactive picker / on|off / command set|none)
        + `ui/shell/selectors/statusline.py`.
  - [x] Tests (config, resolver, command runner, command behavior) + `tests_e2e`
        handshake snapshot refresh (`--inline-snapshot=fix`) + docs section.
  - [x] `/clean-code-guard` checkpoint → `make check-pythinker-code` → CHANGELOG bullet.
- [x] **Slice 2 — parallel foreground `RunAgents` fan-out**
  - [x] Concurrent children via `asyncio.gather` bounded by existing capacity guard;
        ordering preserved; one failure doesn't abort siblings; approval/overflow
        contract unchanged. Audit shared `session.state` writes first.
  - [x] Tests (concurrency, ordering, partial failure, capacity bound) + guard +
        `/clean-code-guard` + check + CHANGELOG.
- [x] **Slice 3 — structured `RunAgents` result synthesis**
  - [x] Pure synthesis: per-child SUMMARY + deduped EVIDENCE/CHANGES/RISKS/BLOCKERS,
        cost preserved, free-text children tolerated (never dropped).
  - [x] Tests (well-formed + free-text + failed child) + `/clean-code-guard` + check
        + CHANGELOG.

Out of scope (logged): DAG/workflow engine; re-doing merged roadmap items; maintainer
deferrals (mcpext-2(a), obs-eval-3/4 live wiring, `lexical_recall`).

**Review (2026-06-11):** All three slices landed on `feat/agentic-orchestration`:
`4302f457` (/statusline: StatusLineConfig + ui/shell/statusline.py + card-footer
wiring + slash command + docs) and `fe165e59` (concurrent foreground RunAgents
fan-out bounded by background.max_running_tasks + batch_risks/batch_blockers
roll-up in subagents/usage.py). Verified: full unit suite 5005 passed,
tests_e2e 65 passed, make check-pythinker-code green. Sub-checkbox statuses
covered by the per-slice commits. Deviations: statusline interactive picker
deferred — subcommands (`segments`, `on/off`, `command`) shipped instead;
customization applies to the card footer style (legacy style keeps stock
footer). Next session: open PR; CodeRabbit gate before merge.

## Recently completed

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
`_intercept_shell_command` (output shows transiently in the live area, not
above it). Regression tests added for (1) and (2). Verified non-issues:
`is_terminal_status` swap deliberately includes "recoverable" (correct — won't
progress unaided); `ToolReturnValue.output` isinstance guard is real
(`str | list[ContentPart]`); `_rich_escape` is a local `(object) -> str` helper;
RunAgents gather doesn't swallow CancelledError. Known minor non-bugs:
`_nonblocking_polls` entries linger for never-re-polled tasks (bounded);
mid-task shell-command tasks aren't cancelled at view teardown. Verified:
full unit suite 5059 passed, targeted telemetry/grep/highlight suites green
after concurrent expected-error-telemetry changes landed, make
check-pythinker-code green.

### 2026-06-11 — Deep-scan report triage (statusline runner + findings roll-up)

Confirmed & fixed (statusline.py): refresh-loop exception guard (#1), explicit
interval clamped to a positive floor (#2), bounded 64KiB stdout read replaces
communicate() (#3), sync cancel() also kills a live child process (#4),
_warn_once dedupes per message instead of one-shot (#5). usage.py:
_extract_section now skips fenced code blocks (#8). Rejected as not-issues:
#6 (Reload from mid-task /statusline is caught by _run_slash_command_during_task),
#7 (self-configured command, exec+shlex, by design), #9 (child output is
same-tier LLM content, full reports already flow unwrapped), #11 (BaseException
passthrough is correct). Regression tests added for every fix.

### 2026-06-11 — Per-command during-task availability for shell slash commands

- `utils/slashcmd.py`: `SlashCommand.available_during_task` flag (+ decorator kwarg).
- Task-safe (read-only) commands flagged: /statusline, /usage(/status), /help,
  /version, /agents, /changelog, /context, /tools.
- `visualize/_interactive.py`: `_intercept_shell_command()` replaces the blanket
  streaming block on both Enter-queue and Ctrl+S paths — flagged commands run
  immediately via a `shell_command_runner` hook (output prints above the live
  area); the rest toast "/x is disabled while a task is in progress".
- `Shell._run_slash_command_during_task` swallows Reload/Switch mid-turn with a
  "saved, applies later" notice so fire-and-forget tasks can't lose control flow.
- Tests: tests/ui_and_conv/test_btw.py (blocked + run + no-runner paths); full
  ui_and_conv, core, utils, tests_e2e green; ruff + pyright clean.
- Follow-ups done same day: bare `/statusline` now opens a dismissable
  settings-list menu at the idle prompt (Esc cancels; apply persists + reloads;
  falls back to the table mid-run since a second prompt_toolkit app can't run
  over the live view); the agent-mode completion popup annotates shell commands
  that are blocked mid-run with "disabled while a task is in progress".
  Tests: test_statusline_slash.py (menu open/apply/fallback),
  test_slash_completer.py (annotation on/off).

### 2026-06-11 — Port upstream tool-call dedup (kimi-cli #2242 + #2372)

- `soul/toolset.py`: canonical args, same-step result sharing, cross-step sparse
  reminders (streak 3/5/8), dedup telemetry.
- `soul/pythinkersoul.py`: per-turn reset, `begin_step` inside the step-retry
  wrapper, `end_step` after tool results, D-Mail revert clears the dedup seed.
- `tests/core/test_toolset.py`: 9 upstream dedup tests ported (25 total green).
- Verified: full suite minus PTY e2e 4852 passed; `make check-pythinker-code` green.
- Skipped #2372 drive-bys (Kimi Code promo banner, /clear→/new alias change).

### Dropped: `pythinker-cli` → `pythinker-code` rename plan (2026-05-07)

Obsolete — the rename is already fully realized: root `pyproject.toml` is
`name = "pythinker-code"`, the module is `src/pythinker_code/`, and zero
`pythinker_cli` references remain in source.

### 2026-06-11 — Bugsink noise: suppress expected user-environment errors

Triaged all 16 open issues on errors.pythinker.com (raw events archived in
tasks/bugsink_issues.json + tasks/bugsink_raw_events.json). Clusters: API
401/403/429/400, OAuth flow timeout/state, offline DNS, MCP method-not-found,
wrong-arch bundled rg, empty API response.

- `telemetry/errors.py`: new `is_expected_error()` (cause-chain walk; expected =
  401/403/408/429/5xx via duck-typed `status_code`, Timeout/Cancelled/Connection/
  gaierror, pythinker_core connection/timeout/empty-response errors, OAuthError,
  aiohttp ClientConnectionError, McpError METHOD_NOT_FOUND).
  `report_handled_error()` now tags OTel events `expected=` and skips Sentry
  capture for expected ones; ring buffer unchanged.
- `telemetry/crash.py`: asyncio handler applies the same gate (covers the
  unhandled McpError event); sys.excepthook intentionally NOT gated — an
  expected error escaping to process death is still a missing-handler bug.
- `tools/file/grep_local.py`: `OSError` at rg exec time ("Exec format error",
  wrong arch) now reports handled + falls back to `_python_grep` instead of
  failing the Grep tool.
- Tests: expected-error matrix in tests/telemetry/test_errors.py, crash-gate in
  test_crash.py, rg-exec fallback in tests/tools/test_grep.py.
- Verified: full suite 5018 passed / 5 skipped; ruff + format + pyright clean.

Out of scope (logged): 400 "enable_thinking restricted to True" is a provider
compat issue in pythinker_core's openai_legacy (external package) — Bugsink
will keep reporting it (4xx_client stays unexpected), which is desired until
fixed upstream.

### 2026-06-11 — Telemetry release sync + SigNoz pipeline & dashboard setup

App-side (this repo):
- `constant.py`: `get_version()` now prefers live pyproject.toml in a source
  checkout (editable dist-info goes stale between uv syncs → events were
  attributed to old releases, e.g. 0.40.0 while pyproject said 0.40.1).
- `telemetry/config.py`: `detect_environment()` — PYTHINKER_ENV wins, source
  checkout → "development", else "production". Wired into sentry.init AND
  otel resource (deployment.environment was hardcoded "production").
- Tests in test_sentry_filters.py; startup-imports test updated (metadata now
  only the wheel/PyInstaller fallback). Full suite 5022 passed.

Infra (Dokploy/SigNoz — not in this repo):
- ROOT CAUSE: otel.pythinker.com had no Traefik route (404) — all client OTLP
  was dropped since launch. Fixed by adding traefik labels for otel-collector
  (port 4318) to the signoz compose + redeploy; domain record alone does not
  generate routing. Verified logs/metrics/traces ingest 200 end-to-end; live
  clients appeared immediately.
- SigNoz now has: dashboard "Pythinker — Product Overview" (12 panels), 5
  saved views (logs: all events / handled errors / crashes; traces: agent
  turns / slow LLM calls), 3 alert rules (API error spike, tool failure
  spike, ingest stalled) → channel pythinker-admin-email.

Out of scope (logged): the edge collector does not validate the bearer token
(any OTLP POST is accepted); SMTP for the email channel may need configuring
in SigNoz for alert delivery.

### 2026-06-11 — Bugsink release sync (seamless)

- Bugsink project renamed pythinker-cli → pythinker-code; junk releases
  (1.0.0-smoke, 1.0.0, manual-probe, 2.4.0) deleted via `ssh vps` +
  `bugsink-manage shell` → "Resolved in latest" now shows 0.40.1.
- `.github/workflows/release-pythinker-cli.yml`: new `register-bugsink-release`
  job (needs validate+release) POSTs `pythinker-code@<version>` to the Bugsink
  releases API at tag time — "resolved in next release" flips when the release
  ships, not when its first error arrives. Idempotent (400 "already exists" is
  success); failures are warnings, never release blockers.
- Secret `BUGSINK_RELEASES_TOKEN` set on Pythoughts-labs/pythinker-code
  (dedicated token "github-actions release sync" in Bugsink Tokens page).

### 2026-06-11 — system.md harmonization + deep-scan fixes (`feat/agentic-orchestration`)

Reviewed the uncommitted `agents/default/system.md` condensing pass against the
codebase and resolved the deep-code-scan findings
(`.pythinker/reports/deep-code-scan-feat-agentic-orchestration.md`).

- [x] system.md diff review — internally consistent (`§N` style throughout,
      §7→§6 security-hygiene move lossless, §3 absorbs the old escalation
      list). Harmonized the one stale cross-reference:
      `code_reviewer.yaml` "base Section 8" → "base §8".
- [x] Updated the two stale prompt pins to the new wording:
      `test_load_agent.py` ("Minimum packet before any codebase judgment"),
      `test_default_agent.py` ("Never game it: no weakened or deleted
      assertions"). All other pins still match.
- [x] High fix: `("tui", "statusline", "command")` scope-locked in
      `config.py` (+2 tests, red→green). `/statusline` unaffected (writes
      user-scope `config.source_file`).
- [x] High fix: OTel error-log forwarding now site-only
      (module/function/line + exc_class, no message body) per the
      `telemetry/errors.py` privacy posture; test rewritten to assert
      wire-controlled content never reaches the exporter.
- [x] Medium finding verified already resolved by 68fb92d0 (add_shared_tools
      + turn-start MCP wait + existing focused test); resolution appended to
      the scan report.
- [x] Verify: make check-pythinker-code clean; focused suites green; full
      tests/ run (see session summary). tests_e2e skipped — no e2e file
      references the changed surfaces.

Review: smallest-diff approach throughout; the system.md edit itself was the
user's and is sound — observations: §5 no longer enumerates the `review` role
and the judge-gate trigger list dropped ".pythinker/reports/ saved" (both
benign: the Agent tool advertises all subagent types dynamically, and the
remaining triggers cover findings reports). "code-reviewr" in specs is a real
CLI name, not a typo — left untouched.
- [x] make-check cleanup (pre-existing, statusline commits): import order/E402
      in `test_soul_status_cost.py` + `test_statusline_render.py`; ruff format
      drift in `config.py`, `test_config.py`, `test_statusline.py`,
      `test_statusline_slash.py`; pyright errors in `test_statusline_render.py`
      (typed `make_ctx` via `dataclasses.replace`, None-guards, raising segment
      stub) and `test_config.py` (`model_validate` for invalid-literal case).
      Final: `make check-pythinker-code` exit 0; full tests/ 5142 passed.
