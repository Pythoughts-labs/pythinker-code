"""Code-review pass: prompt + call + strict JSON parse + one retry."""

from __future__ import annotations

from pythinker_review.engine.chunker import Chunk
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.common import ReviewerResult, complete_reviewer_json, load_prompt


def _build_user(chunk: Chunk, *, review_context: str = "", max_findings: int = 5) -> str:
    parts = [
        "Review the following diff for issues introduced by this change.",
    ]
    if max_findings >= 0:
        parts.append(f"Return at most {max_findings} findings for this chunk.")
    if review_context.strip():
        parts.extend(["", "Additional review context:", "======", review_context.strip(), "======"])
    parts.extend(["", chunk.rendered])
    return "\n".join(parts) + "\n"


async def run_code_review_pass(
    *,
    chunk: Chunk,
    llm: ReviewLLM,
    timeout_s: float,
    review_context: str = "",
    max_findings: int = 5,
) -> ReviewerResult:
    result = await complete_reviewer_json(
        llm=llm,
        system=load_prompt("code_review.system.md"),
        user=_build_user(chunk, review_context=review_context, max_findings=max_findings),
        timeout_s=timeout_s,
    )
    if result.ok and max_findings >= 0:
        return ReviewerResult(ok=True, findings=tuple(result.findings[:max_findings]))
    return result
