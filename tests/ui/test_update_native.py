from __future__ import annotations

from unittest.mock import patch

import pytest

from pythinker_code.ui.shell import update as upd


def test_detect_upgrade_command_returns_native_marker_when_native():
    with patch("pythinker_code.ui.shell.update._is_native_build", return_value=True):
        cmd = upd._detect_upgrade_command()
    assert cmd == [upd.NATIVE_INSTALLER_MARKER]


def test_detect_upgrade_command_pypi_path_when_not_native():
    with patch(
        "pythinker_code.ui.shell.update._is_native_build", return_value=False
    ), patch("sys.executable", "/usr/local/bin/python"):
        cmd = upd._detect_upgrade_command()
    assert "pythinker-code" in cmd
    assert cmd != [upd.NATIVE_INSTALLER_MARKER]


@pytest.mark.asyncio
async def test_native_update_skipped_when_auto_disabled(monkeypatch):
    monkeypatch.setenv("DISABLE_AUTOUPDATER", "1")
    with patch(
        "pythinker_code.ui.shell.update._run_native_installer"
    ) as run_native:
        result = await upd._maybe_run_native_update(latest_version="9.9.9")
    run_native.assert_not_called()
    assert result is upd.UpdateResult.UPDATE_AVAILABLE
