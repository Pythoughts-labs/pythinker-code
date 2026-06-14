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
    """Maps a normalized real path to the file's ``(mtime, size)`` when it was last read.

    Both are tracked because mtime alone misses real external edits: a write within the same
    filesystem-mtime tick, or an mtime preserved/restored by tooling (``touch -r``, archive
    extraction), leaves mtime unchanged while the content — and almost always the size —
    differs. Comparing size as well catches those.
    """

    def __init__(self) -> None:
        self._read_state: dict[str, tuple[float, int]] = {}

    @staticmethod
    def _key(path: HostPath) -> str:
        return os.path.normpath(str(path))

    def record(self, path: HostPath, mtime: float, size: int) -> None:
        """Record (or refresh) the read ``(mtime, size)`` for *path*."""
        self._read_state[self._key(path)] = (mtime, size)

    def read_state(self, path: HostPath) -> tuple[float, int] | None:
        """Return the recorded ``(mtime, size)`` for *path*, or ``None`` if never read."""
        return self._read_state.get(self._key(path))

    def was_read(self, path: HostPath) -> bool:
        """Whether *path* has been read in this session."""
        return self._key(path) in self._read_state


async def overwrite_is_stale(
    cache: FileReadCache, disk_path: HostPath, real_path: HostPath
) -> bool:
    """True when *real_path* was read and its on-disk ``(mtime, size)`` changed since.

    This is the signal that a blind overwrite/edit would clobber changes the agent never
    saw. Stale when the mtime advanced OR the size differs — the latter catches an external
    edit whose mtime was not bumped (same-tick write, or a preserved/restored mtime).
    Returns ``False`` when the file was never read (an ordinary first-contact write) or
    cannot be stat'd, so the guard never blocks a legitimate write.
    """
    state = cache.read_state(real_path)
    if state is None:
        return False
    read_mtime, read_size = state
    try:
        current = await disk_path.stat()
    except OSError:
        return False
    return current.st_mtime > read_mtime or current.st_size != read_size
