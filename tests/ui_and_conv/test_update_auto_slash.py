"""Tests for the `/update auto [on|off]` toggle."""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from pythinker_core.tooling.empty import EmptyToolset

from pythinker_code import update_policy
from pythinker_code.config import get_default_config, load_config, save_config
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
    monkeypatch.setattr(update_policy, "auto_update_override_reason", lambda: None)


def _seed_config_file(path: Path, *, auto_update: bool) -> None:
    config = get_default_config()
    config.auto_update = auto_update
    save_config(config, path)


@pytest.mark.asyncio
async def test_update_auto_on_persists_and_mirrors_live(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PYTHINKER_AUTO_UPDATE", raising=False)
    config_path = (tmp_path / "config.toml").resolve()
    _seed_config_file(config_path, auto_update=False)
    runtime.config.source_file = config_path
    runtime.config.auto_update = False
    app = _make_shell_app(runtime, tmp_path)
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    await _run_update(app, "auto on")

    # Behavior-level: the value is actually persisted to disk...
    assert load_config(config_path).auto_update is True
    # ...and mirrored into the live config (no reload).
    assert runtime.config.auto_update is True


@pytest.mark.asyncio
async def test_update_auto_off_persists(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PYTHINKER_AUTO_UPDATE", raising=False)
    config_path = (tmp_path / "config.toml").resolve()
    _seed_config_file(config_path, auto_update=True)
    runtime.config.source_file = config_path
    runtime.config.auto_update = True
    app = _make_shell_app(runtime, tmp_path)
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    await _run_update(app, "auto off")

    assert load_config(config_path).auto_update is False
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
async def test_bare_update_menu_check_runs_update_flow(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _make_shell_app(runtime, tmp_path)
    monkeypatch.setattr(shell_slash.console, "print", Mock())
    monkeypatch.setattr(shell_slash, "_prompt_update_action", AsyncMock(return_value="check"))
    run_prompt = AsyncMock(return_value=update_module.UpdateResult.UP_TO_DATE)
    monkeypatch.setattr(update_module, "run_update_prompt", run_prompt)
    auto_toggle = AsyncMock()
    monkeypatch.setattr(shell_slash, "_auto_update_toggle", auto_toggle)

    await _run_update(app, "")

    run_prompt.assert_awaited_once()
    auto_toggle.assert_not_called()


@pytest.mark.asyncio
async def test_bare_update_menu_auto_routes_to_toggle(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _make_shell_app(runtime, tmp_path)
    monkeypatch.setattr(shell_slash.console, "print", Mock())
    monkeypatch.setattr(shell_slash, "_prompt_update_action", AsyncMock(return_value="auto"))
    run_prompt = AsyncMock(return_value=update_module.UpdateResult.UP_TO_DATE)
    monkeypatch.setattr(update_module, "run_update_prompt", run_prompt)
    auto_toggle = AsyncMock()
    monkeypatch.setattr(shell_slash, "_auto_update_toggle", auto_toggle)

    await _run_update(app, "")

    auto_toggle.assert_awaited_once_with(app, [])
    run_prompt.assert_not_called()


@pytest.mark.asyncio
async def test_bare_update_menu_cancel_is_noop(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _make_shell_app(runtime, tmp_path)
    monkeypatch.setattr(shell_slash.console, "print", Mock())
    monkeypatch.setattr(shell_slash, "_prompt_update_action", AsyncMock(return_value=None))
    run_prompt = AsyncMock(return_value=update_module.UpdateResult.UP_TO_DATE)
    monkeypatch.setattr(update_module, "run_update_prompt", run_prompt)

    await _run_update(app, "")

    run_prompt.assert_not_called()


@pytest.mark.asyncio
async def test_update_auto_no_args_opens_picker_and_persists(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PYTHINKER_AUTO_UPDATE", raising=False)
    config_path = (tmp_path / "config.toml").resolve()
    _seed_config_file(config_path, auto_update=False)
    runtime.config.source_file = config_path
    runtime.config.auto_update = False
    app = _make_shell_app(runtime, tmp_path)
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    picker = AsyncMock(return_value=True)
    monkeypatch.setattr(shell_slash, "_prompt_auto_update_selection", picker)

    await _run_update(app, "auto")

    # The picker is consulted with the current value as its default cursor...
    assert picker.call_args.kwargs == {"current": False}
    # ...and the chosen state is persisted and mirrored live.
    assert load_config(config_path).auto_update is True
    assert runtime.config.auto_update is True


@pytest.mark.asyncio
async def test_update_auto_no_args_cancel_is_noop(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime.config.auto_update = False
    app = _make_shell_app(runtime, tmp_path)
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", Mock())
    monkeypatch.setattr(
        shell_slash,
        "_prompt_auto_update_selection",
        AsyncMock(return_value=None),
    )

    await _run_update(app, "auto")

    save_mock.assert_not_called()
    assert runtime.config.auto_update is False


@pytest.mark.asyncio
async def test_update_auto_status_surfaces_override(
    runtime: Runtime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime.config.auto_update = True
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    monkeypatch.setattr(
        update_policy,
        "auto_update_override_reason",
        lambda: "disabled by PYTHINKER_CLI_NO_AUTO_UPDATE",
    )
    monkeypatch.setattr(update_policy, "auto_update_enabled", lambda cfg: False)
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_update(app, "auto")

    printed = " ".join(str(call.args[0]) for call in print_mock.call_args_list)
    assert "Auto-update: off" in printed
    assert "PYTHINKER_CLI_NO_AUTO_UPDATE" in printed
