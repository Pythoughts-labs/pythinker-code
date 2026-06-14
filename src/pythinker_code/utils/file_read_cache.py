"""Session-scoped record of when each file was last read.

Backs stale-overwrite detection: once the agent has read a file, overwriting or editing it
is rejected if the on-disk copy changed since that read (an external/user edit the agent
never saw). A file the agent never read is not gated — ordinary first-contact writes are
always allowed. The cache is per-agent (one per ``Runtime``); the Read tool records, the
Write and StrReplace tools consult and refresh it.
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


async def overwrite_is_stale(
    cache: FileReadCache, disk_path: HostPath, real_path: HostPath
) -> bool:
    """True when *real_path* was read and its on-disk mtime advanced since that read.

    This is the signal that a blind overwrite/edit would clobber changes the agent never
    saw. Returns ``False`` when the file was never read (an ordinary first-contact write) or
    cannot be stat'd — only a genuine read-then-externally-modified sequence is flagged, so
    the guard never blocks a legitimate write.
    """
    read_mtime = cache.read_mtime(real_path)
    if read_mtime is None:
        return False
    try:
        current_mtime = (await disk_path.stat()).st_mtime
    except OSError:
        return False
    return current_mtime > read_mtime
