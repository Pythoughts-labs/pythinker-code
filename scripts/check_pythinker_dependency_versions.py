from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


def load_project_table(pyproject_path: Path) -> dict:
    with pyproject_path.open("rb") as handle:
        data = tomllib.load(handle)

    project = data.get("project")
    if not isinstance(project, dict):
        raise ValueError(f"Missing [project] table in {pyproject_path}")

    return project


def load_project_version(pyproject_path: Path) -> str:
    project = load_project_table(pyproject_path)
    version = project.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"Missing project.version in {pyproject_path}")
    return version


def find_pinned_dependency(deps: list[str], name: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(name)}(?:\[[^\]]+\])?(.+)$")
    for dep in deps:
        match = pattern.match(dep)
        if not match:
            continue
        spec = match.group(1)
        pinned = re.match(r"^==(.+)$", spec)
        if pinned:
            return pinned.group(1)
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate pythinker-code dependency versions.")
    parser.add_argument("--root-pyproject", type=Path, required=True)
    parser.add_argument("--pythinker-core-pyproject", type=Path, required=True)
    parser.add_argument("--pythinker-host-pyproject", type=Path, required=True)
    parser.add_argument("--pythinker-review-pyproject", type=Path, required=True)
    parser.add_argument("--pythinker-sdk-pyproject", type=Path, required=True)
    args = parser.parse_args()

    try:
        root_project = load_project_table(args.root_pyproject)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    deps = root_project.get("dependencies", [])
    if not isinstance(deps, list):
        print(
            f"error: project.dependencies must be a list in {args.root_pyproject}",
            file=sys.stderr,
        )
        return 1

    errors: list[str] = []
    package_versions: dict[str, str] = {}
    for name, pyproject_path in (
        ("pythinker-core", args.pythinker_core_pyproject),
        ("pythinker-host", args.pythinker_host_pyproject),
        ("pythinker-review", args.pythinker_review_pyproject),
    ):
        try:
            package_version = load_project_version(pyproject_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        package_versions[name] = package_version

        pinned_version = find_pinned_dependency(deps, name)
        if pinned_version is None:
            errors.append(f"Missing pinned dependency for {name} in {args.root_pyproject}.")
            continue

        if pinned_version != package_version:
            errors.append(
                f"{name} version mismatch: root depends on {pinned_version}, "
                f"but {pyproject_path} has {package_version}."
            )

    try:
        sdk_project = load_project_table(args.pythinker_sdk_pyproject)
    except ValueError as exc:
        errors.append(str(exc))
    else:
        sdk_deps = sdk_project.get("dependencies", [])
        if not isinstance(sdk_deps, list):
            errors.append(f"project.dependencies must be a list in {args.pythinker_sdk_pyproject}")
        elif core_version := package_versions.get("pythinker-core"):
            sdk_core_pin = find_pinned_dependency(sdk_deps, "pythinker-core")
            if sdk_core_pin is None:
                errors.append(
                    "Missing pinned dependency for pythinker-core in "
                    f"{args.pythinker_sdk_pyproject}."
                )
            elif sdk_core_pin != core_version:
                errors.append(
                    f"pythinker-sdk core dependency mismatch: sdk depends on {sdk_core_pin}, "
                    f"but {args.pythinker_core_pyproject} has {core_version}."
                )

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    print("ok: pythinker-code dependencies match workspace package versions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
