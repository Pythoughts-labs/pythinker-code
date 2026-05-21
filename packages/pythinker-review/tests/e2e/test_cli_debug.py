import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.debug import app


def test_debug_failure_uses_log_input(
    tmp_git_repo: Callable[..., Path], monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_git_repo()
    subprocess.run(["git", "checkout", "-b", "feature", "-q"], cwd=repo, check=True)
    (repo / "x.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "change", "-q"], cwd=repo, check=True)
    log = tmp_path / "failure.log"
    log.write_text("AssertionError at x.py:2", encoding="utf-8")
    monkeypatch.setenv("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES", '{"findings": []}')
    result = CliRunner().invoke(
        app, ["failure", str(log), "--repo", str(repo), "--base", "main", "--format", "json"]
    )
    assert result.exit_code == 0, result.stdout
    assert "findings" in json.loads(result.stdout)
