from __future__ import annotations

from unittest.mock import MagicMock

from pythinker_core.message import Message, TextPart

from pythinker_code.session_state import GoalState
from pythinker_code.soul.dynamic_injections.orchestration import OrchestrationInjectionProvider


def _user(text: str) -> Message:
    return Message(role="user", content=[TextPart(text=text)])


def _assistant(text: str = "step") -> Message:
    return Message(role="assistant", content=[TextPart(text=text)])


def _notification() -> Message:
    return _user(
        '<notification id="n1" category="task" type="complete" '
        'source_kind="background_task" source_id="t1">done</notification>'
    )


def _system_reminder(text: str = "internal reminder") -> Message:
    return _user(f"<system-reminder>\n{text}\n</system-reminder>")


def _make_soul(
    *,
    is_subagent: bool = False,
    plan_mode: bool = False,
    is_auto: bool = False,
    goal: GoalState | None = None,
) -> MagicMock:
    soul = MagicMock()
    soul.is_subagent = is_subagent
    soul.plan_mode = plan_mode
    soul.is_auto = is_auto
    soul.runtime.session.state.goal = goal
    return soul


class TestOrchestrationInjectionProvider:
    async def test_injects_for_substantial_root_task(self) -> None:
        provider = OrchestrationInjectionProvider()
        history = [_user("Enhance system prompts and runtime orchestration with tests")]

        result = await provider.get_injections(history, _make_soul())

        assert len(result) == 1
        assert result[0].type == "orchestration"
        assert "RunAgents" in result[0].content
        assert "SetTodoList" in result[0].content
        assert "direct tools" in result[0].content
        assert "verification" in result[0].content

    async def test_does_not_inject_for_simple_conversation(self) -> None:
        provider = OrchestrationInjectionProvider()

        result = await provider.get_injections([_user("hi")], _make_soul())

        assert result == []

    async def test_does_not_inject_for_subagent(self) -> None:
        provider = OrchestrationInjectionProvider()
        history = [_user("Refactor the runtime orchestration")]

        result = await provider.get_injections(history, _make_soul(is_subagent=True))

        assert result == []

    async def test_does_not_inject_in_plan_mode(self) -> None:
        provider = OrchestrationInjectionProvider()
        history = [_user("Enhance runtime orchestration")]

        result = await provider.get_injections(history, _make_soul(plan_mode=True))

        assert result == []

    async def test_does_not_inject_when_goal_active(self) -> None:
        provider = OrchestrationInjectionProvider()
        history = [_user("Enhance runtime orchestration")]
        goal = GoalState(objective="ship the feature", status="active")

        result = await provider.get_injections(history, _make_soul(goal=goal))

        assert result == []

    async def test_does_not_inject_in_auto_mode(self) -> None:
        provider = OrchestrationInjectionProvider()
        history = [_user("Enhance runtime orchestration")]

        result = await provider.get_injections(history, _make_soul(is_auto=True))

        assert result == []

    async def test_ignores_notification_and_system_reminder_when_finding_task(self) -> None:
        provider = OrchestrationInjectionProvider()
        history = [
            _user("Enhance runtime orchestration with tests"),
            _notification(),
            _system_reminder("Plan mode mentions implementation but is not the task"),
        ]

        result = await provider.get_injections(history, _make_soul())

        assert len(result) == 1

    async def test_throttles_after_recent_reminder(self) -> None:
        provider = OrchestrationInjectionProvider()
        history = [
            _user("Enhance runtime orchestration with tests"),
            _system_reminder(
                "Orchestration reminder: choose direct tools, SetTodoList, "
                "RunAgents, and verification."
            ),
            _assistant(),
        ]

        result = await provider.get_injections(history, _make_soul())

        assert result == []

    async def test_reinjects_after_interval(self) -> None:
        provider = OrchestrationInjectionProvider()
        history = [
            _user("Enhance runtime orchestration with tests"),
            _system_reminder(
                "Orchestration reminder: choose direct tools, SetTodoList, "
                "RunAgents, and verification."
            ),
            *[_assistant() for _ in range(5)],
        ]

        result = await provider.get_injections(history, _make_soul())

        assert len(result) == 1

    async def test_substantial_terms_match_whole_words_only(self) -> None:
        provider = OrchestrationInjectionProvider()
        # "prefix" contains "fix" and "explanation" contains "plan" — neither
        # is a substantial-task signal on its own.
        history = [_user("Could you explain the prefix explanation?")]

        result = await provider.get_injections(history, _make_soul())

        assert result == []

    async def test_reinjects_when_compaction_drops_prior_reminder(self) -> None:
        # The provider is stateless: once compaction collapses the reminder
        # into the summary, the marker scan finds nothing and re-arms.
        provider = OrchestrationInjectionProvider()
        throttled_history = [
            _user("Enhance runtime orchestration with tests"),
            _system_reminder("Orchestration reminder: choose the lightest effective work shape."),
            _assistant(),
        ]
        assert await provider.get_injections(throttled_history, _make_soul()) == []

        compacted_history = [_user("Enhance runtime orchestration with tests")]

        result = await provider.get_injections(compacted_history, _make_soul())

        assert len(result) == 1
