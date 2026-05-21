from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pythinker_review.engine.diff_source import (
    DiffMode,
    EmptyDiffError,
    PreflightError,
    ResolvedDiff,
    resolve_diff,
)


def _write_branch_with_change(
    repo: Path, git_run: Callable[..., str], branch: str = "feature"
) -> None:
    git_run(repo, "checkout", "-b", branch, "-q")
    (repo / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    git_run(repo, "add", ".")
    git_run(repo, "commit", "-m", "add f", "-q")


def test_base_mode_diffs_branch_vs_merge_base(
    tmp_git_repo: Callable[..., Path], git_run: Callable[..., str]
) -> None:
    repo = tmp_git_repo()
    _write_branch_with_change(repo, git_run)
    res = resolve_diff(repo, mode=DiffMode.base, base_ref="main")
    assert isinstance(res, ResolvedDiff)
    assert res.source_label == "git-diff:main"
    assert "app.py" in res.changed_files
    assert "diff --git" in res.patch_text
    assert res.head_sha and res.base_sha and res.head_sha != res.base_sha


def test_base_mode_falls_back_main_then_master(
    tmp_git_repo: Callable[..., Path], git_run: Callable[..., str]
) -> None:
    repo = tmp_git_repo()
    _write_branch_with_change(repo, git_run)
    res = resolve_diff(repo, mode=DiffMode.base, base_ref="origin/main")
    assert res.source_label.startswith("git-diff:")
    assert "app.py" in res.changed_files


def test_staged_mode(tmp_git_repo: Callable[..., Path], git_run: Callable[..., str]) -> None:
    repo = tmp_git_repo()
    (repo / "a.py").write_text("x=1\n", encoding="utf-8")
    git_run(repo, "add", "a.py")
    res = resolve_diff(repo, mode=DiffMode.staged)
    assert res.source_label == "staged"
    assert "a.py" in res.changed_files


def test_working_tree_mode_includes_untracked(tmp_git_repo: Callable[..., Path]) -> None:
    repo = tmp_git_repo()
    (repo / "untracked.py").write_text("y=2\n", encoding="utf-8")
    res = resolve_diff(repo, mode=DiffMode.working_tree)
    assert res.source_label == "working-tree"
    assert "untracked.py" in res.changed_files


def test_range_mode(tmp_git_repo: Callable[..., Path], git_run: Callable[..., str]) -> None:
    repo = tmp_git_repo()
    _write_branch_with_change(repo, git_run, branch="b1")
    head = git_run(repo, "rev-parse", "HEAD").strip()
    base = git_run(repo, "rev-parse", "main").strip()
    res = resolve_diff(repo, mode=DiffMode.range, rev_range=f"{base}..{head}")
    assert res.source_label == f"git-range:{base}..{head}"


def test_empty_diff_raises_empty(tmp_git_repo: Callable[..., Path]) -> None:
    with pytest.raises(EmptyDiffError):
        resolve_diff(tmp_git_repo(), mode=DiffMode.working_tree)


def test_unknown_base_ref_raises_preflight(
    tmp_git_repo: Callable[..., Path], git_run: Callable[..., str]
) -> None:
    repo = tmp_git_repo()
    _write_branch_with_change(repo, git_run)
    with pytest.raises(PreflightError):
        resolve_diff(repo, mode=DiffMode.base, base_ref="does-not-exist", fallback_refs=())


def test_not_a_git_repo_raises_preflight(tmp_path: Path) -> None:
    with pytest.raises(PreflightError):
        resolve_diff(tmp_path, mode=DiffMode.base, base_ref="main")
