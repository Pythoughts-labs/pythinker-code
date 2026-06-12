"""Persistent per-project trust decisions.

A cloned repository's project-scope config (``.pythinker/config.toml``)
carries auto-executed surfaces — shell hooks above all — so those load
only after the user trusts the project root. The decision persists
across sessions in a user-scope file keyed by a digest of the normalized
root path; it is never stored inside the project, where the repo could
edit it, and it does not persist local filesystem paths in clear text.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import IO, cast

from pythinker_code.share import get_share_dir
from pythinker_code.utils.logging import logger

_TRUST_FILE_NAME = "trusted_projects.json"
_LOCK_FILE_NAME = f"{_TRUST_FILE_NAME}.lock"
_STORE_KEY = "trusted_project_ids"
_LEGACY_STORE_KEY = "trusted_roots"


def _trust_file() -> Path:
    return get_share_dir() / _TRUST_FILE_NAME


def _lock_file() -> Path:
    return get_share_dir() / _LOCK_FILE_NAME


def _normalize(project_root: Path) -> str:
    return str(project_root.expanduser().resolve(strict=False))


def _project_id(project_root: Path) -> str:
    return hashlib.sha256(_normalize(project_root).encode("utf-8")).hexdigest()


@contextlib.contextmanager
def _locked_trust_store() -> Generator[None]:
    """Serialize trust-store read/modify/write across local processes."""
    path = _lock_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock_file:
        _lock_file_exclusive(lock_file)
        try:
            yield
        finally:
            _unlock_file(lock_file)


def _lock_file_exclusive(lock_file: IO[bytes]) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)


def _unlock_file(lock_file: IO[bytes]) -> None:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_trusted_project_ids() -> set[str]:
    path = _trust_file()
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Unreadable project trust file {path}; treating all projects as untrusted: {error}",
            path=path,
            error=exc,
        )
        return set()
    if not isinstance(data, dict):
        return set()

    project_ids: object = cast("dict[str, object]", data).get(_STORE_KEY)
    if isinstance(project_ids, list):
        return {
            value
            for value in cast("list[object]", project_ids)
            if isinstance(value, str) and _looks_like_sha256(value)
        }

    # Backward compatibility for pre-hash stores. Read legacy clear-text paths,
    # return their digests, and let the next write persist only hashed ids.
    legacy_roots: object = cast("dict[str, object]", data).get(_LEGACY_STORE_KEY)
    if not isinstance(legacy_roots, list):
        return set()
    return {
        hashlib.sha256(root.encode("utf-8")).hexdigest()
        for root in cast("list[object]", legacy_roots)
        if isinstance(root, str)
    }


def _looks_like_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _write_trusted_project_ids(project_ids: set[str]) -> None:
    path = _trust_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({_STORE_KEY: sorted(project_ids)}, indent=2) + "\n"
    # Atomic replace so a crash mid-write cannot corrupt the trust store.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(payload)
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def is_project_trusted(project_root: Path) -> bool:
    """Whether the user has durably trusted *project_root*."""
    with _locked_trust_store():
        return _project_id(project_root) in _read_trusted_project_ids()


def set_project_trusted(project_root: Path, trusted: bool) -> None:
    """Durably record (or revoke) trust for *project_root*."""
    with _locked_trust_store():
        project_ids = _read_trusted_project_ids()
        project_id = _project_id(project_root)
        if trusted:
            project_ids.add(project_id)
        else:
            project_ids.discard(project_id)
        _write_trusted_project_ids(project_ids)
