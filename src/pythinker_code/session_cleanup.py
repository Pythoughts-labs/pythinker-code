"""Age-based cleanup for personal-scope session and plan state.

Runs at agent startup to keep ~/.pythinker/ from growing unboundedly.
Mirrors the design used by Claude Code (cleanupPeriodDays=30): on startup,
directories/files older than the retention threshold are removed if they are
safe to discard (archived sessions, old plan files).

Never raises — every error is logged at DEBUG level and silently skipped.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from pythinker_code.utils.logging import logger

_SESSIONS_DIR_NAME = "sessions"
_PLANS_DIR_NAME = "plans"


def sweep_old_sessions(max_age_days: int, *, share_dir: Path | None = None) -> int:
    """Remove archived session directories older than ``max_age_days`` days.

    Only sessions explicitly marked ``archived=True`` in their ``state.json`` are
    eligible. Active or unarchived sessions are never touched regardless of age.
    Orphan directories (no ``state.json``) are removed if their mtime is old enough.

    Returns the number of directories removed. Returns 0 when disabled (``max_age_days <= 0``).
    """
    if max_age_days <= 0:
        return 0

    from pythinker_code.share import get_share_dir

    sessions_root = (share_dir or get_share_dir()) / _SESSIONS_DIR_NAME
    if not sessions_root.is_dir():
        return 0

    cutoff = time.time() - max_age_days * 86_400.0
    removed = 0

    try:
        buckets = list(sessions_root.iterdir())
    except OSError:
        return 0

    for bucket in buckets:
        if not bucket.is_dir():
            continue
        try:
            session_dirs = list(bucket.iterdir())
        except OSError:
            continue
        for session_dir in session_dirs:
            if not session_dir.is_dir():
                continue
            try:
                removed += _maybe_remove_session(session_dir, cutoff)
            except Exception:
                logger.debug("session_cleanup: skipping {d}", d=session_dir.name)

        # Prune the bucket itself if it is now empty
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


def _maybe_remove_session(session_dir: Path, cutoff: float) -> int:
    """Return 1 if the session directory was removed, 0 otherwise."""
    from pythinker_code.session_state import load_session_state

    state_file = session_dir / "state.json"

    if not state_file.exists():
        # Orphan dir with no state — safe to remove if old enough.
        try:
            if session_dir.stat().st_mtime < cutoff:
                shutil.rmtree(session_dir, ignore_errors=True)
                return 1
        except OSError:
            pass
        return 0

    state = load_session_state(session_dir)

    if not state.archived:
        return 0

    # Use archived_at if recorded, fall back to wire_mtime, then directory mtime.
    try:
        reference: float = state.archived_at or state.wire_mtime or session_dir.stat().st_mtime
    except OSError:
        return 0

    if reference >= cutoff:
        return 0

    shutil.rmtree(session_dir, ignore_errors=True)
    return 1
