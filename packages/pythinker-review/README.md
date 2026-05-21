# pythinker-review

Agent-first code review, security review, and root-cause debugging engine for Pythinker. Standalone
CLI (`pythinker-review`, `pythinker-secscan`, `pythinker-debug`) and integration into
`pythinker-code` as the `review` / `secscan` / `debug` subcommands and the
`code-reviewer` / `security-reviewer` / `debugger` subagent roles.

## CLI

```bash
# Branch-vs-main code review
pythinker-review diff --base origin/main --format pretty

# Branch-vs-main code + security in one pass
pythinker-review diff --with-security --fail-on high

# Security-only scan, SARIF for CI
pythinker-secscan diff --format sarif --fail-on critical

# Root-cause debugger over a captured failure log
pythinker-debug failure failure.log --command "pytest tests/test_app.py::test_case"
```

## Configuration

`pythinker-review` and `pythinker-secscan` accept explicit/env model configuration. When invoked via
`pythinker review` / `pythinker secscan` / `pythinker debug`, the active Pythinker model is wired in
automatically through a `ReviewLLM` adapter.

## Persistence

Each `--save` run writes:

```text
.pythinker-review/
├── index.json
└── runs/
    └── 20260520120000-a1b2c3d4/
        ├── meta.json
        ├── findings.jsonl
        └── diff.patch
```

`.gitignore` is auto-patched idempotently on first save if a `.gitignore` file already exists.

## Phase 1

See `docs/superpowers/specs/2026-05-20-pythinker-review-foundation-design.md` for the full spec.
Future phases add whole-repo audit, external deepsec-style matchers and revalidation, PR-provider
integrations, and a fix loop.
