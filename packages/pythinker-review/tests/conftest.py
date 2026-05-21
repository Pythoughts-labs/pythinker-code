from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


def _run(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Callable[..., Path]:
    def make(*, with_initial_commit: bool = True) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        _run(repo, "init", "--initial-branch=main", "-q")
        _run(repo, "config", "user.email", "test@example.com")
        _run(repo, "config", "user.name", "Test")
        _run(repo, "config", "commit.gpgsign", "false")
        if with_initial_commit:
            (repo / "README.md").write_text("hello\n", encoding="utf-8")
            _run(repo, "add", ".")
            _run(repo, "commit", "-m", "init", "-q")
        return repo

    return make


@pytest.fixture
def git_run() -> Callable[..., str]:
    return _run
