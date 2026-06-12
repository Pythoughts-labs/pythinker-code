"""Tests for the public ``PythinkerSoul.turn()`` contract."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from pythinker_core.message import Message
from pythinker_core.tooling.empty import EmptyToolset

from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul, TurnOutcome


def _make_soul(runtime: Runtime, tmp_path: Path) -> PythinkerSoul:
    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    return PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))


async def test_turn_delegates_to_patched_private_turn(runtime: Runtime, tmp_path: Path) -> None:
    """``turn()`` must delegate to ``self._turn`` so tests patching ``_turn``
    intercept turns started through the public entry point too."""
    soul = _make_soul(runtime, tmp_path)
    sentinel = TurnOutcome(stop_reason="no_tool_calls", final_message=None, step_count=1)
    turn_mock = AsyncMock(return_value=sentinel)
    soul._turn = turn_mock  # type: ignore[method-assign]

    message = Message(role="user", content="hello")
    outcome = await soul.turn(message)

    assert turn_mock.await_count == 1
    assert turn_mock.await_args is not None
    assert turn_mock.await_args.args[0] is message
    assert outcome is sentinel
