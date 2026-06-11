"""Tests for GoalModeInjectionProvider.get_injections() flow."""

from __future__ import annotations

from unittest.mock import MagicMock

from pythinker_core.message import Message, TextPart

from pythinker_code.session_state import GoalState
from pythinker_code.soul.dynamic_injections.goal_mode import (
    GoalModeInjectionProvider,
    _full_reminder,
    _sparse_reminder,
)

GOAL = "Make the importer reject duplicate rows"


def _make_soul_mock(
    goal: str | None = GOAL,
    status: str = "active",
    is_subagent: bool = False,
) -> MagicMock:
    soul = MagicMock()
    soul.is_subagent = is_subagent
    soul.runtime.session.state.goal = (
        GoalState(objective=goal, status=status)  # type: ignore[arg-type]
        if goal is not None
        else None
    )
    return soul


def _reminder_msg(goal: str = GOAL) -> Message:
    """Create a user message that looks like a goal continuation reminder."""
    return Message(
        role="user",
        content=[TextPart(text=_full_reminder(goal))],
    )


def _assistant_msg() -> Message:
    return Message(role="assistant", content=[TextPart(text="step")])


class TestGoalModeInjectionProvider:
    async def test_returns_empty_when_no_goal(self) -> None:
        provider = GoalModeInjectionProvider()
        provider._inject_count = 5
        soul = _make_soul_mock(goal=None)

        result = await provider.get_injections([], soul)

        assert result == []
        assert provider._inject_count == 0

    async def test_returns_empty_when_paused(self) -> None:
        provider = GoalModeInjectionProvider()
        soul = _make_soul_mock(status="paused")

        result = await provider.get_injections([], soul)

        assert result == []

    async def test_returns_empty_when_complete_or_blocked(self) -> None:
        provider = GoalModeInjectionProvider()
        for status in ("complete", "blocked"):
            soul = _make_soul_mock(status=status)
            assert await provider.get_injections([], soul) == []

    async def test_returns_empty_for_subagent(self) -> None:
        provider = GoalModeInjectionProvider()
        soul = _make_soul_mock(is_subagent=True)

        result = await provider.get_injections([], soul)

        assert result == []

    async def test_first_call_injects_full_reminder(self) -> None:
        provider = GoalModeInjectionProvider()
        soul = _make_soul_mock()

        result = await provider.get_injections([], soul)

        assert len(result) == 1
        assert result[0].type == "goal_mode"
        assert "Continue working toward the active thread goal" in result[0].content
        assert "Completion audit" in result[0].content
        assert GOAL in result[0].content
        assert provider._inject_count == 1

    async def test_throttled_before_interval(self) -> None:
        provider = GoalModeInjectionProvider()
        soul = _make_soul_mock()

        # History: reminder + 3 assistant turns (< 5 threshold)
        history = [_reminder_msg()] + [_assistant_msg() for _ in range(3)]

        result = await provider.get_injections(history, soul)
        assert result == []

    async def test_injects_after_interval_reached(self) -> None:
        provider = GoalModeInjectionProvider()
        soul = _make_soul_mock()

        # History: reminder + 5 assistant turns (= threshold)
        history = [_reminder_msg()] + [_assistant_msg() for _ in range(5)]

        result = await provider.get_injections(history, soul)
        assert len(result) == 1

    async def test_sparse_on_non_full_cycle(self) -> None:
        provider = GoalModeInjectionProvider()
        # _inject_count=1 -> after increment becomes 2 -> 2 % 5 != 1 -> sparse
        provider._inject_count = 1
        soul = _make_soul_mock()

        history = [_reminder_msg()] + [_assistant_msg() for _ in range(5)]

        result = await provider.get_injections(history, soul)
        assert len(result) == 1
        assert "still active" in result[0].content

    async def test_full_on_every_5th_cycle(self) -> None:
        provider = GoalModeInjectionProvider()
        # _inject_count=5 -> after increment becomes 6 -> 6 % 5 == 1 -> full
        provider._inject_count = 5
        soul = _make_soul_mock()

        history = [_reminder_msg()] + [_assistant_msg() for _ in range(5)]

        result = await provider.get_injections(history, soul)
        assert len(result) == 1
        assert "Completion audit" in result[0].content

    async def test_goal_change_injects_full_immediately(self) -> None:
        """Reminders for a previous goal must not throttle a newly set goal."""
        provider = GoalModeInjectionProvider()
        provider._inject_count = 2
        soul = _make_soul_mock(goal="Ship the new exporter")

        # History contains reminders for the OLD goal only, with recent turns.
        history = [_reminder_msg(GOAL)] + [_assistant_msg() for _ in range(2)]

        result = await provider.get_injections(history, soul)

        assert len(result) == 1
        assert "Ship the new exporter" in result[0].content
        assert "Completion audit" in result[0].content

    async def test_compaction_resets_counter(self) -> None:
        provider = GoalModeInjectionProvider()
        provider._inject_count = 3

        await provider.on_context_compacted()

        assert provider._inject_count == 0

    async def test_sparse_reminder_names_objective_first_line(self) -> None:
        text = _sparse_reminder("first line of goal\nmore detail")
        assert "first line of goal" in text
        assert "more detail" not in text

    async def test_sparse_reminder_detected_for_throttling(self) -> None:
        """A sparse reminder in history must also throttle re-injection."""
        provider = GoalModeInjectionProvider()
        history = [
            Message(role="user", content=[TextPart(text=_sparse_reminder(GOAL))]),
            _assistant_msg(),
        ]
        soul = _make_soul_mock()

        result = await provider.get_injections(history, soul)
        assert result == []
