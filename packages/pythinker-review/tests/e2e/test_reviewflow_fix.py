import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.review import app
from pythinker_review.reviewflow.models import PatchAttempt
from pythinker_review.reviewflow.state import (
    read_finding,
    read_patch_attempts,
    state_paths,
    write_patch_attempt,
)
from pythinker_review.reviewflow.utils import now_iso


def _prepare_reviewflow_finding(repo: Path, monkeypatch) -> str:
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
    return json.loads(runner.invoke(app, ["report", "--repo", str(repo), "--json"]).stdout)[
        "items"
    ][0]["findingId"]


def test_stateful_fix_applies_model_unified_diff(
    tmp_git_repo: Callable[..., Path], monkeypatch
) -> None:
    repo = tmp_git_repo()
    (repo / "x.py").write_text("bug = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "x.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "add x", "-q"], cwd=repo, check=True)

    runner = CliRunner()
    finding_id = _prepare_reviewflow_finding(repo, monkeypatch)

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


def test_stateful_fix_rejects_diff_outside_feature_scope(
    tmp_git_repo: Callable[..., Path], monkeypatch
) -> None:
    repo = tmp_git_repo()
    (repo / "x.py").write_text("bug = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "x.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "add x", "-q"], cwd=repo, check=True)
    runner = CliRunner()
    finding_id = _prepare_reviewflow_finding(repo, monkeypatch)

    monkeypatch.setenv(
        "PYTHINKER_REVIEW_FAKE_LLM_RESPONSES",
        json.dumps(
            {
                "summary": "Create unrelated file.",
                "unifiedDiff": "diff --git a/y.py b/y.py\nnew file mode 100644\n--- /dev/null\n+++ b/y.py\n@@ -0,0 +1 @@\n+owned = False\n",
                "commands": [],
            }
        ),
    )
    fix_res = runner.invoke(app, ["fix", "--repo", str(repo), "--finding", finding_id, "--json"])

    assert fix_res.exit_code == 2
    assert "outside the selected finding/feature scope" in fix_res.stderr
    assert not (repo / "y.py").exists()


def test_stateful_fix_records_failed_validation(
    tmp_git_repo: Callable[..., Path], monkeypatch
) -> None:
    repo = tmp_git_repo()
    (repo / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (repo / "x.py").write_text("bug = True\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_x.py").write_text(
        "def test_failure():\n    assert False\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "pyproject.toml", "x.py", "tests/test_x.py"], cwd=repo, check=True
    )
    subprocess.run(["git", "commit", "-m", "add failing validation", "-q"], cwd=repo, check=True)
    runner = CliRunner()
    finding_id = _prepare_reviewflow_finding(repo, monkeypatch)

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

    assert fix_res.exit_code == 2
    assert "validation failed after applying fix" in fix_res.stderr
    paths = state_paths(repo / ".pythinker-review-flow")
    patches = read_patch_attempts(paths)
    assert patches[-1].status == "failed"
    assert patches[-1].commands_run
    finding = read_finding(paths, finding_id)
    assert finding is not None
    assert finding.status == "open"


def test_open_pr_dry_run_quotes_commands_and_uses_path_separator(
    tmp_git_repo: Callable[..., Path],
) -> None:
    repo = tmp_git_repo()
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--repo", str(repo)]).exit_code == 0
    now = now_iso()
    paths = state_paths(repo / ".pythinker-review-flow")
    write_patch_attempt(
        paths,
        PatchAttempt(
            patch_attempt_id="pat_safe",
            finding_ids=["fnd_1"],
            feature_ids=["feat_1"],
            status="applied",
            plan="Safe title",
            files_changed=["x.py"],
            created_at=now,
            updated_at=now,
        ),
    )

    res = runner.invoke(
        app,
        ["open-pr", "--repo", str(repo), "--patch", "pat_safe", "--dry-run", "--json"],
    )

    assert res.exit_code == 0, res.stdout
    commands = json.loads(res.stdout)["commands"]
    assert "git add -- x.py" in commands
    assert any(command.startswith("gh pr create ") for command in commands)


def test_open_pr_dry_run_rejects_unsafe_branch(tmp_git_repo: Callable[..., Path]) -> None:
    repo = tmp_git_repo()
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--repo", str(repo)]).exit_code == 0
    now = now_iso()
    paths = state_paths(repo / ".pythinker-review-flow")
    write_patch_attempt(
        paths,
        PatchAttempt(
            patch_attempt_id="pat_safe",
            finding_ids=["fnd_1"],
            feature_ids=["feat_1"],
            status="applied",
            plan="Safe title",
            files_changed=["x.py"],
            created_at=now,
            updated_at=now,
        ),
    )

    res = runner.invoke(
        app,
        [
            "open-pr",
            "--repo",
            str(repo),
            "--patch",
            "pat_safe",
            "--branch",
            "bad branch;rm -rf tmp",
            "--dry-run",
            "--json",
        ],
    )

    assert res.exit_code == 2
    assert "unsafe git branch" in res.stderr


def test_open_pr_dry_run_rejects_unsafe_changed_path(tmp_git_repo: Callable[..., Path]) -> None:
    repo = tmp_git_repo()
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--repo", str(repo)]).exit_code == 0
    now = now_iso()
    paths = state_paths(repo / ".pythinker-review-flow")
    write_patch_attempt(
        paths,
        PatchAttempt(
            patch_attempt_id="pat_unsafe",
            finding_ids=["fnd_1"],
            feature_ids=["feat_1"],
            status="applied",
            plan="Safe title",
            files_changed=["../outside.py"],
            created_at=now,
            updated_at=now,
        ),
    )

    res = runner.invoke(
        app,
        ["open-pr", "--repo", str(repo), "--patch", "pat_unsafe", "--dry-run", "--json"],
    )

    assert res.exit_code == 2
    assert "unsafe filesChanged" in res.stderr
