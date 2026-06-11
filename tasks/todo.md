# Tasks

## Active

### Agentic UX enhancements — branch `feat/agentic-orchestration`

Scope confirmed: customizable status bar + two safe, net-new subagent extras.
The planned loop/orchestration/subagent roadmap items are already merged; this
branch adds only net-new, non-conflicting work. No DAG engine. All framing
generic (no external product names in code/comments/commits/PR/docs).
Design: `docs/superpowers/specs/2026-06-11-statusline-and-agentic-extras-design.md`.

- [ ] **Slice 1 — `/statusline` customizable status bar**
  - [ ] `StatusLineConfig` under `TUIConfig` (config.py) + `PYTHINKER_STATUSLINE` env
        — acceptance: defaults reproduce today's footer exactly; round-trip + unknown-id
        drop tested.
  - [ ] `ui/shell/statusline.py` — `resolve_segments()` (pure) + lifecycle-managed
        async `StatusLineCommandRunner` (shlex argv, timeout, fail-closed, cached line).
  - [ ] Wire into both `bottom_toolbar` render paths via shared resolver (no drift);
        `enabled=False` ⇒ byte-identical legacy footer.
  - [ ] `/statusline` command (show / interactive picker / on|off / command set|none)
        + `ui/shell/selectors/statusline.py`.
  - [ ] Tests (config, resolver, command runner, command behavior) + `tests_e2e`
        handshake snapshot refresh (`--inline-snapshot=fix`) + docs section.
  - [ ] `/clean-code-guard` checkpoint → `make check-pythinker-code` → CHANGELOG bullet.
- [ ] **Slice 2 — parallel foreground `RunAgents` fan-out**
  - [ ] Concurrent children via `asyncio.gather` bounded by existing capacity guard;
        ordering preserved; one failure doesn't abort siblings; approval/overflow
        contract unchanged. Audit shared `session.state` writes first.
  - [ ] Tests (concurrency, ordering, partial failure, capacity bound) + guard +
        `/clean-code-guard` + check + CHANGELOG.
- [ ] **Slice 3 — structured `RunAgents` result synthesis**
  - [ ] Pure synthesis: per-child SUMMARY + deduped EVIDENCE/CHANGES/RISKS/BLOCKERS,
        cost preserved, free-text children tolerated (never dropped).
  - [ ] Tests (well-formed + free-text + failed child) + `/clean-code-guard` + check
        + CHANGELOG.

Out of scope (logged): DAG/workflow engine; re-doing merged roadmap items; maintainer
deferrals (mcpext-2(a), obs-eval-3/4 live wiring, `lexical_recall`).

## Recently completed

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
