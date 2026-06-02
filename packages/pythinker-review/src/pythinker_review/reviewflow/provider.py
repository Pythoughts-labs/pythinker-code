"""Provider prompts for stateful Reviewflow workflow commands."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.common import complete_typed_json
from pythinker_review.reviewflow.models import (
    FeatureRecord,
    FeatureReviewFinding,
    FeatureReviewOutput,
    FindingRecord,
    FixPlanOutput,
    RevalidateOutput,
    ReviewflowConfig,
)
from pythinker_review.reviewflow.utils import read_text_bounded

REVIEW_PROMPT_FILE_CHAR_LIMIT = 24_000

REVIEW_SYSTEM = (
    "You are Pythinker Review running a pure-Python Reviewflow review.\n"
    "Return strict JSON only. Review is read-only. Report only concrete, actionable findings "
    "with evidence inside the supplied feature files. Prefer no findings over speculation.\n"
)

REVALIDATE_SYSTEM = (
    "You are revalidating one saved code-review finding.\n"
    "Return strict JSON only. Decide whether the finding is still open, fixed, false-positive, "
    "or uncertain.\n"
)

FIX_SYSTEM = """You are planning a surgical patch for one accepted finding.
Return strict JSON only with a concise summary and a unified diff rooted at the repository root.
Do not include markdown fences. Keep the diff minimal and scoped to the finding.
"""

ReviewPromptFileRole = Literal["owned", "context", "test"]
ReviewDropLayer = Literal["schema", "validation"]


@dataclass(frozen=True, slots=True)
class ReviewPromptLineRange:
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class ReviewPromptFileManifest:
    path: str
    role: ReviewPromptFileRole
    reason: str
    bytes: int
    included_bytes: int
    included_line_ranges: tuple[ReviewPromptLineRange, ...]
    truncated: bool
    readable: bool
    skipped_reason: str | None
    included_text: str = ""


@dataclass(frozen=True, slots=True)
class ReviewPromptManifest:
    max_owned_files: int
    max_context_files: int
    included_files: tuple[ReviewPromptFileManifest, ...]
    omitted_files: tuple[dict[str, str], ...]
    prompt_bytes: int
    approximate_tokens: int


@dataclass(frozen=True, slots=True)
class ReviewPromptBundle:
    prompt: str
    manifest: ReviewPromptManifest


@dataclass(frozen=True, slots=True)
class ReviewDrop:
    path: tuple[str | int, ...]
    message: str
    layer: ReviewDropLayer


@dataclass(frozen=True, slots=True)
class PartitionedFeatureReviewResult:
    output: FeatureReviewOutput
    manifest: ReviewPromptManifest
    dropped_findings: tuple[ReviewDrop, ...]


class _LooseFeatureReviewOutput(BaseModel):
    findings: list[Any] = Field(default_factory=list)


def feature_review_user_prompt(
    *,
    root: Path,
    feature: FeatureRecord,
    config: ReviewflowConfig,
    mode: str,
    custom_prompt: str | None = None,
) -> str:
    return build_feature_review_prompt_bundle(
        root=root,
        feature=feature,
        config=config,
        mode=mode,
        custom_prompt=custom_prompt,
    ).prompt


def build_feature_review_prompt_bundle(
    *,
    root: Path,
    feature: FeatureRecord,
    config: ReviewflowConfig,
    mode: str,
    custom_prompt: str | None = None,
) -> ReviewPromptBundle:
    prompt_files = _collect_prompt_files(feature, config)
    included_files: list[ReviewPromptFileManifest] = []
    file_blocks: list[str] = []
    for path, role, reason in prompt_files:
        prompt_file = _prompt_file(root=root, path=path, role=role, reason=reason)
        included_files.append(prompt_file.manifest)
        file_blocks.append(prompt_file.block)
    omitted_files = _omitted_prompt_files(feature, config, {path for path, _, _ in prompt_files})
    valid_evidence_paths = [file.path for file in included_files if file.readable]
    custom_block = _custom_prompt_block(custom_prompt)
    prompt_context = _manifest_prompt_context(
        max_owned_files=config.review.max_owned_files,
        max_context_files=config.review.max_context_files,
        included_files=included_files,
        omitted_files=omitted_files,
    )
    tests = "\n".join(f"- {test.path} ({test.command or 'no command'})" for test in feature.tests)
    prompt = f"""
Review mode: {mode}
Feature JSON:
{feature.model_dump_json(by_alias=True, indent=2)}

{custom_block}Relevant tests:
{tests or "- none detected"}

Review guidance:
- Inspect owned files, context files, and linked tests as one feature slice.
- Treat tests as evidence of intended behavior. If tests contradict a suspected bug, skip it or
  downgrade confidence and explain the uncertainty.
- Avoid speculative low-evidence findings. Prefer an empty findings array over a weak guess.
- Deduplicate sibling/root-cause issues: report one finding with multiple evidence refs.
- Evidence paths must be exactly one of the valid paths below.
- When citing line ranges, use the gutter numbers in the Files section.
- Do not cite files or line ranges outside the shown excerpts. If an excerpt is truncated, only cite
  lines that appear in the Files section.
- Provide whyTestsDoNotAlreadyCoverThis, suggestedRegressionTest, and minimumFixScope when useful.
- For shell/YAML/subprocess/Markdown command recipes, treat parsed command output as process-exec
  code; flag mixed command-capture/fallback output that can concatenate machine-readable values.
{_review_mode_guidance(mode)}

Valid evidence paths:
{chr(10).join(f"- {path}" for path in valid_evidence_paths) or "- none"}

Prompt context:
{json.dumps(prompt_context, indent=2)}

Files:
{chr(10).join(file_blocks) or "No readable files."}

Return JSON matching this shape:
{{
  "findings": [
    {{
      "title": "short title",
      "category": "bug|security|performance|concurrency|api-contract|data-loss|test-gap|docs-gap|build-release|maintainability",
      "severity": "critical|high|medium|low",
      "confidence": "high|medium|low",
      "evidence": [{{
        "path": "relative/path",
        "startLine": 1,
        "endLine": 1,
        "symbol": null,
        "quote": "exact snippet or null"
      }}],
      "reasoning": "why this is a real issue",
      "reproduction": "optional concrete trigger or null",
      "recommendation": "minimum safe fix",
      "whyTestsDoNotAlreadyCoverThis": "optional test analysis",
      "suggestedRegressionTest": "optional test to add",
      "minimumFixScope": "smallest file/function scope"
    }}
  ]
}}
""".strip()
    prompt_bytes = len(prompt.encode("utf-8"))
    manifest = ReviewPromptManifest(
        max_owned_files=config.review.max_owned_files,
        max_context_files=config.review.max_context_files,
        included_files=tuple(included_files),
        omitted_files=tuple(omitted_files),
        prompt_bytes=prompt_bytes,
        approximate_tokens=max(1, prompt_bytes // 4),
    )
    return ReviewPromptBundle(prompt=prompt, manifest=manifest)


@dataclass(frozen=True, slots=True)
class _PromptFile:
    block: str
    manifest: ReviewPromptFileManifest


def _collect_prompt_files(
    feature: FeatureRecord, config: ReviewflowConfig
) -> list[tuple[str, ReviewPromptFileRole, str]]:
    output: list[tuple[str, ReviewPromptFileRole, str]] = []
    seen: set[str] = set()

    def add(path: str, role: ReviewPromptFileRole, reason: str) -> None:
        normalized = _normalize_prompt_path(path)
        if normalized in seen:
            return
        seen.add(normalized)
        output.append((normalized, role, reason))

    for ref in feature.owned_files[: config.review.max_owned_files]:
        add(ref.path, "owned", ref.reason)
    for ref in feature.context_files[: config.review.max_context_files]:
        add(ref.path, "context", ref.reason)
    for test in feature.tests[: config.review.max_context_files]:
        add(test.path, "test", test.command or "linked test")
    return output


def _omitted_prompt_files(
    feature: FeatureRecord, config: ReviewflowConfig, included: set[str]
) -> list[dict[str, str]]:
    omitted: list[dict[str, str]] = []

    def add_omitted(path: str, role: str, reason: str) -> None:
        normalized = _normalize_prompt_path(path)
        if normalized not in included:
            omitted.append({"path": normalized, "role": role, "reason": reason})

    for ref in feature.owned_files[config.review.max_owned_files :]:
        add_omitted(ref.path, "owned", "maxOwnedFiles")
    for ref in feature.context_files[config.review.max_context_files :]:
        add_omitted(ref.path, "context", "maxContextFiles")
    for test in feature.tests[config.review.max_context_files :]:
        add_omitted(test.path, "test", "maxContextFiles")
    return omitted


def _prompt_file(*, root: Path, path: str, role: ReviewPromptFileRole, reason: str) -> _PromptFile:
    full_path = _safe_prompt_path(root, path)
    if full_path is None:
        manifest = ReviewPromptFileManifest(
            path=path,
            role=role,
            reason=reason,
            bytes=0,
            included_bytes=0,
            included_line_ranges=(),
            truncated=False,
            readable=False,
            skipped_reason="unsafe path",
        )
        return _PromptFile(
            block=f"## {path}\nRole: {role}\nReason: {reason}\n[unsafe path]",
            manifest=manifest,
        )
    try:
        text = full_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        manifest = ReviewPromptFileManifest(
            path=path,
            role=role,
            reason=reason,
            bytes=0,
            included_bytes=0,
            included_line_ranges=(),
            truncated=False,
            readable=False,
            skipped_reason=f"unreadable: {exc.__class__.__name__}",
        )
        return _PromptFile(
            block=f"## {path}\nRole: {role}\nReason: {reason}\n[unreadable]", manifest=manifest
        )
    included = text[:REVIEW_PROMPT_FILE_CHAR_LIMIT]
    truncated = len(included) < len(text)
    numbered = _line_numbered(included)
    line_count = max(1, included.count("\n") + (0 if included.endswith("\n") else 1))
    manifest = ReviewPromptFileManifest(
        path=path,
        role=role,
        reason=reason,
        bytes=len(text.encode("utf-8")),
        included_bytes=len(included.encode("utf-8")),
        included_line_ranges=(ReviewPromptLineRange(start_line=1, end_line=line_count),),
        truncated=truncated,
        readable=True,
        skipped_reason=None,
        included_text=included,
    )
    trailer = "\n[truncated: only the lines above are valid evidence]" if truncated else ""
    block = f"## {path}\nRole: {role}\nReason: {reason}\n```text\n{numbered}{trailer}\n```"
    return _PromptFile(block=block, manifest=manifest)


def _safe_prompt_path(root: Path, path: str) -> Path | None:
    try:
        root_resolved = root.resolve()
        full_path = (root / path).resolve()
        full_path.relative_to(root_resolved)
    except (OSError, ValueError):
        return None
    return full_path


def _line_numbered(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        lines = [""]
    return "\n".join(f"{idx:>5} | {line}" for idx, line in enumerate(lines, start=1))


def _manifest_prompt_context(
    *,
    max_owned_files: int,
    max_context_files: int,
    included_files: list[ReviewPromptFileManifest],
    omitted_files: list[dict[str, str]],
) -> dict[str, object]:
    return {
        "maxOwnedFiles": max_owned_files,
        "maxContextFiles": max_context_files,
        "includedFiles": [
            {
                "path": file.path,
                "role": file.role,
                "reason": file.reason,
                "bytes": file.bytes,
                "includedBytes": file.included_bytes,
                "includedLineRanges": [
                    {"startLine": item.start_line, "endLine": item.end_line}
                    for item in file.included_line_ranges
                ],
                "truncated": file.truncated,
                "readable": file.readable,
                "skippedReason": file.skipped_reason,
            }
            for file in included_files
        ],
        "omittedFiles": omitted_files,
    }


def _custom_prompt_block(custom_prompt: str | None) -> str:
    if custom_prompt is None or not custom_prompt.strip():
        return ""
    return f"Additional reviewer guidance from --prompt-file:\n{custom_prompt.strip()}\n\n"


def _review_mode_guidance(mode: str) -> str:
    if mode != "deslopify":
        return ""
    return """- Deslopify mode: report only concrete simplification findings in category
  maintainability or performance.
- Do not look for general bugs, security issues, API contract problems, or hypothetical edge cases.
- Findings must remove real complexity or measurable waste without changing behavior."""


def _normalize_prompt_path(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./").rstrip("/")


async def review_feature(
    *,
    llm: ReviewLLM,
    root: Path,
    feature: FeatureRecord,
    config: ReviewflowConfig,
    mode: str,
    timeout_s: float,
    custom_prompt: str | None = None,
) -> FeatureReviewOutput:
    return (
        await review_feature_partitioned(
            llm=llm,
            root=root,
            feature=feature,
            config=config,
            mode=mode,
            timeout_s=timeout_s,
            custom_prompt=custom_prompt,
        )
    ).output


async def review_feature_partitioned(
    *,
    llm: ReviewLLM,
    root: Path,
    feature: FeatureRecord,
    config: ReviewflowConfig,
    mode: str,
    timeout_s: float,
    custom_prompt: str | None = None,
) -> PartitionedFeatureReviewResult:
    bundle = build_feature_review_prompt_bundle(
        root=root,
        feature=feature,
        config=config,
        mode=mode,
        custom_prompt=custom_prompt,
    )
    result = await complete_typed_json(
        llm=llm,
        system=REVIEW_SYSTEM,
        user=bundle.prompt,
        timeout_s=timeout_s,
        output_type=_LooseFeatureReviewOutput,
    )
    if not result.ok or result.output is None:
        raise RuntimeError(result.failure_message or result.failure_reason or "review failed")
    output, drops = _partition_review_output(result.output)
    return PartitionedFeatureReviewResult(
        output=output,
        manifest=bundle.manifest,
        dropped_findings=drops,
    )


def _partition_review_output(
    output: _LooseFeatureReviewOutput,
) -> tuple[FeatureReviewOutput, tuple[ReviewDrop, ...]]:
    findings: list[FeatureReviewFinding] = []
    drops: list[ReviewDrop] = []
    for idx, candidate in enumerate(output.findings):
        try:
            findings.append(FeatureReviewFinding.model_validate(candidate))
        except ValidationError as exc:
            drops.append(
                ReviewDrop(
                    path=("findings", idx),
                    message=_format_validation_error(exc),
                    layer="schema",
                )
            )
    return FeatureReviewOutput(findings=findings), tuple(drops)


def _format_validation_error(error: ValidationError) -> str:
    first = error.errors()[0] if error.errors() else None
    if first is None:
        return "schema validation failed"
    loc = ".".join(str(item) for item in first.get("loc", ())) or "<root>"
    msg = str(first.get("msg", "schema validation failed"))
    return f"{loc}: {msg}"


async def revalidate_finding(
    *, llm: ReviewLLM, root: Path, finding: FindingRecord, timeout_s: float
) -> RevalidateOutput:
    evidence_blocks: list[str] = []
    for evidence in finding.evidence:
        evidence_blocks.append(
            f"## {evidence.path}\n```\n{read_text_bounded(root / evidence.path, limit_chars=12_000)}\n```"
        )
    user = f"""
Saved finding:
{finding.model_dump_json(by_alias=True, indent=2)}

Current evidence files:
{chr(10).join(evidence_blocks) or "No readable evidence files."}

Return JSON: {{"outcome":"open|fixed|false-positive|wont-fix|uncertain","reasoning":"...","commands":["optional validation command"]}}
""".strip()
    result = await complete_typed_json(
        llm=llm,
        system=REVALIDATE_SYSTEM,
        user=user,
        timeout_s=timeout_s,
        output_type=RevalidateOutput,
    )
    if not result.ok or result.output is None:
        raise RuntimeError(result.failure_message or result.failure_reason or "revalidation failed")
    return result.output


async def plan_fix(
    *,
    llm: ReviewLLM,
    root: Path,
    finding: FindingRecord,
    feature: FeatureRecord,
    config: ReviewflowConfig,
    timeout_s: float,
) -> FixPlanOutput:
    file_refs = feature.owned_files[: config.review.max_owned_files]
    file_blocks = [
        f"## {ref.path}\n```\n{read_text_bounded(root / ref.path, limit_chars=20_000)}\n```"
        for ref in file_refs
    ]
    user = f"""
Finding to fix:
{finding.model_dump_json(by_alias=True, indent=2)}

Feature:
{feature.model_dump_json(by_alias=True, indent=2)}

Current files:
{chr(10).join(file_blocks) or "No readable feature files."}

Configured validation commands:
{json.dumps(validation_commands_for_feature(feature, config))}

Return JSON: {{"summary":"what changed", "unifiedDiff":"diff --git ... or null", "commands":["optional extra validation"]}}
""".strip()
    result = await complete_typed_json(
        llm=llm,
        system=FIX_SYSTEM,
        user=user,
        timeout_s=timeout_s,
        output_type=FixPlanOutput,
    )
    if not result.ok or result.output is None:
        raise RuntimeError(result.failure_message or result.failure_reason or "fix planning failed")
    return result.output


def validation_commands_for_feature(feature: FeatureRecord, config: ReviewflowConfig) -> list[str]:
    commands: list[str] = []
    if config.commands.format:
        commands.append(config.commands.format)
    for test in feature.tests:
        if test.command and test.command not in commands:
            commands.append(test.command)
    for command in (config.commands.typecheck, config.commands.lint, config.commands.test):
        if command and command not in commands:
            commands.append(command)
    return commands


__all__ = [
    "PartitionedFeatureReviewResult",
    "REVIEW_PROMPT_FILE_CHAR_LIMIT",
    "ReviewDrop",
    "ReviewPromptFileManifest",
    "ReviewPromptManifest",
    "ReviewPromptBundle",
    "build_feature_review_prompt_bundle",
    "feature_review_user_prompt",
    "plan_fix",
    "review_feature",
    "review_feature_partitioned",
    "revalidate_finding",
    "validation_commands_for_feature",
]
