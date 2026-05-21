"""Debug/root-cause pass over failure diagnostics and diff context."""

from __future__ import annotations

from pythinker_review.engine.chunker import Chunk
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.common import ReviewerResult, complete_reviewer_json, load_prompt


def _build_user(chunk: Chunk, diagnostic: str) -> str:
    return (
        "Failure evidence:\n"
        f"{diagnostic}\n\n"
        "Correlate the failure with this changed diff context.\n\n"
        f"{chunk.rendered}\n"
    )


async def run_debug_review_pass(
    *, chunk: Chunk, diagnostic: str, llm: ReviewLLM, timeout_s: float
) -> ReviewerResult:
    return await complete_reviewer_json(
        llm=llm,
        system=load_prompt("debug_review.system.md"),
        user=_build_user(chunk, diagnostic),
        timeout_s=timeout_s,
    )
