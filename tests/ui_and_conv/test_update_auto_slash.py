"""Tests for the `/update auto [on|off]` toggle."""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest
from pythinker_core.tooling.empty import EmptyToolset

from pythinker_code.config import get_default_config
from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.ui.shell import Shell
from pythinker_code.ui.shell import slash as shell_slash
from pythinker_code.ui.shell import update as update_module


def _make_shell_app(runtime: Runtime, tmp_path: Path) -> SimpleNamespace:
    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    soul = PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))
    return SimpleNamespace(soul=soul)


async def _run_update(app: SimpleNamespace, args: str) -> None:
    await cast(Awaitable[None], shell_slash.update_command(cast(Shell, app), args))


@pytest.fixture(autouse=True)
def _no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    # The suite runs from a source checkout, where the override would otherwise
    # be active; neutralize it so the toggle path is the live (non-override) one.
    monkeypatch.setattr(update_module, "auto_update_override_reason", lambda: None)


@pytest.mark.asyncio
async def test_update_auto_on_persists_and_mirrors_live(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    runtime.config.auto_update = False
    app = _make_shell_app(runtime, tmp_path)

    config_for_save = get_default_config()
    config_for_save.auto_update = False
    load_mock = Mock(return_value=config_for_save)
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "load_config", load_mock)
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    await _run_update(app, "auto on")

    load_mock.assert_called_once_with(config_path)
    save_mock.assert_called_once_with(config_for_save, config_path)
    assert config_for_save.auto_update is True
    # No reload: the running config is mirrored so status reflects immediately.
    assert runtime.config.auto_update is True


@pytest.mark.asyncio
async def test_update_auto_off_persists(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    runtime.config.auto_update = True
    app = _make_shell_app(runtime, tmp_path)

    config_for_save = get_default_config()
    config_for_save.auto_update = True
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "load_config", Mock(return_value=config_for_save))
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    await _run_update(app, "auto off")

    save_mock.assert_called_once()
    assert config_for_save.auto_update is False
    assert runtime.config.auto_update is False


@pytest.mark.asyncio
async def test_update_auto_noop_when_already_set(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime.config.auto_update = True
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_update(app, "auto on")

    save_mock.assert_not_called()
    assert "already on" in str(print_mock.call_args.args[0])


@pytest.mark.asyncio
async def test_update_auto_invalid_value_shows_usage(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_update(app, "auto maybe")

    save_mock.assert_not_called()
    assert "Usage: /update auto" in str(print_mock.call_args.args[0])


@pytest.mark.asyncio
async def test_update_auto_requires_config_file(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime.config.source_file = None
    runtime.config.auto_update = False
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_update(app, "auto on")

    save_mock.assert_not_called()
    assert "config file" in str(print_mock.call_args.args[0])


@pytest.mark.asyncio
async def test_update_auto_status_surfaces_override(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime.config.auto_update = True
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    monkeypatch.setattr(
        update_module,
        "auto_update_override_reason",
        lambda: "disabled by PYTHINKER_CLI_NO_AUTO_UPDATE",
    )
    monkeypatch.setattr(update_module, "auto_update_enabled", lambda cfg: False)
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_update(app, "auto")

    printed = " ".join(str(call.args[0]) for call in print_mock.call_args_list)
    assert "Auto-update: off" in printed
    assert "PYTHINKER_CLI_NO_AUTO_UPDATE" in printed
