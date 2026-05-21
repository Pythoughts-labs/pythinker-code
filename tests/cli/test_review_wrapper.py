import subprocess

import pytest


@pytest.mark.parametrize("cmd", ["review", "secscan", "security-scan", "debug"])
def test_top_level_help_lists_command(cmd: str) -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "--help"], check=True, capture_output=True, text=True
    )
    assert cmd in proc.stdout


def test_review_diff_help_works() -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "review", "diff", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--with-security" in proc.stdout
    assert "--mode" in proc.stdout
    assert "--extra-instructio" in proc.stdout
    assert "--max-findings" in proc.stdout


@pytest.mark.parametrize(
    "command",
    [
        "describe",
        "suggest",
        "improve",
        "ask",
        "ask-line",
        "labels",
        "changelog",
        "docs",
    ],
)
def test_review_artifact_help_works(command: str) -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "review", command, "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--budget-chars" in proc.stdout
    assert "--timeout-s" in proc.stdout


@pytest.mark.parametrize(
    "command,expected",
    [
        ("tools", "code-reviewr"),
        ("config", "--format"),
        ("similar-issues", "--backend"),
    ],
)
def test_review_local_parity_help_works(command: str, expected: str) -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "review", command, "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert expected in proc.stdout


def test_review_help_docs_help_works() -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "review", "help-docs", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--docs-path" in proc.stdout
    assert "--root-readme" in proc.stdout


def test_review_compliance_help_works() -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "review", "compliance", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--checklist" in proc.stdout
    assert "--ticket-file" in proc.stdout


def test_security_scan_help_works() -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "security-scan", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "scan" in proc.stdout
    assert "process" in proc.stdout


def test_standalone_security_scan_help_works() -> None:
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--directory",
            "packages/pythinker-review",
            "pythinker-security-scan",
            "--help",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "scan" in proc.stdout
    assert "process" in proc.stdout


def test_debug_failure_help_works() -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "debug", "failure", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--command" in proc.stdout
