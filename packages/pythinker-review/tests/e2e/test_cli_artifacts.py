import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from pythinker_review.cli.review import app


def _setup_branch(repo: Path) -> None:
    subprocess.run(["git", "checkout", "-b", "feature", "-q"], cwd=repo, check=True)
    (repo / "app.py").write_text("def greet(name):\n    return f'hi {name}'\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "add greet", "-q"], cwd=repo, check=True)


def test_describe_command_outputs_structured_description(
    tmp_git_repo: Callable[..., Path], monkeypatch
) -> None:
    repo = tmp_git_repo()
    _setup_branch(repo)
    monkeypatch.setenv(
        "PYTHINKER_REVIEW_FAKE_LLM_RESPONSES",
        json.dumps(
            {
                "type": ["Enhancement"],
                "title": "Add greeting helper",
                "description": "- Adds a greeting helper",
                "pr_files": [],
                "changes_diagram": None,
            }
        ),
    )
    result = CliRunner().invoke(
        app, ["describe", "--base", "main", "--format", "json", "--repo", str(repo)]
    )
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert parsed["kind"] == "describe"
    assert parsed["result"]["title"] == "Add greeting helper"


def test_improve_alias_outputs_code_suggestions(
    tmp_git_repo: Callable[..., Path], monkeypatch
) -> None:
    repo = tmp_git_repo()
    _setup_branch(repo)
    monkeypatch.setenv(
        "PYTHINKER_REVIEW_FAKE_LLM_RESPONSES",
        json.dumps(
            {
                "code_suggestions": [
                    {
                        "relevant_file": "app.py",
                        "language": "python",
                        "existing_code": "return f'hi {name}'",
                        "suggestion_content": "Handle empty names before formatting.",
                        "improved_code": "if not name:\n    return 'hi'\nreturn f'hi {name}'",
                        "one_sentence_summary": "Handle empty names",
                        "label": "possible bug",
                        "start_line": 2,
                        "end_line": 2,
                    }
                ]
            }
        ),
    )
    result = CliRunner().invoke(
        app, ["improve", "--base", "main", "--format", "json", "--repo", str(repo)]
    )
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert parsed["kind"] == "improve"
    assert parsed["result"]["code_suggestions"][0]["relevant_file"] == "app.py"


def test_ask_command_includes_question(tmp_git_repo: Callable[..., Path], monkeypatch) -> None:
    repo = tmp_git_repo()
    _setup_branch(repo)
    monkeypatch.setenv(
        "PYTHINKER_REVIEW_FAKE_LLM_RESPONSES",
        json.dumps(
            {
                "question": "what changed?",
                "answer": "The diff adds a greeting helper.",
                "confidence": 0.9,
                "referenced_files": ["app.py"],
                "limitations": None,
            }
        ),
    )
    result = CliRunner().invoke(
        app,
        ["ask", "what", "changed?", "--base", "main", "--format", "json", "--repo", str(repo)],
    )
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert parsed["kind"] == "ask"
    assert parsed["result"]["referenced_files"] == ["app.py"]


def test_compliance_command_outputs_checklist_result(
    tmp_git_repo: Callable[..., Path], monkeypatch
) -> None:
    repo = tmp_git_repo()
    _setup_branch(repo)
    monkeypatch.setenv(
        "PYTHINKER_REVIEW_FAKE_LLM_RESPONSES",
        json.dumps(
            {
                "overall_status": "pass",
                "ticket_summary": "Greeting helper is added.",
                "checks": [
                    {
                        "title": "Consistent Naming Conventions",
                        "status": "pass",
                        "rationale": "`greet` uses snake_case-compatible naming.",
                        "evidence_files": ["app.py"],
                        "missing_requirements": [],
                    }
                ],
                "risks": [],
            }
        ),
    )
    result = CliRunner().invoke(
        app,
        [
            "compliance",
            "--base",
            "main",
            "--format",
            "json",
            "--ticket-text",
            "Add a greeting helper.",
            "--repo",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert parsed["kind"] == "compliance"
    assert parsed["result"]["overall_status"] == "pass"
