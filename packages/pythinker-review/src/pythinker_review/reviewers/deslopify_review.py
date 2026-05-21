"""Read-only deslopify pass ported from the source workflow's simplification review mode."""

from __future__ import annotations

from pythinker_review.engine.chunker import Chunk
from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewers.common import ReviewerResult, complete_reviewer_json, load_prompt


def _build_user(chunk: Chunk) -> str:
    return (
        "Review this diff only for locally provable accidental complexity, duplication, "
        "unnecessary wrappers, dead compatibility branches, or brittle test/typing band-aids.\n\n"
        f"{chunk.rendered}\n"
    )


async def run_deslopify_review_pass(
    *, chunk: Chunk, llm: ReviewLLM, timeout_s: float
) -> ReviewerResult:
    return await complete_reviewer_json(
        llm=llm,
        system=load_prompt("deslopify_review.system.md"),
        user=_build_user(chunk),
        timeout_s=timeout_s,
    )
