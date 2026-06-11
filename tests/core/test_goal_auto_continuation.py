"""Tests for the goal auto-continuation loop (Codex goals port)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pythinker_core.tooling.empty import EmptyToolset

import pythinker_code.soul.pythinkersoul as pythinkersoul_module
from pythinker_code.session_state import GoalState
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
    soul = PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))
    soul._turn = AsyncMock(  # type: ignore[method-assign]
        return_value=TurnOutcome(stop_reason="no_tool_calls", final_message=None, step_count=1)
    )
    return soul


@pytest.fixture(autouse=True)
def _mute_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pythinkersoul_module, "wire_send", lambda _msg: None)
    monkeypatch.setattr("pythinker_code.soul.slash.wire_send", lambda _msg: None)


def _turn_texts(soul: PythinkerSoul) -> list[str]:
    turn_mock = soul._turn
    assert isinstance(turn_mock, AsyncMock)
    return [call.args[0].extract_text(" ") for call in turn_mock.await_args_list]


class TestGoalAutoContinuation:
    async def test_off_by_default(self, runtime: Runtime, tmp_path: Path) -> None:
        runtime.session.state.goal = GoalState(objective="ship it", status="active")
        soul = _make_soul(runtime, tmp_path)

        await soul.run("do the thing")

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)
        assert turn_mock.await_count == 1

    async def test_continues_up_to_cap_with_wrap_up_note(
        self, runtime: Runtime, tmp_path: Path
    ) -> None:
        runtime.config.goal.auto_continue = True
        runtime.config.goal.max_continuations = 3
        runtime.session.state.goal = GoalState(objective="ship it", status="active")
        soul = _make_soul(runtime, tmp_path)

        await soul.run("do the thing")

        texts = _turn_texts(soul)
        # 1 primary turn + 3 continuations
        assert len(texts) == 4
        assert all("Continue working toward the active thread goal" in t for t in texts[1:])
        # Wrap-up note only on the final continuation.
        assert "final automatic goal continuation" in texts[3]
        assert "final automatic goal continuation" not in texts[2]

    async def test_stops_when_goal_marked_complete(self, runtime: Runtime, tmp_path: Path) -> None:
        runtime.config.goal.auto_continue = True
        runtime.config.goal.max_continuations = 3
        runtime.session.state.goal = GoalState(objective="ship it", status="active")
        soul = _make_soul(runtime, tmp_path)

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)

        def _complete_after_first_continuation(*args: object, **kwargs: object) -> TurnOutcome:
            if turn_mock.await_count >= 2:
                runtime.session.state.goal = GoalState(objective="ship it", status="complete")
            return TurnOutcome(stop_reason="no_tool_calls", final_message=None, step_count=1)

        turn_mock.side_effect = _complete_after_first_continuation

        await soul.run("do the thing")

        # 1 primary + 1 continuation; the complete status stops the loop.
        assert turn_mock.await_count == 2

    async def test_no_continuation_without_goal(self, runtime: Runtime, tmp_path: Path) -> None:
        runtime.config.goal.auto_continue = True
        runtime.session.state.goal = None
        soul = _make_soul(runtime, tmp_path)

        await soul.run("do the thing")

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)
        assert turn_mock.await_count == 1

    async def test_no_continuation_for_paused_goal(self, runtime: Runtime, tmp_path: Path) -> None:
        runtime.config.goal.auto_continue = True
        runtime.session.state.goal = GoalState(objective="ship it", status="paused")
        soul = _make_soul(runtime, tmp_path)

        await soul.run("do the thing")

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)
        assert turn_mock.await_count == 1

    async def test_stops_on_tool_rejected(self, runtime: Runtime, tmp_path: Path) -> None:
        runtime.config.goal.auto_continue = True
        runtime.config.goal.max_continuations = 3
        runtime.session.state.goal = GoalState(objective="ship it", status="active")
        soul = _make_soul(runtime, tmp_path)

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)

        def _reject_first_continuation(*args: object, **kwargs: object) -> TurnOutcome:
            stop = "tool_rejected" if turn_mock.await_count >= 2 else "no_tool_calls"
            return TurnOutcome(stop_reason=stop, final_message=None, step_count=1)

        turn_mock.side_effect = _reject_first_continuation

        await soul.run("do the thing")

        # 1 primary + 1 rejected continuation, then stop.
        assert turn_mock.await_count == 2

    async def test_no_continuation_after_slash_command(
        self, runtime: Runtime, tmp_path: Path
    ) -> None:
        runtime.config.goal.auto_continue = True
        runtime.session.state.goal = GoalState(objective="ship it", status="active")
        soul = _make_soul(runtime, tmp_path)

        await soul.run("/compact")

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)
        assert turn_mock.await_count == 0

    async def test_no_continuation_in_plan_mode(self, runtime: Runtime, tmp_path: Path) -> None:
        runtime.config.goal.auto_continue = True
        runtime.session.state.goal = GoalState(objective="ship it", status="active")
        soul = _make_soul(runtime, tmp_path)
        soul._plan_mode = True

        await soul.run("do the thing")

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)
        assert turn_mock.await_count == 1

    async def test_no_continuation_when_primary_turn_rejected(
        self, runtime: Runtime, tmp_path: Path
    ) -> None:
        """A tool rejection in the primary turn must not trigger continuations."""
        runtime.config.goal.auto_continue = True
        runtime.session.state.goal = GoalState(objective="ship it", status="active")
        soul = _make_soul(runtime, tmp_path)

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)
        turn_mock.return_value = TurnOutcome(
            stop_reason="tool_rejected", final_message=None, step_count=1
        )

        await soul.run("do the thing")

        assert turn_mock.await_count == 1

    async def test_no_continuation_when_primary_turn_stuck(
        self, runtime: Runtime, tmp_path: Path
    ) -> None:
        runtime.config.goal.auto_continue = True
        runtime.session.state.goal = GoalState(objective="ship it", status="active")
        soul = _make_soul(runtime, tmp_path)

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)
        turn_mock.return_value = TurnOutcome(stop_reason="stuck", final_message=None, step_count=1)

        await soul.run("do the thing")

        assert turn_mock.await_count == 1
