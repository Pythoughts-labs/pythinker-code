"""Tests for /goal slash command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pythinker_core.tooling.empty import EmptyToolset

from pythinker_code.session_state import load_session_state
from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.soul.slash import goal
from pythinker_code.wire.types import TextPart


def _make_soul(runtime: Runtime, tmp_path: Path) -> PythinkerSoul:
    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    soul = PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))
    soul._turn = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return soul


async def _run_goal(soul: PythinkerSoul, args: str) -> None:
    result = goal(soul, args)
    if result is not None:
        await result


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[TextPart]:
    captured: list[TextPart] = []
    monkeypatch.setattr("pythinker_code.soul.slash.wire_send", lambda msg: captured.append(msg))
    return captured


class TestGoalSlashCommand:
    async def test_set_goal_persists_and_starts_turn(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run_goal(soul, "make the importer reject duplicate rows")

        state_goal = runtime.session.state.goal
        assert state_goal is not None
        assert state_goal.objective == "make the importer reject duplicate rows"
        assert state_goal.status == "active"

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)
        turn_mock.assert_awaited_once()
        assert turn_mock.await_args is not None
        message = turn_mock.await_args.args[0]
        text = message.extract_text(" ")
        assert "<objective>" in text
        assert "make the importer reject duplicate rows" in text
        assert "success criteria" in text

    async def test_set_goal_persists_state_to_disk(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run_goal(soul, "fix the flaky test")

        reloaded = load_session_state(Path(str(runtime.session.dir)))
        assert reloaded.goal is not None
        assert reloaded.goal.objective == "fix the flaky test"

    async def test_replace_goal_supersedes_previous(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run_goal(soul, "first goal")
        await _run_goal(soul, "second goal")

        state_goal = runtime.session.state.goal
        assert state_goal is not None
        assert state_goal.objective == "second goal"

    async def test_bare_goal_shows_active_goal(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)
        await _run_goal(soul, "ship the exporter")
        sent.clear()

        await _run_goal(soul, "")

        assert any("ship the exporter" in s.text for s in sent)
        assert any("active" in s.text for s in sent)

    async def test_bare_goal_without_goal_shows_usage(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run_goal(soul, "")

        assert any("Usage" in s.text for s in sent)

    async def test_view_shows_active_goal(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)
        await _run_goal(soul, "ship the exporter")
        sent.clear()

        await _run_goal(soul, "view")

        assert any("ship the exporter" in s.text for s in sent)

    async def test_pause_and_resume(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)
        await _run_goal(soul, "ship the exporter")
        sent.clear()

        await _run_goal(soul, "pause")
        state_goal = runtime.session.state.goal
        assert state_goal is not None and state_goal.status == "paused"
        assert any("paused" in s.text.lower() for s in sent)

        sent.clear()
        await _run_goal(soul, "resume")
        state_goal = runtime.session.state.goal
        assert state_goal is not None and state_goal.status == "active"
        assert any("resum" in s.text.lower() for s in sent)

    async def test_resume_reactivates_completed_goal(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        from pythinker_code.session_state import GoalState

        soul = _make_soul(runtime, tmp_path)
        runtime.session.state.goal = GoalState(objective="ship it", status="complete")

        await _run_goal(soul, "resume")

        state_goal = runtime.session.state.goal
        assert state_goal is not None and state_goal.status == "active"

    async def test_pause_without_goal(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run_goal(soul, "pause")

        assert any("No active goal" in s.text for s in sent)

    async def test_set_with_subcommand_prefix_is_an_objective(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run_goal(soul, "pause the deployment pipeline rollout")

        state_goal = runtime.session.state.goal
        assert state_goal is not None
        assert state_goal.objective == "pause the deployment pipeline rollout"

    async def test_clear_goal(self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]) -> None:
        soul = _make_soul(runtime, tmp_path)
        await _run_goal(soul, "ship the exporter")
        sent.clear()

        await _run_goal(soul, "clear")

        assert runtime.session.state.goal is None
        assert any("cleared" in s.text.lower() for s in sent)

    async def test_clear_without_goal(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run_goal(soul, "clear")

        assert any("No active goal" in s.text for s in sent)

    async def test_goal_command_registered(self, runtime: Runtime, tmp_path: Path) -> None:
        soul = _make_soul(runtime, tmp_path)
        names = {cmd.name for cmd in soul.available_slash_commands}
        assert "goal" in names

    async def test_goal_injection_provider_registered(
        self, runtime: Runtime, tmp_path: Path
    ) -> None:
        from pythinker_code.soul.dynamic_injections.goal_mode import GoalModeInjectionProvider

        soul = _make_soul(runtime, tmp_path)
        provider_types = {type(p) for p in soul._injection_providers}
        assert GoalModeInjectionProvider in provider_types
