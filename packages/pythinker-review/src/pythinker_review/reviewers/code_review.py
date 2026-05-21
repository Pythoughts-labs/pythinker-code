"""Code-review pass: prompt + call + strict JSON parse + one retry."""

from __future__ import annotations

from pythinker_review.engine.chunker import Chunk
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.common import ReviewerResult, complete_reviewer_json, load_prompt


def _build_user(chunk: Chunk) -> str:
    return f"Review the following diff for issues introduced by this change.\n\n{chunk.rendered}\n"


async def run_code_review_pass(*, chunk: Chunk, llm: ReviewLLM, timeout_s: float) -> ReviewerResult:
    return await complete_reviewer_json(
        llm=llm,
        system=load_prompt("code_review.system.md"),
        user=_build_user(chunk),
        timeout_s=timeout_s,
    )
