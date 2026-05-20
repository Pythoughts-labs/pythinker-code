# Pythinker Review — Phase 1: Foundation + Diff-Only Gate

**Date:** 2026-05-20
**Status:** Spec — pending user review
**Scope:** Phase 1 of a multi-phase project to add code-review and security-review
capabilities to Pythinker, porting concepts from `blackbox/clawpatch-main`,
`blackbox/code-review`, and `blackbox/deepsec-main`.

## 1. Goal

Ship the substrate and one immediately useful capability: a diff-only review gate.

- Substrate: a new `packages/pythinker-review` workspace package, a findings data
  model, a JSON-on-disk store, and registration of two new subagent roles
  (`code-reviewer`, `security-reviewer`).
- Capability: two CLI entry points — `pythinker review diff` and
  `pythinker secscan diff` — that review changed lines on the current branch
  against a base ref, emit findings in pretty / JSON / SARIF, and optionally
  fail the build on a configurable severity threshold.

Out of scope for Phase 1 (each gets its own future spec):

- Phase 2: clawpatch-style whole-repo semantic slicing + local audit.
- Phase 3: deepsec-style parallel matchers, INFO.md context, revalidation.
- Phase 4: PR-provider integrations (GitHub / GitLab / Bitbucket / Azure DevOps).
- Phase 5: clawpatch-style fix loop (`fix --finding <id>`, patch attempts).

## 2. Success criteria

A change is done when:

1. `make check-pythinker-review && make test-pythinker-review` pass.
2. From any git repo on `main`, after creating a branch with a planted bug and
   a planted security issue, `pythinker review diff --with-security` produces
   at least one finding for each, in pretty / JSON / SARIF format.
3. `pythinker review diff --fail-on high` exits non-zero when a high-or-above
   finding is produced and exits zero otherwise.
4. `--save` writes a complete `runs/<id>/` directory; `pythinker review list`
   and `pythinker review show <id>` reproduce the run's findings without
   another LLM call.
5. When invoked from inside an interactive Pythinker session, dispatching to
   the `code-reviewer` or `security-reviewer` subagent role returns output in
   the existing `SUMMARY / EVIDENCE / CHANGES / RISKS / BLOCKERS` shape.
6. No regression in existing `pythinker` commands; existing `review` and
   `verifier` subagent roles continue to work.

## 3. Non-goals

- Auto-applying fixes. Findings may carry a `suggestion.patch` string for the
  user to review, but Phase 1 never writes to source files.
- Posting comments to GitHub / GitLab / etc. Pretty / JSON / SARIF only.
- Whole-repo scanning. Diff-only.
- Parallel worker machines (deepsec-style). In-process asyncio fan-out only.
- New telemetry endpoints or hosted services. AGENTS.md forbids these without
  explicit approval.

## 4. Architecture

### 4.1 Package layout

```
packages/pythinker-review/
├── pyproject.toml                 # console_scripts: pythinker-review, pythinker-secscan
├── README.md
├── src/pythinker_review/
│   ├── __init__.py
│   ├── cli/                       # typer entry; review + secscan commands
│   ├── engine/                    # diff_source, chunker, runner, dedupe
│   ├── reviewers/                 # code_review, security_review, schema
│   ├── store/                     # findings_store, run, models, gitignore
│   ├── output/                    # pretty, json, sarif
│   └── subagent/                  # registration of code-reviewer/security-reviewer
└── tests/
    ├── unit/
    └── e2e/
```

Mirrors the existing `packages/pythinker-core`, `packages/pythinker-host`,
`sdks/pythinker-sdk` convention. `make` targets follow the existing pattern:
`make check-pythinker-review`, `make test-pythinker-review`. The verification
matrix in `AGENTS.md` gets one new row.

### 4.2 Dependency direction

```
pythinker-code  ──uses──▶  pythinker-review  ──uses──▶  pythinker-core
                                                  └──▶  (typer, pydantic, gitpython|subprocess)
```

`pythinker-review` reuses `pythinker-core` for LLM calls, prompts, and tool
primitives. It does NOT import from `pythinker-code` — instead, `pythinker-code`
discovers it via the existing subagent registry, the same way it discovers
built-in roles today. This keeps the substrate independently testable and
keeps PR review usable as a standalone CLI without an interactive session.

### 4.3 Two CLIs, one engine

`pythinker review diff` and `pythinker secscan diff` resolve to the same
`engine.run()` call. They differ only in which `passes: list[Pass]` they
enable:

- `pythinker review diff` → `passes=["code_review"]` (plus `["security_review"]`
  if `--with-security`)
- `pythinker secscan diff` → `passes=["security_review"]`

The two passes run in parallel against the same chunked diff when both are
enabled. Findings from each pass are tagged with their `pass` field so output
formatters can group / filter.

## 5. Components

All paths are inside `src/pythinker_review/`.

### 5.1 `engine/`

**`diff_source.py`** — resolves the diff and the SHAs it refers to.

Algorithm:
1. If `--range A..B` given, use it directly.
2. Else if `--working-tree`, `git diff` (uncommitted vs index + index vs HEAD).
3. Else if `--staged`, `git diff --cached`.
4. Else (default): resolve base ref by trying `--base` (default `origin/main`),
   falling back to `main`, then `master`. Diff is `git merge-base HEAD <base>`
   .. HEAD.
5. Run `git diff --unified=10` to expand context. Reject the run with exit 2
   if the diff is empty (no work to do).

Output: a `ResolvedDiff` (raw patch text, base_sha, head_sha, base_ref, list of
changed file paths).

**`chunker.py`** — splits the diff into review chunks.

- Default: one chunk per changed file.
- If a single file's diff exceeds the per-chunk token budget (configurable,
  default ~12k chars), split at hunk boundaries.
- Honors `--include <glob>` / `--exclude <glob>` filters before chunking.
- Skips binary diffs, vendored paths (`node_modules/`, `.venv/`, `dist/`,
  `build/`, `.pythinker-review/`) by default. Skip list is overridable via
  `--no-skip-vendored`.

Output: a list of `Chunk(file, hunks, raw_diff, neighborhood_text)`. The
`neighborhood_text` is up to ±50 lines of pre-change file content for the
reviewer to see in context (read via `git show <base_sha>:<path>` and current
file content; truncated to budget).

**`runner.py`** — concurrency + retry.

- Asyncio worker pool sized by `--jobs` (default 4).
- For each (chunk, pass) pair, schedule one LLM call.
- Per-chunk timeout (default 120s); on timeout, log and continue.
- On Ctrl-C: cancel pending, mark run `cancelled`, flush partial findings.
- Progress bar via Pythinker's existing `ui/` rich primitives, suppressible
  with `--quiet`.

**`dedupe.py`** — collapses duplicates.

Key: `(file, max(start_line, 1), min(end_line, +inf), rule_id)`. When two
findings collide, keep the one with higher `severity`, then higher
`confidence`, then earlier `pass` order (`security_review` wins ties on
intent).

### 5.2 `reviewers/`

**`schema.py`** — pydantic models the LLM is asked to produce.

```python
class ReviewerOutput(BaseModel):
    findings: list[RawFinding]

class RawFinding(BaseModel):
    rule_id: str
    title: str = Field(max_length=80)
    rationale: str
    category: Category
    severity: Severity
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)
    suggestion: Suggestion | None = None
```

Reviewer post-processing converts `RawFinding` → `Finding` by attaching
`id`, `pass`, `created_at`, `run_id`, and the head `sha` for the `Location`.

**`code_review.py`** — prompt + caller for the code-review pass. Covers
correctness, design, performance, readability, missing tests, API breakage.
Prompt is adapted from `blackbox/code-review/code_review/` PR-Agent prompts,
trimmed for diff-only and re-targeted at the `RawFinding` schema.

**`security_review.py`** — prompt + caller for the security pass. Covers
injection (SQL / command / template), authn/authz, secrets/credentials in
diff, SSRF, deserialization, crypto misuse, supply-chain risks introduced
by new dependencies, unsafe defaults. Built-in baseline rule list lives in
`reviewers/security_rules.toml`. Prompt is adapted from
`blackbox/deepsec-main/packages/scanner` prompts, trimmed for diff-only.

Both reviewers:
- One retry on malformed JSON with a stricter prompt suffix.
- Second failure: log warning, drop chunk's findings, record in
  `meta.chunks_failed`.

### 5.3 `store/`

**`models.py`** — pydantic models defined in §6 below.

**`findings_store.py`** — append-only JSONL writer.

- `runs/<run-id>/findings.jsonl` is opened once per run, appended atomically
  per finding (`fsync` on close, not per write).
- `runs/<run-id>/meta.json` and `index.json` updates use `.tmp` + atomic
  rename to avoid partial writes on crash.
- Run ID is a ULID so runs sort lexicographically by time.

**`run.py`** — `RunMeta` lifecycle helpers. Wraps the create / update /
finalize transitions.

**`gitignore.py`** — idempotent `.gitignore` patcher.

- Triggers only on first `--save` per repo.
- Only modifies `.gitignore` if it already exists. If it doesn't, the run
  still succeeds; just logs an info note that `.pythinker-review/` was not
  added to ignore.
- Adds a single line `.pythinker-review/` under a `# pythinker-review` marker
  comment, only if not already present (grep-equivalent check).

### 5.4 `output/`

**`pretty.py`** — TTY rendering via Pythinker's `ui/` package (Rich-based).
Per finding: severity chip, file:line, title, rationale (markdown), optional
suggestion. Findings grouped by file, sorted by `(severity desc, file, start_line)`.

**`json.py`** — emits `{"run": RunMeta, "findings": [Finding, ...]}` to
stdout. Schema is the same as the on-disk JSONL after re-aggregation.

**`sarif.py`** — SARIF 2.1.0. Severity mapping:

| Our severity | SARIF level |
|---|---|
| critical, high | `error` |
| medium | `warning` |
| low, info | `note` |

`rule_id` maps to `ruleId`; `Location` maps to a single `physicalLocation`
with `region.startLine` / `endLine`.

### 5.5 `cli/`

`typer`-based, two commands sharing one option group via a typer callback.

```
pythinker-review diff [--with-security] [shared flags]
pythinker-review list [--limit N]
pythinker-review show <run-id> [--format pretty|json|sarif]

pythinker-secscan diff [shared flags]
```

`pythinker-code` exposes these as `pythinker review` / `pythinker secscan` by
adding two new subcommands in `src/pythinker_code/cli/` that simply delegate
to the `pythinker_review.cli` entry. (This is the only edit to
`pythinker-code` Phase 1 makes outside subagent registration.)

### 5.6 `subagent/`

Registers two roles with the existing subagent registry in
`pythinker_code/subagents/registry.py`:

- `code-reviewer` — wraps `engine.run(passes=["code_review"], diff_source=auto)`.
- `security-reviewer` — wraps `engine.run(passes=["security_review"], diff_source=auto)`.

Output is reformatted into the standard
`### SUMMARY / EVIDENCE / CHANGES / RISKS / BLOCKERS` blocks so a parent
agent in an interactive session can consume the result without re-parsing.
The existing `review` subagent role is left untouched.

## 6. Data model

```python
class Severity(str, Enum):
    critical = "critical"   # exploitable now, or correctness break with prod impact
    high     = "high"       # likely bug or vuln; fix before merge
    medium   = "medium"     # real issue, defer-with-issue acceptable
    low      = "low"        # nit, style, micro-perf
    info     = "info"       # FYI, no action required

class Category(str, Enum):
    correctness   = "correctness"
    security      = "security"
    performance   = "performance"
    readability   = "readability"
    test_coverage = "test_coverage"
    api_design    = "api_design"
    dependency    = "dependency"
    secret        = "secret"

class Location(BaseModel):
    file: str                  # repo-relative POSIX path
    start_line: int            # 1-indexed, inclusive
    end_line: int              # 1-indexed, inclusive
    sha: str | None = None     # commit SHA the line numbers refer to

class Suggestion(BaseModel):
    summary: str               # one-sentence what-to-change
    patch: str | None = None   # unified diff; validated parseable, not applied

class Finding(BaseModel):
    id: str                    # sha256(rule_id + file + start_line + title)[:12]
    rule_id: str               # e.g. "sec.injection.sql", "review.error_handling"
    title: str                 # ≤80 chars
    rationale: str             # markdown
    category: Category
    severity: Severity
    location: Location
    pass_: Literal["code_review", "security_review"] = Field(alias="pass")
    suggestion: Suggestion | None = None
    confidence: float          # 0.0–1.0
    triage: Literal["open", "false_positive", "accepted", "wont_fix"] = "open"
    triage_note: str | None = None
    created_at: datetime
    run_id: str

class RunMeta(BaseModel):
    id: str                    # ULID
    started_at: datetime
    finished_at: datetime | None
    status: Literal["running", "completed", "failed", "cancelled"]
    repo_root: str
    branch: str | None
    head_sha: str
    base_ref: str
    base_sha: str
    passes: list[Literal["code_review", "security_review"]]
    model: str                 # provider:model-id
    chunks_total: int
    chunks_done: int
    chunks_failed: int
    findings_count: int
    config_hash: str           # hash of reviewer prompts + rule list
```

### 6.1 On-disk layout

```
.pythinker-review/
├── index.json                       # {"runs": [{id, started_at, branch, head_sha, status, findings_count}, ...]}
└── runs/
    └── 01J<ulid>/
        ├── meta.json                # RunMeta
        ├── findings.jsonl           # one Finding per line, append-only
        └── diff.patch               # the diff reviewed (for reproducibility)
```

`index.json` is trimmed to the most recent 200 runs; older entries stay on
disk under `runs/` but are not indexed. `pythinker review list` reads
`index.json`; `pythinker review show <id>` reads `runs/<id>/` directly so
unindexed older runs are still recoverable when the user knows the ID.

## 7. CLI surface

Shared option group for `review diff` / `secscan diff`:

| Flag | Default | Purpose |
|---|---|---|
| `--base <ref>` | `origin/main` → `main` → `master` | Base ref for `merge-base HEAD <ref>` |
| `--staged` | off | Diff staged vs HEAD |
| `--working-tree` | off | Diff working tree |
| `--range A..B` | — | Arbitrary range |
| `--format pretty\|json\|sarif` | `pretty` if TTY else `json` | Output format |
| `--fail-on critical\|high\|medium\|low\|none` | `high` | Exit non-zero when finding ≥ threshold |
| `--jobs N` | `4` | Worker pool size |
| `--model <id>` | active Pythinker provider | Override LLM |
| `--save / --no-save` | `--save` | Persist to `.pythinker-review/runs/<id>/` |
| `--quiet` | off | Suppress progress UI |
| `--include <glob>` | — (repeatable) | Filter to matching files (gitignore-style glob, matched against repo-relative POSIX path) |
| `--exclude <glob>` | — (repeatable) | Skip matching files (same glob semantics as `--include`; `--exclude` wins on conflict) |
| `--no-skip-vendored` | off | Don't auto-skip `node_modules/`, `.venv/`, etc. |

Exit codes:

- `0` — success, no finding ≥ `--fail-on`.
- `1` — success, at least one finding ≥ `--fail-on`.
- `2` — preflight error (no git, no diff, base ref unresolvable, bad flags).
- `3` — runtime error (LLM auth / quota / network failure surfaced to user).
- `130` — Ctrl-C (run marked `cancelled`).

## 8. Error handling

Fail loud at the boundary; never inside the runner.

| Condition | Where caught | Behavior |
|---|---|---|
| `git` missing / not a repo | preflight | exit 2 with clear message |
| base ref unresolvable | preflight | exit 2 |
| empty diff | preflight | exit 2, "no changes to review" |
| LLM auth / quota error | runner startup | exit 3, surface provider name |
| Per-chunk LLM error | runner | log, count in `chunks_failed`, continue |
| Malformed JSON | reviewer | one retry; second failure logs + drops chunk |
| Worker exception | runner | per-chunk; logged; run continues |
| Ctrl-C | runner | cancel pending, mark `cancelled`, flush partials, exit 130 |

A run with `chunks_failed > 0` still writes `meta.json` with
`status: completed` and surfaces a warning in pretty output / a `warnings`
array in JSON.

## 9. Testing

Three layers matching existing Pythinker convention:

**`tests/unit/`** — fake LLM returning canned JSON. Covers:
- Diff source resolution (all four modes, base-ref fallback, empty diff).
- Chunker boundaries (per-file, per-hunk split, vendored skip, glob filters).
- Dedupe rules (file/line/rule collision, severity tiebreak).
- Store atomicity (mid-write crash leaves no half-files).
- `gitignore.py` idempotency.
- SARIF schema (round-trip against `jsonschema` validator).
- Severity threshold gate (exit code for each `--fail-on` setting).

**`tests/e2e/`** — real CLI invocations against fixture git repos with
planted bugs/vulns. Still fake LLM (model selection injected via env var).
Verifies exit codes, file outputs, and `--save` persistence.

**`tests_ai/`** — small set of real-model runs on a curated diff fixture,
asserting recall on planted issues. Gated behind `PYTHINKER_AI_TESTS=1` so
default CI doesn't burn tokens.

## 10. Rollout

Phase 1 is additive:

- No behavior change to existing `pythinker` commands.
- New package added to the workspace; existing `make check` / `make test`
  picks it up automatically once added to the workspace list.
- AGENTS.md verification matrix gains one row for `packages/pythinker-review`.
- Existing `review` subagent role stays untouched. New roles
  (`code-reviewer`, `security-reviewer`) are additions.
- README's "What's New" gets a Phase 1 entry once shipped.
- No new external dependencies beyond `typer`, `pydantic`, `ulid-py`, and
  the existing `pythinker-core` reuse. `typer` and `pydantic` are already
  in the workspace.

## 11. Phasing (forward look)

This spec only covers Phase 1. Subsequent phases each get their own spec:

- **Phase 2 — Local audit (clawpatch-style)**: semantic slicer for the whole
  repo, per-slice review, triage CLI (`pythinker review triage <id>`),
  regression diffing between runs.
- **Phase 3 — Deep security (deepsec-style)**: matchers system, INFO.md
  project context injection, FP-cutting revalidation pass, multi-machine
  worker fan-out.
- **Phase 4 — PR provider integrations**: vendor `blackbox/code-review`'s
  `git_providers/` (already Python) for GitHub / GitLab / Bitbucket /
  Azure DevOps; add `pythinker review pr <url|number>`; ship a GitHub
  Action.
- **Phase 5 — Fix loop**: `pythinker review fix --finding <id>` runs an
  isolated worktree, validates with configured commands, records a patch
  attempt. Never auto-applies.

Each phase builds on Phase 1's findings store, data model, and subagent
substrate.

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM cost on large diffs | `--jobs` cap, per-chunk size limit, `--exclude`, hard-skip vendored paths by default. Document recommended diff size. |
| False positives erode trust | Phase 1 ships `confidence` and `triage` fields; Phase 3's revalidation pass will reduce FP. Document `--fail-on` defaults conservatively (`high`). |
| Prompt regressions silently change output | `config_hash` in `RunMeta` makes "this run used the new prompts" detectable. CI `tests_ai/` recall checks on a fixed fixture catch large regressions. |
| SARIF tooling expects specific severities | Mapping documented; SARIF emitter is unit-tested against the official JSON Schema. |
| `.gitignore` patcher modifies user files unexpectedly | Only on first `--save`, only if file exists, only adds a single line under a marker comment, only if not already present. Documented in README. |
| Subagent registration collides with future renames | Names use new identifiers (`code-reviewer`, `security-reviewer`) distinct from the existing `review` role. |

## 13. Open questions

None at spec time. Items to revisit during implementation planning:

- Exact token budget per chunk (depends on the default model's context window).
- Whether `neighborhood_text` should come from `git show <base_sha>:<path>`
  or from the working-tree file — affects accuracy on uncommitted edits.
- Whether to ship a built-in `.pythinker-review-ignore` file convention or
  rely solely on `--exclude` flags.

These are implementation-level and will be decided in the writing-plans
phase.
