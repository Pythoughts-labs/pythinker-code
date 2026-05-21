import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.review import app


def test_stateful_fix_applies_model_unified_diff(
    tmp_git_repo: Callable[..., Path], monkeypatch
) -> None:
    repo = tmp_git_repo()
    (repo / "x.py").write_text("bug = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "x.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "add x", "-q"], cwd=repo, check=True)

    runner = CliRunner()
    assert runner.invoke(app, ["init", "--repo", str(repo)]).exit_code == 0
    assert runner.invoke(app, ["map", "--repo", str(repo)]).exit_code == 0

    monkeypatch.setenv(
        "PYTHINKER_REVIEW_FAKE_LLM_RESPONSES",
        json.dumps(
            {
                "findings": [
                    {
                        "title": "Boolean flag is always enabled",
                        "category": "bug",
                        "severity": "high",
                        "confidence": "high",
                        "evidence": [
                            {
                                "path": "x.py",
                                "startLine": 1,
                                "endLine": 1,
                                "symbol": None,
                                "quote": "bug = True",
                            }
                        ],
                        "reasoning": "The flag is hard-coded on.",
                        "reproduction": None,
                        "recommendation": "Set the flag to false for the test fixture.",
                    }
                ]
            }
        ),
    )
    review_res = runner.invoke(app, ["review", "--repo", str(repo), "--limit", "1", "--json"])
    assert review_res.exit_code == 0, review_res.stdout
    finding_id = json.loads(runner.invoke(app, ["report", "--repo", str(repo), "--json"]).stdout)[
        "items"
    ][0]["findingId"]

    monkeypatch.setenv(
        "PYTHINKER_REVIEW_FAKE_LLM_RESPONSES",
        json.dumps(
            {
                "summary": "Disable hard-coded flag.",
                "unifiedDiff": "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-bug = True\n+bug = False\n",
                "commands": [],
            }
        ),
    )
    fix_res = runner.invoke(app, ["fix", "--repo", str(repo), "--finding", finding_id, "--json"])

    assert fix_res.exit_code == 0, fix_res.stdout
    assert json.loads(fix_res.stdout)["status"] == "applied"
    assert (repo / "x.py").read_text(encoding="utf-8") == "bug = False\n"
