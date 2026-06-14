"""Unit tests for the session-scoped file read cache (stale-overwrite detection)."""

from __future__ import annotations

import os
from pathlib import Path

from pythinker_host.path import HostPath

from pythinker_code.utils.file_read_cache import (
    FileReadCache,
    FileReadState,
    overwrite_is_stale,
    read_was_incomplete,
)


def test_file_read_cache_records_and_normalizes() -> None:
    cache = FileReadCache()

    assert not cache.was_read(HostPath("/repo/a.py"))
    assert cache.read_state(HostPath("/repo/a.py")) is None

    cache.record(HostPath("/repo/a.py"), 100.0, 42)
    assert cache.was_read(HostPath("/repo/a.py"))
    assert cache.read_state(HostPath("/repo/a.py")) == FileReadState(100.0, 42, True)

    # Path normalization: redundant segments resolve to the same entry.
    assert cache.read_state(HostPath("/repo/sub/../a.py")) == FileReadState(100.0, 42, True)

    # Re-recording overwrites the state (e.g. after the tool's own write).
    cache.record(HostPath("/repo/a.py"), 200.0, 7)
    assert cache.read_state(HostPath("/repo/a.py")) == FileReadState(200.0, 7, True)


def test_partial_read_does_not_downgrade_a_full_read_of_the_same_bytes() -> None:
    """Completeness is sticky: once the whole file was seen at a given (mtime, size), a later
    partial re-read of the unchanged bytes keeps it complete (no spurious overwrite block)."""
    cache = FileReadCache()
    p = HostPath("/repo/a.py")

    cache.record(p, 100.0, 42, complete=True)
    cache.record(p, 100.0, 42, complete=False)  # partial re-read of the same bytes
    assert cache.read_state(p) == FileReadState(100.0, 42, True)
    assert not read_was_incomplete(cache, p)

    # But a partial read of a DIFFERENT state (changed mtime/size) does record incomplete.
    cache.record(p, 200.0, 99, complete=False)
    assert cache.read_state(p) == FileReadState(200.0, 99, False)
    assert read_was_incomplete(cache, p)


def test_read_was_incomplete_contract() -> None:
    cache = FileReadCache()
    p = HostPath("/repo/a.py")

    assert not read_was_incomplete(cache, p)  # never read
    cache.record(p, 1.0, 10, complete=True)
    assert not read_was_incomplete(cache, p)  # fully read
    cache.record(p, 1.0, 10, complete=False)  # sticky-complete keeps it complete
    assert not read_was_incomplete(cache, p)
    cache.record(p, 2.0, 5, complete=False)  # fresh partial read of a changed file
    assert read_was_incomplete(cache, p)


async def test_overwrite_is_stale_detects_size_change_with_unchanged_mtime(tmp_path: Path) -> None:
    """A same-mtime external edit that changes the file size (a same-second write, or an mtime
    preserved by ``touch -r``) is still flagged stale — mtime-only detection would miss it."""
    f = tmp_path / "a.txt"
    f.write_text("hello")
    p = HostPath.unsafe_from_local_path(f)
    st = f.stat()
    cache = FileReadCache()
    cache.record(p, st.st_mtime, st.st_size)

    # External edit: different size, with the mtime forced back to the recorded value.
    f.write_text("hello world, now considerably longer")
    os.utime(f, (st.st_atime, st.st_mtime))
    assert f.stat().st_mtime == st.st_mtime  # mtime genuinely unchanged
    assert f.stat().st_size != st.st_size  # size changed

    assert await overwrite_is_stale(cache, p, p) is True


async def test_overwrite_is_stale_false_when_file_unchanged(tmp_path: Path) -> None:
    """An untouched file (same mtime and size) is not stale, so legitimate writes are allowed."""
    f = tmp_path / "a.txt"
    f.write_text("hello")
    p = HostPath.unsafe_from_local_path(f)
    st = f.stat()
    cache = FileReadCache()
    cache.record(p, st.st_mtime, st.st_size)

    assert await overwrite_is_stale(cache, p, p) is False


async def test_overwrite_is_stale_false_when_never_read(tmp_path: Path) -> None:
    """A file the agent never read is not gated (ordinary first-contact write)."""
    f = tmp_path / "a.txt"
    f.write_text("hello")
    p = HostPath.unsafe_from_local_path(f)

    assert await overwrite_is_stale(FileReadCache(), p, p) is False
