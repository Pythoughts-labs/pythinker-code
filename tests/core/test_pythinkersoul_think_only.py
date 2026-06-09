"""Tests for think-only response error handling.

A model response containing only ThinkPart content (no TextPart, no tool_calls)
is an abnormal condition — typically a stream interruption or output token budget
exhaustion during reasoning. This should be detected as an error at the generate
layer and retried through the standard retry mechanism.
"""

from __future__ import annotations

import pytest
from pythinker_core.chat_provider import APIEmptyResponseError, APIStatusError

from pythinker_code.soul.pythinkersoul import PythinkerSoul


@pytest.mark.asyncio
async def test_think_only_error_is_retryable() -> None:
    """APIEmptyResponseError from think-only responses should be retryable."""
    assert PythinkerSoul._is_retryable_error(APIEmptyResponseError("only thinking content"))


def test_hard_usage_limit_429_is_not_retryable() -> None:
    """A subscription usage cap (resets in hours) must NOT be retried — retrying
    only adds backoff latency before the inevitable failure. Covers both the bare
    streaming text and the structured-body shape."""
    bare = APIStatusError(429, "Usage limit reached", body=None)
    structured = APIStatusError(
        429, "Error code: 429", body={"error": {"type": "usage_limit_reached"}}
    )
    assert PythinkerSoul._is_retryable_error(bare) is False
    assert PythinkerSoul._is_retryable_error(structured) is False


def test_transient_429_and_5xx_remain_retryable() -> None:
    """A transient RPM/TPM burst (clears in seconds) and server 5xx still retry."""
    assert PythinkerSoul._is_retryable_error(APIStatusError(429, "rate limit exceeded")) is True
    assert PythinkerSoul._is_retryable_error(APIStatusError(503, "service unavailable")) is True
