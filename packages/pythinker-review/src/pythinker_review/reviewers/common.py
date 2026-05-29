"""Shared reviewer call helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from importlib import resources

from pydantic import BaseModel, ValidationError

from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.schema import RawFinding, ReviewerOutput
from pythinker_review.store.models import ChunkFailureReason

_RETRY_ERROR_BUDGET = 600


def _retry_suffix(last_error: str) -> str:
    """Build the retry instruction, surfacing the concrete validation error.

    The first version only said "reply with valid JSON", which is useless when
    the failure is a *content* violation (e.g. a title over the length cap) on
    otherwise-valid JSON — the model has no signal about what to change. We now
    relay the actual parser/validation error so the model can self-correct.
    """
    suffix = (
        "\n\nIMPORTANT: Your previous response could not be parsed into the required "
        "schema. Reply with strict JSON only — no prose, no markdown fences — and make "
        "every field satisfy the schema (in particular keep each finding 'title' to 80 "
        "characters or fewer)."
    )
    detail = " ".join(last_error.split())
    if detail:
        if len(detail) > _RETRY_ERROR_BUDGET:
            detail = f"{detail[:_RETRY_ERROR_BUDGET]} …"
        suffix += f"\n\nValidation error from your previous attempt: {detail}"
    return suffix


@dataclass(frozen=True, slots=True)
class ReviewerResult:
    ok: bool
    findings: tuple[RawFinding, ...] = field(default_factory=tuple)
    failure_reason: ChunkFailureReason | None = None
    failure_message: str = ""


@dataclass(frozen=True, slots=True)
class TypedReviewerResult[T: BaseModel]:
    ok: bool
    output: T | None = None
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
    parsed = await complete_typed_json(
        llm=llm,
        system=system,
        user=user,
        timeout_s=timeout_s,
        output_type=ReviewerOutput,
    )
    if not parsed.ok or parsed.output is None:
        return ReviewerResult(
            ok=False,
            failure_reason=parsed.failure_reason,
            failure_message=parsed.failure_message,
        )
    return ReviewerResult(ok=True, findings=tuple(parsed.output.findings))


async def complete_typed_json[T: BaseModel](
    *, llm: ReviewLLM, system: str, user: str, timeout_s: float, output_type: type[T]
) -> TypedReviewerResult[T]:
    prompt = user
    last_error = ""
    for attempt in (1, 2):
        try:
            raw = await asyncio.wait_for(
                llm.complete_json(system=system, user=prompt, timeout_s=timeout_s),
                timeout=timeout_s,
            )
        except TimeoutError:
            return TypedReviewerResult(
                False, failure_reason="timeout", failure_message="LLM timed out"
            )
        except Exception as exc:  # noqa: BLE001 - provider boundary
            return TypedReviewerResult(False, failure_reason="llm_error", failure_message=str(exc))
        for candidate in _json_candidates(raw):
            try:
                return TypedReviewerResult(
                    ok=True, output=output_type.model_validate_json(candidate)
                )
            except ValidationError as exc:
                last_error = str(exc)
        if attempt == 2:
            return TypedReviewerResult(
                False, failure_reason="malformed_output", failure_message=last_error
            )
        prompt = user + _retry_suffix(last_error)
    return TypedReviewerResult(False, failure_reason="malformed_output")


def _json_candidates(raw: str) -> tuple[str, ...]:
    stripped = raw.strip()
    candidates = [stripped]
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        fenced = "\n".join(lines).strip()
        if fenced and fenced not in candidates:
            candidates.append(fenced)
    for extracted in _extract_json_objects(stripped):
        if extracted not in candidates:
            candidates.append(extracted)
    return tuple(candidates)


def _extract_json_objects(text: str) -> tuple[str, ...]:
    objects: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escape = False
    for idx, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start : idx + 1])
                start = None
    return tuple(objects)
