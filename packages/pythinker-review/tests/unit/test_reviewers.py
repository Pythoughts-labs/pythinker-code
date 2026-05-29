import json

import pytest

from pythinker_review.engine.chunker import Chunk
from pythinker_review.engine.structured_diff import StructuredHunk
from pythinker_review.llm.fake import FakeReviewLLM
from pythinker_review.reviewers.code_review import run_code_review_pass
from pythinker_review.reviewers.debug_review import run_debug_review_pass
from pythinker_review.reviewers.deslopify_review import run_deslopify_review_pass
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
async def test_code_review_includes_extra_context_and_caps_findings() -> None:
    payload = json.dumps(
        {
            "findings": [
                {
                    "rule_id": f"review.issue_{idx}",
                    "title": f"issue {idx}",
                    "rationale": "...",
                    "category": "correctness",
                    "severity": "low",
                    "file": "x.py",
                    "start_line": 1,
                    "end_line": 1,
                    "confidence": 0.6,
                }
                for idx in range(3)
            ]
        }
    )
    llm = FakeReviewLLM(scripted=[payload])
    result = await run_code_review_pass(
        chunk=_chunk(),
        llm=llm,
        timeout_s=10.0,
        review_context="Extra review instructions:\n======\nFocus on API risks\n======",
        max_findings=2,
    )
    assert result.ok
    assert len(result.findings) == 2
    assert "Focus on API risks" in llm.calls[0][1]
    assert "Return at most 2 findings" in llm.calls[0][1]


@pytest.mark.asyncio
async def test_security_review_retries_once_on_malformed_then_succeeds() -> None:
    llm = FakeReviewLLM(scripted=["not json", '{"findings": []}'])
    result = await run_security_review_pass(chunk=_chunk(), signals=[], llm=llm, timeout_s=10.0)
    assert result.ok
    assert result.findings == ()
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_retry_prompt_surfaces_previous_validation_error() -> None:
    # The retry must relay the concrete parser error so the model can
    # self-correct, not just repeat a generic "reply with valid JSON".
    llm = FakeReviewLLM(scripted=["not valid json at all", '{"findings": []}'])
    result = await run_code_review_pass(chunk=_chunk(), llm=llm, timeout_s=10.0)
    assert result.ok
    assert len(llm.calls) == 2
    retry_prompt = llm.calls[1][1]
    assert "Validation error from your previous attempt" in retry_prompt
    assert retry_prompt != llm.calls[0][1]


@pytest.mark.asyncio
async def test_overlong_title_is_truncated_not_dropped() -> None:
    # A single finding with an over-long title used to fail the whole chunk.
    # It must now survive (truncated) rather than discard sibling findings.
    payload = json.dumps(
        {
            "findings": [
                {
                    "rule_id": "review.x",
                    "title": "T" * 200,
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
    llm = FakeReviewLLM(scripted=[payload])
    result = await run_code_review_pass(chunk=_chunk(), llm=llm, timeout_s=10.0)
    assert result.ok
    assert len(result.findings) == 1
    assert len(result.findings[0].title) == 80
    assert len(llm.calls) == 1  # parsed on the first attempt, no retry needed


@pytest.mark.asyncio
async def test_reviewer_accepts_json_inside_markdown_fence() -> None:
    llm = FakeReviewLLM(scripted=['```json\n{"findings": []}\n```'])
    result = await run_code_review_pass(chunk=_chunk(), llm=llm, timeout_s=10.0)
    assert result.ok
    assert result.findings == ()


@pytest.mark.asyncio
async def test_reviewer_skips_prose_example_object_before_real_json() -> None:
    llm = FakeReviewLLM(scripted=['Example: {}\nFinal answer:\n{"findings": []}'])
    result = await run_code_review_pass(chunk=_chunk(), llm=llm, timeout_s=10.0)
    assert result.ok
    assert result.findings == ()


@pytest.mark.asyncio
async def test_security_review_receives_advisor_context() -> None:
    llm = FakeReviewLLM(scripted=['{"findings": []}'])
    result = await run_security_review_pass(
        chunk=_chunk(),
        signals=[],
        llm=llm,
        timeout_s=10.0,
        advisor_context="## Security advisor context\nDetected tech tags: fastapi",
    )
    assert result.ok
    assert "Detected tech tags: fastapi" in llm.calls[0][1]


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


@pytest.mark.asyncio
async def test_deslopify_review_runs_read_only_simplification_pass() -> None:
    llm = FakeReviewLLM(scripted=['{"findings": []}'])
    result = await run_deslopify_review_pass(chunk=_chunk(), llm=llm, timeout_s=10.0)
    assert result.ok
    assert "accidental complexity" in llm.calls[0][1]
