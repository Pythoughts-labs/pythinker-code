import subprocess

import pytest


@pytest.mark.parametrize("cmd", ["review", "secscan", "debug"])
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


def test_debug_failure_help_works() -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "debug", "failure", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--command" in proc.stdout
