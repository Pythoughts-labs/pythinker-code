from __future__ import annotations

import tarfile
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


def test_native_prompt_does_not_leak_marker(monkeypatch):
    """Regression: the update prompt must never render the raw marker token."""
    with patch("pythinker_code.ui.shell.update._is_native_build", return_value=True):
        rendered = upd._update_prompt_text("0.1.0", "0.2.0")
    text = rendered.plain
    assert upd.NATIVE_INSTALLER_MARKER not in text
    assert "native updater" in text


def test_install_native_archive_replaces_current_executable(monkeypatch, tmp_path):
    current = tmp_path / "pythinker"
    current.write_text("old", encoding="utf-8")
    current.chmod(0o755)

    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "pythinker").write_text("new", encoding="utf-8")
    archive = tmp_path / "pythinker-0.2.0-x86_64-unknown-linux-gnu.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload / "pythinker", arcname="pythinker")

    monkeypatch.setattr(upd.sys, "executable", str(current))

    assert upd._install_native_archive(archive) is upd.UpdateResult.UPDATED
    assert current.read_text(encoding="utf-8") == "new"
    assert current.stat().st_mode & 0o111
