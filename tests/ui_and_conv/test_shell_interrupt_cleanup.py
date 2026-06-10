"""ESC/interrupt must stop background tasks spawned by the interrupted turn.

Regression test for the field bug where a background subagent launched during
a turn survived the user's ESC, finished later, and re-delivered the abandoned
task via its completion notification.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from pythinker_core.tooling.empty import EmptyToolset

import pythinker_code.ui.shell as shell_module
from pythinker_code.soul import RunCancelled
from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.ui.shell import Shell


def _make_shell(runtime: Runtime, tmp_path: Path) -> Shell:
    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    soul = PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))
    return Shell(soul)


@pytest.mark.asyncio
async def test_interrupt_kills_turn_background_tasks(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    shell = _make_shell(runtime, tmp_path)
    monkeypatch.setattr(shell_module, "run_soul", AsyncMock(side_effect=RunCancelled()))
    begin_mock = Mock()
    kill_mock = Mock(return_value=["bash-1234"])
    monkeypatch.setattr(runtime.background_tasks, "begin_turn", begin_mock)
    monkeypatch.setattr(runtime.background_tasks, "kill_turn_tasks", kill_mock)

    ok = await shell.run_soul_command("hello")

    assert ok is False
    begin_mock.assert_called_once()
    kill_mock.assert_called_once_with(reason="Interrupted by user")


@pytest.mark.asyncio
async def test_successful_turn_does_not_kill_turn_tasks(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    shell = _make_shell(runtime, tmp_path)
    monkeypatch.setattr(shell_module, "run_soul", AsyncMock(return_value=None))
    kill_mock = Mock(return_value=[])
    monkeypatch.setattr(runtime.background_tasks, "kill_turn_tasks", kill_mock)

    ok = await shell.run_soul_command("hello")

    assert ok is True
    kill_mock.assert_not_called()
