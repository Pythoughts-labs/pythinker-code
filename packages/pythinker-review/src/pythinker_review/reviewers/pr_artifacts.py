"""Prompt runners for code-reviewr-derived PR assistant artifacts."""

from __future__ import annotations

from pydantic import BaseModel

from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.artifacts import (
    ChangelogOutput,
    CodeSuggestionsOutput,
    ComplianceOutput,
    DocsOutput,
    PRDescriptionOutput,
    PRLabelsOutput,
    PRQuestionAnswerOutput,
)
from pythinker_review.reviewers.common import TypedReviewerResult, complete_typed_json, load_prompt

_META_TEMPLATE = """Repository metadata:
- Branch: {branch}
- Base: {base_ref}
- Source: {source_label}
- Changed files: {changed_files}
"""


def build_artifact_user(
    *,
    diff: str,
    metadata: dict[str, str],
    question: str | None = None,
    artifact_context: str | None = None,
) -> str:
    """Build the user prompt shared by code-reviewr-derived artifact tools."""
    changed_files = metadata.get("changed_files", "")
    meta = _META_TEMPLATE.format(
        branch=metadata.get("branch") or "unknown",
        base_ref=metadata.get("base_ref") or "unknown",
        source_label=metadata.get("source_label") or "unknown",
        changed_files=changed_files or "unknown",
    )
    if question is not None:
        meta += f"\nUser question:\n{question.strip()}\n"
    if artifact_context is not None:
        meta += f"\nArtifact context:\n======\n{artifact_context.strip()}\n======\n"
    return f"{meta}\nStructured diff:\n======\n{diff.strip()}\n======\n"


async def run_pr_description_artifact(
    *, diff: str, metadata: dict[str, str], llm: ReviewLLM, timeout_s: float
) -> TypedReviewerResult[PRDescriptionOutput]:
    return await _complete_artifact(
        prompt="pr_description.system.md",
        output_type=PRDescriptionOutput,
        diff=diff,
        metadata=metadata,
        llm=llm,
        timeout_s=timeout_s,
    )


async def run_code_suggestions_artifact(
    *, diff: str, metadata: dict[str, str], llm: ReviewLLM, timeout_s: float
) -> TypedReviewerResult[CodeSuggestionsOutput]:
    return await _complete_artifact(
        prompt="code_suggestions.system.md",
        output_type=CodeSuggestionsOutput,
        diff=diff,
        metadata=metadata,
        llm=llm,
        timeout_s=timeout_s,
    )


async def run_pr_question_artifact(
    *, question: str, diff: str, metadata: dict[str, str], llm: ReviewLLM, timeout_s: float
) -> TypedReviewerResult[PRQuestionAnswerOutput]:
    return await _complete_artifact(
        prompt="pr_questions.system.md",
        output_type=PRQuestionAnswerOutput,
        diff=diff,
        metadata=metadata,
        question=question,
        llm=llm,
        timeout_s=timeout_s,
    )


async def run_labels_artifact(
    *, diff: str, metadata: dict[str, str], llm: ReviewLLM, timeout_s: float
) -> TypedReviewerResult[PRLabelsOutput]:
    return await _complete_artifact(
        prompt="labels.system.md",
        output_type=PRLabelsOutput,
        diff=diff,
        metadata=metadata,
        llm=llm,
        timeout_s=timeout_s,
    )


async def run_changelog_artifact(
    *, diff: str, metadata: dict[str, str], llm: ReviewLLM, timeout_s: float
) -> TypedReviewerResult[ChangelogOutput]:
    return await _complete_artifact(
        prompt="changelog.system.md",
        output_type=ChangelogOutput,
        diff=diff,
        metadata=metadata,
        llm=llm,
        timeout_s=timeout_s,
    )


async def run_docs_artifact(
    *, diff: str, metadata: dict[str, str], llm: ReviewLLM, timeout_s: float
) -> TypedReviewerResult[DocsOutput]:
    return await _complete_artifact(
        prompt="docs.system.md",
        output_type=DocsOutput,
        diff=diff,
        metadata=metadata,
        llm=llm,
        timeout_s=timeout_s,
    )


async def run_compliance_artifact(
    *,
    diff: str,
    metadata: dict[str, str],
    compliance_context: str,
    llm: ReviewLLM,
    timeout_s: float,
) -> TypedReviewerResult[ComplianceOutput]:
    return await _complete_artifact(
        prompt="compliance.system.md",
        output_type=ComplianceOutput,
        diff=diff,
        metadata=metadata,
        artifact_context=compliance_context,
        llm=llm,
        timeout_s=timeout_s,
    )


async def _complete_artifact(
    *,
    prompt: str,
    output_type: type[BaseModel],
    diff: str,
    metadata: dict[str, str],
    llm: ReviewLLM,
    timeout_s: float,
    question: str | None = None,
    artifact_context: str | None = None,
) -> TypedReviewerResult:
    return await complete_typed_json(
        llm=llm,
        system=load_prompt(prompt),
        user=build_artifact_user(
            diff=diff,
            metadata=metadata,
            question=question,
            artifact_context=artifact_context,
        ),
        timeout_s=timeout_s,
        output_type=output_type,
    )


__all__ = [
    "build_artifact_user",
    "run_changelog_artifact",
    "run_code_suggestions_artifact",
    "run_compliance_artifact",
    "run_docs_artifact",
    "run_labels_artifact",
    "run_pr_description_artifact",
    "run_pr_question_artifact",
]
