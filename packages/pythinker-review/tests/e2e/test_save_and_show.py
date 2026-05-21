import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.review import app


def test_save_then_list_then_show(tmp_git_repo: Callable[..., Path], monkeypatch) -> None:
    repo = tmp_git_repo()
    subprocess.run(["git", "checkout", "-b", "feature", "-q"], cwd=repo, check=True)
    (repo / "x.py").write_text("y = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "x", "-q"], cwd=repo, check=True)
    monkeypatch.setenv("PYTHINKER_REVIEW_FAKE_LLM_RESPONSES", '{"findings": []}')
    runner = CliRunner()
    res = runner.invoke(
        app,
        ["diff", "--base", "main", "--format", "json", "--repo", str(repo), "--fail-on", "none"],
    )
    assert res.exit_code == 0, res.stdout
    assert (repo / ".pythinker-review" / "index.json").exists()
    list_res = runner.invoke(app, ["list", "--repo", str(repo)])
    assert list_res.exit_code == 0
    parts = list_res.stdout.split()
    assert parts, "Expected at least one run id in list output"
    run_id = parts[0]
    show_res = runner.invoke(app, ["show", run_id, "--repo", str(repo), "--format", "json"])
    assert show_res.exit_code == 0


def test_saved_findings_support_next_and_show_finding(
    tmp_git_repo: Callable[..., Path], monkeypatch
) -> None:
    repo = tmp_git_repo()
    subprocess.run(["git", "checkout", "-b", "feature", "-q"], cwd=repo, check=True)
    (repo / "x.py").write_text("y = user_input\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "x", "-q"], cwd=repo, check=True)
    monkeypatch.setenv(
        "PYTHINKER_REVIEW_FAKE_LLM_RESPONSES",
        json.dumps(
            {
                "findings": [
                    {
                        "rule_id": "review.user_input",
                        "title": "Unvalidated user input",
                        "rationale": "The new assignment stores user input directly.",
                        "category": "correctness",
                        "severity": "high",
                        "file": "x.py",
                        "start_line": 1,
                        "end_line": 1,
                        "confidence": 0.9,
                        "evidence_snippet": "user_input",
                        "minimum_fix_scope": "Validate x.py assignment only.",
                    }
                ]
            }
        ),
    )
    runner = CliRunner()
    res = runner.invoke(
        app,
        ["diff", "--base", "main", "--format", "json", "--repo", str(repo), "--fail-on", "none"],
    )
    assert res.exit_code == 0, res.stdout
    parsed = json.loads(res.stdout)
    assert "findings" in parsed and parsed["findings"], "Expected non-empty findings list"
    finding_id = parsed["findings"][0]["id"]
    next_res = runner.invoke(app, ["next", "--repo", str(repo)])
    assert next_res.exit_code == 0
    assert finding_id in next_res.stdout
    show_res = runner.invoke(
        app, ["show-finding", finding_id, "--repo", str(repo), "--format", "json"]
    )
    assert show_res.exit_code == 0
    assert json.loads(show_res.stdout)["findings"][0]["id"] == finding_id
