# Tasks

## Active

(none)

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
