"""Git worktree lifecycle for isolated write-capable child agents.

Local subprocesses are used directly (not the host abstraction):
BackgroundTaskManager.create_agent_task enforces a local backend before
any background agent launches, and worktrees are meaningless across a
remote boundary.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path

from pythinker_code.utils.logging import logger

_GIT_TIMEOUT_S = 30.0
# Serialize worktree add/remove per repo: git's internal locking is reliable
# on current versions, but concurrent isolated agents should not depend on it.
_REPO_LOCKS: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def _base_sha_file(worktree: Path) -> Path:
    # Sidecar NEXT TO the worktree, never inside it — an untracked file inside
    # would make every clean worktree look dirty.
    return worktree.parent / f"{worktree.name}.base-sha"


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


async def _is_registered_worktree(repo_dir: Path, dest: Path) -> bool:
    code, stdout, stderr = await _git(["worktree", "list", "--porcelain"], repo_dir)
    if code != 0:
        # A git failure here is not evidence that dest is unregistered. Collapsing
        # it into "not a worktree" would let the caller delete a path that may
        # still hold the child's only work; surface the real error instead.
        first_line = stderr.splitlines()[0] if stderr else "unknown git error"
        raise WorktreeError(f"could not verify isolation worktree at {dest}: {first_line}")
    wanted = str(dest.resolve(strict=False))
    for line in stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        registered = Path(line.removeprefix("worktree ")).resolve(strict=False)
        if str(registered) == wanted:
            return True
    return False


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
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with _REPO_LOCKS[str(repo_dir)]:
        if dest.exists():
            # Resume of an isolated agent may reuse its existing worktree, but
            # only after verifying the path is still registered for this repo.
            if await _is_registered_worktree(repo_dir, dest):
                return
            raise WorktreeError(
                f"isolation worktree path exists but is not a registered worktree: {dest}"
            )
        code, _, stderr = await _git(["worktree", "add", "--detach", str(dest), "HEAD"], repo_dir)
        if code != 0:
            first_line = stderr.splitlines()[0] if stderr else "unknown git error"
            raise WorktreeError(f"could not create isolation worktree at {dest}: {first_line}")
    # Record the creation base so committed-but-clean child work is detected
    # later; commits ahead of this SHA must never be silently removed.
    code, base_sha, _ = await _git(["rev-parse", "HEAD"], dest)
    if code == 0 and base_sha:
        _base_sha_file(dest).write_text(base_sha + "\n", encoding="utf-8")


async def worktree_change_summary(worktree: Path) -> str:
    """Short human summary of changes in *worktree*; empty string when clean.

    "Changes" includes commits the child made on its detached HEAD: a child
    that commits its work leaves a clean working tree, and `worktree remove`
    would orphan those commits as dangling objects.
    """
    parts: list[str] = []
    commits_ahead = await _commits_ahead_of_base(worktree)
    if commits_ahead:
        parts.append(f"{commits_ahead} commit(s) ahead of the creation base")
    code, status, _ = await _git(["status", "--porcelain"], worktree)
    if code == 0 and status:
        _, diff_stat, _ = await _git(["diff", "--stat", "HEAD"], worktree)
        if diff_stat:
            parts.append(diff_stat)
        untracked = sum(1 for line in status.splitlines() if line.startswith("??"))
        if untracked:
            parts.append(f"{untracked} untracked file(s)")
    return "\n".join(parts)


async def _commits_ahead_of_base(worktree: Path) -> int:
    """Commits on the worktree's detached HEAD since creation.

    Missing or unreadable sidecar fails CLOSED (pretend one commit exists)
    when HEAD cannot be compared — losing work is the only unacceptable
    outcome, so unknown provenance means retain.
    """
    sidecar = _base_sha_file(worktree)
    try:
        base_sha = sidecar.read_text(encoding="utf-8").strip()
    except OSError:
        base_sha = ""
    if not base_sha:
        return 1  # unknown provenance — retain
    code, count, _ = await _git(["rev-list", "--count", f"{base_sha}..HEAD"], worktree)
    if code != 0:
        return 1
    return int(count or 0)


async def cleanup_agent_worktree(repo_dir: Path, worktree: Path, *, has_changes: bool) -> str:
    """Remove a clean worktree; retain one that carries changes.

    Returns the disposition ("removed" or "retained") for the final report.
    Removal failures degrade to retention — losing work is the only
    unacceptable outcome here.
    """
    if has_changes:
        return "retained"
    async with _REPO_LOCKS[str(repo_dir)]:
        code, _, stderr = await _git(["worktree", "remove", str(worktree)], repo_dir)
    if code != 0:
        logger.warning(
            "Could not remove clean isolation worktree {wt}: {err}", wt=worktree, err=stderr
        )
        return "retained"
    _base_sha_file(worktree).unlink(missing_ok=True)
    return "removed"
