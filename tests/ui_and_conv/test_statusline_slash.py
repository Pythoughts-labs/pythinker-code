"""Tests for the `/statusline` shell command."""

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


async def _run_statusline(app: SimpleNamespace, args: str) -> None:
    await cast(Awaitable[None], shell_slash.statusline(cast(Shell, app), args))


def test_statusline_is_registered() -> None:
    assert shell_slash.registry.find_command("statusline") is not None


@pytest.mark.asyncio
async def test_statusline_show_prints_current_config(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_statusline(app, "show")

    printed = " ".join(str(call.args[0]) for call in print_mock.call_args_list)
    assert "cwd" in printed and "model" in printed


@pytest.mark.asyncio
async def test_statusline_off_persists_and_reloads(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    app = _make_shell_app(runtime, tmp_path)

    config_for_save = get_default_config()
    monkeypatch.setattr(shell_slash, "load_config", Mock(return_value=config_for_save))
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    with pytest.raises(Reload):
        await _run_statusline(app, "off")

    save_mock.assert_called_once_with(config_for_save, config_path)
    assert config_for_save.tui.statusline.enabled is False


@pytest.mark.asyncio
async def test_statusline_command_set_and_clear(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    app = _make_shell_app(runtime, tmp_path)

    config_for_save = get_default_config()
    monkeypatch.setattr(shell_slash, "load_config", Mock(return_value=config_for_save))
    monkeypatch.setattr(shell_slash, "save_config", Mock())
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    with pytest.raises(Reload):
        await _run_statusline(app, "command echo hello")
    assert config_for_save.tui.statusline.command == "echo hello"
    assert "command" in config_for_save.tui.statusline.segments

    with pytest.raises(Reload):
        await _run_statusline(app, "command none")
    assert config_for_save.tui.statusline.command is None


@pytest.mark.asyncio
async def test_statusline_segments_set(runtime: Runtime, tmp_path: Path, monkeypatch) -> None:
    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    app = _make_shell_app(runtime, tmp_path)

    config_for_save = get_default_config()
    monkeypatch.setattr(shell_slash, "load_config", Mock(return_value=config_for_save))
    monkeypatch.setattr(shell_slash, "save_config", Mock())
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    with pytest.raises(Reload):
        await _run_statusline(app, "segments model,context")
    assert config_for_save.tui.statusline.segments == ["model", "context"]


@pytest.mark.asyncio
async def test_statusline_segments_rejects_unknown_ids(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_statusline(app, "segments model,bogus")

    save_mock.assert_not_called()
    assert "bogus" in str(print_mock.call_args.args[0])


@pytest.mark.asyncio
async def test_statusline_mutation_requires_config_file(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    runtime.config.source_file = None
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_statusline(app, "off")

    save_mock.assert_not_called()
    printed = " ".join(str(call.args[0]) for call in print_mock.call_args_list)
    assert "config file" in printed


@pytest.mark.asyncio
async def test_statusline_invalid_subcommand_shows_usage(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_statusline(app, "frobnicate")

    assert "Usage" in str(print_mock.call_args.args[0])
