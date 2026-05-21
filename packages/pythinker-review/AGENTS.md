# Pythinker Review Agent Instructions

These instructions apply to all files under `packages/pythinker-review/`.

## Package mission

`pythinker-review` is the standalone code review, security review, debug review, PR artifact, and
Reviewflow stateful workflow engine. It is used directly through `pythinker-review`,
`pythinker-secscan`, `pythinker-security-scan`, and `pythinker-debug`, and indirectly through the
root `pythinker review`, `pythinker secscan`, `pythinker security-scan`, and `pythinker debug`
wrappers.

## Commands

Use `uv` from the package directory for direct checks:

```bash
uv run --directory packages/pythinker-review ruff check
uv run --directory packages/pythinker-review ruff format --check
uv run --directory packages/pythinker-review pyright
uv run --directory packages/pythinker-review pytest tests -vv
```

Preferred repo-level gates:

```bash
make check-pythinker-review
make test-pythinker-review
```

## Architecture map

- `src/pythinker_review/cli/review.py`: main Typer CLI. Hosts diff review, saved finding
  inspection, read-only PR artifact commands, and Reviewflow stateful workflow commands.
- `src/pythinker_review/cli/secscan.py` and `cli/debug.py`: security-only and failure-debug entry
  points sharing the review engine.
- `src/pythinker_review/engine/`: diff resolution, structured diff rendering, chunking, orchestration,
  runner concurrency, artifact context, and token-budget helpers.
- `src/pythinker_review/reviewers/`: reviewer passes, strict schemas, JSON completion helpers,
  finding validation, read-only artifact runners, compliance loading, and prompt files.
- `src/pythinker_review/signals/`: deterministic security signal models, scanning, technology
  detection, and Pythinker Security Scan advisor context.
- `src/pythinker_review/output/`: pretty, JSON, SARIF, and PR artifact renderers.
- `src/pythinker_review/store/`: `.pythinker-review/` run metadata, findings, run IDs, and gitignore
  support.
- `src/pythinker_review/diagnostics/`: bounded failure-log parsing and secret redaction.
- `src/pythinker_review/reviewflow/`: pure-Python Reviewflow state models, state IO,
  heuristic feature mapping, provider prompts, reporting, utilities, and workflow orchestration.
- `tests/unit/`: focused unit tests for schemas, runners, signals, validation, artifacts, Reviewflow,
  diagnostics, outputs, and stores.
- `tests/e2e/`: CLI behavior tests for review/secscan/debug, artifact commands, saved findings, and
  Reviewflow workflow/fix flows.

## Hard rules

- Keep model-facing behavior fail-closed. Malformed JSON, schema validation failures, timeout errors,
  missing base refs, and evidence-validation failures must be surfaced, not silently accepted.
- Findings must be anchored to reviewed evidence. Keep path, hunk-line, and evidence-snippet
  validation strict; reject absolute/traversal/.git paths and findings outside the reviewed chunk or
  feature.
- Preserve read-only semantics for normal diff review, security review, debug review, deslopify, and
  PR artifact/helper commands (`describe`, `suggest`/`improve`, `ask`, `ask-line`, `labels`,
  `changelog`, `docs`, `compliance`, `help-docs`, `similar-issues`, `tools`, `config`).
- Treat `fix` and `open-pr` as explicit mutating Reviewflow workflow commands only. Do not route normal
  review or artifact requests into them.
- Never commit runtime state from `.pythinker-review/` or `.pythinker-review-flow/`.
- Never print or persist secrets. Keep diagnostic log redaction and security prompts conservative.
- Do not add provider publishing/commenting side effects to PR artifact commands without explicit
  maintainer approval.

## When changing public behavior

- CLI options or command names: update `cli/review.py`, package README/docs, wrapper tests under
  root `tests/cli/`, and the Pythinker wrapper in `src/pythinker_code/cli/review.py` if the integrated
  command surface changes.
- Code-reviewer subagent behavior: update `src/pythinker_code/agents/default/code_reviewer.yaml` and
  prompt-loading tests in the root package.
- Output schema changes: update Pydantic models in `reviewers/schema.py` or `reviewers/artifacts.py`,
  renderers, prompts, and unit/e2e snapshots/assertions together.
- Security-signal changes: update `signals/models.py`, `signals/scanner.py`, `signals/advisor.py`,
  `signals/tech.py`, security prompts, and `tests/unit/test_signals.py`.
- Reviewflow workflow changes: update `reviewflow/models.py`, `state.py`, `workflow.py`, `provider.py`,
  `reporting.py`, and the workflow/fix e2e tests together.

## Prompt and schema discipline

- Prompt files live under `src/pythinker_review/reviewers/prompts/`.
- Prompts should demand strict JSON only, no Markdown fences, concrete evidence, minimum fix scope,
  test analysis, and no speculative findings.
- If a prompt asks for new fields, add them to the relevant Pydantic model and tests in the same
  change.
- Keep artifact prompts read-only and framed as drafts/plans, not instructions to mutate files or post
  to providers.
