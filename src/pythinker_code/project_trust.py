"""Persistent per-project trust decisions.

A cloned repository's project-scope config (``.pythinker/config.toml``)
carries auto-executed surfaces — shell hooks above all — so those load
only after the user trusts the project root. The decision persists
across sessions in a user-scope file keyed by the normalized root path;
it is never stored inside the project, where the repo could edit it.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import cast

from pythinker_code.share import get_share_dir
from pythinker_code.utils.logging import logger

_TRUST_FILE_NAME = "trusted_projects.json"


def _trust_file() -> Path:
    return get_share_dir() / _TRUST_FILE_NAME


def _normalize(project_root: Path) -> str:
    return str(project_root.expanduser().resolve(strict=False))


def _read_trusted_roots() -> set[str]:
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
    roots: object = cast("dict[str, object]", data).get("trusted_roots")
    if not isinstance(roots, list):
        return set()
    return {root for root in cast("list[object]", roots) if isinstance(root, str)}


def _write_trusted_roots(roots: set[str]) -> None:
    path = _trust_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"trusted_roots": sorted(roots)}, indent=2) + "\n"
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
    return _normalize(project_root) in _read_trusted_roots()


def set_project_trusted(project_root: Path, trusted: bool) -> None:
    """Durably record (or revoke) trust for *project_root*."""
    roots = _read_trusted_roots()
    normalized = _normalize(project_root)
    if trusted:
        roots.add(normalized)
    else:
        roots.discard(normalized)
    _write_trusted_roots(roots)
