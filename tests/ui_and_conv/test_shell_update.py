from __future__ import annotations

from types import SimpleNamespace

import pytest
from rich.console import Console

from pythinker_code.ui.shell import update


@pytest.mark.asyncio
async def test_prompt_pre_start_update_runs_update_and_exits_on_accept(monkeypatch):
    calls: list[tuple[bool]] = []

    async def fake_resolve() -> str:
        return "999.0.0"

    async def fake_confirm(current: str, latest: str) -> bool:
        return True

    async def fake_do_update(*, print: bool) -> update.UpdateResult:
        calls.append((print,))
        return update.UpdateResult.UPDATED

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fake_resolve)
    monkeypatch.setattr(update, "_confirm_update_now", fake_confirm)
    monkeypatch.setattr(update, "do_update", fake_do_update)

    with pytest.raises(update.typer.Exit) as excinfo:
        await update.prompt_pre_start_update()

    assert excinfo.value.exit_code == 0
    assert calls == [(True,)]


@pytest.mark.asyncio
async def test_prompt_pre_start_update_continues_on_decline(monkeypatch):
    async def fake_resolve() -> str:
        return "999.0.0"

    async def fake_confirm(current: str, latest: str) -> bool:
        return False

    async def fail_do_update(*, print: bool) -> update.UpdateResult:
        raise AssertionError("declining must not run the update")

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fake_resolve)
    monkeypatch.setattr(update, "_confirm_update_now", fake_confirm)
    monkeypatch.setattr(update, "do_update", fail_do_update)

    # Returns without raising typer.Exit (session continues).
    assert await update.prompt_pre_start_update() is None


@pytest.mark.asyncio
async def test_prompt_pre_start_update_skips_when_up_to_date(monkeypatch):
    confirmed: list[bool] = []

    async def fake_resolve() -> str:
        return "0.0.0"

    async def fake_confirm(current: str, latest: str) -> bool:
        confirmed.append(True)
        return True

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fake_resolve)
    monkeypatch.setattr(update, "_confirm_update_now", fake_confirm)

    assert await update.prompt_pre_start_update() is None
    assert confirmed == []


@pytest.mark.asyncio
async def test_prompt_pre_start_update_respects_opt_out(monkeypatch):
    async def fail_resolve() -> str:
        raise AssertionError("opt-out must short-circuit before checking versions")

    monkeypatch.setenv("PYTHINKER_CLI_NO_AUTO_UPDATE", "1")
    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fail_resolve)

    assert await update.prompt_pre_start_update() is None


@pytest.mark.asyncio
async def test_prompt_pre_start_update_skips_non_tty(monkeypatch):
    async def fail_resolve() -> str:
        raise AssertionError("non-tty must short-circuit before checking versions")

    monkeypatch.setattr(update.sys, "stdout", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: False)
    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fail_resolve)

    assert await update.prompt_pre_start_update() is None


@pytest.mark.asyncio
async def test_resolve_latest_version_fetches_when_due(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    last_check_file = tmp_path / "last_update_check.txt"
    calls: list[tuple[bool, bool]] = []

    async def fake_do_update(*, print: bool, check_only: bool) -> update.UpdateResult:
        calls.append((print, check_only))
        latest_file.write_text("2.0.0", encoding="utf-8")
        return update.UpdateResult.UPDATE_AVAILABLE

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "LAST_UPDATE_CHECK_FILE", last_check_file)
    monkeypatch.setattr(update, "_should_auto_check_for_updates", lambda: True)
    monkeypatch.setattr(update, "do_update", fake_do_update)

    result = await update._resolve_latest_version_for_prompt()

    assert result == "2.0.0"
    assert calls == [(False, True)]
    assert last_check_file.exists()


@pytest.mark.asyncio
async def test_resolve_latest_version_uses_cache_when_not_due(monkeypatch, tmp_path):
    latest_file = tmp_path / "latest.txt"
    latest_file.write_text("3.1.0", encoding="utf-8")

    async def fail_do_update(*, print: bool, check_only: bool) -> update.UpdateResult:
        raise AssertionError("must not hit the network when the throttle is not due")

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", latest_file)
    monkeypatch.setattr(update, "_should_auto_check_for_updates", lambda: False)
    monkeypatch.setattr(update, "do_update", fail_do_update)

    assert await update._resolve_latest_version_for_prompt() == "3.1.0"


@pytest.mark.asyncio
async def test_do_update_on_windows_spawns_detached_and_exits(monkeypatch, tmp_path):
    spawned: list[list[str]] = []

    async def fake_get_latest(session):
        return "999.0.0"

    monkeypatch.setattr(update, "LATEST_VERSION_FILE", tmp_path / "latest.txt")
    monkeypatch.setattr(update, "_get_latest_version", fake_get_latest)
    monkeypatch.setattr(update, "_is_windows", lambda: True)

    def fake_spawn(cmd: list[str]) -> bool:
        spawned.append(cmd)
        return True

    monkeypatch.setattr(update, "_spawn_detached_windows_upgrade", fake_spawn)

    async def _noop_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(update.asyncio, "sleep", _noop_sleep)

    def fake_run(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called on Windows path")

    monkeypatch.setattr(update.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as excinfo:
        await update.do_update(print=False, check_only=False)

    assert excinfo.value.code == 0
    assert spawned and "pythinker-code" in spawned[0]


def test_update_prompt_text_shows_version_and_command(monkeypatch):
    rendered = Console(width=100, record=True, color_system=None)
    monkeypatch.setattr(update, "console", rendered)
    monkeypatch.setattr(
        update,
        "_detect_upgrade_command",
        lambda: ["uv", "tool", "upgrade", "pythinker-code"],
    )

    text = update._update_prompt_text("1.2.0", "1.3.0")
    rendered.print(text)
    output = rendered.export_text()

    assert "✨ Update available! 1.2.0 -> 1.3.0" in output
    assert "Release notes:" in output
    assert "uv tool upgrade pythinker-code" in output
