import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.secscan import app


def test_secscan_finds_secret(tmp_git_repo: Callable[..., Path], monkeypatch) -> None:
    repo = tmp_git_repo()
    subprocess.run(["git", "checkout", "-b", "feature", "-q"], cwd=repo, check=True)
    (repo / "config.py").write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "leak key", "-q"], cwd=repo, check=True)
    payload = json.dumps(
        {
            "findings": [
                {
                    "rule_id": "sec.signal.secret.aws_access_key",
                    "title": "AWS access key committed to source",
                    "rationale": "...",
                    "category": "secret",
                    "severity": "critical",
                    "file": "config.py",
                    "start_line": 1,
                    "end_line": 1,
                    "confidence": 0.95,
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
            "sarif",
            "--no-save",
            "--repo",
            str(repo),
            "--fail-on",
            "critical",
        ],
    )
    assert result.exit_code == 1, result.stdout
    assert json.loads(result.stdout)["runs"][0]["results"][0]["level"] == "error"
