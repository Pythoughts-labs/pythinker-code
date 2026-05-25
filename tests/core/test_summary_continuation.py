"""Tests for per-type summary min-length thresholds and run_with_summary_continuation."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pythinker_code.subagents.runner import (
    run_with_summary_continuation,
    _SUMMARY_MIN_LENGTH_BY_TYPE,
    _SUMMARY_MIN_LENGTH_DEFAULT,
)


def test_summary_min_length_by_type_has_verifier_below_default():
    """verifier type has a lower min_length than the default."""
    assert _SUMMARY_MIN_LENGTH_BY_TYPE["verifier"] < _SUMMARY_MIN_LENGTH_DEFAULT


def test_summary_min_length_by_type_has_plan_above_default():
    """plan type has a higher min_length than the default."""
    assert _SUMMARY_MIN_LENGTH_BY_TYPE["plan"] > _SUMMARY_MIN_LENGTH_DEFAULT


@pytest.mark.asyncio
async def test_run_with_summary_continuation_accepts_min_length_param():
    """run_with_summary_continuation does NOT retry when response >= min_length."""
    soul = MagicMock()
    soul.context.history = [MagicMock()]
    soul.context.history[-1].extract_text = MagicMock(return_value="OK")

    call_count = 0

    async def fake_run_soul_checked(s, prompt, ui_loop_fn, wire_path, phase):
        nonlocal call_count
        call_count += 1
        return None

    with patch("pythinker_code.subagents.runner.run_soul_checked", fake_run_soul_checked):
        response, failure = await run_with_summary_continuation(
            soul,
            "prompt",
            AsyncMock(),
            MagicMock(),
            min_length=1,
        )

    assert failure is None
    assert response == "OK"
    assert call_count == 1, "Should not retry when response length >= min_length"
