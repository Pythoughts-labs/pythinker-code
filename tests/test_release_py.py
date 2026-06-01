from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEP_CHECK = REPO_ROOT / "scripts" / "check_pythinker_dependency_versions.py"


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def _run_dep_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(DEP_CHECK), *args],
        capture_output=True,
        text=True,
    )


def test_dep_check_passes_when_review_pin_matches(tmp_path: Path) -> None:
    root = _write(
        tmp_path,
        "root.toml",
        '[project]\nname="pythinker-code"\nversion="0.27.0"\n'
        'dependencies=["pythinker-core[contrib]==1.1.1","pythinker-host==1.0.0",'
        '"pythinker-review==0.1.0"]\n',
    )
    core = _write(tmp_path, "core.toml", '[project]\nname="pythinker-core"\nversion="1.1.1"\n')
    host = _write(tmp_path, "host.toml", '[project]\nname="pythinker-host"\nversion="1.0.0"\n')
    review = _write(tmp_path, "review.toml", '[project]\nname="pythinker-review"\nversion="0.1.0"\n')
    result = _run_dep_check(
        "--root-pyproject", str(root),
        "--pythinker-core-pyproject", str(core),
        "--pythinker-host-pyproject", str(host),
        "--pythinker-review-pyproject", str(review),
    )
    assert result.returncode == 0, result.stderr


def test_dep_check_fails_when_review_pin_drifts(tmp_path: Path) -> None:
    root = _write(
        tmp_path,
        "root.toml",
        '[project]\nname="pythinker-code"\nversion="0.27.0"\n'
        'dependencies=["pythinker-core[contrib]==1.1.1","pythinker-host==1.0.0",'
        '"pythinker-review==0.1.0"]\n',
    )
    core = _write(tmp_path, "core.toml", '[project]\nname="pythinker-core"\nversion="1.1.1"\n')
    host = _write(tmp_path, "host.toml", '[project]\nname="pythinker-host"\nversion="1.0.0"\n')
    review = _write(tmp_path, "review.toml", '[project]\nname="pythinker-review"\nversion="0.2.0"\n')
    result = _run_dep_check(
        "--root-pyproject", str(root),
        "--pythinker-core-pyproject", str(core),
        "--pythinker-host-pyproject", str(host),
        "--pythinker-review-pyproject", str(review),
    )
    assert result.returncode == 1
    assert "pythinker-review version mismatch" in result.stderr
