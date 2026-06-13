from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from pythinker_core.tooling.empty import EmptyToolset

from pythinker_code.config import get_default_config
from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.soul.slash import recap as recap_slash
from pythinker_code.wire.types import TextPart


def _make_soul(runtime: Runtime, tmp_path: Path) -> PythinkerSoul:
    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    return PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))


async def _run_recap(soul: PythinkerSoul, args: str = "") -> None:
    # `recap` is async; the registry types commands as the looser
    # `None | Awaitable[None]`, so cast to await the concrete coroutine.
    await cast(Awaitable[None], recap_slash(soul, args))


async def test_recap_on_persists_and_updates_runtime(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    runtime.config.tui.turn_recaps = False
    soul = _make_soul(runtime, tmp_path)
    sent: list[TextPart] = []

    config_for_save = get_default_config()
    monkeypatch.setattr("pythinker_code.soul.slash.load_config", Mock(return_value=config_for_save))
    save_mock = Mock()
    monkeypatch.setattr("pythinker_code.soul.slash.save_config", save_mock)
    monkeypatch.setattr("pythinker_code.soul.slash.wire_send", lambda msg: sent.append(msg))

    await _run_recap(soul, "on")

    assert runtime.config.tui.turn_recaps is True
    assert config_for_save.tui.turn_recaps is True
    save_mock.assert_called_once_with(config_for_save, config_path)
    assert any("Turn recaps on" in msg.text for msg in sent)


async def test_recap_off_without_config_file_updates_runtime_only(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime.config.source_file = None
    runtime.config.tui.turn_recaps = True
    soul = _make_soul(runtime, tmp_path)
    sent: list[TextPart] = []
    save_mock = Mock()

    monkeypatch.setattr("pythinker_code.soul.slash.save_config", save_mock)
    monkeypatch.setattr("pythinker_code.soul.slash.wire_send", lambda msg: sent.append(msg))

    await _run_recap(soul, "off")

    assert runtime.config.tui.turn_recaps is False
    save_mock.assert_not_called()
    assert any("current session only" in msg.text for msg in sent)
