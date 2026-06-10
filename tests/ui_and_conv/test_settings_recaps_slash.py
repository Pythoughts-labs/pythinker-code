"""Tests for the `/settings recaps on|off` (alias `/config`) toggle."""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest
from pythinker_core.tooling.empty import EmptyToolset

from pythinker_code.cli import Reload
from pythinker_code.config import get_default_config
from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.ui.shell import Shell
from pythinker_code.ui.shell import slash as shell_slash


def _make_shell_app(runtime: Runtime, tmp_path: Path) -> SimpleNamespace:
    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    soul = PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))
    return SimpleNamespace(soul=soul)


async def _run_settings(app: SimpleNamespace, args: str) -> None:
    await cast(Awaitable[None], shell_slash.settings(cast(Shell, app), args))


@pytest.mark.asyncio
async def test_recaps_on_persists_and_reloads(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    runtime.config.tui.turn_recaps = False
    app = _make_shell_app(runtime, tmp_path)

    config_for_save = get_default_config()
    load_mock = Mock(return_value=config_for_save)
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "load_config", load_mock)
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    with pytest.raises(Reload):
        await _run_settings(app, "recaps on")

    load_mock.assert_called_once_with(config_path)
    save_mock.assert_called_once_with(config_for_save, config_path)
    assert config_for_save.tui.turn_recaps is True


@pytest.mark.asyncio
async def test_recaps_off_persists(runtime: Runtime, tmp_path: Path, monkeypatch) -> None:
    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    runtime.config.tui.turn_recaps = True
    app = _make_shell_app(runtime, tmp_path)

    config_for_save = get_default_config()
    config_for_save.tui.turn_recaps = True
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "load_config", Mock(return_value=config_for_save))
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    with pytest.raises(Reload):
        await _run_settings(app, "recaps off")

    save_mock.assert_called_once()
    assert config_for_save.tui.turn_recaps is False


@pytest.mark.asyncio
async def test_recaps_noop_when_already_set(runtime: Runtime, tmp_path: Path, monkeypatch) -> None:
    runtime.config.tui.turn_recaps = False
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_settings(app, "recaps off")

    save_mock.assert_not_called()
    assert "already off" in str(print_mock.call_args.args[0])


@pytest.mark.asyncio
async def test_recaps_invalid_value_shows_usage(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_settings(app, "recaps maybe")

    save_mock.assert_not_called()
    assert "Usage: /settings recaps on|off" in str(print_mock.call_args.args[0])


@pytest.mark.asyncio
async def test_recaps_requires_config_file(runtime: Runtime, tmp_path: Path, monkeypatch) -> None:
    runtime.config.source_file = None
    runtime.config.tui.turn_recaps = False
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_settings(app, "recaps on")

    save_mock.assert_not_called()
    assert "config file" in str(print_mock.call_args.args[0])
