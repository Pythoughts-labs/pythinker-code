"""Session-scoped record of when each file was last read.

Backs read-before-write enforcement: a blind overwrite of an existing file requires the
agent to have read it first, and the on-disk file must not have changed since that read
(stale-overwrite detection). The cache is per-agent (one per ``Runtime``); the Read tool
records, the Write tool consults and refreshes it.
"""

from __future__ import annotations

import os

from pythinker_host.path import HostPath


class FileReadCache:
    """Maps a normalized real path to the file's mtime at the time it was last read."""

    def __init__(self) -> None:
        self._read_mtime: dict[str, float] = {}

    @staticmethod
    def _key(path: HostPath) -> str:
        return os.path.normpath(str(path))

    def record(self, path: HostPath, mtime: float) -> None:
        """Record (or refresh) the read mtime for *path*."""
        self._read_mtime[self._key(path)] = mtime

    def read_mtime(self, path: HostPath) -> float | None:
        """Return the recorded read mtime for *path*, or ``None`` if never read."""
        return self._read_mtime.get(self._key(path))

    def was_read(self, path: HostPath) -> bool:
        """Whether *path* has been read in this session."""
        return self._key(path) in self._read_mtime
