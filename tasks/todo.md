# Tasks

## Active

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
