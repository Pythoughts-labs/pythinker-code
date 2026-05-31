import os
import subprocess


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    env["COLUMNS"] = "120"
    return env


def test_secscan_diff_help_works() -> None:
    proc = subprocess.run(
        ["uv", "run", "pythinker", "secscan", "diff", "--help"],
        check=True,
        capture_output=True,
        text=True,
        env=_cli_env(),
    )
    assert "--fail-on" in proc.stdout
