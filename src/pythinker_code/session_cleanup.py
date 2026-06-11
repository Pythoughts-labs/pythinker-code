"""Age-based cleanup for personal-scope session and plan state.

Runs at agent startup to keep ~/.pythinker/ from growing unboundedly: with a
30-day retention period, directories/files older than the retention threshold
are removed if they are safe to discard (archived sessions, old plan files).

Never raises — every error is logged at DEBUG level and silently skipped.
"""

from __future__ import annotations

import contextlib
import shutil
import time
from hashlib import md5 as _md5
from pathlib import Path

from pythinker_code.utils.logging import logger

_SESSIONS_DIR_NAME = "sessions"
_PLANS_DIR_NAME = "plans"
_LOCAL_HOST = "local"


# ---------------------------------------------------------------------------
# Public sweep functions
# ---------------------------------------------------------------------------


def sweep_old_sessions(max_age_days: int, *, share_dir: Path | None = None) -> int:
    """Remove archived session directories older than ``max_age_days`` days.

    Only sessions explicitly marked ``archived=True`` in their ``state.json`` are
    eligible. Active or unarchived sessions are never touched regardless of age.
    Orphan directories (no ``state.json``) are removed if their mtime is old enough.

    After removing a session directory the corresponding per-session scratchpad
    file in the project's ``.pythinker/scratch/`` directory is also deleted
    (best-effort; a missing project dir is silently skipped).

    Returns the number of directories removed. Returns 0 when disabled (``max_age_days <= 0``).
    """
    if max_age_days <= 0:
        return 0

    from pythinker_code.share import get_share_dir

    root = share_dir or get_share_dir()
    sessions_root = root / _SESSIONS_DIR_NAME
    if not sessions_root.is_dir():
        return 0

    cutoff = time.time() - max_age_days * 86_400.0
    bucket_to_path = _load_bucket_path_map(root)
    removed = 0

    try:
        buckets = list(sessions_root.iterdir())
    except OSError:
        return 0

    for bucket in buckets:
        if not bucket.is_dir():
            continue
        work_dir_path = bucket_to_path.get(bucket.name)
        try:
            session_dirs = list(bucket.iterdir())
        except OSError:
            continue
        for session_dir in session_dirs:
            if not session_dir.is_dir():
                continue
            try:
                if _maybe_remove_session(session_dir, cutoff, work_dir_path=work_dir_path):
                    removed += 1
            except Exception:
                logger.debug("session_cleanup: skipping {d}", d=session_dir.name)

        # Prune the bucket itself if it is now empty.
        try:
            if not any(bucket.iterdir()):
                bucket.rmdir()
        except OSError:
            pass

    if removed:
        logger.debug("session_cleanup: removed {n} old archived session(s)", n=removed)
    return removed


def sweep_old_plans(max_age_days: int, *, share_dir: Path | None = None) -> int:
    """Remove plan markdown files older than ``max_age_days`` days.

    Plan files are hero-name-slugged markdown files written to ~/.pythinker/plans/
    for each planning session. They are ephemeral by nature and safe to prune once old.

    Returns the number of files removed. Returns 0 when disabled (``max_age_days <= 0``).
    """
    if max_age_days <= 0:
        return 0

    from pythinker_code.share import get_share_dir

    plans_dir = (share_dir or get_share_dir()) / _PLANS_DIR_NAME
    if not plans_dir.is_dir():
        return 0

    cutoff = time.time() - max_age_days * 86_400.0
    removed = 0

    try:
        plan_files = list(plans_dir.glob("*.md"))
    except OSError:
        return 0

    for plan_file in plan_files:
        try:
            if plan_file.stat().st_mtime < cutoff:
                plan_file.unlink(missing_ok=True)
                removed += 1
        except Exception:
            logger.debug("session_cleanup: skipping plan {f}", f=plan_file.name)

    if removed:
        logger.debug("session_cleanup: removed {n} old plan file(s)", n=removed)
    return removed


def sweep_stale_work_dirs(*, share_dir: Path | None = None) -> int:
    """Prune pythinker.json entries for paths that no longer exist and have no sessions.

    An entry is removed only when both conditions hold:
    - The work directory path does not exist on disk.
    - The corresponding sessions bucket directory is absent or empty.

    This prevents data loss for projects that have been moved or temporarily
    unmounted while sessions still exist.

    Returns the number of entries pruned.
    """
    from pythinker_code.metadata import Metadata, WorkDirMeta, mutate_metadata
    from pythinker_code.share import get_share_dir

    root = share_dir or get_share_dir()
    sessions_root = root / _SESSIONS_DIR_NAME

    def _prune(metadata: Metadata) -> int:
        keep: list[WorkDirMeta] = []
        pruned = 0
        for wd in metadata.work_dirs:
            if Path(wd.path).exists():
                keep.append(wd)
                continue
            try:
                hash_ = _md5(wd.path.encode("utf-8"), usedforsecurity=False).hexdigest()
                bucket_name = hash_ if wd.host == _LOCAL_HOST else f"{wd.host}_{hash_}"
                bucket_dir = sessions_root / bucket_name
                has_sessions = bucket_dir.is_dir() and any(bucket_dir.iterdir())
            except Exception:
                has_sessions = True  # err on the side of keeping
            if has_sessions:
                keep.append(wd)
            else:
                pruned += 1
        if pruned:
            metadata.work_dirs = keep
        return pruned

    try:
        pruned = mutate_metadata(_prune)
    except Exception:
        logger.debug("session_cleanup: failed to prune work_dir registry")
        return 0
    if pruned:
        logger.debug("session_cleanup: pruned {n} stale work_dir(s) from registry", n=pruned)

    return pruned


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _maybe_remove_session(
    session_dir: Path, cutoff: float, *, work_dir_path: str | None = None
) -> bool:
    """Return True if the session directory was removed, False otherwise."""
    from pythinker_code.session_state import load_session_state

    state_file = session_dir / "state.json"

    if not state_file.exists():
        # Orphan dir with no state — safe to remove if old enough.
        try:
            if session_dir.stat().st_mtime < cutoff:
                shutil.rmtree(session_dir, ignore_errors=True)
                return True
        except OSError:
            pass
        return False

    state = load_session_state(session_dir)

    if not state.archived:
        return False

    try:
        reference: float = state.archived_at or state.wire_mtime or session_dir.stat().st_mtime
    except OSError:
        return False

    if reference >= cutoff:
        return False

    shutil.rmtree(session_dir, ignore_errors=True)
    if work_dir_path is not None:
        _try_remove_scratchpad(work_dir_path, session_dir.name)
    return True


def _try_remove_scratchpad(work_dir_path: str, session_uuid: str) -> None:
    """Best-effort: delete the per-session scratchpad file for a removed session."""
    scratch_dir = Path(work_dir_path) / ".pythinker" / "scratch"
    if not scratch_dir.is_dir():
        return
    short_id = _session_short_id(session_uuid)
    for f in scratch_dir.glob(f"{short_id}-*.md"):
        with contextlib.suppress(OSError):
            f.unlink(missing_ok=True)


def _session_short_id(session_uuid: str) -> str:
    """Compute the 12-char slug used as the scratchpad filename prefix."""
    text = "".join(c if c.isalnum() else "-" for c in session_uuid.lower())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")[:12].strip("-") or "session"


def _load_bucket_path_map(share_dir: Path) -> dict[str, str]:
    """Return a mapping of sessions bucket directory name → work_dir path string."""
    from pythinker_code.metadata import load_metadata

    try:
        metadata = load_metadata()
    except Exception:
        return {}

    result: dict[str, str] = {}
    for wd in metadata.work_dirs:
        try:
            hash_ = _md5(wd.path.encode("utf-8"), usedforsecurity=False).hexdigest()
            bucket = hash_ if wd.host == _LOCAL_HOST else f"{wd.host}_{hash_}"
            result[bucket] = wd.path
        except Exception:
            pass
    return result
