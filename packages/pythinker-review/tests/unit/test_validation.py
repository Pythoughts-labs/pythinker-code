import json

import pytest

from pythinker_review.engine.chunker import Chunk
from pythinker_review.engine.runner import run_chunks
from pythinker_review.engine.structured_diff import StructuredHunk
from pythinker_review.llm.fake import FakeReviewLLM


def _chunk() -> Chunk:
    h = StructuredHunk(
        header="@@ -1,2 +1,2 @@",
        new_block="1   def f():\n2 +    return user",
        old_block="  def f():\n-    return 'ok'",
    )
    return Chunk(file="x.py", hunks=(h,), rendered="## File: 'x.py'\n" + h.new_block)


def _payload(**overrides: object) -> str:
    finding = {
        "rule_id": "review.example",
        "title": "bad return",
        "rationale": "returns untrusted data",
        "category": "correctness",
        "severity": "low",
        "file": "x.py",
        "start_line": 2,
        "end_line": 2,
        "confidence": 0.9,
        "evidence_snippet": "return user",
    }
    finding.update(overrides)
    return json.dumps({"findings": [finding]})


@pytest.mark.asyncio
async def test_runner_drops_finding_for_file_outside_chunk() -> None:
    result = await run_chunks(
        chunks=[_chunk()],
        passes=("code_review",),
        signals_by_file={},
        diagnostics_by_file={},
        llm=FakeReviewLLM(scripted=[_payload(file="../secret.py")]),
        jobs=1,
        per_chunk_timeout_s=10.0,
        allow_partial=False,
    )
    assert result.findings == ()
    # Model hallucinations show up in chunk_failures so they're visible, but
    # don't gate the run — one stray hallucinated path shouldn't abort review.
    assert result.failed is False
    assert result.chunk_failures[0].reason == "validation_error"


@pytest.mark.asyncio
async def test_runner_keeps_valid_finding_with_matching_evidence() -> None:
    result = await run_chunks(
        chunks=[_chunk()],
        passes=("code_review",),
        signals_by_file={},
        diagnostics_by_file={},
        llm=FakeReviewLLM(scripted=[_payload()]),
        jobs=1,
        per_chunk_timeout_s=10.0,
        allow_partial=False,
    )
    assert result.chunks_failed == 0
    assert len(result.findings) == 1


@pytest.mark.asyncio
async def test_runner_rejects_line_range_outside_hunk() -> None:
    result = await run_chunks(
        chunks=[_chunk()],
        passes=("code_review",),
        signals_by_file={},
        diagnostics_by_file={},
        llm=FakeReviewLLM(scripted=[_payload(start_line=20, end_line=20)]),
        jobs=1,
        per_chunk_timeout_s=10.0,
        allow_partial=True,
    )
    assert result.findings == ()
    assert result.failed is False
    assert result.chunk_failures[0].reason == "validation_error"
