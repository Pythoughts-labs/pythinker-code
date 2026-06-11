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

    # Guard against a trivially-true clear: the command must actually be set
    # before "command none" is exercised.
    assert config_for_save.tui.statusline.command is not None
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


@pytest.mark.asyncio
async def test_statusline_glued_verb_shows_usage_instead_of_misparsing(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    """ "/statusline commands" must not parse as `command` with argument "s"
    (persisting a junk external command); same for "segmentscwd"."""
    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    app = _make_shell_app(runtime, tmp_path)
    print_mock = Mock()
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    await _run_statusline(app, "commands")
    await _run_statusline(app, "segmentscwd")

    save_mock.assert_not_called()
    printed = " ".join(str(call.args[0]) for call in print_mock.call_args_list)
    assert "Usage" in printed


@pytest.mark.asyncio
async def test_statusline_bare_opens_menu_and_esc_dismisses(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    """Bare /statusline at the idle prompt opens the interactive menu; cancel saves nothing."""
    app = _make_shell_app(runtime, tmp_path)
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    seen_configs = []

    async def fake_menu(config):
        seen_configs.append(config)
        return None  # Esc / cancel

    monkeypatch.setattr(
        "pythinker_code.ui.shell.components.settings_list.run_settings_list", fake_menu
    )

    await _run_statusline(app, "")

    save_mock.assert_not_called()
    item_ids = [item.id for item in seen_configs[0].items]
    assert "enabled" in item_ids
    assert "segment:git" in item_ids
    assert "command_timeout_ms" in item_ids


@pytest.mark.asyncio
async def test_statusline_menu_apply_persists_changes(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    from pythinker_code.ui.shell.components.settings_list import SettingsListResult

    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    app = _make_shell_app(runtime, tmp_path)

    config_for_save = get_default_config()
    monkeypatch.setattr(shell_slash, "load_config", Mock(return_value=config_for_save))
    monkeypatch.setattr(shell_slash, "save_config", Mock())
    monkeypatch.setattr(shell_slash.console, "print", Mock())

    async def fake_menu(config):
        return SettingsListResult(
            changes={
                "enabled": "off",
                "segment:git": "off",
                "command_timeout_ms": "2000",
            }
        )

    monkeypatch.setattr(
        "pythinker_code.ui.shell.components.settings_list.run_settings_list", fake_menu
    )

    with pytest.raises(Reload):
        await _run_statusline(app, "")

    sl = config_for_save.tui.statusline
    assert sl.enabled is False
    assert "git" not in sl.segments
    assert sl.command_timeout_ms == 2000


@pytest.mark.asyncio
async def test_statusline_bare_falls_back_to_table_during_task(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    """While a turn is streaming, bare /statusline prints the table instead of a menu."""
    app = _make_shell_app(runtime, tmp_path)
    app._active_view = object()  # simulate a running turn
    print_mock = Mock()
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    menu_mock = Mock()
    monkeypatch.setattr(
        "pythinker_code.ui.shell.components.settings_list.run_settings_list", menu_mock
    )

    await _run_statusline(app, "")

    menu_mock.assert_not_called()
    from rich.table import Table

    tables = [call.args[0] for call in print_mock.call_args_list if isinstance(call.args[0], Table)]
    assert tables, "expected the settings table to be printed during a running turn"
    row_labels = list(tables[0].columns[0].cells)
    assert "Enabled" in row_labels
    assert "Segments" in row_labels


@pytest.mark.asyncio
async def test_statusline_style_persists(runtime: Runtime, tmp_path: Path, monkeypatch) -> None:
    config_path = (tmp_path / "config.toml").resolve()
    runtime.config.source_file = config_path
    app = _make_shell_app(runtime, tmp_path)
    config_for_save = get_default_config()
    monkeypatch.setattr(shell_slash, "load_config", Mock(return_value=config_for_save))
    monkeypatch.setattr(shell_slash, "save_config", Mock())
    monkeypatch.setattr(shell_slash.console, "print", Mock())
    with pytest.raises(Reload):
        await _run_statusline(app, "style plain")
    assert config_for_save.tui.statusline.style == "plain"


@pytest.mark.asyncio
async def test_statusline_style_rejects_unknown(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    runtime.config.source_file = (tmp_path / "config.toml").resolve()
    app = _make_shell_app(runtime, tmp_path)
    save_mock = Mock()
    monkeypatch.setattr(shell_slash, "load_config", Mock(return_value=get_default_config()))
    monkeypatch.setattr(shell_slash, "save_config", save_mock)
    monkeypatch.setattr(shell_slash.console, "print", Mock())
    await _run_statusline(app, "style neon")  # no Reload raised
    save_mock.assert_not_called()


@pytest.mark.asyncio
async def test_statusline_bar_width_bounds(runtime: Runtime, tmp_path: Path, monkeypatch) -> None:
    runtime.config.source_file = (tmp_path / "config.toml").resolve()
    app = _make_shell_app(runtime, tmp_path)
    config_for_save = get_default_config()
    monkeypatch.setattr(shell_slash, "load_config", Mock(return_value=config_for_save))
    monkeypatch.setattr(shell_slash, "save_config", Mock())
    monkeypatch.setattr(shell_slash.console, "print", Mock())
    with pytest.raises(Reload):
        await _run_statusline(app, "bar-width 14")
    assert config_for_save.tui.statusline.bar_width == 14
    # out of range: rejected, no Reload
    await _run_statusline(app, "bar-width 3")
    assert config_for_save.tui.statusline.bar_width == 14


@pytest.mark.asyncio
async def test_statusline_budget_set_and_clear(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    runtime.config.source_file = (tmp_path / "config.toml").resolve()
    app = _make_shell_app(runtime, tmp_path)
    config_for_save = get_default_config()
    monkeypatch.setattr(shell_slash, "load_config", Mock(return_value=config_for_save))
    monkeypatch.setattr(shell_slash, "save_config", Mock())
    monkeypatch.setattr(shell_slash.console, "print", Mock())
    with pytest.raises(Reload):
        await _run_statusline(app, "budget 50")
    assert config_for_save.tui.statusline.cost_budget == 50.0
    with pytest.raises(Reload):
        await _run_statusline(app, "budget none")
    assert config_for_save.tui.statusline.cost_budget is None


@pytest.mark.asyncio
async def test_statusline_budget_rejects_non_finite(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    # float() parses "nan"/"inf", and nan < 0 is False — both must be rejected
    # instead of persisted as a dollar amount.
    runtime.config.source_file = (tmp_path / "config.toml").resolve()
    app = _make_shell_app(runtime, tmp_path)
    config_for_save = get_default_config()
    monkeypatch.setattr(shell_slash, "load_config", Mock(return_value=config_for_save))
    monkeypatch.setattr(shell_slash, "save_config", Mock())
    monkeypatch.setattr(shell_slash.console, "print", Mock())
    for raw in ("nan", "inf", "-inf", "-5"):
        await _run_statusline(app, f"budget {raw}")  # no Reload raised
        assert config_for_save.tui.statusline.cost_budget is None


@pytest.mark.asyncio
async def test_statusline_segments_bare_lists_all_ids(
    runtime: Runtime, tmp_path: Path, monkeypatch
) -> None:
    app = _make_shell_app(runtime, tmp_path)
    printed: list[object] = []
    monkeypatch.setattr(
        shell_slash.console, "print", lambda *a, **k: printed.append(a[0] if a else None)
    )
    await _run_statusline(app, "segments")
    blob = " ".join(str(p) for p in printed)
    for seg in ("spinner", "speed", "limits", "clock"):
        assert seg in blob
