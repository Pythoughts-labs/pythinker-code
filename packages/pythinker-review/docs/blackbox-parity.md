# Blackbox parity map

Phase 1 ports behavior from the mounted blackbox repositories into Pythinker Review. This map is the
source-to-target contract for what is preserved now, what is deferred, and where tests should anchor
compatibility.

## `blackbox/clawpatch-main`

| Blackbox source module/prompt/rule/workflow | Behavior to preserve | Pythinker target path | Test coverage | Documented deviation |
| --- | --- | --- | --- | --- |
| `blackbox/clawpatch-main/README.md`, `docs/index.md`, `docs/spec.md` | Review is evidence-first and read-only; state is durable; fix/PR flows are explicit follow-ups. | `packages/pythinker-review/src/pythinker_review/engine/orchestrator.py`, `store/` | Store round-trip, list/show, fail-closed runner tests. | Phase 1 persists `.pythinker-review/`, not `.clawpatch/`, and does not implement fix/PR flows. |
| `blackbox/clawpatch-main/src/prompt.ts` review prompt | Bounded diff/context, strict JSON, evidence/reasoning/test-analysis/minimum-fix-scope concepts. | `reviewers/prompts/code_review.system.md`, `reviewers/prompts/debug_review.system.md` | Reviewer prompt/caller tests and malformed-output retry tests. | Phase 1 finding schema is smaller; fix-plan fields are deferred until remediation workflow. |
| `blackbox/clawpatch-main/src/review-validation.ts` | Reject stale/out-of-context evidence; never silently persist hallucinated findings. | `reviewers/schema.py`, `engine/dedupe.py`, future `validation.py` | Schema validation, dedupe, runner malformed-output tests. | Full quote-matching evidence validator is deferred; malformed JSON still fails closed now. |
| `blackbox/clawpatch-main/src/app.ts` | Bounded worker pool, retry malformed model output once, run metadata, partial failure visibility. | `engine/runner.py`, `store/models.py`, `store/findings_store.py` | Runner fail-closed/allow-partial tests; store atomicity tests. | Feature locks and full map/review queues are out of Phase 1. |
| `blackbox/clawpatch-main/src/selection.ts`, `src/git.ts` | Git-scoped selection (`since`/dirty/range), changed-file focus, path-relative behavior. | `engine/diff_source.py`, `engine/chunker.py` | Git fixture tests for base/staged/working-tree/range and glob filters. | Phase 1 uses diff-scoped review instead of semantic feature mapping. |
| `blackbox/clawpatch-main/src/reporting.ts` | Human and machine reports preserve evidence and recommended next action. | `output/pretty.py`, `output/json.py`, `output/sarif.py` | Pretty/JSON/SARIF formatter tests. | Clawpatch deslopify clusters are deferred. |
| `blackbox/clawpatch-main/src/validation.ts`, `src/change-audit.ts`, `src/app.ts` fix/open-pr | Mutating fixes require explicit finding IDs, dirty-worktree safety, validation command tracking. | Future `review fix` / remediation phase. | Future dirty-worktree and patch-attempt tests. | Not in Phase 1; Pythinker remains read-only for review/debug/security surfaces. |

## `blackbox/code-review`

| Blackbox source module/prompt/rule/workflow | Behavior to preserve | Pythinker target path | Test coverage | Documented deviation |
| --- | --- | --- | --- | --- |
| `blackbox/code-review/README.md`, `pyproject.toml` | Diff-scoped automated reviewer that can be used locally and in CI. | `packages/pythinker-review`, `cli/review.py`, `src/pythinker_code/cli/review.py` | CLI e2e tests for exit codes and JSON/SARIF output. | PR-provider write/comment integrations are deferred. |
| Code-review prompt/rules | Focus only on issues introduced by the diff; prefer no finding over vague speculation; cite concrete failure modes and changed lines. | `reviewers/prompts/code_review.system.md`, `reviewers/code_review.py` | Reviewer strict-JSON tests and prompt resource load tests. | Uses Pydantic JSON rather than the source project's native review serialization. |
| Structured diff workflow (`__new hunk__` / `__old hunk__`) | Preserve post-change line numbering and old/new comparison blocks. | `engine/structured_diff.py` | Added-file, deletion, binary-skip, line-number tests. | Renderer is lightweight stdlib Python, not a direct Python port of provider/UI code. |
| Token-aware diff/context compression | Keep review input bounded and split oversized files on hunk boundaries. | `engine/context.py`, `engine/chunker.py` | Budget/window tests and per-hunk chunk tests. | Exact token budgeting is character-budgeted in Phase 1. |
| Runtime flow/output parsing/no-findings behavior | Strict model output parsing; malformed output is not a green no-finding result. | `reviewers/*.py`, `engine/runner.py` | One-retry malformed JSON and fail-closed runner tests. | Standalone CLI uses fake/env configuration unless root `pythinker review` injects an active model. |
| Inline comments, labels, provider abstractions | Provider concepts inform later PR integration. | Future PR-provider phase. | Future provider adapter tests. | Phase 1 outputs pretty/JSON/SARIF only. |

## `blackbox/deepsec-main`

| Blackbox source module/prompt/rule/workflow | Behavior to preserve | Pythinker target path | Test coverage | Documented deviation |
| --- | --- | --- | --- | --- |
| `blackbox/deepsec-main/docs/reviewing-changes.md`, scanner/processor direct mode | Direct diff/file mode scans every selected file and fails loud on runtime errors. | `cli/secscan.py`, `engine/runner.py`, `engine/orchestrator.py` | Secscan e2e, empty/malformed output tests, exit-code tests. | No distributed processor or persistent DeepSec data mirror in Phase 1. |
| `packages/processor/src/agents/shared.ts` JSON parsing | Malformed/non-array model output is a batch error, not "no findings". | `reviewers/security_review.py`, `engine/runner.py` | Security reviewer retries once then records `malformed_output`; fail-closed runner tests. | Pythinker schema is `{"findings": [...]}` instead of DeepSec arrays. |
| Security prompt core | Static-analysis mindset, trace inputs/imports/mitigations, report only validated exploitable issues. | `reviewers/prompts/security_review.system.md` | Prompt/caller tests and signal scanner tests. | Severity taxonomy maps to Pythinker `critical/high/medium/low/info`. |
| Scanner rule metadata/matchers | Deterministic signals are prompt anchors, not findings, and carry rule metadata/reasons/confidence. | `signals/models.py`, `signals/scanner.py` | Secret, shell, SQL, deserialization, SSRF, weak-crypto rule tests. | Curated in-process rules replace DeepSec's plugin marketplace for Phase 1. |
| Prompt assembly with tech highlights/slug notes/project context | Batch-scoped anchors avoid prompt bloat while preserving signal context. | `signals/scanner.py`, `reviewers/security_review.py` | Signal formatting in security reviewer tests. | Tech-stack detection and INFO.md are deferred. |
| Revalidation/verdict workflow | Findings should be validated before being treated as final. | Future `revalidate.py`; current strict schema and fail-closed parser. | Future verdict parser tests. | Phase 1 performs one model pass plus deterministic anchors; separate revalidation is deferred. |
| Export/report/metrics | Machine-readable output and CI gating only on net findings. | `output/json.py`, `output/sarif.py`, `cli/_shared.py` | JSON/SARIF schema tests and threshold exit-code tests. | Markdown PR comments and metrics dashboards are deferred. |
