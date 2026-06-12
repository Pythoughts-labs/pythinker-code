"""Git worktree lifecycle for isolated write-capable child agents.

Local subprocesses are used directly (not the host abstraction):
BackgroundTaskManager.create_agent_task enforces a local backend before
any background agent launches, and worktrees are meaningless across a
remote boundary.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pythinker_code.utils.logging import logger

_GIT_TIMEOUT_S = 30.0


class WorktreeError(Exception):
    """Worktree lifecycle failure with a user-actionable message."""


async def _git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(cwd),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=_GIT_TIMEOUT_S)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise WorktreeError(f"git {' '.join(args)} timed out after {_GIT_TIMEOUT_S:g}s") from None
    return (
        process.returncode or 0,
        stdout.decode("utf-8", errors="replace").strip(),
        stderr.decode("utf-8", errors="replace").strip(),
    )


async def create_agent_worktree(repo_dir: Path, dest: Path) -> None:
    """Create a detached worktree of HEAD at *dest* for one child agent.

    Raises WorktreeError with an actionable message when *repo_dir* is not
    a git repository or the worktree cannot be created.
    """
    code, _, _ = await _git(["rev-parse", "--is-inside-work-tree"], repo_dir)
    if code != 0:
        raise WorktreeError(
            f"isolation='worktree' requires a git repository at {repo_dir}; "
            "launch without isolation, or run `git init` first"
        )
    if dest.exists():
        # Resume of an isolated agent reuses its existing worktree.
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    code, _, stderr = await _git(["worktree", "add", "--detach", str(dest), "HEAD"], repo_dir)
    if code != 0:
        first_line = stderr.splitlines()[0] if stderr else "unknown git error"
        raise WorktreeError(f"could not create isolation worktree at {dest}: {first_line}")


async def worktree_change_summary(worktree: Path) -> str:
    """Short human summary of changes in *worktree*; empty string when clean."""
    code, status, _ = await _git(["status", "--porcelain"], worktree)
    if code != 0 or not status:
        return ""
    _, diff_stat, _ = await _git(["diff", "--stat", "HEAD"], worktree)
    untracked = sum(1 for line in status.splitlines() if line.startswith("??"))
    parts = [part for part in (diff_stat, f"{untracked} untracked file(s)" if untracked else "")]
    return "\n".join(part for part in parts if part)


async def cleanup_agent_worktree(repo_dir: Path, worktree: Path, *, has_changes: bool) -> str:
    """Remove a clean worktree; retain one that carries changes.

    Returns the disposition ("removed" or "retained") for the final report.
    Removal failures degrade to retention — losing work is the only
    unacceptable outcome here.
    """
    if has_changes:
        return "retained"
    code, _, stderr = await _git(["worktree", "remove", str(worktree)], repo_dir)
    if code != 0:
        logger.warning(
            "Could not remove clean isolation worktree {wt}: {err}", wt=worktree, err=stderr
        )
        return "retained"
    return "removed"
