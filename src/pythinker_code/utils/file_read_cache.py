"""Session-scoped record of when each file was last read.

Backs two overwrite guards. Stale-overwrite detection: once the agent has read a file,
overwriting or editing it is rejected if the on-disk copy changed since that read (an
external/user edit the agent never saw). Partial-overwrite detection: a full ``WriteFile``
overwrite is rejected when the recorded read only saw part of the file, because the
overwrite would discard the unseen remainder. A file the agent never read is not gated —
ordinary first-contact writes are always allowed. The cache is per-agent (one per
``Runtime``); the Read tool records, the Write and StrReplace tools consult and refresh it.
"""

from __future__ import annotations

import os
from typing import NamedTuple

from pythinker_host.path import HostPath


class FileReadState(NamedTuple):
    """The file's ``(mtime, size)`` when last read, plus whether that read saw the whole file.

    ``mtime``/``size`` back stale detection (mtime alone misses a same-tick or
    mtime-preserving external edit, so size is compared too). ``complete`` backs
    partial-overwrite detection: ``False`` when a capped or offset read left part of the file
    unseen.
    """

    mtime: float
    size: int
    complete: bool


class FileReadCache:
    """Maps a normalized real path to the :class:`FileReadState` of its last read."""

    def __init__(self) -> None:
        self._read_state: dict[str, FileReadState] = {}

    @staticmethod
    def _key(path: HostPath) -> str:
        return os.path.normpath(str(path))

    def record(self, path: HostPath, mtime: float, size: int, complete: bool = True) -> None:
        """Record (or refresh) the read state for *path*.

        A partial read (``complete=False``) never downgrades an existing full-read record at
        the same ``(mtime, size)``: once the agent has seen the whole file, a later partial
        re-read of the unchanged bytes does not un-see it.
        """
        key = self._key(path)
        if not complete:
            existing = self._read_state.get(key)
            if (
                existing is not None
                and existing.complete
                and existing.mtime == mtime
                and existing.size == size
            ):
                return
        self._read_state[key] = FileReadState(mtime, size, complete)

    def read_state(self, path: HostPath) -> FileReadState | None:
        """Return the recorded :class:`FileReadState` for *path*, or ``None`` if never read."""
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
    try:
        current = await disk_path.stat()
    except OSError:
        return False
    return current.st_mtime > state.mtime or current.st_size != state.size


def read_was_incomplete(cache: FileReadCache, real_path: HostPath) -> bool:
    """True when *real_path* was read but the agent only saw part of it (a capped/offset read).

    A full overwrite would discard the unseen remainder, so the WriteFile overwrite path
    rejects it until the agent reads the file in full. Returns ``False`` when the file was
    never read or was read completely. The unchanged-on-disk precondition is handled
    separately by :func:`overwrite_is_stale`, which the overwrite path checks first.
    """
    state = cache.read_state(real_path)
    return state is not None and not state.complete
