"""Safe path helpers for the Python-native Pythinker Security Scan data mirror."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

DEFAULT_STATE_DIR = ".pythinker-review/security-scan"


def get_state_dir(state_dir: str | Path | None = None) -> Path:
    if state_dir is not None:
        return Path(state_dir)
    env = os.environ.get("PYTHINKER_SECURITY_SCAN_STATE_DIR")
    if env:
        return Path(env)
    return Path(DEFAULT_STATE_DIR)


def get_data_root(state_dir: str | Path | None = None) -> Path:
    env = os.environ.get("PYTHINKER_SECURITY_SCAN_DATA_ROOT")
    if env:
        return Path(env)
    return get_state_dir(state_dir) / "data"


def assert_safe_segment(name: str, label: str = "segment") -> None:
    if not isinstance(name, str) or not name:
        raise ValueError(f"Invalid {label}: must be a non-empty string")
    if name in {".", ".."}:
        raise ValueError(f"Invalid {label}: {name!r}")
    if "\0" in name:
        raise ValueError(f"Invalid {label}: contains null byte")
    if "/" in name or "\\" in name:
        raise ValueError(f"Invalid {label}: contains path separator")
    if Path(name).is_absolute():
        raise ValueError(f"Invalid {label}: must not be absolute")


def assert_safe_file_path(file_path: str) -> None:
    if not isinstance(file_path, str) or not file_path:
        raise ValueError("Invalid filePath: must be a non-empty string")
    if "\0" in file_path:
        raise ValueError("Invalid filePath: contains null byte")
    if "\\" in file_path:
        raise ValueError("Invalid filePath: contains backslash")
    if Path(file_path).is_absolute():
        raise ValueError("Invalid filePath: must not be absolute")
    for part in PurePosixPath(file_path).parts:
        if part in {"", ".", ".."}:
            raise ValueError(f"Invalid filePath: contains {part!r} segment")


def normalize_relpath(path: str | Path, *, root: Path | None = None) -> str | None:
    raw = str(path).replace("\\", "/")
    if raw.startswith("./"):
        raw = raw[2:]
    candidate = Path(raw)
    if candidate.is_absolute():
        if root is None:
            return None
        try:
            raw = candidate.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return None
    if raw == "." or raw.startswith("../") or raw == "..":
        return None
    try:
        assert_safe_file_path(raw)
    except ValueError:
        return None
    return raw


def data_dir(project_id: str, *, data_root: Path) -> Path:
    assert_safe_segment(project_id, "projectId")
    return data_root / project_id


def project_config_path(project_id: str, *, data_root: Path) -> Path:
    return data_dir(project_id, data_root=data_root) / "project.json"


def files_dir(project_id: str, *, data_root: Path) -> Path:
    return data_dir(project_id, data_root=data_root) / "files"


def file_record_path(project_id: str, file_path: str, *, data_root: Path) -> Path:
    assert_safe_file_path(file_path)
    return files_dir(project_id, data_root=data_root) / f"{file_path}.json"


def runs_dir(project_id: str, *, data_root: Path) -> Path:
    return data_dir(project_id, data_root=data_root) / "runs"


def run_meta_path(project_id: str, run_id: str, *, data_root: Path) -> Path:
    assert_safe_segment(run_id, "runId")
    return runs_dir(project_id, data_root=data_root) / f"{run_id}.json"


def reports_dir(project_id: str, *, data_root: Path) -> Path:
    return data_dir(project_id, data_root=data_root) / "reports"
