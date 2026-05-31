"""Tests for the non-blocking update parity + robust Windows native installer.

Kept in a separate file from test_shell_update.py to avoid colliding with
concurrent edits there. Covers: the cached-only startup notice, the Windows
installer command shape, the /update slash command registration, and the
in-shell run_update_prompt flow.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

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


def test_windows_upgrade_helper_uses_direct_command_not_powershell(monkeypatch):
    monkeypatch.setattr(update, "_is_windows", lambda: True)

    def fake_which(name: str) -> str | None:
        return {"uv": "C:\\Program Files\\uv\\uv.exe"}.get(name)

    monkeypatch.setattr(update, "which", fake_which)

    captured: dict[str, object] = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(update.subprocess, "Popen", fake_popen)

    assert update._spawn_detached_windows_upgrade(["uv", "tool", "upgrade", "pythinker code"])

    args = cast(list[str], captured["args"])
    assert args == ["C:\\Program Files\\uv\\uv.exe", "tool", "upgrade", "pythinker code"]
    assert "powershell" not in " ".join(args).lower()
    assert "encoded" not in " ".join(args).lower()

    kwargs = cast(dict[str, object], captured["kwargs"])
    assert cast(int, kwargs["creationflags"]) & 0x00000010  # CREATE_NEW_CONSOLE
    assert kwargs["close_fds"] is True


async def test_shell_auto_update_toast_shows_new_version_immediately(monkeypatch):
    import pythinker_code.ui.shell as shell_mod

    async def fake_refresh():
        return update.UpdateResult.UPDATE_AVAILABLE

    toast_calls: list[tuple[str, dict[str, object]]] = []
    invalidated: list[bool] = []

    def fake_toast(message: str, **kwargs):
        toast_calls.append((message, kwargs))

    shell = shell_mod.Shell.__new__(shell_mod.Shell)
    # SimpleNamespace stand-in for the CustomPromptSession; only invalidate()
    # is exercised by _auto_update().
    shell._prompt_session = SimpleNamespace(  # type: ignore[assignment]
        invalidate=lambda: invalidated.append(True)
    )

    monkeypatch.setattr(shell_mod, "refresh_update_cache_if_due", fake_refresh)
    monkeypatch.setattr(
        shell_mod,
        "pending_update_notice",
        lambda: "Update available: 0.19.0 → 0.21.0. Run /update to install.",
    )
    monkeypatch.setattr(shell_mod, "toast", fake_toast)

    await shell_mod.Shell._auto_update(shell)

    assert toast_calls == [
        (
            "Update available: 0.19.0 → 0.21.0. Run /update to install.",
            {
                "topic": "update",
                "duration": 30.0,
                "immediate": True,
                "style": "fg:ansibrightyellow bold",
            },
        )
    ]
    assert invalidated == [True]


def test_windows_installer_launches_signed_inno_directly(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "_is_windows", lambda: True)

    captured: dict[str, object] = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(update.subprocess, "Popen", fake_popen)

    installer = tmp_path / "PythinkerSetup-1.2.0.exe"
    installer.write_bytes(b"stub")
    assert update._spawn_detached_windows_installer(installer) is True

    args = cast(list[str], captured["args"])
    assert args == [
        str(installer),
        "/SILENT",
        "/NORESTART",
        "/CURRENTUSER",
        "/CLOSEAPPLICATIONS",
        "/NORESTARTAPPLICATIONS",
    ]
    assert "powershell" not in " ".join(args).lower()
    assert "encoded" not in " ".join(args).lower()
    assert "/VERYSILENT" not in args
    assert "/SUPPRESSMSGBOXES" not in args

    kwargs = cast(dict[str, object], captured["kwargs"])
    assert cast(int, kwargs["creationflags"]) & 0x00000200  # CREATE_NEW_PROCESS_GROUP
    assert kwargs["close_fds"] is True


def test_update_command_registered():
    from pythinker_code.ui.shell import slash

    assert slash.registry.find_command("update") is not None
    assert slash.registry.find_command("upgrade") is not None


async def test_run_update_prompt_reports_up_to_date(monkeypatch):
    monkeypatch.setattr(constant, "VERSION", "2.0.0")
    calls: list[tuple[bool, bool]] = []

    async def fake_do_update(*, print: bool, check_only: bool):
        calls.append((print, check_only))
        return update.UpdateResult.UP_TO_DATE

    monkeypatch.setattr(update, "do_update", fake_do_update)

    assert await update.run_update_prompt() is update.UpdateResult.UP_TO_DATE
    assert calls == [(True, True)]


async def test_run_update_prompt_skip_returns_none(monkeypatch):
    monkeypatch.setattr(constant, "VERSION", "1.0.0")

    async def fake_do_update(*, print: bool, check_only: bool):
        assert (print, check_only) == (True, True)
        return update.UpdateResult.UPDATE_AVAILABLE

    async def fake_prompt(current, latest):
        assert current == "1.0.0"
        assert latest == "1.2.0"
        return update.UpdatePromptSelection.SKIP

    monkeypatch.setattr(update, "do_update", fake_do_update)
    monkeypatch.setattr(update, "_read_latest_version_cache", lambda: "1.2.0")
    monkeypatch.setattr(update, "_prompt_update_selection", fake_prompt)

    assert await update.run_update_prompt() is None
