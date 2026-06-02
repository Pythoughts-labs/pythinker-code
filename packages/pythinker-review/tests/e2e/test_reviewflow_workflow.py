import json
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.review import app
from pythinker_review.reviewflow.state import read_runs, state_paths


def test_stateful_reviewflow_init_map_review_report_triage_and_fix_dry_run(
    tmp_git_repo: Callable[..., Path], monkeypatch
) -> None:
    repo = tmp_git_repo()
    (repo / "x.py").write_text("bug = True\n", encoding="utf-8")

    runner = CliRunner()
    init_res = runner.invoke(app, ["init", "--repo", str(repo), "--json"])
    assert init_res.exit_code == 0, init_res.stdout
    assert (repo / ".pythinker-review-flow" / "project.json").exists()

    map_res = runner.invoke(app, ["map", "--repo", str(repo), "--json"])
    assert map_res.exit_code == 0, map_res.stdout
    assert json.loads(map_res.stdout)["features"] >= 1

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
                        "reasoning": "The mapped feature hard-codes the flag on.",
                        "reproduction": "Import x and inspect bug.",
                        "recommendation": "Configure the flag instead of hard-coding it.",
                        "whyTestsDoNotAlreadyCoverThis": "No tests exist for x.py.",
                        "suggestedRegressionTest": "Assert the flag follows configuration.",
                        "minimumFixScope": "x.py only",
                    }
                ]
            }
        ),
    )
    review_res = runner.invoke(app, ["review", "--repo", str(repo), "--limit", "1", "--json"])
    assert review_res.exit_code == 0, review_res.stdout
    assert json.loads(review_res.stdout)["findings"] == 1

    report_res = runner.invoke(app, ["report", "--repo", str(repo), "--json"])
    assert report_res.exit_code == 0, report_res.stdout
    report = json.loads(report_res.stdout)
    finding_id = report["items"][0]["findingId"]

    next_res = runner.invoke(app, ["next", "--repo", str(repo), "--json"])
    assert next_res.exit_code == 0, next_res.stdout
    assert json.loads(next_res.stdout)["finding"]["findingId"] == finding_id

    triage_res = runner.invoke(
        app,
        [
            "triage",
            "--repo",
            str(repo),
            "--finding",
            finding_id,
            "--status",
            "false-positive",
            "--json",
        ],
    )
    assert triage_res.exit_code == 0, triage_res.stdout
    assert json.loads(triage_res.stdout)["status"] == "false-positive"

    fix_res = runner.invoke(
        app, ["fix", "--repo", str(repo), "--finding", finding_id, "--dry-run", "--json"]
    )
    assert fix_res.exit_code == 0, fix_res.stdout
    assert json.loads(fix_res.stdout)["dryRun"] is True


def test_stateful_review_partitions_invalid_findings_without_failing_run(
    tmp_git_repo: Callable[..., Path], monkeypatch
) -> None:
    repo = tmp_git_repo()
    (repo / "x.py").write_text("bug = True\n", encoding="utf-8")

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
                        "recommendation": "Configure the flag.",
                    },
                    {
                        "title": "Invented evidence path",
                        "category": "bug",
                        "severity": "medium",
                        "confidence": "high",
                        "evidence": [
                            {
                                "path": "missing.py",
                                "startLine": 1,
                                "endLine": 1,
                                "symbol": None,
                                "quote": "missing",
                            }
                        ],
                        "reasoning": "This should be dropped, not fail the feature.",
                        "reproduction": None,
                        "recommendation": "No-op.",
                    },
                ]
            }
        ),
    )

    review_res = runner.invoke(app, ["review", "--repo", str(repo), "--limit", "1", "--json"])

    assert review_res.exit_code == 0, review_res.stdout
    assert json.loads(review_res.stdout)["findings"] == 1
    runs = read_runs(state_paths(repo / ".pythinker-review-flow"))
    assert runs[-1].status == "completed"
    assert any(error.code == "validation-drop" for error in runs[-1].errors)
