"""Shared reviewer call helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from importlib import resources

from pydantic import ValidationError

from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.schema import RawFinding, ReviewerOutput
from pythinker_review.store.models import ChunkFailureReason

_RETRY_SUFFIX = (
    "\n\nIMPORTANT: Your previous response was not valid JSON for the given schema. "
    "Reply with strict JSON only, no prose, no markdown fences."
)


@dataclass(frozen=True, slots=True)
class ReviewerResult:
    ok: bool
    findings: tuple[RawFinding, ...] = field(default_factory=tuple)
    failure_reason: ChunkFailureReason | None = None
    failure_message: str = ""


def load_prompt(filename: str) -> str:
    return (
        resources.files("pythinker_review.reviewers.prompts")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


async def complete_reviewer_json(
    *, llm: ReviewLLM, system: str, user: str, timeout_s: float
) -> ReviewerResult:
    prompt = user
    for attempt in (1, 2):
        try:
            raw = await asyncio.wait_for(
                llm.complete_json(system=system, user=prompt, timeout_s=timeout_s),
                timeout=timeout_s,
            )
        except TimeoutError:
            return ReviewerResult(False, failure_reason="timeout", failure_message="LLM timed out")
        except Exception as exc:  # noqa: BLE001 - provider boundary
            return ReviewerResult(False, failure_reason="llm_error", failure_message=str(exc))
        try:
            out = ReviewerOutput.model_validate_json(raw)
            return ReviewerResult(ok=True, findings=tuple(out.findings))
        except ValidationError as exc:
            if attempt == 2:
                return ReviewerResult(
                    False, failure_reason="malformed_output", failure_message=str(exc)
                )
            prompt = prompt + _RETRY_SUFFIX
    return ReviewerResult(False, failure_reason="malformed_output")
