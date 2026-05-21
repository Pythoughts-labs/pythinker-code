import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.review import app


def _setup_branch(repo: Path) -> None:
    subprocess.run(["git", "checkout", "-b", "feature", "-q"], cwd=repo, check=True)
    (repo / "app.py").write_text("def f():\n    return 'AKIAIOSFODNN7EXAMPLE'\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "add secret", "-q"], cwd=repo, check=True)


def test_review_diff_returns_finding_and_exits_one(
    tmp_git_repo: Callable[..., Path], monkeypatch
) -> None:
    repo = tmp_git_repo()
    _setup_branch(repo)
    payload = json.dumps(
        {
            "findings": [
                {
                    "rule_id": "review.return_constant",
                    "title": "Function returns a constant",
                    "rationale": "...",
                    "category": "correctness",
                    "severity": "high",
                    "file": "app.py",
                    "start_line": 2,
                    "end_line": 2,
                    "confidence": 0.9,
                }
            ]
        }
    )
    monkeypatch.setenv("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES", payload)
    result = CliRunner().invoke(
        app,
        [
            "diff",
            "--base",
            "main",
            "--format",
            "json",
            "--no-save",
            "--repo",
            str(repo),
            "--fail-on",
            "high",
        ],
    )
    assert result.exit_code == 1, result.stdout
    assert json.loads(result.stdout)["findings"][0]["rule_id"] == "review.return_constant"
