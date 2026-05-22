from __future__ import annotations

import sys
from unittest.mock import patch

from pythinker_code import native


def test_is_native_build_false_when_not_frozen():
    with patch.object(sys, "frozen", False, create=True):
        assert native.is_native_build() is False


def test_is_native_build_false_when_frozen_without_sentinel(tmp_path):
    fake_exe = tmp_path / "pythinker.exe"
    fake_exe.write_bytes(b"")
    with (
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "executable", str(fake_exe)),
    ):
        assert native.is_native_build() is False


def test_is_native_build_true_when_sentinel_present(tmp_path):
    fake_exe = tmp_path / "pythinker.exe"
    fake_exe.write_bytes(b"")
    (tmp_path / ".pythinker-native").write_text("pythinker-native-build")
    with (
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "executable", str(fake_exe)),
    ):
        assert native.is_native_build() is True


def test_native_installer_release_url_latest():
    url = native.native_installer_release_url(channel="latest")
    assert url == ("https://api.github.com/repos/mohamed-elkholy95/Pythinker-Code/releases/latest")


def test_native_installer_release_url_stable():
    url = native.native_installer_release_url(channel="stable")
    assert "/releases/tags/stable" in url


def test_native_installer_asset_name():
    assert native.native_installer_asset_name("0.11.0") == "PythinkerSetup-0.11.0.exe"
