"""Unit tests for the session-scoped file read cache (read-before-write support)."""

from __future__ import annotations

from pythinker_host.path import HostPath

from pythinker_code.utils.file_read_cache import FileReadCache


def test_file_read_cache_records_and_normalizes() -> None:
    cache = FileReadCache()

    assert not cache.was_read(HostPath("/repo/a.py"))
    assert cache.read_mtime(HostPath("/repo/a.py")) is None

    cache.record(HostPath("/repo/a.py"), 100.0)
    assert cache.was_read(HostPath("/repo/a.py"))
    assert cache.read_mtime(HostPath("/repo/a.py")) == 100.0

    # Path normalization: redundant segments resolve to the same entry.
    assert cache.read_mtime(HostPath("/repo/sub/../a.py")) == 100.0

    # Re-recording overwrites the timestamp (e.g. after the tool's own write).
    cache.record(HostPath("/repo/a.py"), 200.0)
    assert cache.read_mtime(HostPath("/repo/a.py")) == 200.0
