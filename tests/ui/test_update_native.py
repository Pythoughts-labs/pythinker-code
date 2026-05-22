from __future__ import annotations

from unittest.mock import patch

import pytest

from pythinker_code.ui.shell import update as upd


def test_detect_upgrade_command_returns_native_marker_when_native():
    with patch("pythinker_code.ui.shell.update._is_native_build", return_value=True):
        cmd = upd._detect_upgrade_command()
    assert cmd == [upd.NATIVE_INSTALLER_MARKER]


def test_detect_upgrade_command_pypi_path_when_not_native():
    with (
        patch("pythinker_code.ui.shell.update._is_native_build", return_value=False),
        patch("sys.executable", "/usr/local/bin/python"),
    ):
        cmd = upd._detect_upgrade_command()
    assert "pythinker-code" in cmd
    assert cmd != [upd.NATIVE_INSTALLER_MARKER]


@pytest.mark.asyncio
async def test_native_update_skipped_when_auto_disabled(monkeypatch):
    monkeypatch.setenv("PYTHINKER_CLI_NO_AUTO_UPDATE", "1")
    with patch("pythinker_code.ui.shell.update._run_native_installer") as run_native:
        result = await upd._maybe_run_native_update(latest_version="9.9.9")
    run_native.assert_not_called()
    assert result is upd.UpdateResult.UPDATE_AVAILABLE


def test_native_banner_does_not_leak_marker(monkeypatch):
    """Regression: the update banner must never render the raw marker token."""
    with patch("pythinker_code.ui.shell.update._is_native_build", return_value=True):
        rendered = upd._update_banner_text("0.1.0", "0.2.0")
    text = rendered.plain
    assert upd.NATIVE_INSTALLER_MARKER not in text
    assert "PythinkerSetup-0.2.0.exe" in text
