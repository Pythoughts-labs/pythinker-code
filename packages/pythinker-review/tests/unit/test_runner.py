import json

import pytest

from pythinker_review.engine.chunker import Chunk
from pythinker_review.engine.runner import RunnerResult, run_chunks
from pythinker_review.engine.structured_diff import StructuredHunk
from pythinker_review.llm.fake import FakeReviewLLM


def _chunk(name: str = "x.py") -> Chunk:
    h = StructuredHunk(header="@@ -1 +1 @@", new_block="1 +x=1", old_block="")
    return Chunk(file=name, hunks=(h,), rendered=f"## File: '{name}'\nx=1")


def _payload(rule: str = "review.x") -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "rule_id": rule,
                    "title": "t",
                    "rationale": "r",
                    "category": "correctness",
                    "severity": "low",
                    "file": "x.py",
                    "start_line": 1,
                    "end_line": 1,
                    "confidence": 0.9,
                }
            ]
        }
    )


@pytest.mark.asyncio
async def test_runs_both_passes_in_parallel_and_collects_findings() -> None:
    result = await run_chunks(
        chunks=[_chunk()],
        passes=("code_review", "security_review"),
        signals_by_file={},
        diagnostics_by_file={},
        llm=FakeReviewLLM(scripted=[_payload("review.x"), _payload("sec.x")]),
        jobs=2,
        per_chunk_timeout_s=10.0,
        allow_partial=False,
    )
    assert isinstance(result, RunnerResult)
    assert result.chunks_done == 2
    assert result.chunks_failed == 0
    assert len(result.findings) == 2


@pytest.mark.asyncio
async def test_chunk_failure_is_fatal_without_allow_partial() -> None:
    result = await run_chunks(
        chunks=[_chunk()],
        passes=("code_review",),
        signals_by_file={},
        diagnostics_by_file={},
        llm=FakeReviewLLM(scripted=["not json", "still nope"]),
        jobs=1,
        per_chunk_timeout_s=10.0,
        allow_partial=False,
    )
    assert result.chunks_failed == 1
    assert result.failed is True


@pytest.mark.asyncio
async def test_chunk_failure_is_warning_with_allow_partial() -> None:
    result = await run_chunks(
        chunks=[_chunk()],
        passes=("code_review",),
        signals_by_file={},
        diagnostics_by_file={},
        llm=FakeReviewLLM(scripted=["not json", "still nope"]),
        jobs=1,
        per_chunk_timeout_s=10.0,
        allow_partial=True,
    )
    assert result.chunks_failed == 1
    assert result.failed is False
    assert result.chunk_failures


@pytest.mark.asyncio
async def test_debug_pass_uses_diagnostic_input() -> None:
    llm = FakeReviewLLM(scripted=['{"findings": []}'])
    result = await run_chunks(
        chunks=[_chunk()],
        passes=("debug_review",),
        signals_by_file={},
        diagnostics_by_file={"x.py": "AssertionError at x.py:1"},
        llm=llm,
        jobs=1,
        per_chunk_timeout_s=10.0,
        allow_partial=False,
    )
    assert result.chunks_failed == 0
    assert llm.calls
