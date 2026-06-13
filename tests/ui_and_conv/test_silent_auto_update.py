"""Silent auto-update: background install + result surfacing at startup."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pythinker_core.tooling.empty import EmptyToolset

import pythinker_code.ui.shell as shell_module
from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.ui.shell import Shell
from pythinker_code.ui.shell.update import UpdateResult


def _make_shell(runtime: Runtime, tmp_path: Path) -> Shell:
    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    soul = PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))
    return Shell(soul)


@pytest.fixture
def _toasts(monkeypatch):
    captured: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        shell_module, "toast", lambda msg, **kw: captured.append((msg, kw))
    )
    return captured


@pytest.mark.asyncio
async def test_silent_update_success_toasts_restart(
    runtime: Runtime, tmp_path: Path, monkeypatch, _toasts
):
    shell = _make_shell(runtime, tmp_path)
    monkeypatch.setattr(shell_module, "_should_auto_check_for_updates", lambda: True)
    monkeypatch.setattr(shell_module, "_mark_auto_update_check_attempt", lambda: None)
    monkeypatch.setattr(shell_module, "_detect_upgrade_command", lambda: ["pip"])

    async def fake_job(**kw):
        assert kw["print_output"] is False
        assert kw["source"] == "startup-auto"
        return UpdateResult.UPDATED

    monkeypatch.setattr(shell_module, "run_update_job", fake_job)
    monkeypatch.setattr(
        shell_module,
        "read_update_status",
        lambda: SimpleNamespace(message="updated", target_version="0.43.0"),
    )

    await shell._silent_auto_update()

    assert any("Restart Pythinker to apply" in m for m, _ in _toasts)
    assert any("0.43.0" in m for m, _ in _toasts)


@pytest.mark.asyncio
async def test_silent_update_smoke_fail_toasts_verification_failed(
    runtime: Runtime, tmp_path: Path, monkeypatch, _toasts
):
    shell = _make_shell(runtime, tmp_path)
    monkeypatch.setattr(shell_module, "_should_auto_check_for_updates", lambda: True)
    monkeypatch.setattr(shell_module, "_mark_auto_update_check_attempt", lambda: None)
    monkeypatch.setattr(shell_module, "_detect_upgrade_command", lambda: ["pip"])

    async def fake_job(**kw):
        return UpdateResult.UPDATED

    monkeypatch.setattr(shell_module, "run_update_job", fake_job)
    monkeypatch.setattr(
        shell_module,
        "read_update_status",
        lambda: SimpleNamespace(
            message="Updated, but smoke check did not pass: boom",
            target_version="0.43.0",
        ),
    )

    await shell._silent_auto_update()

    assert any("verification failed" in m for m, _ in _toasts)
    assert not any("Restart Pythinker to apply" in m for m, _ in _toasts)


@pytest.mark.asyncio
async def test_silent_update_failed_is_silent(
    runtime: Runtime, tmp_path: Path, monkeypatch, _toasts
):
    shell = _make_shell(runtime, tmp_path)
    monkeypatch.setattr(shell_module, "_should_auto_check_for_updates", lambda: True)
    monkeypatch.setattr(shell_module, "_mark_auto_update_check_attempt", lambda: None)
    monkeypatch.setattr(shell_module, "_detect_upgrade_command", lambda: ["pip"])

    async def fake_job(**kw):
        return UpdateResult.FAILED

    monkeypatch.setattr(shell_module, "run_update_job", fake_job)
    await shell._silent_auto_update()
    assert _toasts == []


@pytest.mark.asyncio
async def test_silent_update_managed_channel_toasts_channel_hint(
    runtime: Runtime, tmp_path: Path, monkeypatch, _toasts
):
    shell = _make_shell(runtime, tmp_path)
    monkeypatch.setattr(shell_module, "_should_auto_check_for_updates", lambda: True)
    monkeypatch.setattr(shell_module, "_mark_auto_update_check_attempt", lambda: None)
    monkeypatch.setattr(
        shell_module,
        "_detect_upgrade_command",
        lambda: [shell_module.MANAGED_CHANNEL_MARKER, "Nix"],
    )

    async def fake_job(**kw):
        return UpdateResult.UPDATE_AVAILABLE

    monkeypatch.setattr(shell_module, "run_update_job", fake_job)
    monkeypatch.setattr(shell_module, "welcome_update_target", lambda: "0.43.0")
    monkeypatch.setattr(
        shell_module,
        "format_managed_channel_notice",
        lambda cur, latest: f"managed Nix {cur} -> {latest}",
    )

    await shell._silent_auto_update()
    assert any("managed Nix" in m for m, _ in _toasts)


@pytest.mark.asyncio
async def test_silent_update_respects_throttle(
    runtime: Runtime, tmp_path: Path, monkeypatch, _toasts
):
    shell = _make_shell(runtime, tmp_path)
    monkeypatch.setattr(shell_module, "_should_auto_check_for_updates", lambda: False)
    called = False

    async def fake_job(**kw):
        nonlocal called
        called = True
        return UpdateResult.UPDATED

    monkeypatch.setattr(shell_module, "run_update_job", fake_job)
    await shell._silent_auto_update()
    assert called is False
    assert _toasts == []
