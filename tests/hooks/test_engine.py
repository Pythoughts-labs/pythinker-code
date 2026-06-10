from unittest.mock import patch

import pytest

from pythinker_code.hooks.config import HookDef
from pythinker_code.hooks.engine import HookEngine, WireHookSubscription


@pytest.fixture
def engine():
    hooks = [
        HookDef(event="PreToolUse", matcher="Shell|WriteFile", command="exit 0", timeout=5),
        HookDef(event="PreToolUse", matcher="ReadFile", command="exit 2", timeout=5),
        HookDef(event="Stop", matcher="", command="echo done", timeout=5),
    ]
    return HookEngine(hooks)


@pytest.mark.asyncio
async def test_match_tool_name(engine):
    results = await engine.trigger(
        "PreToolUse", matcher_value="Shell", input_data={"tool_name": "Shell"}
    )
    assert len(results) == 1
    assert results[0].action == "allow"


@pytest.mark.asyncio
async def test_no_match(engine):
    results = await engine.trigger("PreToolUse", matcher_value="Grep", input_data={})
    assert len(results) == 0


@pytest.mark.asyncio
async def test_block(engine):
    results = await engine.trigger("PreToolUse", matcher_value="ReadFile", input_data={})
    assert len(results) == 1
    assert results[0].action == "block"


@pytest.mark.asyncio
async def test_empty_matcher_matches_all(engine):
    results = await engine.trigger("Stop", matcher_value="anything", input_data={})
    assert len(results) == 1


@pytest.mark.asyncio
async def test_no_hooks_for_event(engine):
    results = await engine.trigger("UserPromptSubmit", matcher_value="", input_data={})
    assert len(results) == 0


@pytest.mark.asyncio
async def test_dedup_identical_commands():
    hooks = [
        HookDef(event="Stop", command="echo once", timeout=5),
        HookDef(event="Stop", command="echo once", timeout=5),
    ]
    engine = HookEngine(hooks)
    results = await engine.trigger("Stop", input_data={})
    assert len(results) == 1


@pytest.mark.asyncio
async def test_invalid_regex_skips_hook():
    hooks = [
        HookDef(event="PreToolUse", matcher="[invalid", command="exit 0", timeout=5),
    ]
    engine = HookEngine(hooks)
    # Should not raise, just skip the hook with invalid regex
    results = await engine.trigger("PreToolUse", matcher_value="Shell", input_data={})
    assert len(results) == 0


def test_add_wire_subscriptions_dedups_by_id():
    """Calling add_wire_subscriptions twice with the same id must not
    accumulate duplicate entries — summary count stays 1, not 2."""
    engine = HookEngine([])
    sub = WireHookSubscription(id="h1", event="PreToolUse", matcher="Shell")
    engine.add_wire_subscriptions([sub])
    # Second call with identical subscription (same id)
    engine.add_wire_subscriptions([sub])
    assert engine.summary.get("PreToolUse", 0) == 1
    assert len(engine._wire_by_event["PreToolUse"]) == 1


@pytest.mark.asyncio
async def test_telemetry_failure_does_not_discard_block_result(engine):
    """Safety-critical: a telemetry failure MUST NOT cause the hook engine
    to fail open. For PreToolUse block, dropping results to [] silently
    bypasses the block — that's exactly what this guard prevents.
    """
    with patch("pythinker_code.telemetry.track", side_effect=RuntimeError("telemetry broken")):
        results = await engine.trigger("PreToolUse", matcher_value="ReadFile", input_data={})
    assert len(results) == 1
    assert results[0].action == "block"
