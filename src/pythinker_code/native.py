"""Native-build detection + GitHub Releases lookup helpers.

The Windows native installer drops a sentinel file ``.pythinker-native`` next
to the PyInstaller-frozen ``pythinker.exe``. The runtime probes for that file
to decide whether ``pythinker update`` should re-run the native installer
instead of shelling out to ``uv tool upgrade``.
"""

from __future__ import annotations

import sys
from pathlib import Path

GITHUB_REPO = "mohamed-elkholy95/Pythinker-Code"
SENTINEL_FILENAME = ".pythinker-native"


def is_native_build() -> bool:
    """True iff this process is a Pythinker native (Inno Setup) install."""
    if not getattr(sys, "frozen", False):
        return False
    try:
        exe_dir = Path(sys.executable).resolve().parent
    except OSError:
        return False
    return (exe_dir / SENTINEL_FILENAME).is_file()


def native_installer_release_url(channel: str = "latest") -> str:
    """Return the GitHub API URL for the requested release channel."""
    if channel == "latest":
        return f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    return f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{channel}"


def native_installer_asset_name(version: str) -> str:
    """Filename of the installer asset attached to a Release."""
    return f"PythinkerSetup-{version}.exe"
