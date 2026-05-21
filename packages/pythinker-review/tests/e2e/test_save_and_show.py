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
    run_id = list_res.stdout.split()[0]
    show_res = runner.invoke(app, ["show", run_id, "--repo", str(repo), "--format", "json"])
    assert show_res.exit_code == 0
