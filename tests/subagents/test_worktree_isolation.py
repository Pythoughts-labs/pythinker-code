"""Worktree isolation lifecycle (P2 of tasks/worktree-isolation-design.md)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pythinker_code.soul.permission import subagent_type_allows_file_mutation
from pythinker_code.subagents.worktree import (
    WorktreeError,
    cleanup_agent_worktree,
    create_agent_worktree,
    worktree_change_summary,
)


async def _git(cwd: Path, *args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()


async def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    await _git(repo, "init", "-b", "main")
    await _git(repo, "config", "user.email", "t@t")
    await _git(repo, "config", "user.name", "T")
    (repo / "a.txt").write_text("a")
    await _git(repo, "add", ".")
    await _git(repo, "commit", "-m", "base")
    return repo


class TestWorktreeLifecycle:
    @pytest.mark.asyncio
    async def test_clean_roundtrip_removes_worktree(self, tmp_path: Path) -> None:
        repo = await _repo(tmp_path)
        worktree = tmp_path / "session" / "worktrees" / "a1"

        await create_agent_worktree(repo, worktree)
        assert (worktree / "a.txt").read_text() == "a"

        assert await worktree_change_summary(worktree) == ""
        disposition = await cleanup_agent_worktree(repo, worktree, has_changes=False)

        assert disposition == "removed"
        assert not worktree.exists()

    @pytest.mark.asyncio
    async def test_changes_are_summarized_and_retained(self, tmp_path: Path) -> None:
        repo = await _repo(tmp_path)
        worktree = tmp_path / "wt"
        await create_agent_worktree(repo, worktree)
        (worktree / "a.txt").write_text("modified")
        (worktree / "new.txt").write_text("untracked")

        summary = await worktree_change_summary(worktree)
        disposition = await cleanup_agent_worktree(repo, worktree, has_changes=bool(summary))

        assert "a.txt" in summary
        assert "1 untracked" in summary
        assert disposition == "retained"
        assert worktree.exists()

    @pytest.mark.asyncio
    async def test_resume_reuses_existing_worktree(self, tmp_path: Path) -> None:
        repo = await _repo(tmp_path)
        worktree = tmp_path / "wt"
        await create_agent_worktree(repo, worktree)
        (worktree / "keep.txt").write_text("work in progress")

        await create_agent_worktree(repo, worktree)  # second launch (resume)

        assert (worktree / "keep.txt").read_text() == "work in progress"

    @pytest.mark.asyncio
    async def test_non_git_root_is_actionable_error(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()

        with pytest.raises(WorktreeError, match="git repository"):
            await create_agent_worktree(plain, tmp_path / "wt")


class TestWriteProfileGate:
    def test_write_types_qualify(self) -> None:
        assert subagent_type_allows_file_mutation("coder") is True
        assert subagent_type_allows_file_mutation("implementer") is True

    def test_read_types_do_not(self) -> None:
        for read_type in ("explore", "review", "verifier", "judge", "unknown-type"):
            assert subagent_type_allows_file_mutation(read_type) is False


class TestCommittedChangesRetention:
    @pytest.mark.asyncio
    async def test_committed_clean_worktree_is_retained(self, tmp_path: Path) -> None:
        """A child that commits its work leaves a CLEAN tree; removing the
        worktree would orphan those commits as dangling objects."""
        repo = await _repo(tmp_path)
        worktree = tmp_path / "wt"
        await create_agent_worktree(repo, worktree)
        (worktree / "a.txt").write_text("committed work")
        await _git(worktree, "add", ".")
        await _git(worktree, "config", "user.email", "t@t")
        await _git(worktree, "config", "user.name", "T")
        await _git(worktree, "commit", "-m", "child work")

        summary = await worktree_change_summary(worktree)
        disposition = await cleanup_agent_worktree(repo, worktree, has_changes=bool(summary))

        assert "commit(s) ahead" in summary
        assert disposition == "retained"
        assert worktree.exists()

    @pytest.mark.asyncio
    async def test_missing_base_sidecar_fails_closed_to_retention(self, tmp_path: Path) -> None:
        repo = await _repo(tmp_path)
        worktree = tmp_path / "wt"
        await create_agent_worktree(repo, worktree)
        (worktree.parent / f"{worktree.name}.base-sha").unlink()

        summary = await worktree_change_summary(worktree)

        assert "commit(s) ahead" in summary  # unknown provenance counts as changes
