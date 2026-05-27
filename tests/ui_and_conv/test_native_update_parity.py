"""Tests for the non-blocking update parity + robust Windows native installer.

Kept in a separate file from test_shell_update.py to avoid colliding with
concurrent edits there. Covers: the cached-only startup notice, the Windows
PID-wait installer command shape, the /update slash command registration, and
the in-shell run_update_prompt flow.
"""

from __future__ import annotations

import pythinker_code.constant as constant
from pythinker_code.ui.shell import update


def _set_notice_state(
    monkeypatch, *, current, cached, dismissed=None, disabled=False, source=False
):
    monkeypatch.setattr(constant, "VERSION", current)
    monkeypatch.setattr(update, "_read_latest_version_cache", lambda: cached)
    monkeypatch.setattr(update, "_read_dismissed_version", lambda: dismissed)
    monkeypatch.setattr(update, "_auto_update_disabled", lambda: disabled)
    monkeypatch.setattr(update, "_is_running_from_source_checkout", lambda: source)
    monkeypatch.setattr(update, "_skipped_version_this_session", None)


def test_pending_update_notice_shows_when_newer(monkeypatch):
    _set_notice_state(monkeypatch, current="1.0.0", cached="1.2.0")
    notice = update.pending_update_notice()
    assert notice is not None
    assert "1.0.0" in notice and "1.2.0" in notice and "/update" in notice


def test_pending_update_notice_none_when_up_to_date(monkeypatch):
    _set_notice_state(monkeypatch, current="1.2.0", cached="1.2.0")
    assert update.pending_update_notice() is None


def test_pending_update_notice_none_when_no_cache(monkeypatch):
    _set_notice_state(monkeypatch, current="1.0.0", cached=None)
    assert update.pending_update_notice() is None


def test_pending_update_notice_none_when_dismissed(monkeypatch):
    _set_notice_state(monkeypatch, current="1.0.0", cached="1.2.0", dismissed="1.2.0")
    assert update.pending_update_notice() is None


def test_pending_update_notice_none_when_skipped_this_session(monkeypatch):
    _set_notice_state(monkeypatch, current="1.0.0", cached="1.2.0")
    update._skip_version_this_session("1.2.0")
    assert update.pending_update_notice() is None


def test_pending_update_notice_none_for_source_checkout(monkeypatch):
    _set_notice_state(monkeypatch, current="1.0.0", cached="1.2.0", source=True)
    assert update.pending_update_notice() is None


def test_windows_installer_waits_on_pid_and_cleans_up(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "_is_windows", lambda: True)
    monkeypatch.setattr(update, "which", lambda name: "C:\\Windows\\System32\\cmd.exe")
    monkeypatch.setattr(update.os, "getpid", lambda: 4242)

    captured: dict[str, object] = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        return object()

    monkeypatch.setattr(update.subprocess, "Popen", fake_popen)

    installer = tmp_path / "PythinkerSetup-1.2.0.exe"
    installer.write_bytes(b"stub")
    assert update._spawn_detached_windows_installer(installer) is True

    args = captured["args"]
    assert isinstance(args, list)
    inner = args[-1]  # the `cmd /k <inner>` payload
    # Robust wait on this process's own PID instead of a fixed sleep, capped:
    assert "Wait-Process -Id 4242" in inner
    assert "Timeout 60" in inner
    assert "timeout /t 3" not in inner
    # Silent install + staged-file cleanup:
    assert "/VERYSILENT" in inner
    assert "del /q" in inner
    assert "rmdir /s /q" in inner


def test_update_command_registered():
    from pythinker_code.ui.shell import slash

    assert slash.registry.find_command("update") is not None
    assert slash.registry.find_command("upgrade") is not None


async def test_run_update_prompt_reports_up_to_date(monkeypatch):
    monkeypatch.setattr(constant, "VERSION", "2.0.0")
    force_refresh_values: list[bool] = []

    async def fake_resolve(*, force_refresh: bool = False):
        force_refresh_values.append(force_refresh)
        return "1.0.0"

    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fake_resolve)
    assert await update.run_update_prompt() is update.UpdateResult.UP_TO_DATE
    assert force_refresh_values == [True]


async def test_run_update_prompt_skip_returns_none(monkeypatch):
    monkeypatch.setattr(constant, "VERSION", "1.0.0")

    async def fake_resolve(*, force_refresh: bool = False):
        assert force_refresh is True
        return "1.2.0"

    async def fake_prompt(current, latest):
        return update.UpdatePromptSelection.SKIP

    monkeypatch.setattr(update, "_resolve_latest_version_for_prompt", fake_resolve)
    monkeypatch.setattr(update, "_prompt_update_selection", fake_prompt)
    assert await update.run_update_prompt() is None
