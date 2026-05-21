import json

import pytest

from pythinker_review.engine.chunker import Chunk
from pythinker_review.engine.structured_diff import StructuredHunk
from pythinker_review.llm.fake import FakeReviewLLM
from pythinker_review.reviewers.code_review import run_code_review_pass
from pythinker_review.reviewers.debug_review import run_debug_review_pass
from pythinker_review.reviewers.security_review import run_security_review_pass


def _chunk() -> Chunk:
    h = StructuredHunk(header="@@ -1 +1 @@", new_block="1 +x=1", old_block="")
    return Chunk(file="x.py", hunks=(h,), rendered="## File: 'x.py'\nx=1")


@pytest.mark.asyncio
async def test_code_review_returns_findings_on_valid_json() -> None:
    llm = FakeReviewLLM(
        scripted=[
            json.dumps(
                {
                    "findings": [
                        {
                            "rule_id": "review.error_handling",
                            "title": "missing handler",
                            "rationale": "...",
                            "category": "correctness",
                            "severity": "low",
                            "file": "x.py",
                            "start_line": 1,
                            "end_line": 1,
                            "confidence": 0.6,
                        }
                    ]
                }
            )
        ]
    )
    result = await run_code_review_pass(chunk=_chunk(), llm=llm, timeout_s=10.0)
    assert result.ok
    assert len(result.findings) == 1


@pytest.mark.asyncio
async def test_security_review_retries_once_on_malformed_then_succeeds() -> None:
    llm = FakeReviewLLM(scripted=["not json", '{"findings": []}'])
    result = await run_security_review_pass(chunk=_chunk(), signals=[], llm=llm, timeout_s=10.0)
    assert result.ok
    assert result.findings == ()
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_security_review_fails_after_second_malformed() -> None:
    result = await run_security_review_pass(
        chunk=_chunk(),
        signals=[],
        llm=FakeReviewLLM(scripted=["nope", "still nope"]),
        timeout_s=10.0,
    )
    assert not result.ok
    assert result.failure_reason == "malformed_output"


@pytest.mark.asyncio
async def test_debug_review_returns_root_cause_findings() -> None:
    llm = FakeReviewLLM(scripted=['{"findings": []}'])
    result = await run_debug_review_pass(
        chunk=_chunk(), diagnostic="AssertionError at x.py:1", llm=llm, timeout_s=10.0
    )
    assert result.ok
    assert llm.calls
