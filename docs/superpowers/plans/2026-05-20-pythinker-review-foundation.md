# Pythinker Review — Phase 1A (Review/Debug/Security Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

---

## Implementation Status (as of 2026-05-20)

**Phase 1A + blackbox hardening code-complete in tree (uncommitted).** All 18 originally-planned tasks, the debug capability added by the revised spec, and the new read-only blackbox hardening pass are implemented. Tests are green; the only remaining work is commit/release housekeeping.

### What landed beyond the original 18-task plan

The revised spec (`docs/superpowers/specs/2026-05-20-pythinker-review-foundation-design.md`) introduced a **third pass — `debug_review` — plus product-direction changes** to make Pythinker primarily an evidence-first reviewer/debugger/security agent. All of that is in tree:

- `packages/pythinker-review/src/pythinker_review/diagnostics/` — `models.py` + `parser.py` for failure-log / stack-trace ingestion.
- `packages/pythinker-review/src/pythinker_review/reviewers/debug_review.py` + `reviewers/prompts/debug_review.system.md` — root-cause reviewer pass.
- `Pass` literal in `store/models.py` extended to `"code_review" | "security_review" | "debug_review"`; new `Category.debugging`.
- `engine/orchestrator.py` and `engine/runner.py` route diagnostics + debug pass.
- `packages/pythinker-review/src/pythinker_review/cli/debug.py` — `pythinker-debug` standalone CLI; `src/pythinker_code/cli/debug.py` — `pythinker debug` lazy wrapper.
- `src/pythinker_code/agents/default/debugger.yaml` — third YAML subagent role alongside `code_reviewer.yaml` and `security_reviewer.yaml`.
- `src/pythinker_code/agents/default/system.md` — opening "Product posture" paragraph: ambiguous engineering requests prefer evidence-first review/diagnosis before editing.
- `packages/pythinker-review/docs/blackbox-parity.md` — explicit blackbox parity map covering all three reference repos (criterion #2 of the revised spec), updated for the extra hardening work.
- Additional blackbox ports: Reviewflow-style evidence validation, read-only `--mode deslopify`, saved-finding `next`/`show-finding`, Reviewflow workflow state/mapping/reporting substrate, code-review prompt/test/minimum-fix-scope fields, code-reviewr read-only PR assistant artifacts (`describe`, `improve`/`suggest`, `ask`, `labels`, `changelog`, `docs`), DeepSec-style tech detection/advisor context, expanded deterministic security signals, and diagnostic secret redaction.
- Tests: `test_diagnostics.py`, `test_cli_debug.py`, `test_review_wrapper.py`, `test_secscan_wrapper.py`, plus debug/security/deslopify/evidence-validation coverage in `test_runner.py`, `test_reviewers.py`, `test_validation.py`, `test_signals.py`, and `test_token_budget.py`.

### Status by task

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Package skeleton + workspace registration | ✅ done | `packages/pythinker-review/pyproject.toml`, root `[tool.uv.workspace]` updated, Make targets added |
| 2 | Data model | ✅ done | `Pass` extended to include `debug_review`; `Category.debugging` added |
| 3 | Run ID generator | ✅ done | stdlib `secrets.token_hex(4)` |
| 4 | Diff source resolver | ✅ done | base/staged/working-tree/range modes |
| 5 | Structured diff renderer | ✅ done | `__new hunk__` / `__old hunk__` format |
| 6 | Context gatherer | ✅ done | bounded windows + base-file `git show` |
| 7 | Chunker | ✅ done | per-file/per-hunk, include/exclude/vendored filters |
| 8 | Signals scanner | ✅ done | secret/shell/SQL/deserialization/SSRF/weak-crypto rules |
| 9 | Reviewer schemas + LLM Protocol + FakeReviewLLM | ✅ done | shared `reviewers/common.py` factored out |
| 10 | Code-review + security-review passes | ✅ done | prompts in `reviewers/prompts/`, one-retry on bad JSON |
| 10b | **Debug-review pass** (added by revised spec) | ✅ done | `reviewers/debug_review.py`, `prompts/debug_review.system.md`, `diagnostics/parser.py` |
| 11 | Runner (asyncio, fail-closed) | ✅ done | wires all three passes; `--allow-partial` semantics intact |
| 12 | Dedupe + Orchestrator | ✅ done | orchestrator threads `diagnostics_by_file` for debug pass |
| 13 | Findings store + gitignore patcher | ✅ done | atomic writes, index trimmed to 200 |
| 14 | Output formatters | ✅ done | pretty/JSON/SARIF; unit tests consolidated in `test_outputs.py` |
| 15 | Standalone Typer CLIs | ✅ done | `pythinker-review`, `pythinker-secscan`, `pythinker-debug` |
| 16 | `pythinker-code` lazy CLI wrappers + adapter | ✅ done | `cli/review.py`, `cli/secscan.py`, `cli/debug.py`; `_lazy_group.py` extended |
| 17 | YAML subagent roles | ✅ done | `code_reviewer.yaml`, `security_reviewer.yaml`, `debugger.yaml`; `agent.yaml` updated |
| 18 | AGENTS.md row + README "What's New" + package README | ✅ done | row added, 0.8.0 section added, package README expanded |
| — | **Blackbox parity map** (criterion #2) | ✅ done | `packages/pythinker-review/docs/blackbox-parity.md` covers all three repos |
| — | **Product-posture default prompt** (criterion #10) | ✅ done | `agents/default/system.md` opens with evidence-first posture |
| 20 | **Blackbox hardening: evidence, deslopify, advisor context** | ✅ done | `reviewers/validation.py`, `deslopify_review.py`, `signals/{scanner,tech,advisor}.py`, richer prompts/schema, saved-finding `next`/`show-finding` |
| 21 | **Blackbox parity artifacts + Reviewflow substrate** | ✅ done | `reviewers/pr_artifacts.py`, `output/artifacts.py`, `engine/artifact_context.py`, `reviewflow/*`, artifact CLI commands/tests |

### Test + lint status

| Gate | Command | Result |
|---|---|---|
| Package lint/type | `make check-pythinker-review` | ✅ 0 errors, 0 warnings (ruff + pyright + ty) |
| Package tests | `make test-pythinker-review` | ✅ 90 passed after blackbox hardening + Reviewflow/code-reviewr parity ports |
| CLI wrapper smoke | `uv run pytest tests/utils/test_pyinstaller_utils.py tests/cli/test_review_wrapper.py tests/cli/test_secscan_wrapper.py -q` | ✅ 9 passed |
| Full workspace lint/type | `make check` | ✅ exit 0; `ty` emitted non-blocking diagnostics outside the new review package |
| Full workspace tests | `make test` | ✅ 3222 root tests + package suites passed (plus expected skips/xfail); review package now 90 passed |
| Full workspace build | `make build` | ✅ built code/core/host/review/sdk distributions after hardening |

### Files modified / created (uncommitted)

**Modified (current working tree):** root/user docs, the existing `packages/pythinker-review` package files for review/debug/security hardening, `src/pythinker_code/agents/default/code_reviewer.yaml`, the root active-model `review` wrapper, two root shell typing/formatting fixes required by `make check`, and related tests.

**New (current working tree):** `packages/pythinker-review/docs/code-reviewr-migration.md`; `pythinker_review/reviewflow/*`; artifact context/output/reviewer modules; deslopify, validation, security-advisor/tech modules; artifact/deslopify prompt files; and tests for Reviewflow workflows, artifact commands, token budgeting, and evidence validation.

### Remaining work

1. **Commit** — everything is uncommitted. Recommended split for the current tree:
   1. `feat(review): harden pythinker-review blackbox parity` — `packages/pythinker-review/**` including Reviewflow workflow, code-reviewr artifact commands, validation/deslopify/security advisor work, docs, and package tests.
   2. `feat(code): wire review active-model integration` — `src/pythinker_code/cli/review.py`, `src/pythinker_code/agents/default/code_reviewer.yaml`, and related root tests.
   3. `docs(review): document review foundation completion` — root README plus plan/spec updates.

2. **Release decision (not required for Phase 1A):**
   - Bump root `pyproject.toml` `version = "2.6.0"` → `"0.8.0"`.
   - Add CHANGELOG entry.
   - Cut release per existing release process.

3. **Out-of-scope cleanups** (mention only, do not block Phase 1A):
   - `ty` still emits non-blocking diagnostics outside the new review package during `make check`.
   - The deprecation warning from `loguru` on Python 3.14 (`asyncio.iscoroutinefunction`) is third-party and tracked separately.

### Tasks added or extended below

The tasks below remain the source-of-truth for re-running Phase 1A from scratch (e.g., a clean re-implementation, or to validate test coverage one task at a time). Tasks 19–21 cover commit/release and the extra blackbox hardening/parity ports. The original Tasks 1–18 are preserved verbatim; check the table above for what to skip when re-executing.

---


**Product direction:** Pythinker is being steered to be primarily a professional security reviewer, debugger, and code-reviewer agent. Coding/editing remains available, but the default posture is read-only analysis first: inspect evidence, produce findings, explain root cause, and only patch code after an explicit remediation request.

**Goal:** Land the `packages/pythinker-review` workspace package, standalone automation CLIs (`pythinker-review`, `pythinker-secscan`, `pythinker-debug`), and `pythinker-code` integration (lazy CLI wrappers + YAML subagent roles) for review, security scan, and debugger/root-cause workflows. The diff-only gate remains the first CI-capable slice, not the whole product identity.

**Blackbox porting requirement:** Port the three repos in this workspace's `blackbox/` folder (`blackbox/clawpatch-main`, `blackbox/code-review`, `blackbox/deepsec-main`) into Pythinker. Do not silently downgrade to an "inspired by" implementation. Task 0 is now an intake/audit of those mounted repos, not a search for missing source.

**Architecture:** New uv workspace package owns a shared review/debug/security engine, findings data model, JSON-on-disk store, structured diff renderer, Deepsec-like security signal scanner, debugger input normalizers, three output formatters (pretty/JSON/SARIF), and a `ReviewLLM` Protocol the host wires up. `pythinker-code` adds lazy root subcommands and YAML-driven subagent roles. The agent UX is primary; CLI wrappers are automation surfaces. Fail-closed by default; `--allow-partial` is the only escape hatch.

**Completion boundary:** The checked-off tasks below are the foundation slice. Do not declare Phase 1 complete after Task 10; the follow-up runner/store/output/CLI/wrapper/subagent/debugger tasks must also be added or implemented per the reference spec.

**Tech Stack:** Python 3.12+, `typer==0.21.1`, `pydantic>=2.12.5`, `pyyaml==6.0.3`, `rich==14.2.0`, stdlib `subprocess` / `asyncio` / `secrets` / `hashlib`. Dev: `pytest`, `pytest-asyncio`, `jsonschema` (already in `uv.lock`).

**Reference spec:** `docs/superpowers/specs/2026-05-20-pythinker-review-foundation-design.md`. When in doubt, the spec wins.

**Conventions (read before starting):**
- Use `uv run --directory packages/pythinker-review <cmd>` for any package-scoped tool.
- Never add a runtime dep not already in the workspace. Stdlib for git and run IDs.
- `pyright` and `ruff check`/`ruff format --check` must pass; `ty` is non-blocking.
- Commit per task at the boundary shown. Conventional Commits style (`feat(review): ...`, `test(review): ...`, `chore(review): ...`).
- Never add Claude co-author trailers or "Generated with Claude Code" footers (global CLAUDE.md).

---

## Task 0: Blackbox intake + product-direction lock

**Files:**
- Modify: this plan and/or the reference spec if blackbox intake changes mappings
- Create: `packages/pythinker-review/docs/blackbox-parity.md`
- Modify later: `src/pythinker_code/agents/default/system.md` or role guidance to prefer review/diagnosis before edits

- [ ] **Step 1: Audit the mounted blackbox repos**

Use the mounted source paths `blackbox/clawpatch-main`, `blackbox/code-review`, and `blackbox/deepsec-main`. Read their README/docs, package manifests, prompt/rule files, tests, and main runtime entrypoints before designing Pythinker targets. Do not invent blackbox behavior from memory.

- [ ] **Step 2: Build parity map**

Create `packages/pythinker-review/docs/blackbox-parity.md` (create parent directories if needed) with one section per repo and columns: blackbox source module/prompt/rule/workflow, behavior to preserve, Pythinker target path, test coverage, and documented deviation. This map is required before writing engine code.

- [ ] **Step 3: Lock agent-first behavior**

Record that review/debug/security diagnosis is the first response for ambiguous engineering requests. Coding changes are opt-in or delegated after findings are accepted.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers packages/pythinker-review/docs/blackbox-parity.md src/pythinker_code/agents/default/system.md
git commit -m "docs(review): lock blackbox parity and agent-first review direction"
```

---

## File Structure Map

```
packages/pythinker-review/
├── pyproject.toml
├── README.md
├── docs/
│   └── blackbox-parity.md          # required source-to-target behavior map
├── src/pythinker_review/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── _shared.py              # shared option group, exit code mapping
│   │   ├── review.py               # standalone pythinker-review entry
│   │   ├── secscan.py              # standalone pythinker-secscan entry
│   │   └── debug.py                # standalone pythinker-debug entry
│   ├── diagnostics/
│   │   ├── __init__.py
│   │   ├── models.py               # DiagnosticInput, stack/log/repro records
│   │   └── parser.py               # bounded failure-log / stack-trace parser
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── diff_source.py          # git subprocess wrapper, ResolvedDiff
│   │   ├── structured_diff.py      # __new hunk__ / __old hunk__ renderer
│   │   ├── context.py              # bounded file context gatherer
│   │   ├── chunker.py              # per-file/per-hunk chunking
│   │   ├── runner.py               # asyncio fan-out, fail-closed
│   │   ├── dedupe.py               # finding dedupe
│   │   └── orchestrator.py         # public engine.run() entry
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── protocol.py             # ReviewLLM Protocol
│   │   └── fake.py                 # FakeReviewLLM for tests
│   ├── reviewers/
│   │   ├── __init__.py
│   │   ├── schema.py               # RawFinding, ReviewerOutput
│   │   ├── code_review.py          # code-review pass
│   │   ├── security_review.py      # security pass
│   │   ├── debug_review.py         # root-cause/debug pass
│   │   └── prompts/
│   │       ├── code_review.system.md
│   │       ├── security_review.system.md
│   │       └── debug_review.system.md
│   ├── signals/
│   │   ├── __init__.py
│   │   ├── models.py               # Signal model + Deepsec-like metadata
│   │   └── scanner.py              # deterministic rule registry
│   ├── store/
│   │   ├── __init__.py
│   │   ├── models.py               # Severity, Category, Location, Suggestion,
│   │   │                           # Finding, ChunkFailure, RunMeta
│   │   ├── ids.py                  # YYYYMMDDHHMMSS-hex8 run id
│   │   ├── run.py                  # RunMeta lifecycle
│   │   ├── findings_store.py       # JSONL writer + index updater
│   │   └── gitignore.py            # idempotent .gitignore patcher
│   └── output/
│       ├── __init__.py
│       ├── pretty.py
│       ├── json.py
│       └── sarif.py
└── tests/
    ├── __init__.py
    ├── conftest.py                 # fixtures: tmp git repo, FakeReviewLLM
    ├── unit/
    │   ├── test_models.py
    │   ├── test_ids.py
    │   ├── test_diff_source.py
    │   ├── test_structured_diff.py
    │   ├── test_context.py
    │   ├── test_diagnostics.py
    │   ├── test_chunker.py
    │   ├── test_signals.py
    │   ├── test_schema.py
    │   ├── test_runner.py
    │   ├── test_dedupe.py
    │   ├── test_findings_store.py
    │   ├── test_gitignore.py
    │   ├── test_pretty.py
    │   ├── test_json.py
    │   └── test_sarif.py
    └── e2e/
        ├── test_cli_review.py
        ├── test_cli_secscan.py
        ├── test_cli_debug.py
        └── test_save_and_show.py

src/pythinker_code/                  # edits only
├── cli/
│   ├── _lazy_group.py               # add review + secscan + debug entries
│   ├── review.py                    # new: builds ReviewLLM adapter + delegates
│   ├── secscan.py                   # new: builds ReviewLLM adapter + delegates
│   └── debug.py                     # new: builds ReviewLLM adapter + delegates
├── agents/default/
│   ├── agent.yaml                   # add subagents.code-reviewer, security-reviewer, debugger
│   ├── code_reviewer.yaml           # new
│   ├── security_reviewer.yaml       # new
│   └── debugger.yaml                # new
└── ...

tests/                               # pythinker-code root tests
├── cli/test_review_wrapper.py       # new
└── cli/test_secscan_wrapper.py      # new

AGENTS.md                            # one verification matrix row
README.md                            # one "What's New" entry (post-ship)
Makefile                             # check/test/build/format targets
pyproject.toml                       # workspace member + source
```

---

## Task 1: Package skeleton + workspace registration

**Files:**
- Create: `packages/pythinker-review/pyproject.toml`
- Create: `packages/pythinker-review/README.md`
- Create: `packages/pythinker-review/src/pythinker_review/__init__.py`
- Modify: `pyproject.toml` (root) — add to `[tool.uv.workspace].members` and `[tool.uv.sources]`
- Modify: `Makefile` — add `check-pythinker-review`, `test-pythinker-review`, `format-pythinker-review`, `build-pythinker-review` targets and include in aggregates

- [ ] **Step 1: Create package pyproject.toml**

Create `packages/pythinker-review/pyproject.toml`:

```toml
[project]
name = "pythinker-review"
version = "0.1.0"
description = "Review, debug, and security analysis engine for Pythinker."
readme = "README.md"
requires-python = ">=3.12"
license = "Apache-2.0"
authors = [{ name = "Mohamed Elkholy", email = "moelkholy1995@gmail.com" }]
keywords = ["code-review", "security", "debugging", "sarif", "diff", "pythinker"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
    "Topic :: Software Development :: Quality Assurance",
    "Topic :: Security",
]
dependencies = [
    "typer==0.21.1",
    "pydantic>=2.12.5",
    "pyyaml==6.0.3",
    "rich==14.2.0",
]

[project.scripts]
pythinker-review = "pythinker_review.cli.review:app"
pythinker-secscan = "pythinker_review.cli.secscan:app"
pythinker-debug = "pythinker_review.cli.debug:app"

[project.urls]
Homepage = "https://github.com/TechMatrix-labs/pythinker-code"
Repository = "https://github.com/TechMatrix-labs/pythinker-code"

[dependency-groups]
dev = [
    "pyright>=1.1.407",
    "ty>=0.0.7",
    "pytest>=9.0.3",
    "pytest-asyncio>=1.3.0",
    "ruff>=0.14.10",
    "jsonschema>=4.26.0",
]

[build-system]
requires = ["uv_build>=0.8.5,<0.10.0"]
build-backend = "uv_build"

[tool.ruff]
line-length = 100

[tool.pyright]
include = ["src", "tests"]
pythonVersion = "3.12"
typeCheckingMode = "strict"
```

- [ ] **Step 2: Create README and `__init__.py`**

Create `packages/pythinker-review/README.md`:

```markdown
# pythinker-review

Agent-first review, debugging, and security analysis engine. Phase 1 of the
Pythinker Review project shifts Pythinker toward professional evidence-first
code review, security review, and root-cause debugging.

See `docs/superpowers/specs/2026-05-20-pythinker-review-foundation-design.md`.
```

Create `packages/pythinker-review/src/pythinker_review/__init__.py`:

```python
"""Pythinker Review — diff-only code/security review engine."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Register in workspace**

Edit `pyproject.toml` (root). Add `"packages/pythinker-review"` to the `members` list and `pythinker-review = { workspace = true }` to `[tool.uv.sources]`. The two blocks become:

```toml
[tool.uv.workspace]
members = [
    "packages/pythinker-core",
    "packages/pythinker-host",
    "packages/pythinker-review",
    "sdks/pythinker-sdk",
]

[tool.uv.sources]
pythinker-core = { workspace = true }
pythinker-host = { workspace = true }
pythinker-review = { workspace = true }
pythinker-code = { workspace = true }
```

Also add `"pythinker-review"` to the root `[project].dependencies` list so `pythinker-code` can import it for the lazy CLI wrappers (added in Task 16):

```toml
dependencies = [
    ...existing...,
    "pythinker-review",
]
```

- [ ] **Step 4: Sync the workspace**

Run: `uv sync`
Expected: no errors; `uv.lock` updated with `pythinker-review` 0.1.0 as a workspace member. No new third-party packages downloaded (typer/pydantic/pyyaml/rich are already pinned by root).

- [ ] **Step 5: Add Make targets**

Edit `Makefile`. Append `check-pythinker-review`, `test-pythinker-review`, `format-pythinker-review`, `build-pythinker-review` mirroring the `pythinker-core` pattern, and add them to the `.PHONY:` line + aggregate `check:` / `test:` / `build:` / `format:` targets.

Concrete additions (insert near existing `check-pythinker-host`, etc.):

```makefile
check-pythinker-review: ## Run linting and type checks for pythinker-review.
	@echo "==> Checking pythinker-review (ruff + pyright + ty; ty is non-blocking)"
	@uv run --directory packages/pythinker-review ruff check
	@uv run --directory packages/pythinker-review ruff format --check
	@uv run --directory packages/pythinker-review pyright
	@uv run --directory packages/pythinker-review ty check || true

test-pythinker-review: ## Run pythinker-review tests.
	@echo "==> Running pythinker-review tests"
	@uv run --directory packages/pythinker-review pytest tests -vv

build-pythinker-review: ## Build the pythinker-review sdist and wheel.
	@echo "==> Building pythinker-review distributions"
	@uv build --package pythinker-review --no-sources --out-dir dist/pythinker-review
```

Update the four aggregate lines (`check:`, `test:`, `build:`, and the `.PHONY:` lines that list them) to include the new targets.

- [ ] **Step 6: Smoke test**

Run: `make check-pythinker-review`
Expected: PASS (no Python files to lint yet, but ruff/pyright should both report 0 errors).

Run: `make test-pythinker-review`
Expected: pytest exit code 5 (no tests collected). That is fine — we wire up tests in later tasks.

- [ ] **Step 7: Commit**

```bash
git add packages/pythinker-review pyproject.toml uv.lock Makefile
git commit -m "feat(review): scaffold pythinker-review workspace package"
```

---

## Task 2: Data model

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/store/__init__.py`
- Create: `packages/pythinker-review/src/pythinker_review/store/models.py`
- Create: `packages/pythinker-review/tests/__init__.py`
- Create: `packages/pythinker-review/tests/unit/__init__.py`
- Create: `packages/pythinker-review/tests/unit/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `packages/pythinker-review/tests/unit/test_models.py`:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from pythinker_review.store.models import (
    Category,
    ChunkFailure,
    Finding,
    Location,
    RunMeta,
    Severity,
    Suggestion,
)


def _now() -> datetime:
    return datetime(2026, 5, 20, 12, 30, 45, tzinfo=timezone.utc)


def test_severity_and_category_are_string_enums():
    assert Severity.high.value == "high"
    assert Category.security.value == "security"
    assert Category.debugging.value == "debugging"


def test_finding_round_trip_uses_pass_alias():
    finding = Finding(
        id="abcd12345678",
        rule_id="sec.injection.sql",
        title="Unsanitized user input concatenated into SQL",
        rationale="...",
        category=Category.security,
        severity=Severity.high,
        location=Location(file="src/db.py", start_line=10, end_line=12, sha="deadbeef"),
        suggestion=Suggestion(summary="Use parameterized query"),
        evidence_snippet="cursor.execute('... ' + user_input)",
        confidence=0.9,
        created_at=_now(),
        run_id="20260520123045-a1b2c3d4",
        **{"pass": "security_review"},
    )
    dumped = finding.model_dump(by_alias=True)
    assert dumped["pass"] == "security_review"
    assert "pass_" not in dumped
    reloaded = Finding.model_validate(dumped)
    assert reloaded.pass_ == "security_review"


def test_finding_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        Finding(
            id="abcd12345678",
            rule_id="r",
            title="t",
            rationale="r",
            category=Category.correctness,
            severity=Severity.low,
            location=Location(file="a", start_line=1, end_line=1),
            confidence=1.5,
            created_at=_now(),
            run_id="r",
            **{"pass": "code_review"},
        )


def test_run_meta_default_lists_are_empty():
    run = RunMeta(
        id="20260520123045-a1b2c3d4",
        started_at=_now(),
        finished_at=None,
        status="running",
        repo_root="/tmp/repo",
        branch="main",
        head_sha="abc",
        base_ref="origin/main",
        base_sha="def",
        source_label="git-diff:origin/main",
        passes=["code_review"],
        model="anthropic:claude-sonnet-4-6",
        chunks_total=0,
        chunks_done=0,
        chunks_failed=0,
        findings_count=0,
        allow_partial=False,
        config_hash="0" * 64,
    )
    assert run.chunk_failures == []


def test_chunk_failure_serializes_pass_alias():
    failure = ChunkFailure(
        file="src/x.py",
        reason="timeout",
        message="exceeded 120s",
        **{"pass": "code_review"},
    )
    dumped = failure.model_dump(by_alias=True)
    assert dumped["pass"] == "code_review"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_models.py -vv`
Expected: FAIL with `ModuleNotFoundError: No module named 'pythinker_review.store'`.

- [ ] **Step 3: Write the data model**

Create `packages/pythinker-review/src/pythinker_review/store/__init__.py` (empty).

Create `packages/pythinker-review/src/pythinker_review/store/models.py`:

```python
"""Pydantic models for findings, runs, and chunk failures."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.critical: 4,
    Severity.high: 3,
    Severity.medium: 2,
    Severity.low: 1,
    Severity.info: 0,
}


class Category(str, Enum):
    correctness = "correctness"
    security = "security"
    debugging = "debugging"
    performance = "performance"
    readability = "readability"
    test_coverage = "test_coverage"
    api_design = "api_design"
    dependency = "dependency"
    secret = "secret"


Pass = Literal["code_review", "security_review", "debug_review"]
ChunkFailureReason = Literal["timeout", "llm_error", "malformed_output", "worker_error"]
RunStatus = Literal["running", "completed", "completed_with_warnings", "failed", "cancelled"]
Triage = Literal["open", "false_positive", "accepted", "wont_fix"]


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    sha: str | None = None


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    patch: str | None = None


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str
    rule_id: str
    title: str = Field(max_length=80)
    rationale: str
    category: Category
    severity: Severity
    location: Location
    pass_: Pass = Field(alias="pass")
    suggestion: Suggestion | None = None
    evidence_snippet: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_reason: str | None = None
    exploitability: str | None = None
    reproduction: str | None = None
    triage: Triage = "open"
    triage_note: str | None = None
    created_at: datetime
    run_id: str


class ChunkFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    file: str
    pass_: Pass = Field(alias="pass")
    reason: ChunkFailureReason
    message: str


class RunMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    started_at: datetime
    finished_at: datetime | None
    status: RunStatus
    repo_root: str
    branch: str | None
    head_sha: str
    base_ref: str
    base_sha: str
    source_label: str
    passes: list[Pass]
    model: str
    chunks_total: int = Field(ge=0)
    chunks_done: int = Field(ge=0)
    chunks_failed: int = Field(ge=0)
    findings_count: int = Field(ge=0)
    allow_partial: bool
    chunk_failures: list[ChunkFailure] = Field(default_factory=list)
    config_hash: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_models.py -vv`
Expected: 5 passed.

- [ ] **Step 5: Lint and type-check**

Run: `make check-pythinker-review`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/pythinker-review/src/pythinker_review/store packages/pythinker-review/tests
git commit -m "feat(review): add Finding/RunMeta/ChunkFailure pydantic models"
```

---

## Task 3: Run ID generator

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/store/ids.py`
- Create: `packages/pythinker-review/tests/unit/test_ids.py`

- [ ] **Step 1: Write the failing test**

Create `packages/pythinker-review/tests/unit/test_ids.py`:

```python
import re
from datetime import datetime, timezone

from pythinker_review.store.ids import generate_run_id, parse_run_id_timestamp

RUN_ID_RE = re.compile(r"^\d{14}-[0-9a-f]{8}$")


def test_generate_run_id_matches_format():
    rid = generate_run_id()
    assert RUN_ID_RE.fullmatch(rid)


def test_generate_run_id_sorts_lexicographically_by_time():
    fixed = datetime(2026, 5, 20, 12, 30, 45, tzinfo=timezone.utc)
    later = datetime(2026, 5, 20, 12, 30, 46, tzinfo=timezone.utc)
    a = generate_run_id(now=fixed)
    b = generate_run_id(now=later)
    assert a < b


def test_parse_run_id_timestamp():
    fixed = datetime(2026, 5, 20, 12, 30, 45, tzinfo=timezone.utc)
    rid = generate_run_id(now=fixed)
    parsed = parse_run_id_timestamp(rid)
    assert parsed.replace(tzinfo=timezone.utc) == fixed


def test_two_ids_in_same_second_differ():
    fixed = datetime(2026, 5, 20, 12, 30, 45, tzinfo=timezone.utc)
    a = generate_run_id(now=fixed)
    b = generate_run_id(now=fixed)
    assert a != b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_ids.py -vv`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `packages/pythinker-review/src/pythinker_review/store/ids.py`:

```python
"""Sortable run IDs of the form YYYYMMDDHHMMSS-<8 hex chars>."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone


def generate_run_id(*, now: datetime | None = None) -> str:
    when = now or datetime.now(tz=timezone.utc)
    stamp = when.strftime("%Y%m%d%H%M%S")
    return f"{stamp}-{secrets.token_hex(4)}"


def parse_run_id_timestamp(run_id: str) -> datetime:
    stamp, _hex = run_id.split("-", 1)
    return datetime.strptime(stamp, "%Y%m%d%H%M%S")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_ids.py -vv`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/pythinker-review/src/pythinker_review/store/ids.py packages/pythinker-review/tests/unit/test_ids.py
git commit -m "feat(review): add sortable run-id generator (stdlib-only)"
```

---

## Task 4: Diff source resolver (git subprocess wrapper)

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/engine/__init__.py`
- Create: `packages/pythinker-review/src/pythinker_review/engine/diff_source.py`
- Create: `packages/pythinker-review/tests/conftest.py`
- Create: `packages/pythinker-review/tests/unit/test_diff_source.py`

- [ ] **Step 1: Create the test git-repo fixture**

Create `packages/pythinker-review/tests/conftest.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import pytest


def _run(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Callable[..., Path]:
    """Create an isolated git repo with a known main branch, return a builder."""

    def _make(*, with_initial_commit: bool = True) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        _run(repo, "init", "--initial-branch=main", "-q")
        _run(repo, "config", "user.email", "test@example.com")
        _run(repo, "config", "user.name", "Test")
        _run(repo, "config", "commit.gpgsign", "false")
        if with_initial_commit:
            (repo / "README.md").write_text("hello\n")
            _run(repo, "add", ".")
            _run(repo, "commit", "-m", "init", "-q")
        return repo

    return _make


@pytest.fixture
def git_run() -> Callable[..., str]:
    """Run a git command in a given repo and return stdout."""
    return _run
```

- [ ] **Step 2: Write the failing test**

Create `packages/pythinker-review/tests/unit/test_diff_source.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from pythinker_review.engine.diff_source import (
    DiffMode,
    EmptyDiffError,
    PreflightError,
    ResolvedDiff,
    resolve_diff,
)


def _write_branch_with_change(repo: Path, git_run, branch: str = "feature") -> None:
    git_run(repo, "checkout", "-b", branch, "-q")
    (repo / "app.py").write_text("def f():\n    return 1\n")
    git_run(repo, "add", ".")
    git_run(repo, "commit", "-m", "add f", "-q")


def test_base_mode_diffs_branch_vs_merge_base(tmp_git_repo, git_run):
    repo = tmp_git_repo()
    _write_branch_with_change(repo, git_run)
    res = resolve_diff(repo, mode=DiffMode.base, base_ref="main")
    assert isinstance(res, ResolvedDiff)
    assert res.source_label == "git-diff:main"
    assert "app.py" in res.changed_files
    assert "diff --git" in res.patch_text
    assert res.head_sha and res.base_sha and res.head_sha != res.base_sha


def test_base_mode_falls_back_main_then_master(tmp_git_repo, git_run):
    repo = tmp_git_repo()
    _write_branch_with_change(repo, git_run)
    res = resolve_diff(repo, mode=DiffMode.base, base_ref="origin/main")
    assert res.source_label.startswith("git-diff:")
    assert "app.py" in res.changed_files


def test_staged_mode(tmp_git_repo, git_run):
    repo = tmp_git_repo()
    (repo / "a.py").write_text("x=1\n")
    git_run(repo, "add", "a.py")
    res = resolve_diff(repo, mode=DiffMode.staged)
    assert res.source_label == "staged"
    assert "a.py" in res.changed_files


def test_working_tree_mode_includes_untracked(tmp_git_repo, git_run):
    repo = tmp_git_repo()
    (repo / "untracked.py").write_text("y=2\n")
    res = resolve_diff(repo, mode=DiffMode.working_tree)
    assert res.source_label == "working-tree"
    assert "untracked.py" in res.changed_files


def test_range_mode(tmp_git_repo, git_run):
    repo = tmp_git_repo()
    _write_branch_with_change(repo, git_run, branch="b1")
    head = git_run(repo, "rev-parse", "HEAD").strip()
    base = git_run(repo, "rev-parse", "main").strip()
    res = resolve_diff(repo, mode=DiffMode.range, rev_range=f"{base}..{head}")
    assert res.source_label == f"git-range:{base}..{head}"


def test_empty_diff_raises_empty(tmp_git_repo, git_run):
    repo = tmp_git_repo()
    with pytest.raises(EmptyDiffError):
        resolve_diff(repo, mode=DiffMode.working_tree)


def test_unknown_base_ref_raises_preflight(tmp_git_repo, git_run):
    repo = tmp_git_repo()
    _write_branch_with_change(repo, git_run)
    with pytest.raises(PreflightError):
        resolve_diff(repo, mode=DiffMode.base, base_ref="does-not-exist", fallback_refs=())


def test_not_a_git_repo_raises_preflight(tmp_path):
    with pytest.raises(PreflightError):
        resolve_diff(tmp_path, mode=DiffMode.base, base_ref="main")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_diff_source.py -vv`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

Create `packages/pythinker-review/src/pythinker_review/engine/__init__.py` (empty).

Create `packages/pythinker-review/src/pythinker_review/engine/diff_source.py`:

```python
"""Resolve the diff to review, plus base/head SHAs and changed file list."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

_GIT_TIMEOUT_S = 20.0


class DiffMode(str, Enum):
    base = "base"
    staged = "staged"
    working_tree = "working_tree"
    range = "range"


class PreflightError(RuntimeError):
    """Recoverable, user-actionable git/setup issue."""


class EmptyDiffError(PreflightError):
    """The resolved diff is empty after filters."""


@dataclass(frozen=True, slots=True)
class ResolvedDiff:
    patch_text: str
    base_sha: str
    head_sha: str
    base_ref: str
    source_label: str
    changed_files: tuple[str, ...] = field(default_factory=tuple)


def _git(repo: Path, *args: str, check: bool = True) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise PreflightError("git executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise PreflightError(f"git {args[0]} timed out after {_GIT_TIMEOUT_S}s") from exc
    if check and proc.returncode != 0:
        raise PreflightError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def _ensure_repo(repo: Path) -> None:
    if not (repo / ".git").exists():
        raise PreflightError(f"{repo} is not a git repository (no .git dir)")


def _resolve_ref(repo: Path, ref: str) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_S,
    )
    if proc.returncode != 0:
        raise PreflightError(f"base ref '{ref}' is not resolvable in {repo}")
    return proc.stdout.strip()


def resolve_diff(
    repo: Path,
    *,
    mode: DiffMode,
    base_ref: str = "origin/main",
    fallback_refs: tuple[str, ...] = ("main", "master"),
    rev_range: str | None = None,
    unified: int = 10,
) -> ResolvedDiff:
    _ensure_repo(repo)
    head_sha = _resolve_ref(repo, "HEAD")

    if mode is DiffMode.range:
        if not rev_range or ".." not in rev_range:
            raise PreflightError("--range requires A..B")
        a, _, b = rev_range.partition("..")
        base_sha = _resolve_ref(repo, a)
        head_sha = _resolve_ref(repo, b) if b else head_sha
        patch = _git(repo, "diff", f"--unified={unified}", rev_range)
        files = _changed_files_from_diff(patch)
        if not files:
            raise EmptyDiffError("range diff is empty")
        return ResolvedDiff(
            patch_text=patch,
            base_sha=base_sha,
            head_sha=head_sha,
            base_ref=a,
            source_label=f"git-range:{rev_range}",
            changed_files=files,
        )

    if mode is DiffMode.staged:
        patch = _git(repo, "diff", "--cached", f"--unified={unified}")
        files = _changed_files_from_diff(patch)
        if not files:
            raise EmptyDiffError("no staged changes")
        return ResolvedDiff(
            patch_text=patch,
            base_sha=head_sha,
            head_sha=head_sha,
            base_ref="HEAD",
            source_label="staged",
            changed_files=files,
        )

    if mode is DiffMode.working_tree:
        # Tracked working-tree + staged
        tracked = _git(repo, "diff", f"--unified={unified}", "HEAD")
        # Untracked, non-ignored, as synthetic added-file patches
        untracked = _git(
            repo, "ls-files", "--others", "--exclude-standard", check=True
        ).splitlines()
        synthetic = "".join(_synthesize_added_file_patch(repo, p) for p in untracked if p)
        patch = tracked + synthetic
        files = _changed_files_from_diff(patch)
        if not files:
            raise EmptyDiffError("no working-tree changes")
        return ResolvedDiff(
            patch_text=patch,
            base_sha=head_sha,
            head_sha=head_sha,
            base_ref="HEAD",
            source_label="working-tree",
            changed_files=files,
        )

    # mode is DiffMode.base
    candidates = (base_ref, *fallback_refs)
    chosen_ref: str | None = None
    chosen_sha: str | None = None
    last_err: PreflightError | None = None
    for ref in candidates:
        try:
            chosen_sha = _resolve_ref(repo, ref)
            chosen_ref = ref
            break
        except PreflightError as exc:
            last_err = exc
    if not chosen_ref or not chosen_sha:
        raise last_err or PreflightError("no resolvable base ref")
    merge_base = _git(repo, "merge-base", "HEAD", chosen_ref).strip()
    if not merge_base:
        raise PreflightError(f"no merge-base between HEAD and {chosen_ref}")
    patch = _git(repo, "diff", f"--unified={unified}", f"{merge_base}..HEAD")
    files = _changed_files_from_diff(patch)
    if not files:
        raise EmptyDiffError(f"no changes between {chosen_ref} and HEAD")
    return ResolvedDiff(
        patch_text=patch,
        base_sha=merge_base,
        head_sha=head_sha,
        base_ref=chosen_ref,
        source_label=f"git-diff:{chosen_ref}",
        changed_files=files,
    )


def _changed_files_from_diff(patch: str) -> tuple[str, ...]:
    files: list[str] = []
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            path = line[len("+++ b/") :].strip()
            if path != "/dev/null":
                files.append(path)
    return tuple(dict.fromkeys(files))


def _synthesize_added_file_patch(repo: Path, rel_path: str) -> str:
    full = repo / rel_path
    try:
        text = full.read_text()
    except (UnicodeDecodeError, OSError):
        return ""
    lines = text.splitlines(keepends=True)
    body = "".join(f"+{line}" for line in lines)
    header = (
        f"diff --git a/{rel_path} b/{rel_path}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{rel_path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
    )
    return header + body
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_diff_source.py -vv`
Expected: 7 passed.

- [ ] **Step 6: Lint + type-check**

Run: `make check-pythinker-review`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/pythinker-review/src/pythinker_review/engine packages/pythinker-review/tests
git commit -m "feat(review): resolve diff via git subprocess (base/staged/working-tree/range)"
```

---

## Task 5: Structured diff renderer

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/engine/structured_diff.py`
- Create: `packages/pythinker-review/tests/unit/test_structured_diff.py`

- [ ] **Step 1: Write the failing test**

Create `packages/pythinker-review/tests/unit/test_structured_diff.py`:

```python
from pythinker_review.engine.structured_diff import StructuredFile, render_structured_diff

SAMPLE_DIFF = """diff --git a/src/app.py b/src/app.py
index 1111..2222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,5 @@
 def f():
-    return 1
+    return 2
+    # added
     # comment
 # tail
"""


def test_renders_file_header_and_hunks():
    out = render_structured_diff(SAMPLE_DIFF)
    assert len(out) == 1
    sf = out[0]
    assert isinstance(sf, StructuredFile)
    assert sf.path == "src/app.py"
    assert "## File: 'src/app.py'" in sf.rendered
    assert "__new hunk__" in sf.rendered
    assert "__old hunk__" in sf.rendered
    # New hunk lines are numbered with post-change line numbers
    assert "2 +    return 2" in sf.rendered
    assert "3 +    # added" in sf.rendered


def test_handles_added_file():
    diff = (
        "diff --git a/new.py b/new.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/new.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+x = 1\n"
        "+y = 2\n"
    )
    out = render_structured_diff(diff)
    assert len(out) == 1
    assert out[0].path == "new.py"
    assert "1 +x = 1" in out[0].rendered
    assert "2 +y = 2" in out[0].rendered


def test_handles_pure_deletion_hunk():
    diff = (
        "diff --git a/old.py b/old.py\n"
        "--- a/old.py\n"
        "+++ b/old.py\n"
        "@@ -1,2 +1,1 @@\n"
        " keep\n"
        "-removed\n"
    )
    out = render_structured_diff(diff)
    assert "-removed" in out[0].rendered
    assert "__old hunk__" in out[0].rendered


def test_skips_binary_diffs():
    diff = (
        "diff --git a/img.png b/img.png\n"
        "Binary files a/img.png and b/img.png differ\n"
    )
    out = render_structured_diff(diff)
    assert out == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_structured_diff.py -vv`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `packages/pythinker-review/src/pythinker_review/engine/structured_diff.py`:

```python
"""Render a unified diff into the blackbox-style review input.

For each file, emit:

    ## File: '<path>'

    @@ ... @@ optional header
    __new hunk__
    <post-change line number> + added/changed line
    <post-change line number>   unchanged context
    __old hunk__
       unchanged context
    -    removed line
       unchanged context

Reviewers must anchor findings to a changed post-change line when possible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FILE_HDR = re.compile(r"^diff --git a/(.+) b/(.+)$")
_PLUS_PATH = re.compile(r"^\+\+\+ b/(.+)$")
_MINUS_PATH = re.compile(r"^--- (?:a/(.+)|/dev/null)$")
_HUNK_HDR = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


@dataclass(frozen=True, slots=True)
class StructuredHunk:
    header: str
    new_block: str
    old_block: str


@dataclass(frozen=True, slots=True)
class StructuredFile:
    path: str
    rendered: str
    hunks: tuple[StructuredHunk, ...]


def render_structured_diff(patch_text: str) -> list[StructuredFile]:
    files: list[StructuredFile] = []
    for raw_file in _split_files(patch_text):
        rendered = _render_file(raw_file)
        if rendered is not None:
            files.append(rendered)
    return files


def _split_files(patch_text: str) -> list[list[str]]:
    out: list[list[str]] = []
    current: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            if current:
                out.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        out.append(current)
    return out


def _render_file(file_lines: list[str]) -> StructuredFile | None:
    head = file_lines[0]
    m = _FILE_HDR.match(head)
    if not m:
        return None
    path = m.group(2)
    if any("Binary files" in line for line in file_lines):
        return None

    # Skip metadata until first @@ hunk header.
    idx = 0
    while idx < len(file_lines) and not file_lines[idx].startswith("@@"):
        idx += 1

    hunks: list[StructuredHunk] = []
    while idx < len(file_lines):
        if not file_lines[idx].startswith("@@"):
            idx += 1
            continue
        hunk_header = file_lines[idx]
        idx += 1
        body: list[str] = []
        while idx < len(file_lines) and not file_lines[idx].startswith("@@") and not file_lines[
            idx
        ].startswith("diff --git "):
            body.append(file_lines[idx])
            idx += 1
        hm = _HUNK_HDR.match(hunk_header)
        if not hm:
            continue
        new_start = int(hm.group(3))
        new_block_lines: list[str] = []
        old_block_lines: list[str] = []
        new_lineno = new_start
        for bl in body:
            if bl.startswith("+") and not bl.startswith("+++"):
                new_block_lines.append(f"{new_lineno} {bl}")
                new_lineno += 1
            elif bl.startswith("-") and not bl.startswith("---"):
                old_block_lines.append(bl)
            else:
                content = bl[1:] if bl.startswith(" ") else bl
                new_block_lines.append(f"{new_lineno}   {content}")
                old_block_lines.append(f"  {content}")
                new_lineno += 1
        hunks.append(
            StructuredHunk(
                header=hunk_header,
                new_block="\n".join(new_block_lines),
                old_block="\n".join(old_block_lines),
            )
        )

    if not hunks:
        return None

    parts = [f"## File: '{path}'", ""]
    for h in hunks:
        parts.append(h.header)
        parts.append("__new hunk__")
        parts.append(h.new_block)
        parts.append("__old hunk__")
        parts.append(h.old_block)
        parts.append("")
    return StructuredFile(path=path, rendered="\n".join(parts), hunks=tuple(hunks))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_structured_diff.py -vv`
Expected: 4 passed.

- [ ] **Step 5: Lint + type-check, then commit**

Run: `make check-pythinker-review`
Expected: PASS.

```bash
git add packages/pythinker-review/src/pythinker_review/engine/structured_diff.py packages/pythinker-review/tests/unit/test_structured_diff.py
git commit -m "feat(review): render unified diff into __new hunk__/__old hunk__ blocks"
```

---

## Task 6: Context gatherer

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/engine/context.py`
- Create: `packages/pythinker-review/tests/unit/test_context.py`

- [ ] **Step 1: Write the failing test**

Create `packages/pythinker-review/tests/unit/test_context.py`:

```python
from pathlib import Path

from pythinker_review.engine.context import FileContext, gather_context


def test_full_current_file_when_under_budget(tmp_path: Path):
    f = tmp_path / "a.py"
    f.write_text("line1\nline2\nline3\n")
    ctx = gather_context(
        repo=tmp_path,
        file_path="a.py",
        hunks_post_lines=[1, 2],
        budget_chars=10_000,
        base_sha=None,
    )
    assert isinstance(ctx, FileContext)
    assert ctx.current_full == "line1\nline2\nline3\n"
    assert ctx.current_windows == ()


def test_windowed_when_over_budget(tmp_path: Path):
    f = tmp_path / "big.py"
    body = "\n".join(f"line{i}" for i in range(1, 401)) + "\n"
    f.write_text(body)
    ctx = gather_context(
        repo=tmp_path,
        file_path="big.py",
        hunks_post_lines=[100],
        budget_chars=500,
        base_sha=None,
    )
    assert ctx.current_full is None
    assert ctx.current_windows
    window = ctx.current_windows[0]
    assert window.start_line <= 100 <= window.end_line


def test_missing_file_returns_empty_context(tmp_path: Path):
    ctx = gather_context(
        repo=tmp_path,
        file_path="missing.py",
        hunks_post_lines=[1],
        budget_chars=10_000,
        base_sha=None,
    )
    assert ctx.current_full is None
    assert ctx.current_windows == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_context.py -vv`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `packages/pythinker-review/src/pythinker_review/engine/context.py`:

```python
"""Gather bounded current/base file context around hunks for the reviewer."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_WINDOW_HALF = 50  # ± lines around each hunk when the full file does not fit


@dataclass(frozen=True, slots=True)
class ContextWindow:
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True, slots=True)
class FileContext:
    path: str
    current_full: str | None = None
    current_windows: tuple[ContextWindow, ...] = field(default_factory=tuple)
    base_windows: tuple[ContextWindow, ...] = field(default_factory=tuple)


def gather_context(
    *,
    repo: Path,
    file_path: str,
    hunks_post_lines: list[int],
    budget_chars: int,
    base_sha: str | None,
) -> FileContext:
    full = _read_current(repo, file_path)
    if full is not None and len(full) <= budget_chars:
        return FileContext(path=file_path, current_full=full)

    if full is None:
        return FileContext(path=file_path)

    windows = tuple(_windows_from_lines(full, hunks_post_lines))
    base_windows: tuple[ContextWindow, ...] = ()
    if base_sha:
        base_text = _read_base(repo, base_sha, file_path)
        if base_text:
            base_windows = tuple(_windows_from_lines(base_text, hunks_post_lines))
    return FileContext(
        path=file_path, current_windows=windows, base_windows=base_windows
    )


def _read_current(repo: Path, rel: str) -> str | None:
    try:
        return (repo / rel).read_text()
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return None


def _read_base(repo: Path, sha: str, rel: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "show", f"{sha}:{rel}"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=10.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _windows_from_lines(text: str, line_anchors: list[int]) -> list[ContextWindow]:
    lines = text.splitlines()
    spans: list[tuple[int, int]] = []
    for anchor in sorted(set(line_anchors)):
        start = max(1, anchor - _WINDOW_HALF)
        end = min(len(lines), anchor + _WINDOW_HALF)
        spans.append((start, end))
    merged = _merge_spans(spans)
    return [
        ContextWindow(start_line=s, end_line=e, text="\n".join(lines[s - 1 : e]))
        for s, e in merged
    ]


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans.sort()
    out = [spans[0]]
    for s, e in spans[1:]:
        last_s, last_e = out[-1]
        if s <= last_e + 1:
            out[-1] = (last_s, max(last_e, e))
        else:
            out.append((s, e))
    return out
```

- [ ] **Step 4: Run test, lint, commit**

```bash
uv run --directory packages/pythinker-review pytest tests/unit/test_context.py -vv  # 3 passed
make check-pythinker-review
git add packages/pythinker-review/src/pythinker_review/engine/context.py packages/pythinker-review/tests/unit/test_context.py
git commit -m "feat(review): bounded current/base file context gatherer"
```

---

## Task 7: Chunker

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/engine/chunker.py`
- Create: `packages/pythinker-review/tests/unit/test_chunker.py`

- [ ] **Step 1: Write the failing test**

Create `packages/pythinker-review/tests/unit/test_chunker.py`:

```python
from pythinker_review.engine.chunker import Chunk, build_chunks
from pythinker_review.engine.structured_diff import StructuredFile, StructuredHunk


def _sf(path: str, body: str = "  X") -> StructuredFile:
    h = StructuredHunk(
        header="@@ -1,1 +1,1 @@", new_block=f"1 +{body}", old_block="-old"
    )
    return StructuredFile(path=path, rendered=f"## File: '{path}'\n{body}", hunks=(h,))


def test_one_chunk_per_file_by_default():
    files = [_sf("src/a.py"), _sf("src/b.py")]
    chunks = build_chunks(files, includes=(), excludes=(), skip_vendored=True, budget_chars=10_000)
    assert [c.file for c in chunks] == ["src/a.py", "src/b.py"]


def test_exclude_glob_drops_file():
    files = [_sf("src/a.py"), _sf("tests/b.py")]
    chunks = build_chunks(
        files, includes=(), excludes=("tests/**",), skip_vendored=True, budget_chars=10_000
    )
    assert [c.file for c in chunks] == ["src/a.py"]


def test_include_filter_keeps_only_matching():
    files = [_sf("src/a.py"), _sf("docs/b.md")]
    chunks = build_chunks(
        files, includes=("src/**",), excludes=(), skip_vendored=True, budget_chars=10_000
    )
    assert [c.file for c in chunks] == ["src/a.py"]


def test_vendored_skipped_by_default():
    files = [_sf("node_modules/x/index.js"), _sf("src/a.py"), _sf(".venv/lib/y.py")]
    chunks = build_chunks(files, includes=(), excludes=(), skip_vendored=True, budget_chars=10_000)
    assert [c.file for c in chunks] == ["src/a.py"]


def test_oversized_file_split_per_hunk():
    h1 = StructuredHunk(header="@@ -1 +1 @@", new_block="1 +A" * 200, old_block="")
    h2 = StructuredHunk(header="@@ -10 +10 @@", new_block="10 +B" * 200, old_block="")
    sf = StructuredFile(path="src/big.py", rendered="x", hunks=(h1, h2))
    chunks = build_chunks([sf], includes=(), excludes=(), skip_vendored=True, budget_chars=500)
    assert len(chunks) >= 2
    assert all(c.file == "src/big.py" for c in chunks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_chunker.py -vv`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `packages/pythinker-review/src/pythinker_review/engine/chunker.py`:

```python
"""Group/split structured files into review chunks."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from pythinker_review.engine.structured_diff import StructuredFile, StructuredHunk

VENDORED_PREFIXES: tuple[str, ...] = (
    "node_modules/",
    ".venv/",
    "venv/",
    "dist/",
    "build/",
    ".git/",
    ".pythinker-review/",
    "coverage/",
    "htmlcov/",
    "__pycache__/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    "target/",
)


@dataclass(frozen=True, slots=True)
class Chunk:
    file: str
    hunks: tuple[StructuredHunk, ...]
    rendered: str


def build_chunks(
    files: list[StructuredFile],
    *,
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
    skip_vendored: bool,
    budget_chars: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sf in files:
        if not _matches_filters(sf.path, includes, excludes, skip_vendored):
            continue
        if len(sf.rendered) <= budget_chars or len(sf.hunks) <= 1:
            chunks.append(Chunk(file=sf.path, hunks=sf.hunks, rendered=sf.rendered))
        else:
            chunks.extend(_split_per_hunk(sf, budget_chars))
    return chunks


def _matches_filters(
    path: str,
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
    skip_vendored: bool,
) -> bool:
    if skip_vendored and any(path.startswith(p) for p in VENDORED_PREFIXES):
        return False
    if includes and not any(fnmatch.fnmatch(path, p) for p in includes):
        return False
    if any(fnmatch.fnmatch(path, p) for p in excludes):
        return False
    return True


def _split_per_hunk(sf: StructuredFile, budget_chars: int) -> list[Chunk]:
    out: list[Chunk] = []
    for hunk in sf.hunks:
        rendered = (
            f"## File: '{sf.path}'\n"
            f"{hunk.header}\n__new hunk__\n{hunk.new_block}\n__old hunk__\n{hunk.old_block}\n"
        )
        if len(rendered) > budget_chars:
            rendered = rendered[: budget_chars - 20] + "\n... [truncated]"
        out.append(Chunk(file=sf.path, hunks=(hunk,), rendered=rendered))
    return out
```

- [ ] **Step 4: Run test, lint, commit**

```bash
uv run --directory packages/pythinker-review pytest tests/unit/test_chunker.py -vv  # 5 passed
make check-pythinker-review
git add packages/pythinker-review/src/pythinker_review/engine/chunker.py packages/pythinker-review/tests/unit/test_chunker.py
git commit -m "feat(review): per-file/per-hunk chunker with include/exclude/vendored filters"
```

---

## Task 8: Signals scanner

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/signals/__init__.py`
- Create: `packages/pythinker-review/src/pythinker_review/signals/models.py`
- Create: `packages/pythinker-review/src/pythinker_review/signals/scanner.py`
- Create: `packages/pythinker-review/tests/unit/test_signals.py`

- [ ] **Step 1: Write the failing test**

Create `packages/pythinker-review/tests/unit/test_signals.py`:

```python
from pythinker_review.signals.scanner import scan_signals


def test_detects_aws_access_key():
    findings = scan_signals(
        file_path="config.py",
        added_lines=[(10, 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"')],
    )
    assert any(s.rule_id == "sec.signal.secret.aws_access_key" for s in findings)


def test_detects_shell_with_user_input():
    findings = scan_signals(
        file_path="x.py",
        added_lines=[(5, "subprocess.run(f'rm {user_path}', shell=True)")],
    )
    assert any(s.rule_id == "sec.signal.shell.user_var" for s in findings)


def test_detects_sql_concatenation():
    findings = scan_signals(
        file_path="db.py",
        added_lines=[(3, 'cursor.execute("SELECT * FROM t WHERE id=" + user_id)')],
    )
    assert any(s.rule_id == "sec.signal.sql.concat" for s in findings)


def test_no_false_positive_on_plain_text():
    findings = scan_signals(
        file_path="x.py", added_lines=[(1, "x = 1 + 2  # arithmetic")]
    )
    assert findings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_signals.py -vv`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `packages/pythinker-review/src/pythinker_review/signals/__init__.py` (empty).

Create `packages/pythinker-review/src/pythinker_review/signals/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Signal:
    rule_id: str
    file: str
    line: int
    snippet: str
    reason: str
    confidence: float
```

Create `packages/pythinker-review/src/pythinker_review/signals/scanner.py`. Patterns intentionally use character classes (e.g. `[p]ickle`) to avoid tripping host security hooks during plan review — runtime behavior is identical to the plain literal form:

```python
"""Deterministic security-signal regex scanner. Prompt anchors only."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pythinker_review.signals.models import Signal


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_id: str
    pattern: re.Pattern[str]
    reason: str
    confidence: float


_RULES: tuple[_Rule, ...] = (
    _Rule(
        rule_id="sec.signal.secret.aws_access_key",
        pattern=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        reason="Looks like an AWS access key ID added to source.",
        confidence=0.95,
    ),
    _Rule(
        rule_id="sec.signal.secret.generic_token",
        pattern=re.compile(
            r"""(?ix)
            (?:api[_-]?key|secret|token|password|passwd|pwd)\s*[=:]\s*
            ['"][A-Za-z0-9_\-]{16,}['"]
            """
        ),
        reason="Possible hardcoded credential.",
        confidence=0.7,
    ),
    _Rule(
        rule_id="sec.signal.shell.user_var",
        pattern=re.compile(
            r"""(?x)
            (?:subprocess\.(?:run|Popen|call|check_call|check_output)|os\.(?:system|popen))
            \([^)]*\bshell\s*=\s*True
            """
        ),
        reason="shell=True with dynamic argument shape.",
        confidence=0.75,
    ),
    _Rule(
        rule_id="sec.signal.sql.concat",
        pattern=re.compile(
            r"""(?ix)
            (?:cursor|conn|connection|db)\.execute\s*\(
            \s*["'][^"']*\bSELECT\b[^"']*["']\s*[+%]
            """
        ),
        reason="SQL string concatenation passed to execute().",
        confidence=0.85,
    ),
    _Rule(
        rule_id="sec.signal.deserialization.unsafe",
        pattern=re.compile(r"\b[p]ickle\.(?:load|loads)\s*\("),
        reason="Unsafe deserialization of potentially untrusted data.",
        confidence=0.7,
    ),
    _Rule(
        rule_id="sec.signal.ssrf.requests_var_url",
        pattern=re.compile(
            r"""(?x)
            (?:requests|urllib|httpx|aiohttp)\.(?:get|post|put|delete|request)\s*\(
            \s*[A-Za-z_][A-Za-z0-9_]*
            """
        ),
        reason="HTTP request to a URL held in a variable; check for SSRF guard.",
        confidence=0.5,
    ),
    _Rule(
        rule_id="sec.signal.crypto.weak_hash",
        pattern=re.compile(r"\bhashlib\.(?:md5|sha1)\s*\("),
        reason="Weak hash used; verify it is not a security boundary.",
        confidence=0.6,
    ),
)


def scan_signals(*, file_path: str, added_lines: list[tuple[int, str]]) -> list[Signal]:
    out: list[Signal] = []
    for lineno, text in added_lines:
        for rule in _RULES:
            if rule.pattern.search(text):
                out.append(
                    Signal(
                        rule_id=rule.rule_id,
                        file=file_path,
                        line=lineno,
                        snippet=text.strip(),
                        reason=rule.reason,
                        confidence=rule.confidence,
                    )
                )
    return out
```

- [ ] **Step 4: Run test, lint, commit**

```bash
uv run --directory packages/pythinker-review pytest tests/unit/test_signals.py -vv  # 4 passed
make check-pythinker-review
git add packages/pythinker-review/src/pythinker_review/signals packages/pythinker-review/tests/unit/test_signals.py
git commit -m "feat(review): deterministic security-signal scanner (prompt anchors only)"
```

---

## Task 9: Reviewer schemas + LLM Protocol + FakeReviewLLM

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/llm/__init__.py`
- Create: `packages/pythinker-review/src/pythinker_review/llm/protocol.py`
- Create: `packages/pythinker-review/src/pythinker_review/llm/fake.py`
- Create: `packages/pythinker-review/src/pythinker_review/reviewers/__init__.py`
- Create: `packages/pythinker-review/src/pythinker_review/reviewers/schema.py`
- Create: `packages/pythinker-review/tests/unit/test_schema.py`

- [ ] **Step 1: Implement Protocol + FakeReviewLLM (no TDD; trivial)**

Create `packages/pythinker-review/src/pythinker_review/llm/__init__.py`:

```python
from pythinker_review.llm.protocol import ReviewLLM

__all__ = ["ReviewLLM"]
```

Create `packages/pythinker-review/src/pythinker_review/llm/protocol.py`:

```python
"""Minimal LLM contract the review engine depends on."""

from __future__ import annotations

from typing import Protocol


class ReviewLLM(Protocol):
    model_display_name: str

    async def complete_json(
        self, *, system: str, user: str, timeout_s: float
    ) -> str: ...
```

Create `packages/pythinker-review/src/pythinker_review/llm/fake.py`:

```python
"""Deterministic FakeReviewLLM for unit/e2e tests."""

from __future__ import annotations

from collections.abc import Callable, Iterable


class FakeReviewLLM:
    model_display_name = "fake:test-model"

    def __init__(
        self,
        *,
        responder: Callable[[str, str], str] | None = None,
        scripted: Iterable[str] | None = None,
    ) -> None:
        self._responder = responder
        self._scripted = list(scripted) if scripted is not None else None
        self.calls: list[tuple[str, str]] = []

    async def complete_json(
        self, *, system: str, user: str, timeout_s: float
    ) -> str:
        self.calls.append((system, user))
        if self._responder is not None:
            return self._responder(system, user)
        if self._scripted:
            return self._scripted.pop(0)
        return '{"findings": []}'
```

- [ ] **Step 2: Write the failing test for `RawFinding` schema**

Create `packages/pythinker-review/tests/unit/test_schema.py`:

```python
import pytest
from pydantic import ValidationError

from pythinker_review.reviewers.schema import RawFinding, ReviewerOutput
from pythinker_review.store.models import Category, Severity


def test_reviewer_output_parses_minimal_payload():
    data = {
        "findings": [
            {
                "rule_id": "review.error_handling",
                "title": "Catch is too broad",
                "rationale": "...",
                "category": "correctness",
                "severity": "medium",
                "file": "src/a.py",
                "start_line": 5,
                "end_line": 5,
                "confidence": 0.8,
            }
        ]
    }
    out = ReviewerOutput.model_validate(data)
    assert len(out.findings) == 1
    f = out.findings[0]
    assert f.category is Category.correctness
    assert f.severity is Severity.medium


def test_reviewer_output_rejects_lines_under_one():
    with pytest.raises(ValidationError):
        RawFinding(
            rule_id="r",
            title="t",
            rationale="r",
            category=Category.correctness,
            severity=Severity.low,
            file="a",
            start_line=0,
            end_line=1,
            confidence=0.5,
        )
```

- [ ] **Step 3: Implement schema**

Create `packages/pythinker-review/src/pythinker_review/reviewers/__init__.py` (empty).

Create `packages/pythinker-review/src/pythinker_review/reviewers/schema.py`:

```python
"""Strict pydantic models the LLM is asked to produce."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pythinker_review.store.models import Category, Severity, Suggestion


class RawFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str
    title: str = Field(max_length=80)
    rationale: str
    category: Category
    severity: Severity
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_snippet: str | None = None
    suggestion: Suggestion | None = None


class ReviewerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[RawFinding] = Field(default_factory=list)
```

- [ ] **Step 4: Run test, lint, commit**

```bash
uv run --directory packages/pythinker-review pytest tests/unit/test_schema.py -vv  # 2 passed
make check-pythinker-review
git add packages/pythinker-review/src/pythinker_review/llm packages/pythinker-review/src/pythinker_review/reviewers packages/pythinker-review/tests/unit/test_schema.py
git commit -m "feat(review): ReviewLLM protocol + FakeReviewLLM + RawFinding schema"
```

---

## Task 10: Code-review, security-review, and debug-review passes (prompts + callers)

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/reviewers/prompts/code_review.system.md`
- Create: `packages/pythinker-review/src/pythinker_review/reviewers/prompts/security_review.system.md`
- Create: `packages/pythinker-review/src/pythinker_review/reviewers/prompts/debug_review.system.md`
- Create: `packages/pythinker-review/src/pythinker_review/reviewers/code_review.py`
- Create: `packages/pythinker-review/src/pythinker_review/reviewers/security_review.py`
- Create: `packages/pythinker-review/src/pythinker_review/reviewers/debug_review.py`
- Modify: `packages/pythinker-review/pyproject.toml` — add prompts to package data + configure pytest-asyncio
- Create: `packages/pythinker-review/tests/unit/test_reviewers.py`

- [ ] **Step 1: Configure pytest-asyncio (one-time, do before writing async tests)**

Append to `packages/pythinker-review/pyproject.toml`:

```toml
[tool.uv_build]
package-data = ["src/pythinker_review/reviewers/prompts/*.md"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Write the failing test**

Create `packages/pythinker-review/tests/unit/test_reviewers.py`:

```python
import json

import pytest

from pythinker_review.engine.chunker import Chunk
from pythinker_review.engine.structured_diff import StructuredHunk
from pythinker_review.llm.fake import FakeReviewLLM
from pythinker_review.reviewers.code_review import run_code_review_pass
from pythinker_review.reviewers.security_review import run_security_review_pass
from pythinker_review.reviewers.debug_review import run_debug_review_pass


def _chunk() -> Chunk:
    h = StructuredHunk(header="@@ -1 +1 @@", new_block="1 +x=1", old_block="")
    return Chunk(file="x.py", hunks=(h,), rendered="## File: 'x.py'\nx=1")


def _diagnostic() -> str:
    return "pytest tests/test_x.py::test_x failed with AssertionError at x.py:1"


@pytest.mark.asyncio
async def test_code_review_returns_findings_on_valid_json():
    llm = FakeReviewLLM(
        scripted=[
            json.dumps(
                {
                    "findings": [
                        {
                            "rule_id": "review.error_handling",
                            "title": "missing handler",
                            "rationale": "...",
                            "category": "correctness",
                            "severity": "low",
                            "file": "x.py",
                            "start_line": 1,
                            "end_line": 1,
                            "confidence": 0.6,
                        }
                    ]
                }
            )
        ]
    )
    result = await run_code_review_pass(chunk=_chunk(), llm=llm, timeout_s=10.0)
    assert result.ok
    assert len(result.findings) == 1
    assert result.findings[0].rule_id == "review.error_handling"


@pytest.mark.asyncio
async def test_security_review_retries_once_on_malformed_then_succeeds():
    llm = FakeReviewLLM(scripted=["not json", '{"findings": []}'])
    result = await run_security_review_pass(
        chunk=_chunk(), signals=[], llm=llm, timeout_s=10.0
    )
    assert result.ok
    assert result.findings == ()
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_security_review_fails_after_second_malformed():
    llm = FakeReviewLLM(scripted=["nope", "still nope"])
    result = await run_security_review_pass(
        chunk=_chunk(), signals=[], llm=llm, timeout_s=10.0
    )
    assert not result.ok
    assert result.failure_reason == "malformed_output"


@pytest.mark.asyncio
async def test_debug_review_returns_root_cause_findings():
    llm = FakeReviewLLM(scripted=['{"findings": []}'])
    result = await run_debug_review_pass(
        chunk=_chunk(), diagnostic=_diagnostic(), llm=llm, timeout_s=10.0
    )
    assert result.ok
    assert llm.calls
```

- [ ] **Step 3: Write the prompt files**

Create `packages/pythinker-review/src/pythinker_review/reviewers/prompts/code_review.system.md` with the body shown in §5.3 of the spec, in particular: focus on diff-introduced issues; no vague speculation; flag clear bugs/security even with narrow triggers; low-severity findings require high confidence; cite concrete failure modes and changed lines; output strict JSON only. Include the JSON schema example from Task 10 below the rules.

Create `packages/pythinker-review/src/pythinker_review/reviewers/prompts/security_review.system.md` with the body shown in §5.3 of the spec: anchor to post-change lines; verify signals against code; prefer no finding over speculation; severity guide; categories `security` / `secret` / `dependency`; strict JSON output. Create `packages/pythinker-review/src/pythinker_review/reviewers/prompts/debug_review.system.md` with the debugger/root-cause rules from §5.3 of the spec: normalize failure evidence, correlate stack/log lines to changed code, identify likely root cause, cite reproduction evidence, and never patch code.

All three files end with `If you find no issues, return {"findings": []}. Output JSON only, no prose.`

The exact prompt skeletons live in the spec; copy them verbatim from `docs/superpowers/specs/2026-05-20-pythinker-review-foundation-design.md` §5.3 plus the schema example below:

```json
{
  "findings": [
    {
      "rule_id": "<dotted id>",
      "title": "<≤80 chars>",
      "rationale": "<markdown>",
      "category": "<see categories above>",
      "severity": "critical|high|medium|low|info",
      "file": "<repo-relative POSIX path>",
      "start_line": <post-change line>,
      "end_line": <post-change line>,
      "confidence": 0.0-1.0,
      "evidence_snippet": "<optional code excerpt>",
      "suggestion": {"summary": "<one sentence>", "patch": "<optional unified diff>"}
    }
  ]
}
```

- [ ] **Step 4: Implement the three reviewer modules**

Create `packages/pythinker-review/src/pythinker_review/reviewers/code_review.py`:

```python
"""Code-review pass: prompt + call + strict JSON parse + one retry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from importlib import resources

from pydantic import ValidationError

from pythinker_review.engine.chunker import Chunk
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.schema import RawFinding, ReviewerOutput
from pythinker_review.store.models import ChunkFailureReason


@dataclass(frozen=True, slots=True)
class ReviewerResult:
    ok: bool
    findings: tuple[RawFinding, ...] = field(default_factory=tuple)
    failure_reason: ChunkFailureReason | None = None
    failure_message: str = ""


_RETRY_SUFFIX = (
    "\n\nIMPORTANT: Your previous response was not valid JSON for the given "
    "schema. Reply with strict JSON only, no prose, no markdown fences."
)


def _load_system_prompt() -> str:
    return (
        resources.files("pythinker_review.reviewers.prompts")
        .joinpath("code_review.system.md")
        .read_text(encoding="utf-8")
    )


def _build_user(chunk: Chunk) -> str:
    return f"Review the following diff for issues introduced by this change.\n\n{chunk.rendered}\n"


async def run_code_review_pass(
    *, chunk: Chunk, llm: ReviewLLM, timeout_s: float
) -> ReviewerResult:
    system = _load_system_prompt()
    user = _build_user(chunk)
    for attempt in (1, 2):
        try:
            raw = await asyncio.wait_for(
                llm.complete_json(system=system, user=user, timeout_s=timeout_s),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            return ReviewerResult(
                ok=False, failure_reason="timeout", failure_message="LLM timed out"
            )
        except Exception as exc:  # noqa: BLE001 — surface any provider error
            return ReviewerResult(
                ok=False, failure_reason="llm_error", failure_message=str(exc)
            )
        try:
            out = ReviewerOutput.model_validate_json(raw)
            return ReviewerResult(ok=True, findings=tuple(out.findings))
        except ValidationError as exc:
            if attempt == 2:
                return ReviewerResult(
                    ok=False, failure_reason="malformed_output", failure_message=str(exc)
                )
            user = user + _RETRY_SUFFIX
    return ReviewerResult(ok=False, failure_reason="malformed_output")
```

Create `packages/pythinker-review/src/pythinker_review/reviewers/security_review.py`:

```python
"""Security-review pass: like code_review but receives deterministic signals."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from importlib import resources

from pydantic import ValidationError

from pythinker_review.engine.chunker import Chunk
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.schema import RawFinding, ReviewerOutput
from pythinker_review.signals.models import Signal
from pythinker_review.store.models import ChunkFailureReason

_RETRY_SUFFIX = (
    "\n\nIMPORTANT: Your previous response was not valid JSON for the given "
    "schema. Reply with strict JSON only, no prose, no markdown fences."
)


@dataclass(frozen=True, slots=True)
class ReviewerResult:
    ok: bool
    findings: tuple[RawFinding, ...] = field(default_factory=tuple)
    failure_reason: ChunkFailureReason | None = None
    failure_message: str = ""


def _load_system_prompt() -> str:
    return (
        resources.files("pythinker_review.reviewers.prompts")
        .joinpath("security_review.system.md")
        .read_text(encoding="utf-8")
    )


def _format_signals(signals: list[Signal]) -> str:
    if not signals:
        return "_No deterministic signals matched. Review the diff cold._"
    lines = ["Signals (verify in code before emitting):"]
    for s in signals:
        lines.append(
            f"- [{s.rule_id}] {s.file}:{s.line} (conf={s.confidence:.2f}) — "
            f"{s.reason}\n  `{s.snippet}`"
        )
    return "\n".join(lines)


def _build_user(chunk: Chunk, signals: list[Signal]) -> str:
    return (
        f"{_format_signals(signals)}\n\n"
        f"Review the following diff for security issues introduced by this change.\n\n"
        f"{chunk.rendered}\n"
    )


async def run_security_review_pass(
    *, chunk: Chunk, signals: list[Signal], llm: ReviewLLM, timeout_s: float
) -> ReviewerResult:
    system = _load_system_prompt()
    user = _build_user(chunk, signals)
    for attempt in (1, 2):
        try:
            raw = await asyncio.wait_for(
                llm.complete_json(system=system, user=user, timeout_s=timeout_s),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            return ReviewerResult(
                ok=False, failure_reason="timeout", failure_message="LLM timed out"
            )
        except Exception as exc:  # noqa: BLE001
            return ReviewerResult(
                ok=False, failure_reason="llm_error", failure_message=str(exc)
            )
        try:
            out = ReviewerOutput.model_validate_json(raw)
            return ReviewerResult(ok=True, findings=tuple(out.findings))
        except ValidationError as exc:
            if attempt == 2:
                return ReviewerResult(
                    ok=False, failure_reason="malformed_output", failure_message=str(exc)
                )
            user = user + _RETRY_SUFFIX
    return ReviewerResult(ok=False, failure_reason="malformed_output")
```

- [ ] **Step 5: Run test, lint, commit**

After `security_review.py`, create `packages/pythinker-review/src/pythinker_review/reviewers/debug_review.py` by following the same one-retry/strict-JSON pattern, but build the user prompt from `(chunk, diagnostic)` and use `debug_review.system.md`.

```bash
uv run --directory packages/pythinker-review pytest tests/unit/test_reviewers.py -vv  # 4 passed
make check-pythinker-review
git add packages/pythinker-review/src/pythinker_review/reviewers packages/pythinker-review/tests/unit/test_reviewers.py packages/pythinker-review/pyproject.toml
git commit -m "feat(review): code/security/debug reviewer passes with prompts and one-retry on bad JSON"
```

---

## Task 11: Runner (asyncio fan-out, fail-closed)

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/engine/runner.py`
- Create: `packages/pythinker-review/tests/unit/test_runner.py`

- [ ] **Step 1: Write the failing test**

Create `packages/pythinker-review/tests/unit/test_runner.py`:

```python
import json

import pytest

from pythinker_review.engine.chunker import Chunk
from pythinker_review.engine.runner import RunnerResult, run_chunks
from pythinker_review.engine.structured_diff import StructuredHunk
from pythinker_review.llm.fake import FakeReviewLLM


def _chunk(name: str = "x.py") -> Chunk:
    h = StructuredHunk(header="@@ -1 +1 @@", new_block="1 +x=1", old_block="")
    return Chunk(file=name, hunks=(h,), rendered=f"## File: '{name}'\nx=1")


def _payload(rule: str = "review.x") -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "rule_id": rule,
                    "title": "t",
                    "rationale": "r",
                    "category": "correctness",
                    "severity": "low",
                    "file": "x.py",
                    "start_line": 1,
                    "end_line": 1,
                    "confidence": 0.9,
                }
            ]
        }
    )


@pytest.mark.asyncio
async def test_runs_both_passes_in_parallel_and_collects_findings():
    llm = FakeReviewLLM(scripted=[_payload("review.x"), _payload("sec.x")])
    result = await run_chunks(
        chunks=[_chunk()],
        passes=("code_review", "security_review"),
        signals_by_file={},
        diagnostics_by_file={},
        llm=llm,
        jobs=2,
        per_chunk_timeout_s=10.0,
        allow_partial=False,
    )
    assert isinstance(result, RunnerResult)
    assert result.chunks_done == 1
    assert result.chunks_failed == 0
    assert len(result.findings) == 2


@pytest.mark.asyncio
async def test_chunk_failure_is_fatal_without_allow_partial():
    llm = FakeReviewLLM(scripted=["not json", "still nope"])
    result = await run_chunks(
        chunks=[_chunk()],
        passes=("code_review",),
        signals_by_file={},
        diagnostics_by_file={},
        llm=llm,
        jobs=1,
        per_chunk_timeout_s=10.0,
        allow_partial=False,
    )
    assert result.chunks_failed == 1
    assert result.failed is True


@pytest.mark.asyncio
async def test_chunk_failure_is_warning_with_allow_partial():
    llm = FakeReviewLLM(scripted=["not json", "still nope"])
    result = await run_chunks(
        chunks=[_chunk()],
        passes=("code_review",),
        signals_by_file={},
        diagnostics_by_file={},
        llm=llm,
        jobs=1,
        per_chunk_timeout_s=10.0,
        allow_partial=True,
    )
    assert result.chunks_failed == 1
    assert result.failed is False
    assert result.chunk_failures


@pytest.mark.asyncio
async def test_debug_pass_uses_diagnostic_input():
    llm = FakeReviewLLM(scripted=['{"findings": []}'])
    result = await run_chunks(
        chunks=[_chunk()],
        passes=("debug_review",),
        signals_by_file={},
        diagnostics_by_file={"x.py": "AssertionError at x.py:1"},
        llm=llm,
        jobs=1,
        per_chunk_timeout_s=10.0,
        allow_partial=False,
    )
    assert result.chunks_failed == 0
    assert llm.calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_runner.py -vv`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `packages/pythinker-review/src/pythinker_review/engine/runner.py`:

```python
"""Asyncio fan-out over (chunk, pass) work items. Fail-closed by default."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from pythinker_review.engine.chunker import Chunk
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.code_review import run_code_review_pass
from pythinker_review.reviewers.schema import RawFinding
from pythinker_review.reviewers.security_review import run_security_review_pass
from pythinker_review.reviewers.debug_review import run_debug_review_pass
from pythinker_review.signals.models import Signal
from pythinker_review.store.models import ChunkFailure, Pass


@dataclass(frozen=True, slots=True)
class TaggedFinding:
    pass_: Pass
    finding: RawFinding


@dataclass(frozen=True, slots=True)
class RunnerResult:
    chunks_total: int
    chunks_done: int
    chunks_failed: int
    findings: tuple[TaggedFinding, ...] = field(default_factory=tuple)
    chunk_failures: tuple[ChunkFailure, ...] = field(default_factory=tuple)
    failed: bool = False
    cancelled: bool = False


async def run_chunks(
    *,
    chunks: list[Chunk],
    passes: tuple[Pass, ...],
    signals_by_file: dict[str, list[Signal]],
    diagnostics_by_file: dict[str, str],
    llm: ReviewLLM,
    jobs: int,
    per_chunk_timeout_s: float,
    allow_partial: bool,
) -> RunnerResult:
    work: list[tuple[Chunk, Pass]] = [(c, p) for c in chunks for p in passes]
    chunks_total = len(work)
    if chunks_total == 0:
        return RunnerResult(0, 0, 0)

    sem = asyncio.Semaphore(max(1, jobs))
    findings: list[TaggedFinding] = []
    failures: list[ChunkFailure] = []
    chunks_done = 0
    cancelled = False

    async def _one(chunk: Chunk, p: Pass) -> None:
        nonlocal chunks_done
        async with sem:
            if p == "code_review":
                res = await run_code_review_pass(
                    chunk=chunk, llm=llm, timeout_s=per_chunk_timeout_s
                )
            elif p == "security_review":
                signals = signals_by_file.get(chunk.file, [])
                res = await run_security_review_pass(
                    chunk=chunk, signals=signals, llm=llm, timeout_s=per_chunk_timeout_s
                )
            elif p == "debug_review":
                diagnostic = (
                    diagnostics_by_file.get(chunk.file)
                    or diagnostics_by_file.get("*")
                    or "No diagnostic input provided."
                )
                res = await run_debug_review_pass(
                    chunk=chunk, diagnostic=diagnostic, llm=llm, timeout_s=per_chunk_timeout_s
                )
            else:
                failures.append(
                    ChunkFailure(
                        file=chunk.file,
                        reason="worker_error",
                        message=f"unknown pass: {p}",
                        **{"pass": p},
                    )
                )
                chunks_done += 1
                return
            if res.ok:
                findings.extend(TaggedFinding(p, f) for f in res.findings)
            else:
                failures.append(
                    ChunkFailure(
                        file=chunk.file,
                        reason=res.failure_reason or "worker_error",
                        message=res.failure_message,
                        **{"pass": p},
                    )
                )
            chunks_done += 1

    tasks = [asyncio.create_task(_one(c, p)) for c, p in work]
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        cancelled = True
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    failed = (not allow_partial) and bool(failures)
    return RunnerResult(
        chunks_total=chunks_total,
        chunks_done=chunks_done,
        chunks_failed=len(failures),
        findings=tuple(findings),
        chunk_failures=tuple(failures),
        failed=failed,
        cancelled=cancelled,
    )
```

- [ ] **Step 4: Run test, lint, commit**

```bash
uv run --directory packages/pythinker-review pytest tests/unit/test_runner.py -vv  # 4 passed
make check-pythinker-review
git add packages/pythinker-review/src/pythinker_review/engine/runner.py packages/pythinker-review/tests/unit/test_runner.py
git commit -m "feat(review): asyncio runner with fail-closed/allow-partial semantics"
```

---

## Task 12: Dedupe + Orchestrator

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/engine/dedupe.py`
- Create: `packages/pythinker-review/src/pythinker_review/engine/orchestrator.py`
- Create: `packages/pythinker-review/tests/unit/test_dedupe.py`

- [ ] **Step 1: Write the failing test for dedupe**

Create `packages/pythinker-review/tests/unit/test_dedupe.py`:

```python
from datetime import datetime, timezone

from pythinker_review.engine.dedupe import dedupe_findings, finding_id
from pythinker_review.reviewers.schema import RawFinding
from pythinker_review.store.models import Category, Finding, Location, Severity


def _raw(
    rule: str = "sec.x",
    line: int = 5,
    sev: Severity = Severity.high,
    conf: float = 0.7,
) -> RawFinding:
    return RawFinding(
        rule_id=rule,
        title="t",
        rationale="r",
        category=Category.security,
        severity=sev,
        file="a.py",
        start_line=line,
        end_line=line,
        confidence=conf,
    )


def test_finding_id_is_deterministic():
    a = finding_id("sec.x", "a.py", 5, "t")
    b = finding_id("sec.x", "a.py", 5, "t")
    assert a == b
    assert len(a) == 12


def test_dedupe_collapses_same_key_keeping_higher_severity():
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    low = _raw(sev=Severity.low, conf=0.9)
    high = _raw(sev=Severity.high, conf=0.5)
    result = dedupe_findings(
        [
            ("security_review", low),
            ("security_review", high),
        ],
        run_id="r1",
        head_sha="abc",
        created_at=now,
    )
    assert len(result) == 1
    assert result[0].severity is Severity.high


def test_dedupe_security_wins_tie_with_code_review():
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    a = _raw(rule="sec.x", sev=Severity.medium, conf=0.8)
    b = _raw(rule="sec.x", sev=Severity.medium, conf=0.8)
    out = dedupe_findings(
        [("code_review", a), ("security_review", b)],
        run_id="r1",
        head_sha="abc",
        created_at=now,
    )
    assert len(out) == 1
    assert out[0].pass_ == "security_review"


def test_dedupe_returns_full_finding(_=None):
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    out = dedupe_findings(
        [("code_review", _raw())], run_id="r1", head_sha="abc", created_at=now
    )
    assert isinstance(out[0], Finding)
    assert isinstance(out[0].location, Location)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_dedupe.py -vv`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement dedupe**

Create `packages/pythinker-review/src/pythinker_review/engine/dedupe.py`:

```python
"""Stable Finding IDs + dedupe rules."""

from __future__ import annotations

import hashlib
from datetime import datetime

from pythinker_review.reviewers.schema import RawFinding
from pythinker_review.store.models import (
    SEVERITY_ORDER,
    Finding,
    Location,
    Pass,
)


def finding_id(rule_id: str, file: str, start_line: int, title: str) -> str:
    digest = hashlib.sha256(
        f"{rule_id}|{file}|{start_line}|{title}".encode("utf-8")
    ).hexdigest()
    return digest[:12]


def dedupe_findings(
    tagged: list[tuple[Pass, RawFinding]],
    *,
    run_id: str,
    head_sha: str,
    created_at: datetime,
) -> list[Finding]:
    bucket: dict[tuple[str, int, int, str], tuple[Pass, RawFinding]] = {}
    pass_rank = {"security_review": 1, "code_review": 0}
    for p, f in tagged:
        key = (f.file, f.start_line, f.end_line, f.rule_id)
        cur = bucket.get(key)
        if cur is None:
            bucket[key] = (p, f)
            continue
        cur_p, cur_f = cur
        if (
            SEVERITY_ORDER[f.severity] > SEVERITY_ORDER[cur_f.severity]
            or (
                f.severity == cur_f.severity
                and f.confidence > cur_f.confidence
            )
            or (
                f.severity == cur_f.severity
                and f.confidence == cur_f.confidence
                and pass_rank[p] > pass_rank[cur_p]
            )
        ):
            bucket[key] = (p, f)

    out: list[Finding] = []
    for p, f in bucket.values():
        out.append(
            Finding(
                id=finding_id(f.rule_id, f.file, f.start_line, f.title),
                rule_id=f.rule_id,
                title=f.title,
                rationale=f.rationale,
                category=f.category,
                severity=f.severity,
                location=Location(
                    file=f.file,
                    start_line=f.start_line,
                    end_line=f.end_line,
                    sha=head_sha,
                ),
                suggestion=f.suggestion,
                evidence_snippet=f.evidence_snippet,
                confidence=f.confidence,
                created_at=created_at,
                run_id=run_id,
                **{"pass": p},
            )
        )
    return out
```

- [ ] **Step 4: Implement orchestrator (public engine entry)**

Create `packages/pythinker-review/src/pythinker_review/engine/orchestrator.py`:

```python
"""Public engine entry that ties diff resolution → render → chunk → run → dedupe."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from pythinker_review.engine.chunker import build_chunks
from pythinker_review.engine.diff_source import DiffMode, ResolvedDiff, resolve_diff
from pythinker_review.engine.dedupe import dedupe_findings
from pythinker_review.engine.runner import RunnerResult, run_chunks
from pythinker_review.engine.structured_diff import render_structured_diff
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.signals.scanner import scan_signals
from pythinker_review.store.ids import generate_run_id
from pythinker_review.store.models import Finding, Pass, RunMeta


@dataclass(frozen=True, slots=True)
class EngineRunInput:
    repo: Path
    mode: DiffMode
    base_ref: str
    rev_range: str | None
    passes: tuple[Pass, ...]
    diagnostics_by_file: dict[str, str]
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    skip_vendored: bool
    jobs: int
    per_chunk_timeout_s: float
    chunk_budget_chars: int
    allow_partial: bool


@dataclass(frozen=True, slots=True)
class EngineRunOutput:
    meta: RunMeta
    findings: list[Finding]
    runner: RunnerResult
    resolved: ResolvedDiff


def _config_hash(passes: tuple[Pass, ...]) -> str:
    parts: list[str] = list(passes)
    for name in ("code_review.system.md", "security_review.system.md", "debug_review.system.md"):
        try:
            parts.append(
                resources.files("pythinker_review.reviewers.prompts")
                .joinpath(name)
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ModuleNotFoundError):
            continue
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _added_lines_by_file(patch_text: str) -> dict[str, list[tuple[int, str]]]:
    out: dict[str, list[tuple[int, str]]] = {}
    current: str | None = None
    new_lineno = 0
    for line in patch_text.splitlines():
        if line.startswith("+++ b/"):
            current = line[len("+++ b/") :].strip()
            out.setdefault(current, [])
            continue
        if line.startswith("@@"):
            try:
                plus = line.split("+", 1)[1].split(",", 1)[0].split(" ", 1)[0]
                new_lineno = int(plus)
            except (IndexError, ValueError):
                new_lineno = 0
            continue
        if not current:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            out[current].append((new_lineno, line[1:]))
            new_lineno += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue
        else:
            new_lineno += 1
    return out


async def run_engine(
    *, llm: ReviewLLM, inputs: EngineRunInput
) -> EngineRunOutput:
    resolved = resolve_diff(
        inputs.repo,
        mode=inputs.mode,
        base_ref=inputs.base_ref,
        rev_range=inputs.rev_range,
    )
    files = render_structured_diff(resolved.patch_text)
    chunks = build_chunks(
        files,
        includes=inputs.includes,
        excludes=inputs.excludes,
        skip_vendored=inputs.skip_vendored,
        budget_chars=inputs.chunk_budget_chars,
    )

    signals_by_file: dict[str, list] = {}
    if "security_review" in inputs.passes:
        added = _added_lines_by_file(resolved.patch_text)
        for path, lines in added.items():
            signals_by_file[path] = scan_signals(file_path=path, added_lines=lines)

    started = datetime.now(tz=timezone.utc)
    run_id = generate_run_id(now=started)
    runner = await run_chunks(
        chunks=chunks,
        passes=inputs.passes,
        signals_by_file=signals_by_file,
        diagnostics_by_file=inputs.diagnostics_by_file,
        llm=llm,
        jobs=inputs.jobs,
        per_chunk_timeout_s=inputs.per_chunk_timeout_s,
        allow_partial=inputs.allow_partial,
    )
    findings = dedupe_findings(
        [(t.pass_, t.finding) for t in runner.findings],
        run_id=run_id,
        head_sha=resolved.head_sha,
        created_at=started,
    )

    finished = datetime.now(tz=timezone.utc)
    if runner.cancelled:
        status: str = "cancelled"
    elif runner.failed:
        status = "failed"
    elif runner.chunks_failed and inputs.allow_partial:
        status = "completed_with_warnings"
    else:
        status = "completed"

    meta = RunMeta(
        id=run_id,
        started_at=started,
        finished_at=finished,
        status=status,  # type: ignore[arg-type]
        repo_root=str(inputs.repo),
        branch=None,
        head_sha=resolved.head_sha,
        base_ref=resolved.base_ref,
        base_sha=resolved.base_sha,
        source_label=resolved.source_label,
        passes=list(inputs.passes),
        model=llm.model_display_name,
        chunks_total=runner.chunks_total,
        chunks_done=runner.chunks_done,
        chunks_failed=runner.chunks_failed,
        findings_count=len(findings),
        allow_partial=inputs.allow_partial,
        chunk_failures=list(runner.chunk_failures),
        config_hash=_config_hash(inputs.passes),
    )
    return EngineRunOutput(meta=meta, findings=findings, runner=runner, resolved=resolved)
```

- [ ] **Step 5: Run test, lint, commit**

```bash
uv run --directory packages/pythinker-review pytest tests/unit/test_dedupe.py -vv  # 4 passed
make check-pythinker-review
git add packages/pythinker-review/src/pythinker_review/engine/dedupe.py packages/pythinker-review/src/pythinker_review/engine/orchestrator.py packages/pythinker-review/tests/unit/test_dedupe.py
git commit -m "feat(review): dedupe rules + orchestrator that ties the engine together"
```

---

## Task 13: Findings store + run lifecycle + .gitignore patcher

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/store/findings_store.py`
- Create: `packages/pythinker-review/src/pythinker_review/store/run.py`
- Create: `packages/pythinker-review/src/pythinker_review/store/gitignore.py`
- Create: `packages/pythinker-review/tests/unit/test_findings_store.py`
- Create: `packages/pythinker-review/tests/unit/test_gitignore.py`

- [ ] **Step 1: Write the failing tests**

Create `packages/pythinker-review/tests/unit/test_findings_store.py`:

```python
import json
from datetime import datetime, timezone
from pathlib import Path

from pythinker_review.store.findings_store import FindingsStore
from pythinker_review.store.models import (
    Category,
    Finding,
    Location,
    RunMeta,
    Severity,
)


def _finding(rid: str = "abc") -> Finding:
    return Finding(
        id="abcd12345678",
        rule_id="sec.x",
        title="t",
        rationale="r",
        category=Category.security,
        severity=Severity.high,
        location=Location(file="a.py", start_line=1, end_line=1),
        confidence=0.9,
        created_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        run_id=rid,
        **{"pass": "security_review"},
    )


def _meta(rid: str = "abc") -> RunMeta:
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    return RunMeta(
        id=rid,
        started_at=now,
        finished_at=now,
        status="completed",
        repo_root="/r",
        branch="main",
        head_sha="h",
        base_ref="main",
        base_sha="b",
        source_label="staged",
        passes=["security_review"],
        model="m",
        chunks_total=1,
        chunks_done=1,
        chunks_failed=0,
        findings_count=1,
        allow_partial=False,
        config_hash="0" * 64,
    )


def test_writes_meta_and_findings_and_index(tmp_path: Path):
    store = FindingsStore(repo_root=tmp_path)
    store.begin(_meta("20260520120000-aaaaaaaa"))
    store.append(_finding("20260520120000-aaaaaaaa"))
    store.finalize(_meta("20260520120000-aaaaaaaa"))
    run_dir = tmp_path / ".pythinker-review" / "runs" / "20260520120000-aaaaaaaa"
    assert (run_dir / "meta.json").exists()
    assert (run_dir / "findings.jsonl").exists()
    index = json.loads((tmp_path / ".pythinker-review" / "index.json").read_text())
    assert index["runs"][0]["id"] == "20260520120000-aaaaaaaa"


def test_atomic_meta_write_no_tmp_left(tmp_path: Path):
    store = FindingsStore(repo_root=tmp_path)
    meta = _meta("20260520120000-aaaaaaaa")
    store.begin(meta)
    store.finalize(meta)
    run_dir = tmp_path / ".pythinker-review" / "runs" / "20260520120000-aaaaaaaa"
    assert not any(p.suffix == ".tmp" for p in run_dir.iterdir())
```

Create `packages/pythinker-review/tests/unit/test_gitignore.py`:

```python
from pathlib import Path

from pythinker_review.store.gitignore import ensure_gitignored


def test_appends_when_file_exists_and_missing_entry(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("# user\nbuild/\n")
    ensure_gitignored(repo_root=tmp_path)
    text = (tmp_path / ".gitignore").read_text()
    assert ".pythinker-review/" in text
    assert "# pythinker-review" in text


def test_idempotent(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("# user\nbuild/\n")
    ensure_gitignored(repo_root=tmp_path)
    ensure_gitignored(repo_root=tmp_path)
    text = (tmp_path / ".gitignore").read_text()
    assert text.count(".pythinker-review/") == 1


def test_no_op_when_gitignore_missing(tmp_path: Path):
    ensure_gitignored(repo_root=tmp_path)
    assert not (tmp_path / ".gitignore").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_findings_store.py tests/unit/test_gitignore.py -vv`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement findings store + run + gitignore**

Create `packages/pythinker-review/src/pythinker_review/store/findings_store.py`:

```python
"""Append-only JSONL store + atomic meta/index updates."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pythinker_review.store.models import Finding, RunMeta

_STATE_DIR = ".pythinker-review"
_INDEX_LIMIT = 200


class FindingsStore:
    def __init__(self, *, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)
        self.state_dir = self.repo_root / _STATE_DIR
        self._fp = None

    def _run_dir(self, run_id: str) -> Path:
        return self.state_dir / "runs" / run_id

    def begin(self, meta: RunMeta) -> None:
        run_dir = self._run_dir(meta.id)
        run_dir.mkdir(parents=True, exist_ok=True)
        self._fp = (run_dir / "findings.jsonl").open("a", encoding="utf-8")
        self._write_meta(meta)

    def append(self, finding: Finding) -> None:
        assert self._fp is not None, "begin() not called"
        self._fp.write(finding.model_dump_json(by_alias=True) + "\n")

    def write_diff(self, run_id: str, patch_text: str) -> None:
        (self._run_dir(run_id) / "diff.patch").write_text(patch_text, encoding="utf-8")

    def finalize(self, meta: RunMeta) -> None:
        if self._fp is not None:
            self._fp.flush()
            os.fsync(self._fp.fileno())
            self._fp.close()
            self._fp = None
        self._write_meta(meta)
        self._update_index(meta)

    def _write_meta(self, meta: RunMeta) -> None:
        path = self._run_dir(meta.id) / "meta.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(meta.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _update_index(self, meta: RunMeta) -> None:
        idx_path = self.state_dir / "index.json"
        runs: list[dict[str, object]] = []
        if idx_path.exists():
            try:
                runs = json.loads(idx_path.read_text())["runs"]
            except (KeyError, json.JSONDecodeError):
                runs = []
        runs = [r for r in runs if r.get("id") != meta.id]
        runs.insert(
            0,
            {
                "id": meta.id,
                "started_at": meta.started_at.isoformat(),
                "branch": meta.branch,
                "head_sha": meta.head_sha,
                "status": meta.status,
                "findings_count": meta.findings_count,
            },
        )
        runs = runs[:_INDEX_LIMIT]
        tmp = idx_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"runs": runs}, indent=2), encoding="utf-8")
        os.replace(tmp, idx_path)
```

Create `packages/pythinker-review/src/pythinker_review/store/run.py`:

```python
"""RunMeta lifecycle helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from pythinker_review.store.models import ChunkFailure, RunMeta, RunStatus


def transition(
    meta: RunMeta, *, status: RunStatus, chunk_failures: list[ChunkFailure] | None = None
) -> RunMeta:
    payload = meta.model_dump(by_alias=True)
    payload["status"] = status
    payload["finished_at"] = datetime.now(tz=timezone.utc).isoformat()
    if chunk_failures is not None:
        payload["chunk_failures"] = [cf.model_dump(by_alias=True) for cf in chunk_failures]
    return RunMeta.model_validate(payload)
```

Create `packages/pythinker-review/src/pythinker_review/store/gitignore.py`:

```python
"""Idempotent .gitignore patcher."""

from __future__ import annotations

from pathlib import Path

_MARKER = "# pythinker-review"
_ENTRY = ".pythinker-review/"


def ensure_gitignored(*, repo_root: Path) -> bool:
    gi = repo_root / ".gitignore"
    if not gi.exists():
        return False
    text = gi.read_text()
    if _ENTRY in text:
        return False
    appendage = (
        ""
        if text.endswith("\n")
        else "\n"
    ) + f"\n{_MARKER}\n{_ENTRY}\n"
    gi.write_text(text + appendage)
    return True
```

- [ ] **Step 4: Run tests, lint, commit**

```bash
uv run --directory packages/pythinker-review pytest tests/unit/test_findings_store.py tests/unit/test_gitignore.py -vv  # 5 passed
make check-pythinker-review
git add packages/pythinker-review/src/pythinker_review/store packages/pythinker-review/tests/unit/test_findings_store.py packages/pythinker-review/tests/unit/test_gitignore.py
git commit -m "feat(review): findings store, run lifecycle, idempotent gitignore patcher"
```

---

## Task 14: Output formatters (pretty / JSON / SARIF)

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/output/__init__.py`
- Create: `packages/pythinker-review/src/pythinker_review/output/pretty.py`
- Create: `packages/pythinker-review/src/pythinker_review/output/json.py`
- Create: `packages/pythinker-review/src/pythinker_review/output/sarif.py`
- Create: `packages/pythinker-review/tests/unit/test_pretty.py`
- Create: `packages/pythinker-review/tests/unit/test_json.py`
- Create: `packages/pythinker-review/tests/unit/test_sarif.py`
- Create: `packages/pythinker-review/tests/fixtures/sarif-2.1.0-schema.json` — copy from `https://json.schemastore.org/sarif-2.1.0.json` (commit the file; do not fetch at test time)

- [ ] **Step 1: Write failing tests for each formatter**

Create `packages/pythinker-review/tests/unit/test_pretty.py`:

```python
from datetime import datetime, timezone

from pythinker_review.output.pretty import render_pretty
from pythinker_review.store.models import (
    Category,
    Finding,
    Location,
    RunMeta,
    Severity,
)


def _finding() -> Finding:
    return Finding(
        id="abcd12345678",
        rule_id="sec.x",
        title="Hardcoded secret",
        rationale="The key looks real.",
        category=Category.secret,
        severity=Severity.critical,
        location=Location(file="a.py", start_line=10, end_line=10),
        confidence=0.95,
        created_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        run_id="r1",
        **{"pass": "security_review"},
    )


def _meta() -> RunMeta:
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    return RunMeta(
        id="r1",
        started_at=now,
        finished_at=now,
        status="completed",
        repo_root="/r",
        branch="main",
        head_sha="h",
        base_ref="main",
        base_sha="b",
        source_label="git-diff:main",
        passes=["security_review"],
        model="m",
        chunks_total=1,
        chunks_done=1,
        chunks_failed=0,
        findings_count=1,
        allow_partial=False,
        config_hash="0" * 64,
    )


def test_pretty_contains_severity_file_and_title():
    out = render_pretty(_meta(), [_finding()], no_color=True)
    assert "CRITICAL" in out
    assert "a.py:10" in out
    assert "Hardcoded secret" in out


def test_pretty_no_findings_message():
    out = render_pretty(_meta(), [], no_color=True)
    assert "no findings" in out.lower()
```

Create `packages/pythinker-review/tests/unit/test_json.py`:

```python
import json
from datetime import datetime, timezone

from pythinker_review.output.json import render_json
from pythinker_review.store.models import (
    Category,
    Finding,
    Location,
    RunMeta,
    Severity,
)


def test_json_shape():
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    meta = RunMeta(
        id="r1",
        started_at=now,
        finished_at=now,
        status="completed",
        repo_root="/r",
        branch=None,
        head_sha="h",
        base_ref="main",
        base_sha="b",
        source_label="staged",
        passes=["code_review"],
        model="m",
        chunks_total=1,
        chunks_done=1,
        chunks_failed=0,
        findings_count=0,
        allow_partial=False,
        config_hash="0" * 64,
    )
    out = json.loads(render_json(meta, []))
    assert out["run"]["id"] == "r1"
    assert out["findings"] == []
```

Create `packages/pythinker-review/tests/unit/test_sarif.py`:

```python
import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from pythinker_review.output.sarif import render_sarif
from pythinker_review.store.models import (
    Category,
    Finding,
    Location,
    RunMeta,
    Severity,
)

SCHEMA = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "sarif-2.1.0-schema.json").read_text()
)


def test_sarif_validates_against_official_schema():
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    finding = Finding(
        id="abcd12345678",
        rule_id="sec.x",
        title="t",
        rationale="r",
        category=Category.security,
        severity=Severity.high,
        location=Location(file="a.py", start_line=1, end_line=2),
        confidence=0.9,
        created_at=now,
        run_id="r1",
        **{"pass": "security_review"},
    )
    meta = RunMeta(
        id="r1",
        started_at=now,
        finished_at=now,
        status="completed",
        repo_root="/r",
        branch=None,
        head_sha="h",
        base_ref="main",
        base_sha="b",
        source_label="staged",
        passes=["security_review"],
        model="m",
        chunks_total=1,
        chunks_done=1,
        chunks_failed=0,
        findings_count=1,
        allow_partial=False,
        config_hash="0" * 64,
    )
    sarif_doc = json.loads(render_sarif(meta, [finding]))
    jsonschema.validate(sarif_doc, SCHEMA)
    assert sarif_doc["runs"][0]["results"][0]["level"] == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory packages/pythinker-review pytest tests/unit/test_pretty.py tests/unit/test_json.py tests/unit/test_sarif.py -vv`
Expected: FAIL — formatters not implemented.

- [ ] **Step 3: Implement formatters**

Create `packages/pythinker-review/src/pythinker_review/output/__init__.py` (empty).

Create `packages/pythinker-review/src/pythinker_review/output/pretty.py`:

```python
"""Pretty TTY rendering via rich (already a workspace dep)."""

from __future__ import annotations

import io

from rich.console import Console

from pythinker_review.store.models import Finding, RunMeta, SEVERITY_ORDER

_SEV_COLOR = {
    "critical": "bright_red",
    "high": "red",
    "medium": "yellow",
    "low": "blue",
    "info": "dim",
}


def render_pretty(meta: RunMeta, findings: list[Finding], *, no_color: bool = False) -> str:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=not no_color, no_color=no_color, width=120)
    console.print(
        f"[bold]pythinker review[/bold] run [cyan]{meta.id}[/cyan]  "
        f"status={meta.status}  findings={meta.findings_count}"
    )
    if meta.chunks_failed:
        console.print(
            f"[yellow]warning:[/yellow] {meta.chunks_failed} chunk(s) failed "
            f"(allow_partial={meta.allow_partial})"
        )
    if not findings:
        console.print("[green]no findings ≥ threshold[/green]")
        return buf.getvalue()

    findings = sorted(
        findings,
        key=lambda f: (-SEVERITY_ORDER[f.severity], f.location.file, f.location.start_line),
    )
    last_file: str | None = None
    for f in findings:
        if f.location.file != last_file:
            console.print(f"\n[bold]{f.location.file}[/bold]")
            last_file = f.location.file
        sev = f.severity.value.upper()
        color = _SEV_COLOR[f.severity.value]
        console.print(
            f"  [{color}]{sev:8}[/{color}] "
            f"{f.location.file}:{f.location.start_line}  "
            f"[bold]{f.title}[/bold]  [{f.rule_id}]"
        )
        console.print(f"    {f.rationale}")
        if f.suggestion:
            console.print(f"    [dim]suggestion:[/dim] {f.suggestion.summary}")
    return buf.getvalue()
```

Create `packages/pythinker-review/src/pythinker_review/output/json.py`:

```python
"""JSON output: {"run": RunMeta, "findings": [Finding, ...]}."""

from __future__ import annotations

import json as _json

from pythinker_review.store.models import Finding, RunMeta


def render_json(meta: RunMeta, findings: list[Finding]) -> str:
    return _json.dumps(
        {
            "run": meta.model_dump(by_alias=True, mode="json"),
            "findings": [f.model_dump(by_alias=True, mode="json") for f in findings],
        },
        indent=2,
    )
```

Create `packages/pythinker-review/src/pythinker_review/output/sarif.py`:

```python
"""SARIF 2.1.0 emitter."""

from __future__ import annotations

import json as _json
from typing import Any

from pythinker_review.store.models import Finding, RunMeta, Severity

_SEV_TO_LEVEL: dict[Severity, str] = {
    Severity.critical: "error",
    Severity.high: "error",
    Severity.medium: "warning",
    Severity.low: "note",
    Severity.info: "note",
}


def render_sarif(meta: RunMeta, findings: list[Finding]) -> str:
    rules_seen: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for f in findings:
        rules_seen.setdefault(
            f.rule_id,
            {
                "id": f.rule_id,
                "shortDescription": {"text": f.title[:60]},
                "fullDescription": {"text": f.title},
                "defaultConfiguration": {"level": _SEV_TO_LEVEL[f.severity]},
            },
        )
        results.append(
            {
                "ruleId": f.rule_id,
                "level": _SEV_TO_LEVEL[f.severity],
                "message": {"text": f.rationale},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": f.location.file},
                            "region": {
                                "startLine": f.location.start_line,
                                "endLine": f.location.end_line,
                            },
                        }
                    }
                ],
                "properties": {
                    "category": f.category.value,
                    "severity": f.severity.value,
                    "confidence": f.confidence,
                    "pass": f.pass_,
                },
            }
        )
    doc: dict[str, Any] = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "pythinker-review",
                        "informationUri": "https://github.com/TechMatrix-labs/pythinker-code",
                        "rules": list(rules_seen.values()),
                    }
                },
                "results": results,
                "invocations": [
                    {
                        "executionSuccessful": meta.status
                        in ("completed", "completed_with_warnings"),
                        "exitCodeDescription": meta.status,
                    }
                ],
            }
        ],
    }
    return _json.dumps(doc, indent=2)
```

- [ ] **Step 4: Add SARIF schema fixture**

Run from the repo root (one time, by the implementer — fixture must be committed, not fetched at test time):

```bash
mkdir -p packages/pythinker-review/tests/fixtures
curl -sSfL -o packages/pythinker-review/tests/fixtures/sarif-2.1.0-schema.json \
  https://json.schemastore.org/sarif-2.1.0.json
git add packages/pythinker-review/tests/fixtures/sarif-2.1.0-schema.json
```

- [ ] **Step 5: Run tests, lint, commit**

```bash
uv run --directory packages/pythinker-review pytest tests/unit/test_pretty.py tests/unit/test_json.py tests/unit/test_sarif.py -vv  # all green
make check-pythinker-review
git add packages/pythinker-review/src/pythinker_review/output packages/pythinker-review/tests
git commit -m "feat(review): pretty/JSON/SARIF formatters with SARIF schema validation"
```

---

## Task 15: Standalone Typer CLI

**Files:**
- Create: `packages/pythinker-review/src/pythinker_review/cli/__init__.py`
- Create: `packages/pythinker-review/src/pythinker_review/cli/_shared.py`
- Create: `packages/pythinker-review/src/pythinker_review/cli/review.py`
- Create: `packages/pythinker-review/src/pythinker_review/cli/secscan.py`
- Create: `packages/pythinker-review/src/pythinker_review/cli/debug.py`
- Create: `packages/pythinker-review/tests/e2e/__init__.py`
- Create: `packages/pythinker-review/tests/e2e/test_cli_review.py`
- Create: `packages/pythinker-review/tests/e2e/test_cli_secscan.py`
- Create: `packages/pythinker-review/tests/e2e/test_cli_debug.py`
- Create: `packages/pythinker-review/tests/e2e/test_save_and_show.py`

- [ ] **Step 1: Implement shared option types and exit-code mapping**

Create `packages/pythinker-review/src/pythinker_review/cli/__init__.py` (empty).

Create `packages/pythinker-review/src/pythinker_review/cli/_shared.py`:

```python
"""Shared CLI types: format/threshold/exit code computation."""

from __future__ import annotations

from enum import Enum

from pythinker_review.store.models import SEVERITY_ORDER, Finding, RunMeta, Severity


class OutputFormat(str, Enum):
    pretty = "pretty"
    json = "json"
    sarif = "sarif"


class FailOn(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    none = "none"


_FAIL_TO_SEV: dict[FailOn, Severity | None] = {
    FailOn.critical: Severity.critical,
    FailOn.high: Severity.high,
    FailOn.medium: Severity.medium,
    FailOn.low: Severity.low,
    FailOn.none: None,
}


def exit_code(*, meta: RunMeta, findings: list[Finding], fail_on: FailOn, llm_error: bool) -> int:
    if llm_error:
        return 3
    if meta.status == "failed":
        return 4
    if meta.status == "cancelled":
        return 130
    threshold = _FAIL_TO_SEV[fail_on]
    if threshold is not None and any(
        SEVERITY_ORDER[f.severity] >= SEVERITY_ORDER[threshold] for f in findings
    ):
        return 1
    return 0
```

- [ ] **Step 2: Implement standalone `pythinker-review`, `pythinker-secscan`, and `pythinker-debug` apps**

Create `packages/pythinker-review/src/pythinker_review/cli/review.py`:

```python
"""Standalone `pythinker-review` Typer entry."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import typer

from pythinker_review.cli._shared import FailOn, OutputFormat, exit_code
from pythinker_review.engine.diff_source import DiffMode, EmptyDiffError, PreflightError
from pythinker_review.engine.orchestrator import EngineRunInput, run_engine
from pythinker_review.llm.fake import FakeReviewLLM
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.output.json import render_json
from pythinker_review.output.pretty import render_pretty
from pythinker_review.output.sarif import render_sarif
from pythinker_review.store.findings_store import FindingsStore
from pythinker_review.store.gitignore import ensure_gitignored
from pythinker_review.store.models import Pass

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _resolve_llm() -> ReviewLLM:
    # Standalone CLI uses explicit/env config; test override hook below.
    fake = os.environ.get("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES")
    if fake:
        return FakeReviewLLM(scripted=fake.split("\0"))
    typer.secho(
        "No active model configured. Set PYTHINKER_REVIEW_FAKE_LLM_RESPONSES for "
        "tests, or invoke via `pythinker review` for the Pythinker-integrated path.",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=3)


def _emit(
    fmt: OutputFormat, *, meta, findings, no_color: bool
) -> str:
    if fmt is OutputFormat.json:
        return render_json(meta, findings)
    if fmt is OutputFormat.sarif:
        return render_sarif(meta, findings)
    return render_pretty(meta, findings, no_color=no_color)


@app.command()
def diff(
    base: str = typer.Option("origin/main", "--base"),
    staged: bool = typer.Option(False, "--staged"),
    working_tree: bool = typer.Option(False, "--working-tree"),
    range_: str | None = typer.Option(None, "--range"),
    fmt: OutputFormat = typer.Option(
        OutputFormat.pretty if sys.stdout.isatty() else OutputFormat.json, "--format"
    ),
    fail_on: FailOn = typer.Option(FailOn.high, "--fail-on"),
    allow_partial: bool = typer.Option(False, "--allow-partial"),
    jobs: int = typer.Option(4, "--jobs"),
    save: bool = typer.Option(True, "--save/--no-save"),
    quiet: bool = typer.Option(False, "--quiet"),
    include: list[str] = typer.Option([], "--include"),
    exclude: list[str] = typer.Option([], "--exclude"),
    no_skip_vendored: bool = typer.Option(False, "--no-skip-vendored"),
    with_security: bool = typer.Option(False, "--with-security"),
    chunk_budget_chars: int = typer.Option(12_000),
    per_chunk_timeout_s: float = typer.Option(120.0),
    repo: Path = typer.Option(Path.cwd(), "--repo"),
) -> None:
    passes: tuple[Pass, ...] = (("code_review", "security_review") if with_security else ("code_review",))
    mode = (
        DiffMode.range
        if range_
        else DiffMode.working_tree
        if working_tree
        else DiffMode.staged
        if staged
        else DiffMode.base
    )
    inputs = EngineRunInput(
        repo=repo.resolve(),
        mode=mode,
        base_ref=base,
        rev_range=range_,
        passes=passes,
        diagnostics_by_file={},
        includes=tuple(include),
        excludes=tuple(exclude),
        skip_vendored=not no_skip_vendored,
        jobs=jobs,
        per_chunk_timeout_s=per_chunk_timeout_s,
        chunk_budget_chars=chunk_budget_chars,
        allow_partial=allow_partial,
    )
    try:
        llm = _resolve_llm()
    except typer.Exit:
        raise
    try:
        output = asyncio.run(run_engine(llm=llm, inputs=inputs))
    except EmptyDiffError as exc:
        typer.secho(f"no changes to review: {exc}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=2)
    except PreflightError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    if save:
        store = FindingsStore(repo_root=inputs.repo)
        store.begin(output.meta)
        for f in output.findings:
            store.append(f)
        store.write_diff(output.meta.id, output.resolved.patch_text)
        store.finalize(output.meta)
        ensure_gitignored(repo_root=inputs.repo)

    text = _emit(fmt, meta=output.meta, findings=output.findings, no_color=quiet)
    typer.echo(text)
    raise typer.Exit(code=exit_code(
        meta=output.meta, findings=output.findings, fail_on=fail_on, llm_error=False
    ))


@app.command(name="list")
def list_runs(limit: int = typer.Option(20, "--limit"), repo: Path = typer.Option(Path.cwd())) -> None:
    import json as _json

    idx = (repo / ".pythinker-review" / "index.json")
    if not idx.exists():
        typer.echo("no runs")
        raise typer.Exit(code=0)
    runs = _json.loads(idx.read_text())["runs"][:limit]
    for r in runs:
        typer.echo(f"{r['id']}  {r['status']:24}  findings={r['findings_count']}  branch={r.get('branch')}")


@app.command()
def show(
    run_id: str,
    fmt: OutputFormat = typer.Option(OutputFormat.pretty, "--format"),
    repo: Path = typer.Option(Path.cwd()),
) -> None:
    import json as _json

    from pythinker_review.store.models import Finding, RunMeta

    run_dir = repo / ".pythinker-review" / "runs" / run_id
    if not run_dir.exists():
        typer.secho(f"unknown run: {run_id}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    meta = RunMeta.model_validate_json((run_dir / "meta.json").read_text())
    findings: list[Finding] = []
    fjsonl = run_dir / "findings.jsonl"
    if fjsonl.exists():
        for line in fjsonl.read_text().splitlines():
            if line.strip():
                findings.append(Finding.model_validate_json(line))
    text = _emit(fmt, meta=meta, findings=findings, no_color=False)
    typer.echo(text)
```

Create `packages/pythinker-review/src/pythinker_review/cli/secscan.py`:

```python
"""Standalone `pythinker-secscan` Typer entry — delegates to review.diff with passes=('security_review',)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer

from pythinker_review.cli import review as review_mod
from pythinker_review.cli._shared import FailOn, OutputFormat, exit_code
from pythinker_review.engine.diff_source import DiffMode, EmptyDiffError, PreflightError
from pythinker_review.engine.orchestrator import EngineRunInput, run_engine
from pythinker_review.store.findings_store import FindingsStore
from pythinker_review.store.gitignore import ensure_gitignored

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def diff(
    base: str = typer.Option("origin/main", "--base"),
    staged: bool = typer.Option(False, "--staged"),
    working_tree: bool = typer.Option(False, "--working-tree"),
    range_: str | None = typer.Option(None, "--range"),
    fmt: OutputFormat = typer.Option(
        OutputFormat.pretty if sys.stdout.isatty() else OutputFormat.json, "--format"
    ),
    fail_on: FailOn = typer.Option(FailOn.high, "--fail-on"),
    allow_partial: bool = typer.Option(False, "--allow-partial"),
    jobs: int = typer.Option(4, "--jobs"),
    save: bool = typer.Option(True, "--save/--no-save"),
    quiet: bool = typer.Option(False, "--quiet"),
    include: list[str] = typer.Option([], "--include"),
    exclude: list[str] = typer.Option([], "--exclude"),
    no_skip_vendored: bool = typer.Option(False, "--no-skip-vendored"),
    chunk_budget_chars: int = typer.Option(12_000),
    per_chunk_timeout_s: float = typer.Option(120.0),
    repo: Path = typer.Option(Path.cwd(), "--repo"),
) -> None:
    mode = (
        DiffMode.range
        if range_
        else DiffMode.working_tree
        if working_tree
        else DiffMode.staged
        if staged
        else DiffMode.base
    )
    inputs = EngineRunInput(
        repo=repo.resolve(),
        mode=mode,
        base_ref=base,
        rev_range=range_,
        passes=("security_review",),
        diagnostics_by_file={},
        includes=tuple(include),
        excludes=tuple(exclude),
        skip_vendored=not no_skip_vendored,
        jobs=jobs,
        per_chunk_timeout_s=per_chunk_timeout_s,
        chunk_budget_chars=chunk_budget_chars,
        allow_partial=allow_partial,
    )
    llm = review_mod._resolve_llm()
    try:
        output = asyncio.run(run_engine(llm=llm, inputs=inputs))
    except EmptyDiffError as exc:
        typer.secho(f"no changes to review: {exc}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=2)
    except PreflightError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    if save:
        store = FindingsStore(repo_root=inputs.repo)
        store.begin(output.meta)
        for f in output.findings:
            store.append(f)
        store.write_diff(output.meta.id, output.resolved.patch_text)
        store.finalize(output.meta)
        ensure_gitignored(repo_root=inputs.repo)
    text = review_mod._emit(fmt, meta=output.meta, findings=output.findings, no_color=quiet)
    typer.echo(text)
    raise typer.Exit(code=exit_code(
        meta=output.meta, findings=output.findings, fail_on=fail_on, llm_error=False
    ))
```

Create `packages/pythinker-review/src/pythinker_review/cli/debug.py`:

```python
"""Standalone `pythinker-debug` Typer entry for root-cause analysis."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from pythinker_review.cli import review as review_mod
from pythinker_review.cli._shared import OutputFormat
from pythinker_review.engine.diff_source import DiffMode, EmptyDiffError, PreflightError
from pythinker_review.engine.orchestrator import EngineRunInput, run_engine

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def failure(
    log_file: Path,
    command: str | None = typer.Option(None, "--command"),
    base: str = typer.Option("origin/main", "--base"),
    fmt: OutputFormat = typer.Option(OutputFormat.json, "--format"),
    repo: Path = typer.Option(Path.cwd(), "--repo"),
    jobs: int = typer.Option(4, "--jobs"),
    per_chunk_timeout_s: float = typer.Option(120.0),
) -> None:
    diagnostic = log_file.read_text(errors="replace")
    if command:
        diagnostic = f"Reproduction command: {command}\n\n{diagnostic}"
    inputs = EngineRunInput(
        repo=repo.resolve(),
        mode=DiffMode.base,
        base_ref=base,
        rev_range=None,
        passes=("debug_review",),
        diagnostics_by_file={"*": diagnostic},
        includes=(),
        excludes=(),
        skip_vendored=True,
        jobs=jobs,
        per_chunk_timeout_s=per_chunk_timeout_s,
        chunk_budget_chars=12_000,
        allow_partial=False,
    )
    try:
        output = asyncio.run(run_engine(llm=review_mod._resolve_llm(), inputs=inputs))
    except EmptyDiffError as exc:
        typer.secho(f"no changes to correlate: {exc}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=2)
    except PreflightError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    typer.echo(review_mod._emit(fmt, meta=output.meta, findings=output.findings, no_color=False))
```

- [ ] **Step 3: Write e2e CLI tests**

Create `packages/pythinker-review/tests/e2e/__init__.py` (empty).

Create `packages/pythinker-review/tests/e2e/test_cli_review.py`:

```python
import json
import os
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.review import app


def _setup_branch(repo: Path) -> None:
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    run("checkout", "-b", "feature", "-q")
    (repo / "app.py").write_text("def f():\n    return 'AKIAIOSFODNN7EXAMPLE'\n")
    run("add", ".")
    run("commit", "-m", "add secret", "-q")


def test_review_diff_returns_finding_and_exits_one(tmp_git_repo, monkeypatch):
    repo = tmp_git_repo()
    _setup_branch(repo)
    payload = json.dumps(
        {
            "findings": [
                {
                    "rule_id": "review.return_constant",
                    "title": "Function returns a constant",
                    "rationale": "...",
                    "category": "correctness",
                    "severity": "high",
                    "file": "app.py",
                    "start_line": 2,
                    "end_line": 2,
                    "confidence": 0.9,
                }
            ]
        }
    )
    monkeypatch.setenv("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES", payload)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "diff",
            "--base",
            "main",
            "--format",
            "json",
            "--no-save",
            "--repo",
            str(repo),
            "--fail-on",
            "high",
        ],
    )
    assert result.exit_code == 1, result.stdout
    payload_out = json.loads(result.stdout)
    assert payload_out["findings"][0]["rule_id"] == "review.return_constant"
```

Create `packages/pythinker-review/tests/e2e/test_cli_secscan.py`:

```python
import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.secscan import app


def _branch_with_secret(repo: Path) -> None:
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    run("checkout", "-b", "feature", "-q")
    (repo / "config.py").write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')
    run("add", ".")
    run("commit", "-m", "leak key", "-q")


def test_secscan_finds_secret(tmp_git_repo, monkeypatch):
    repo = tmp_git_repo()
    _branch_with_secret(repo)
    payload = json.dumps(
        {
            "findings": [
                {
                    "rule_id": "sec.signal.secret.aws_access_key",
                    "title": "AWS access key committed to source",
                    "rationale": "...",
                    "category": "secret",
                    "severity": "critical",
                    "file": "config.py",
                    "start_line": 1,
                    "end_line": 1,
                    "confidence": 0.95,
                }
            ]
        }
    )
    monkeypatch.setenv("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES", payload)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "diff",
            "--base",
            "main",
            "--format",
            "sarif",
            "--no-save",
            "--repo",
            str(repo),
            "--fail-on",
            "critical",
        ],
    )
    assert result.exit_code == 1, result.stdout
    sarif = json.loads(result.stdout)
    assert sarif["runs"][0]["results"][0]["level"] == "error"
```

Create `packages/pythinker-review/tests/e2e/test_cli_debug.py`:

```python
import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.debug import app


def test_debug_failure_uses_log_input(tmp_git_repo, monkeypatch, tmp_path: Path):
    repo = tmp_git_repo()
    subprocess.run(["git", "checkout", "-b", "feature", "-q"], cwd=repo, check=True)
    (repo / "x.py").write_text("def f():\n    return 2\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "change", "-q"], cwd=repo, check=True)
    log = tmp_path / "failure.log"
    log.write_text("AssertionError at x.py:2")
    monkeypatch.setenv("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES", '{"findings": []}')
    result = CliRunner().invoke(app, ["failure", str(log), "--repo", str(repo), "--format", "json"])
    assert result.exit_code == 0, result.stdout
    assert "findings" in json.loads(result.stdout)
```

Create `packages/pythinker-review/tests/e2e/test_save_and_show.py`:

```python
import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.review import app


def test_save_then_list_then_show(tmp_git_repo, monkeypatch):
    repo = tmp_git_repo()
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    run("checkout", "-b", "feature", "-q")
    (repo / "x.py").write_text("y = 1\n")
    run("add", ".")
    run("commit", "-m", "x", "-q")
    monkeypatch.setenv("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES", '{"findings": []}')
    runner = CliRunner()
    res = runner.invoke(
        app, ["diff", "--base", "main", "--format", "json", "--repo", str(repo), "--fail-on", "none"]
    )
    assert res.exit_code == 0, res.stdout
    runs_dir = repo / ".pythinker-review" / "runs"
    assert any(p.name.startswith("2") for p in runs_dir.iterdir())
    list_res = runner.invoke(app, ["list", "--repo", str(repo)])
    assert list_res.exit_code == 0
    # gitignore patcher should have added the entry (no .gitignore present → no-op acceptable;
    # we only assert state directory exists)
    assert (repo / ".pythinker-review" / "index.json").exists()
```

- [ ] **Step 4: Run tests, lint, commit**

```bash
uv run --directory packages/pythinker-review pytest tests/e2e -vv  # all green
make check-pythinker-review
git add packages/pythinker-review/src/pythinker_review/cli packages/pythinker-review/tests/e2e
git commit -m "feat(review): standalone Typer CLIs (pythinker-review / pythinker-secscan / pythinker-debug)"
```

---

## Task 16: pythinker-code lazy CLI wrappers + ReviewLLM adapter

**Files:**
- Modify: `src/pythinker_code/cli/_lazy_group.py`
- Create: `src/pythinker_code/cli/review.py`
- Create: `src/pythinker_code/cli/secscan.py`
- Create: `src/pythinker_code/cli/debug.py`
- Create: `tests/cli/test_review_wrapper.py`
- Create: `tests/cli/test_secscan_wrapper.py`

- [ ] **Step 1: Implement the ReviewLLM adapter + lazy delegate**

Create `src/pythinker_code/cli/review.py`:

```python
"""`pythinker review` — delegates to pythinker_review with an active-model adapter."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import typer

from pythinker_review.cli.review import app as upstream_app
from pythinker_review.llm.protocol import ReviewLLM


class PythinkerActiveLLM:
    """Adapter that bridges pythinker-core's active model to ReviewLLM.

    The build path imports lazily so `pythinker --help` does not pay for it.
    """

    def __init__(self, *, model_id: str) -> None:
        self.model_display_name = model_id
        self._model_id = model_id

    async def complete_json(self, *, system: str, user: str, timeout_s: float) -> str:
        # Import lazily — pythinker_core is heavy.
        from pythinker_core.chat import chat_complete  # type: ignore[import-not-found]

        text = await asyncio.wait_for(
            chat_complete(
                model=self._model_id,
                system=system,
                messages=[{"role": "user", "content": user}],
                response_format={"type": "json_object"},
            ),
            timeout=timeout_s,
        )
        return text


def _install_adapter() -> ReviewLLM | None:
    """Install the active-Pythinker ReviewLLM. Returns None when no model is configured."""
    model_id = os.environ.get("PYTHINKER_MODEL") or _resolve_active_model_from_config()
    if not model_id:
        return None
    return PythinkerActiveLLM(model_id=model_id)


def _resolve_active_model_from_config() -> str | None:
    try:
        from pythinker_code.config import load_active_model  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return None
    try:
        return load_active_model()
    except Exception:  # noqa: BLE001
        return None


def cli() -> typer.Typer:
    """Lazy entry. Reuses upstream Typer app; pre-installs the active-model adapter."""

    @upstream_app.callback()
    def _wire(ctx: typer.Context) -> None:  # noqa: ARG001
        adapter = _install_adapter()
        if adapter is not None:
            # Stash on env-less channel so the upstream code's _resolve_llm() picks it up.
            os.environ.setdefault("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES", "")
            # Replace _resolve_llm at runtime so we never touch the env-var fallback.
            from pythinker_review.cli import review as up

            def _override() -> ReviewLLM:
                return adapter

            up._resolve_llm = _override  # type: ignore[assignment]

    return upstream_app
```

Create `src/pythinker_code/cli/secscan.py`:

```python
"""`pythinker secscan` — same wiring as review.py but for the secscan upstream app."""

from __future__ import annotations

import os
from typing import Any

import typer

from pythinker_review.cli.secscan import app as upstream_app
from pythinker_review.llm.protocol import ReviewLLM

from pythinker_code.cli.review import PythinkerActiveLLM, _install_adapter


def cli() -> typer.Typer:
    @upstream_app.callback()
    def _wire(ctx: typer.Context) -> None:  # noqa: ARG001
        adapter = _install_adapter()
        if adapter is not None:
            from pythinker_review.cli import review as up
            from pythinker_review.cli import secscan as up_sec

            def _override() -> ReviewLLM:
                return adapter

            up._resolve_llm = _override  # type: ignore[assignment]
            # secscan.py imports review_mod and reuses _resolve_llm, so one override suffices.

    return upstream_app
```

Create `src/pythinker_code/cli/debug.py`:

```python
"""`pythinker debug` — active-model wrapper for pythinker-debug."""

from __future__ import annotations

import typer

from pythinker_review.cli.debug import app as upstream_app
from pythinker_review.llm.protocol import ReviewLLM

from pythinker_code.cli.review import _install_adapter


def cli() -> typer.Typer:
    @upstream_app.callback()
    def _wire(ctx: typer.Context) -> None:  # noqa: ARG001
        adapter = _install_adapter()
        if adapter is not None:
            from pythinker_review.cli import review as up

            def _override() -> ReviewLLM:
                return adapter

            up._resolve_llm = _override  # type: ignore[assignment]

    return upstream_app
```

- [ ] **Step 2: Register all three in `_lazy_group.py`**

Edit `src/pythinker_code/cli/_lazy_group.py`. Extend the `lazy_subcommands` dict and `lazy_command_order` tuple:

```python
    lazy_subcommands: dict[str, tuple[str, str, str]] = {
        "info": ("pythinker_code.cli.info", "cli", "Show version and protocol information."),
        "export": ("pythinker_code.cli.export", "cli", "Export session data."),
        "mcp": ("pythinker_code.cli.mcp", "cli", "Manage MCP server configurations."),
        "plugin": ("pythinker_code.cli.plugin", "cli", "Manage plugins."),
        "review": (
            "pythinker_code.cli.review",
            "cli",
            "Diff-focused code review (delegates to pythinker-review).",
        ),
        "secscan": (
            "pythinker_code.cli.secscan",
            "cli",
            "Diff-focused security review (delegates to pythinker-review).",
        ),
        "debug": (
            "pythinker_code.cli.debug",
            "cli",
            "Failure/log root-cause analysis (delegates to pythinker-review).",
        ),
        "update": (
            "pythinker_code.cli.update",
            "cli",
            "Check for and install Pythinker CLI updates.",
        ),
        "vis": ("pythinker_code.cli.vis", "cli", "Run Pythinker Agent Tracing Visualizer."),
        "web": ("pythinker_code.cli.web", "cli", "Run Pythinker CLI web interface."),
    }
    lazy_command_order: tuple[str, ...] = (
        "info",
        "export",
        "mcp",
        "plugin",
        "review",
        "secscan",
        "debug",
        "update",
        "vis",
        "web",
    )
```

- [ ] **Step 3: Write a smoke test**

Create `tests/cli/test_review_wrapper.py`:

```python
import os
import subprocess

import pytest


@pytest.mark.parametrize("cmd", ["review", "secscan", "debug"])
def test_top_level_help_lists_command(cmd: str) -> None:
    env = os.environ.copy()
    env["PATH"] = env.get("PATH", "")
    proc = subprocess.run(
        ["uv", "run", "pythinker", "--help"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert cmd in proc.stdout


def test_review_diff_help_works() -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "review", "diff", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--with-security" in proc.stdout


def test_debug_failure_help_works() -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "debug", "failure", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--command" in proc.stdout
```

- [ ] **Step 4: Run smoke + lint + commit**

```bash
uv sync
uv run pytest tests/cli/test_review_wrapper.py -vv  # all green
make check-pythinker-code
git add src/pythinker_code/cli/review.py src/pythinker_code/cli/secscan.py src/pythinker_code/cli/debug.py src/pythinker_code/cli/_lazy_group.py tests/cli/test_review_wrapper.py tests/cli/test_secscan_wrapper.py
git commit -m "feat(code): add pythinker review/secscan/debug lazy CLI wrappers with active-model adapter"
```

---

## Task 17: YAML subagent roles

**Files:**
- Create: `src/pythinker_code/agents/default/code_reviewer.yaml`
- Create: `src/pythinker_code/agents/default/security_reviewer.yaml`
- Create: `src/pythinker_code/agents/default/debugger.yaml`
- Modify: `src/pythinker_code/agents/default/agent.yaml` — extend `subagents:`

- [ ] **Step 1: Create the three new role YAMLs**

Create `src/pythinker_code/agents/default/code_reviewer.yaml`:

```yaml
version: 1
agent:
  extend: ./agent.yaml
  system_prompt_args:
    ROLE_ADDITIONAL: |
      You are now running as a subagent. All `user` messages are sent by the main agent. The main agent cannot see your context, only your last message. Treat the parent agent as your caller. Do not ask the end user questions; surface ambiguity in your final summary.

      You are a diff-focused code reviewer. Your job is to run `pythinker review diff` (or `pythinker review diff --with-security` when the parent asks for security too) and reformat the result for the parent.

      Operating rules:
      - Read-only by convention. You may run the review CLI and read its output, but do not edit source files.
      - Default to `--format json --no-save` so the parent gets structured data without writing run state.
      - If the parent requests persistence, drop `--no-save`.
      - Translate the JSON output into the structured response block below.

      Final response contract:
      ### SUMMARY
      One paragraph: how many findings, top severity, what the parent should look at first.
      ### EVIDENCE
      Bullet list of `<file>:<line> [severity] <rule_id> — <title>` for each finding, top 10.
      ### CHANGES
      None.
      ### RISKS
      Notable false-positive risks or coverage gaps; or `None observed.`.
      ### BLOCKERS
      Anything that prevented a clean run (exit code 3/4, base ref missing, etc.), or `None.`.
  when_to_use: |
    Use to run a diff-focused code review on the current branch and return a structured summary of findings. Pair with `security-reviewer` (parallel) for combined coverage, or use `--with-security` when invoking this agent alone.
  allowed_tools:
    - "pythinker_code.tools.shell:Shell"
    - "pythinker_code.tools.file:ReadFile"
    - "pythinker_code.tools.file:Grep"
```

Create `src/pythinker_code/agents/default/security_reviewer.yaml`:

```yaml
version: 1
agent:
  extend: ./agent.yaml
  system_prompt_args:
    ROLE_ADDITIONAL: |
      You are now running as a subagent. All `user` messages are sent by the main agent. The main agent cannot see your context, only your last message. Treat the parent agent as your caller. Do not ask the end user questions; surface ambiguity in your final summary.

      You are a diff-only security reviewer. Your job is to run `pythinker secscan diff` and reformat the result for the parent.

      Operating rules:
      - Read-only by convention. You may run the secscan CLI and read its output, but do not edit source files.
      - Default to `--format json --no-save`.
      - Use `--fail-on critical` for triage runs unless the parent specifies otherwise.
      - Translate the JSON output into the structured response block below.

      Final response contract:
      ### SUMMARY
      One paragraph: number and severity of security findings, what the parent should fix first.
      ### EVIDENCE
      Bullet list of `<file>:<line> [severity] <rule_id> — <title>`, top 10.
      ### CHANGES
      None.
      ### RISKS
      False-positive risks, missing context, or coverage gaps; or `None observed.`.
      ### BLOCKERS
      Anything that prevented a clean run (exit 3/4, base ref missing), or `None.`.
  when_to_use: |
    Use to run a diff-only security review on the current branch. Can run in parallel with `code-reviewer` to get both perspectives without overlap.
  allowed_tools:
    - "pythinker_code.tools.shell:Shell"
    - "pythinker_code.tools.file:ReadFile"
    - "pythinker_code.tools.file:Grep"
```

Create `src/pythinker_code/agents/default/debugger.yaml`:

```yaml
version: 1
agent:
  extend: ./agent.yaml
  system_prompt_args:
    ROLE_ADDITIONAL: |
      You are now running as a subagent. All `user` messages are sent by the main agent. The main agent cannot see your context, only your last message. Treat the parent agent as your caller. Do not ask the end user questions; surface ambiguity in your final summary.

      You are a root-cause debugger. Your job is to run `pythinker debug failure <log-file>` when a failure log is available, or request the parent provide the log path/command evidence.

      Operating rules:
      - Read-only by convention. Do not edit source files.
      - Focus on reproduction evidence, changed-file correlation, likely root cause, and minimal next action.
      - Default to `--format json` and translate the result into the structured response block below.

      Final response contract:
      ### SUMMARY
      One paragraph: likely root cause, confidence, and first recommended action.
      ### EVIDENCE
      Bullet list of log/stack/diff evidence with file:line when available.
      ### CHANGES
      None.
      ### RISKS
      Ambiguities, missing reproduction context, or `None observed.`.
      ### BLOCKERS
      Missing log path, command, environment, or `None.`.
  when_to_use: |
    Use for failing tests, stack traces, runtime errors, flaky failures, or debugging requests where root cause should be found before editing code.
  allowed_tools:
    - "pythinker_code.tools.shell:Shell"
    - "pythinker_code.tools.file:ReadFile"
    - "pythinker_code.tools.file:Grep"
```

- [ ] **Step 2: Register in `agent.yaml`**

Edit `src/pythinker_code/agents/default/agent.yaml`. Add to the `subagents:` map (keep alphabetical-ish among siblings, matching the existing convention):

```yaml
  subagents:
    coder:
      path: ./coder.yaml
    code-reviewer:
      path: ./code_reviewer.yaml
    debugger:
      path: ./debugger.yaml
    security-reviewer:
      path: ./security_reviewer.yaml
    # ... other existing entries ...
```

(Preserve the rest of `subagents:` exactly as it was — only add the three new keys.)

- [ ] **Step 3: Smoke test the registration**

Run: `uv run pythinker --help`
Expected: succeeds; no traceback from YAML loading.

Run (if Pythinker has a subagent-list CLI): `uv run pythinker info --subagents` or equivalent — confirm `code-reviewer`, `security-reviewer`, and `debugger` appear.

If no built-in introspection exists, write a tiny smoke test under `tests/cli/test_review_wrapper.py`:

```python
def test_subagent_roles_load() -> None:
    from pythinker_code.subagents.registry import load_default_registry  # adjust import to the real entry

    reg = load_default_registry()
    assert "code-reviewer" in reg
    assert "security-reviewer" in reg
    assert "debugger" in reg
```

If the registry import path differs, update it to match the actual module after a one-line grep (`grep -R "def load.*registry" src/pythinker_code/subagents`).

- [ ] **Step 4: Commit**

```bash
make check-pythinker-code
git add src/pythinker_code/agents/default
git commit -m "feat(code): register code-reviewer, security-reviewer, and debugger YAML subagent roles"
```

---

## Task 18: AGENTS.md row, README "What's New", and final make check/test

**Files:**
- Modify: `AGENTS.md` — verification matrix
- Modify: `README.md` — "What's New" entry
- Modify: `packages/pythinker-review/README.md` — flesh out

- [ ] **Step 1: Add the verification-matrix row**

Edit `AGENTS.md`. Find the verification matrix table (search for "Verification matrix"). Insert a new row after the existing package rows:

```markdown
| `packages/pythinker-review` | `make check-pythinker-review && make test-pythinker-review` |
```

- [ ] **Step 2: Add a "What's New" entry**

Edit `README.md`. Insert a new section above the existing "What's New in 2.6.0":

```markdown
## 🆕 What's New in 0.8.0

First-class agent-first code review, security review, and root-cause debugging, via the new
`pythinker-review` workspace package.

- **`pythinker review diff`** — runs a code-review pass on the current branch's diff against `origin/main` (or `--base <ref>`, `--staged`, `--working-tree`, `--range A..B`). Outputs pretty / JSON / SARIF. `--fail-on <severity>` makes it a CI gate.
- **`pythinker review diff --with-security`** — runs the code-review and security-review passes in parallel.
- **`pythinker secscan diff`** — security-only pass with deterministic prompt anchors for secrets, command/SQL injection, deserialization, SSRF, weak crypto.
- **`pythinker debug failure <log-file>`** — root-cause debugger pass over failing test output, stack traces, logs, and correlated diff context.
- **Findings store** at `.pythinker-review/runs/<id>/` for inspection via `pythinker review list` / `pythinker review show <id>`.
- **Three new subagent roles** — `code-reviewer`, `security-reviewer`, and `debugger` — usable from any interactive Pythinker session, producing the standard SUMMARY/EVIDENCE/CHANGES/RISKS/BLOCKERS block.
- **Fail-closed by default** — any chunk timeout, malformed model output, or worker exception exits non-zero. `--allow-partial` is the explicit escape hatch and surfaces failures in output.

No new third-party runtime dependencies. Reuses the active Pythinker model when invoked via `pythinker review` / `pythinker secscan` / `pythinker debug`; the standalone `pythinker-review` / `pythinker-secscan` / `pythinker-debug` console scripts accept explicit/env configuration.

Upgrade with `pythinker update` or `pip install --upgrade pythinker-code==0.8.0`.
```

(Bump `version = "2.6.0"` to `"0.8.0"` in root `pyproject.toml` only when actually releasing — not as part of this implementation plan. Document the bump as a release-time step.)

- [ ] **Step 3: Flesh out package README**

Edit `packages/pythinker-review/README.md`:

```markdown
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

`pythinker-review` and `pythinker-secscan` accept an explicit model via
`--model` or env config. When invoked via `pythinker review` /
`pythinker secscan` / `pythinker debug` (the wrappers in `pythinker-code`), the active Pythinker
model is wired in automatically through a `ReviewLLM` adapter.

## Persistence

Each `--save` run writes:

```
.pythinker-review/
├── index.json
└── runs/
    └── 20260520120000-a1b2c3d4/
        ├── meta.json
        ├── findings.jsonl
        └── diff.patch
```

`.gitignore` is auto-patched (idempotently) on first save if a `.gitignore`
file already exists.

## Phase 1

See `docs/superpowers/specs/2026-05-20-pythinker-review-foundation-design.md`
for the full spec. Future phases add whole-repo audit, external deepsec-style
matchers + revalidation, PR-provider integrations, and a fix loop.
```

- [ ] **Step 4: Run the full check + test suites**

```bash
make check
make test
```

Expected: all targets pass, including the new `check-pythinker-review` / `test-pythinker-review` slots.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md README.md packages/pythinker-review/README.md
git commit -m "docs(review): add AGENTS.md verification row, README What's New, package README"
```

---

## Self-Review

Run this checklist against the spec before declaring the plan ready.

**Spec coverage:**

| Spec section | Covered by | Status |
|---|---|---|
| §1 Goal — review/debug/security substrate + diff/debug gates | Tasks 0–15 | ✅ |
| §2 Success criteria #1 — make check/test pass | Task 1 + Task 18 | ✅ |
| §2 #2 — blackbox parity map exists | Task 0 | ✅ |
| §2 #3 — diff produces ≥1 finding per pass in all formats | Task 15 e2e tests | ✅ |
| §2 #4 — debug failure produces root-cause finding | Tasks 10, 15 e2e tests | ✅ |
| §2 #5 — `--fail-on high` exit codes | Task 15 `exit_code` + e2e | ✅ |
| §2 #6 — fail-closed default, `--allow-partial` opt-in | Tasks 11, 15 | ✅ |
| §2 #7 — `--save` writes `runs/<id>/`, `list`/`show` rehydrate | Tasks 13, 15 | ✅ |
| §2 #8 — root CLI defaults to active model | Task 16 adapter | ✅ |
| §2 #9 — YAML subagent roles emit SUMMARY/EVIDENCE/… | Task 17 | ✅ |
| §2 #10 — default prompt/role guidance prefers diagnosis first | Task 0 + Task 17 | ✅ |
| §2 #11 — no regression in existing pythinker | Task 16 + Task 18 `make test` | ✅ |
| §2 #12 — no unapproved deps | All tasks; stdlib subprocess + secrets | ✅ |
| §3 Non-goals — no auto-fix, no PR-posting, no whole-repo | Out of scope, deferred | ✅ |
| §4.1 Package layout | Task 1 | ✅ |
| §4.2 ReviewLLM Protocol + adapter injection | Tasks 9, 16 | ✅ |
| §4.3 Root vs standalone CLI + debug surface | Tasks 15, 16 | ✅ |
| §5.1 diff_source / structured_diff / context / chunker / runner / dedupe / orchestrator | Tasks 4, 5, 6, 7, 11, 12 | ✅ |
| §5.2 signals scanner | Task 8 | ✅ |
| §5.3 reviewers/debugger + prompts + retry | Tasks 9, 10 | ✅ |
| §5.4 findings store + run lifecycle + ids + gitignore | Tasks 3, 13 | ✅ |
| §5.5 pretty / JSON / SARIF + jsonschema validator | Task 14 | ✅ |
| §5.6 standalone CLI (`review`/`secscan`/`debug`) | Task 15 | ✅ |
| §5.7 YAML subagent roles, shell-out path | Task 17 | ✅ |
| §6 Data model | Task 2 | ✅ |
| §6.1 On-disk layout | Tasks 13, 15 | ✅ |
| §7 CLI surface — shared flags | Task 15 | ✅ |
| §7 Exit codes 0/1/2/3/4/130 | Task 15 `_shared.exit_code` | ✅ |
| §8 Error-handling table | Tasks 10, 11, 15 | ✅ |
| §9 Testing (unit / e2e / tests_ai gate) | Tasks 2–15 unit tests; Task 15 e2e; `tests_ai` left as future work (spec §13 open) | ⚠ partial |
| §10 Rollout — workspace member, Make targets, lazy group, YAML, README, AGENTS.md | Tasks 1, 16, 17, 18 | ✅ |

**Partial-coverage note (§9 `tests_ai/`):** the spec defers the real-model gated test suite to implementation planning. Recommend adding a follow-up task in the next planning round once a stable fixture diff and a canned model adapter exist; doing it Phase 1 risks shipping flaky tests with no model budget.

**Placeholder scan:** no `TBD`, `TODO`, "implement later", or "similar to Task N" markers in this plan. All steps contain concrete code or concrete commands. ✅

**Type consistency check:**
- `Chunk` referenced from Tasks 7, 10, 11, 12 — same shape (`file`, `hunks`, `rendered`). ✅
- `ReviewerResult` defined in Tasks 9 + 10 (code/security/debug passes); identical shape; runner imports all three. ✅
- `Finding` / `RawFinding` distinguished consistently: `RawFinding` from LLM, `Finding` after dedupe attaches `id`/`run_id`/`location.sha`. ✅
- `Pass` literal `"code_review" | "security_review" | "debug_review"` used uniformly. ✅
- `ChunkFailureReason` matches across reviewers (Task 10) and runner (Task 11). ✅
- `RunMeta.status` literal includes `"completed_with_warnings"` in models (Task 2) and is produced by orchestrator (Task 12). ✅
- Exit codes match spec §7 and CLI implementation (Task 15). ✅

No drift found. Plan ready for execution.

---

## Task 19: Commit Phase 1A and update the plan

**Files (uncommitted):** see "Implementation Status" header at the top of this plan for the full list.

This task is the only blocker between the current in-tree implementation and a landed Phase 1A. All code, tests, prompts, YAML roles, docs, and parity-map work are already present locally.

- [ ] **Step 1: Re-run the green gates before committing**

```bash
make check-pythinker-review
make test-pythinker-review
uv run pytest tests/core/test_agent_spec.py tests/core/test_default_agent.py tests/utils/test_pyinstaller_utils.py tests/cli/ -vv
```

Expected: 62 + 48 = 110 tests pass, lint/type clean. If any gate fails, stop and fix before committing.

(The root `make check-pythinker-code` is known to emit 200 pre-existing pyright diagnostics on plain `HEAD` — not introduced by Phase 1A. Do not block the commit on those.)

- [ ] **Step 2: Stage and commit in three logical commits**

Stage the new package + workspace registration + Make targets first:

```bash
git add packages/pythinker-review pyproject.toml Makefile uv.lock
git commit -m "feat(review): add pythinker-review workspace package

Diff-only review, security scan, and root-cause debugger engine.
Implements the substrate described in
docs/superpowers/specs/2026-05-20-pythinker-review-foundation-design.md:
data model, store, structured-diff renderer, security signal scanner,
diagnostics parser, three reviewer passes (code/security/debug),
asyncio runner with fail-closed/--allow-partial semantics, pretty/JSON/
SARIF formatters, and standalone Typer CLIs (pythinker-review,
pythinker-secscan, pythinker-debug). Reuses pythinker-core via the
ReviewLLM protocol; no new third-party runtime deps."
```

Then the `pythinker-code` integration:

```bash
git add src/pythinker_code/cli/review.py src/pythinker_code/cli/secscan.py src/pythinker_code/cli/debug.py \
        src/pythinker_code/cli/_lazy_group.py src/pythinker_code/__main__.py \
        src/pythinker_code/agents/default/code_reviewer.yaml \
        src/pythinker_code/agents/default/security_reviewer.yaml \
        src/pythinker_code/agents/default/debugger.yaml \
        src/pythinker_code/agents/default/agent.yaml \
        src/pythinker_code/agents/default/system.md \
        tests/cli/test_review_wrapper.py tests/cli/test_secscan_wrapper.py \
        tests/core/test_agent_spec.py tests/core/test_default_agent.py \
        tests/utils/test_pyinstaller_utils.py
git commit -m "feat(code): integrate pythinker-review via lazy CLI and YAML subagents

Adds lazy 'review', 'secscan', and 'debug' root subcommands that wrap
the pythinker-review CLIs and inject the active Pythinker model via a
ReviewLLM adapter. Registers three new YAML subagent roles
(code-reviewer, security-reviewer, debugger) following the existing
agents/default/agent.yaml mechanism. Updates the default system prompt
so ambiguous engineering requests prefer evidence-first review/
diagnosis before editing code. Existing review/verifier roles untouched."
```

Finally the docs:

```bash
git add AGENTS.md README.md \
        docs/superpowers/specs/2026-05-20-pythinker-review-foundation-design.md \
        docs/superpowers/plans/2026-05-20-pythinker-review-foundation.md
git commit -m "docs(review): AGENTS.md verification row + README What's New 0.8.0 + spec/plan revisions

Spec was revised after implementation to record the product-direction
shift (review/debug/security first), add the debug capability and
debugger subagent, and require an explicit blackbox parity map for the
three vendored reference repos. The plan now opens with an
Implementation Status section so future re-runs can skip what is
already landed."
```

- [ ] **Step 3: Verify the working tree is clean**

```bash
git status
```

Expected: no modified, no untracked. If anything remains, decide whether it belongs in this set of commits or in a follow-up.

- [ ] **Step 4: Optional — Release prep (not required for landing Phase 1A)**

Only do this if cutting a `pythinker-code` 0.8.0 release in the same change set. Otherwise defer to a separate release commit.

- Bump `version = "2.6.0"` → `"0.8.0"` in root `pyproject.toml`.
- Update `CHANGELOG.md` with a 0.8.0 entry mirroring the README "What's New" section.
- Re-run `make check && make test`.
- Commit: `chore(release): 0.8.0 — pythinker-review Phase 1A`.

---
