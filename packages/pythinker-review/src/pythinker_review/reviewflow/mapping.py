"""Heuristic project detection and feature mapping.

This is a compact Python port of Reviewflow's mapper concept: produce durable,
semantic-ish feature records from repository evidence without invoking a model.
It intentionally favors conservative grouping over exhaustive language-specific
AST parsing so the workflow remains pure Python and dependency-free.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import cast

from pythinker_review.reviewflow.models import (
    DetectedProject,
    FeatureEntrypoint,
    FeatureFileRef,
    FeatureRecord,
    FeatureTestRef,
    GitInfo,
    ProjectCommands,
    ProjectRecord,
    ReviewflowConfig,
)
from pythinker_review.reviewflow.utils import (
    discover_git,
    now_iso,
    path_matches,
    read_text_bounded,
    stable_id,
)

SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".cs",
    ".fs",
    ".vb",
    ".rb",
    ".ex",
    ".exs",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hpp",
    ".swift",
    ".php",
}
CONFIG_NAMES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "pnpm-workspace.yaml",
    "yarn.lock",
    "package-lock.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "mix.exs",
    "Makefile",
    "Dockerfile",
}
TEST_MARKERS = ("test", "tests", "spec", "specs", "__tests__")
_UNHELPFUL_FAMILIES = {
    "index",
    "main",
    "shared",
    "helper",
    "helpers",
    "util",
    "utils",
    "type",
    "types",
    "spec",
    "test",
    "tests",
}


def detect_project(root: Path, config: ReviewflowConfig | None = None) -> ProjectRecord:
    config = config or ReviewflowConfig()
    git_root, remote, default_branch, current_branch, head_sha, _dirty = discover_git(root)
    languages: set[str] = set()
    frameworks: set[str] = set()
    package_managers: set[str] = set()
    commands = ProjectCommands()

    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        languages.add("python")
        package_managers.add("uv" if (root / "uv.lock").exists() else "pip")
        commands.test = commands.test or "pytest"
        commands.format = commands.format or "ruff format"
        commands.lint = commands.lint or "ruff check"
    package_json = root / "package.json"
    if package_json.exists():
        languages.add("typescript/javascript")
        package_managers.add(_node_package_manager(root))
        scripts = _package_scripts(package_json)
        commands.test = scripts.get("test")
        commands.lint = scripts.get("lint")
        commands.typecheck = scripts.get("typecheck")
        commands.format = scripts.get("format")
        deps = " ".join(_package_deps(package_json))
        for marker, framework in {
            "next": "nextjs",
            "react": "react",
            "@angular/core": "angular",
            "vue": "vue",
            "express": "express",
            "fastify": "fastify",
        }.items():
            if marker in deps:
                frameworks.add(framework)
    if (root / "go.mod").exists():
        languages.add("go")
        package_managers.add("go")
        commands.test = commands.test or "go test ./..."
    if (root / "Cargo.toml").exists():
        languages.add("rust")
        package_managers.add("cargo")
        commands.test = commands.test or "cargo test"
        commands.typecheck = commands.typecheck or "cargo check"
    if (root / "pom.xml").exists():
        languages.add("jvm")
        package_managers.add("maven")
        commands.test = commands.test or "mvn test"
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        languages.add("jvm")
        package_managers.add("gradle")
        commands.test = commands.test or "./gradlew test"
    if (root / "composer.json").exists():
        languages.add("php")
        package_managers.add("composer")
    if (root / "mix.exs").exists():
        languages.add("elixir")
        package_managers.add("mix")
        commands.test = commands.test or "mix test"

    for path in iter_repo_files(root, config):
        if path.suffix == ".py":
            languages.add("python")
            text = read_text_bounded(path, limit_chars=4000)
            if "FastAPI(" in text:
                frameworks.add("fastapi")
            if "Flask(" in text:
                frameworks.add("flask")
            if "django" in text.lower():
                frameworks.add("django")
        elif path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
            languages.add("typescript/javascript")
        elif path.suffix == ".go":
            languages.add("go")
        elif path.suffix == ".rs":
            languages.add("rust")
        elif path.suffix in {".rb"}:
            languages.add("ruby")
        elif path.suffix in {".swift"}:
            languages.add("swift")
        elif path.suffix in {".cs", ".fs", ".vb"}:
            languages.add("dotnet")
        elif path.suffix in {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"}:
            languages.add("c/c++")
        elif path.suffix in {".ex", ".exs"}:
            languages.add("elixir")
        elif path.suffix == ".php":
            languages.add("php")

    now = now_iso()
    return ProjectRecord(
        project_id=stable_id("prj", [str(root.resolve())]),
        name=root.name,
        root_path=str(root.resolve()),
        git=GitInfo(
            remote_url=remote,
            default_branch=default_branch,
            current_branch=current_branch,
            head_sha=head_sha,
        ),
        detected=DetectedProject(
            languages=sorted(languages),
            frameworks=sorted(frameworks),
            package_managers=sorted(package_managers),
            commands=commands,
        ),
        created_at=now,
        updated_at=now,
    )


def map_features(
    root: Path,
    project: ProjectRecord,
    config: ReviewflowConfig,
    existing: list[FeatureRecord],
) -> tuple[list[FeatureRecord], dict[str, int]]:
    now = now_iso()
    previous = {feature.feature_id: feature for feature in existing}
    seeds: dict[str, dict[str, object]] = {}
    config_files: list[str] = []
    groups: dict[str, list[str]] = defaultdict(list)
    tests_by_group: dict[str, list[str]] = defaultdict(list)
    all_tests: list[str] = []
    all_sources: list[str] = []

    for file_path in iter_repo_files(root, config):
        rel = file_path.relative_to(root).as_posix()
        if file_path.name in CONFIG_NAMES or file_path.suffix in {
            ".toml",
            ".yaml",
            ".yml",
            ".json",
        }:
            config_files.append(rel)
        if file_path.suffix not in SOURCE_SUFFIXES:
            continue
        key = _group_key(rel)
        if _is_test_path(rel):
            tests_by_group[key].append(rel)
            all_tests.append(rel)
        else:
            groups[key].append(rel)
            all_sources.append(rel)

    if config_files:
        feature_id = stable_id("feat", ["config", *sorted(config_files)])
        seeds[feature_id] = {
            "title": "Project configuration",
            "summary": "Build, dependency, and tool configuration files.",
            "kind": "config",
            "owned": sorted(config_files)[: config.review.max_owned_files],
            "context": [],
            "tests": [],
            "tags": ["config"],
        }

    for feature_id, seed in _python_console_script_seeds(root, all_tests, project).items():
        seeds[feature_id] = seed
    for feature_id, seed in _python_route_seeds(root, all_sources, all_tests).items():
        seeds[feature_id] = seed
    for feature_id, seed in _node_package_seeds(root, config_files, all_tests, project).items():
        seeds[feature_id] = seed

    for key, files in groups.items():
        for label, grouped_files in _partition_feature_files(
            key, sorted(files), config.review.max_owned_files
        ):
            tests = _associated_tests(grouped_files, all_tests)
            if not tests:
                tests = sorted(tests_by_group.get(key, []))
            title = _title_for_group(label, grouped_files)
            kind = _kind_for_group(label, grouped_files, tests)
            feature_id = stable_id("feat", [label, *grouped_files[:20]])
            seeds[feature_id] = {
                "title": title,
                "summary": f"Source slice for {title}.",
                "kind": kind,
                "owned": grouped_files[: config.review.max_owned_files],
                "context": grouped_files[
                    config.review.max_owned_files : config.review.max_owned_files + 6
                ],
                "tests": tests[:8],
                "tags": sorted(_tags_for_files(grouped_files)),
            }

    features: list[FeatureRecord] = []
    created = 0
    changed = 0
    for feature_id, seed in sorted(seeds.items()):
        prior = previous.get(feature_id)
        created_at = prior.created_at if prior else now
        status = prior.status if prior and prior.status not in {"skipped", "claimed"} else "pending"
        finding_ids = prior.finding_ids if prior else []
        patch_ids = prior.patch_attempt_ids if prior else []
        analysis = prior.analysis_history if prior else []
        feature = FeatureRecord(
            feature_id=feature_id,
            title=str(seed["title"]),
            summary=str(seed["summary"]),
            kind=seed["kind"],  # type: ignore[arg-type]
            source="heuristic",
            confidence="medium",
            entrypoints=_seed_entrypoints(seed),
            owned_files=[
                FeatureFileRef(path=path, reason="owned by heuristic feature slice")
                for path in seed["owned"]  # type: ignore[union-attr]
            ],
            context_files=[
                FeatureFileRef(path=path, reason="nearby source context")
                for path in seed["context"]  # type: ignore[union-attr]
            ],
            tests=[
                FeatureTestRef(path=path, command=project.detected.commands.test)
                for path in seed["tests"]  # type: ignore[union-attr]
            ],
            tags=list(seed["tags"]),  # type: ignore[arg-type]
            trust_boundaries=_trust_boundaries(root, seed["owned"]),  # type: ignore[arg-type]
            status=status,
            finding_ids=finding_ids,
            patch_attempt_ids=patch_ids,
            analysis_history=analysis,
            created_at=created_at,
            updated_at=now,
        )
        features.append(feature)
        if prior is None:
            created += 1
        elif _feature_fingerprint(prior) != _feature_fingerprint(feature):
            changed += 1

    stale = max(len(existing) - len(features), 0)
    return features, {"created": created, "changed": changed, "stale": stale}


def _seed_entrypoints(seed: dict[str, object]) -> list[FeatureEntrypoint]:
    raw = seed.get("entrypoints")
    if isinstance(raw, list):
        entrypoints: list[FeatureEntrypoint] = []
        for index, item in enumerate(raw):
            if index >= 3:
                break
            if not isinstance(item, dict):
                continue
            data = cast("dict[str, object]", item)
            path = data.get("path")
            symbol = data.get("symbol")
            route = data.get("route")
            command = data.get("command")
            if not isinstance(path, str):
                continue
            entrypoints.append(
                FeatureEntrypoint(
                    path=path,
                    symbol=symbol if isinstance(symbol, str) else None,
                    route=route if isinstance(route, str) else None,
                    command=command if isinstance(command, str) else None,
                )
            )
        if entrypoints:
            return entrypoints
    owned = seed.get("owned")
    if not isinstance(owned, list):
        return []
    entrypoints = []
    for index, path in enumerate(owned):
        if index >= 3:
            break
        if isinstance(path, str):
            entrypoints.append(FeatureEntrypoint(path=path))
    return entrypoints


def _python_console_script_seeds(
    root: Path, all_tests: list[str], project: ProjectRecord
) -> dict[str, dict[str, object]]:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return {}
    try:
        parsed = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    scripts: dict[str, str] = {}
    project_table = parsed.get("project")
    tool_table = parsed.get("tool")
    poetry_table = tool_table.get("poetry") if isinstance(tool_table, dict) else None
    project_scripts = project_table.get("scripts", {}) if isinstance(project_table, dict) else {}
    poetry_scripts = poetry_table.get("scripts", {}) if isinstance(poetry_table, dict) else {}
    for table in (project_scripts, poetry_scripts):
        if not isinstance(table, dict):
            continue
        for name, target in table.items():
            if isinstance(name, str) and isinstance(target, str):
                scripts[name] = target

    seeds: dict[str, dict[str, object]] = {}
    for name, target in sorted(scripts.items()):
        source_path, symbol = _resolve_python_entrypoint(root, target)
        owned = [source_path or "pyproject.toml"]
        context = [] if source_path is None else ["pyproject.toml"]
        tests = _associated_tests(owned, all_tests)
        feature_id = stable_id("feat", ["python-script", name, target, owned[0]])
        seeds[feature_id] = {
            "title": f"Python CLI command {name}",
            "summary": f"Python console script '{name}' targets {target}.",
            "kind": "cli-command",
            "owned": owned,
            "context": context,
            "tests": tests[:8],
            "tags": ["python", "cli"],
            "entrypoints": [
                {"path": owned[0], "symbol": symbol, "command": name},
            ],
        }
        if project.detected.commands.test and tests:
            seeds[feature_id]["testCommand"] = project.detected.commands.test
    return seeds


def _resolve_python_entrypoint(root: Path, target: str) -> tuple[str | None, str | None]:
    module, _sep, symbol = target.partition(":")
    module = module.split("[", 1)[0].strip()
    symbol = symbol.split("[", 1)[0].strip() or None
    if not module:
        return None, symbol
    rel = module.replace(".", "/")
    candidates = [
        f"{rel}.py",
        f"src/{rel}.py",
        f"{rel}/__init__.py",
        f"src/{rel}/__init__.py",
    ]
    for candidate in candidates:
        if (root / candidate).exists():
            return candidate, symbol
    return None, symbol


_FASTAPI_ROUTE_RE = re.compile(
    r"^\s*@(?:(?:app|api|router|[A-Za-z_][A-Za-z0-9_]*(?:app|api|router))\.)"
    r"(?P<method>api_route|get|post|put|patch|delete|options|head|trace)\((?P<args>.*)\)",
    re.IGNORECASE,
)
_FLASK_ROUTE_RE = re.compile(
    r"^\s*@(?:[A-Za-z_][A-Za-z0-9_]*\.)?route\((?P<args>.*)\)", re.IGNORECASE
)
_DEF_RE = re.compile(r"^\s*(?:async\s+def|def)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
_ROUTE_PATH_RE = re.compile(r"[\"']([^\"']*)[\"']")
_ROUTE_METHODS_RE = re.compile(r"methods\s*=\s*\[(?P<methods>[^\]]+)\]", re.IGNORECASE)


def _python_route_seeds(
    root: Path, source_files: list[str], all_tests: list[str]
) -> dict[str, dict[str, object]]:
    seeds: dict[str, dict[str, object]] = {}
    for rel in sorted(path for path in source_files if path.endswith(".py")):
        text = read_text_bounded(root / rel, limit_chars=80_000)
        lines = text.splitlines()
        for index, line in enumerate(lines):
            route = _parse_python_route_decorator(line)
            if route is None:
                continue
            route_path, methods = route
            symbol = _next_python_def(lines, index + 1)
            title = f"Python route {'/'.join(methods)} {route_path}"
            feature_id = stable_id("feat", ["python-route", rel, route_path, *methods])
            seeds[feature_id] = {
                "title": title,
                "summary": f"Python web route {', '.join(methods)} {route_path} in {rel}.",
                "kind": "route",
                "owned": [rel],
                "context": [],
                "tests": _associated_tests([rel, symbol or route_path], all_tests)[:8],
                "tags": ["python", "route"],
                "entrypoints": [
                    {"path": rel, "symbol": symbol, "route": route_path},
                ],
            }
    return seeds


def _parse_python_route_decorator(line: str) -> tuple[str, list[str]] | None:
    fastapi = _FASTAPI_ROUTE_RE.match(line)
    if fastapi:
        args = fastapi.group("args")
        route_path = _first_string_arg(args) or "/"
        method = fastapi.group("method").upper()
        methods = ["ANY"] if method == "API_ROUTE" else [method]
        return route_path, methods
    flask = _FLASK_ROUTE_RE.match(line)
    if flask:
        args = flask.group("args")
        route_path = _first_string_arg(args) or "/"
        methods = _decorator_methods(args) or ["GET"]
        return route_path, methods
    return None


def _first_string_arg(args: str) -> str | None:
    match = _ROUTE_PATH_RE.search(args)
    return match.group(1) if match else None


def _decorator_methods(args: str) -> list[str]:
    match = _ROUTE_METHODS_RE.search(args)
    if not match:
        return []
    return [
        method.upper() for method in re.findall(r"[\"']([A-Za-z]+)[\"']", match.group("methods"))
    ]


def _next_python_def(lines: list[str], start: int) -> str | None:
    for line in lines[start : start + 8]:
        match = _DEF_RE.match(line)
        if match:
            return match.group("name")
    return None


def _node_package_seeds(
    root: Path, config_files: list[str], all_tests: list[str], project: ProjectRecord
) -> dict[str, dict[str, object]]:
    seeds: dict[str, dict[str, object]] = {}
    for package_json_rel in sorted(path for path in config_files if path.endswith("package.json")):
        package_json = root / package_json_rel
        parsed = _read_json_object(package_json)
        if parsed is None:
            continue
        package_root = Path(package_json_rel).parent.as_posix()
        package_name = parsed.get("name") if isinstance(parsed.get("name"), str) else package_root
        scripts = _scripts_from_object(parsed)
        bins = _bins_from_object(parsed)
        package_files = _node_package_metadata_files(root, package_root, package_json_rel)
        feature_id = stable_id("feat", ["node-package", package_json_rel, str(package_name)])
        seeds[feature_id] = {
            "title": f"Node package {package_name}",
            "summary": f"Node package metadata and review context rooted at {package_root}.",
            "kind": "library",
            "owned": package_files[:1] or [package_json_rel],
            "context": package_files[1:8],
            "tests": [],
            "tags": ["node", "package"],
            "entrypoints": [{"path": package_json_rel, "symbol": str(package_name)}],
        }
        for command, target in sorted(bins.items()):
            entry = _package_relative(package_root, target)
            owned = [entry if (root / entry).exists() else package_json_rel]
            feature_id = stable_id("feat", ["node-bin", package_json_rel, command, target])
            seeds[feature_id] = {
                "title": f"CLI command {command}",
                "summary": f"Package bin '{command}' targets {target}.",
                "kind": "cli-command",
                "owned": owned,
                "context": [package_json_rel] if owned[0] != package_json_rel else [],
                "tests": _associated_tests(owned, all_tests)[:8],
                "tags": ["node", "cli"],
                "entrypoints": [{"path": owned[0], "command": command}],
            }
        for script, command in sorted(scripts.items()):
            if script not in {"start", "build", "test", "lint", "typecheck", "format"}:
                continue
            feature_id = stable_id("feat", ["node-script", package_json_rel, script, command])
            seeds[feature_id] = {
                "title": f"Package script {script}",
                "summary": f"Package script '{script}' in {package_json_rel}: {command}",
                "kind": "test-suite" if script == "test" else "release",
                "owned": [package_json_rel],
                "context": [],
                "tests": [],
                "tags": ["node", "package-script"],
                "entrypoints": [{"path": package_json_rel, "symbol": script, "command": script}],
            }
            if script == "test" and project.detected.commands.test:
                seeds[feature_id]["tests"] = [package_json_rel]
    return seeds


def _read_json_object(path: Path) -> dict[str, object] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _scripts_from_object(parsed: dict[str, object]) -> dict[str, str]:
    scripts = parsed.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {str(key): value for key, value in scripts.items() if isinstance(value, str)}


def _bins_from_object(parsed: dict[str, object]) -> dict[str, str]:
    bin_value = parsed.get("bin")
    if isinstance(bin_value, str):
        raw_name = parsed.get("name")
        name = raw_name if isinstance(raw_name, str) else "bin"
        return {name: bin_value}
    if isinstance(bin_value, dict):
        return {str(key): value for key, value in bin_value.items() if isinstance(value, str)}
    return {}


def _node_package_metadata_files(root: Path, package_root: str, package_json_rel: str) -> list[str]:
    candidates = [
        package_json_rel,
        _package_relative(package_root, "README.md"),
        _package_relative(package_root, "AGENTS.md"),
        _package_relative(package_root, "tsconfig.json"),
        _package_relative(package_root, "vite.config.ts"),
        _package_relative(package_root, "next.config.js"),
        _package_relative(package_root, "next.config.mjs"),
        _package_relative(package_root, "next.config.ts"),
    ]
    seen: set[str] = set()
    out: list[str] = []
    for rel in candidates:
        if rel not in seen and (root / rel).exists():
            seen.add(rel)
            out.append(rel)
    return out


def _package_relative(package_root: str, rel: str) -> str:
    if package_root in {"", "."}:
        return rel.replace("\\", "/").removeprefix("./")
    return f"{package_root.rstrip('/')}/{rel}".replace("\\", "/").removeprefix("./")


def iter_repo_files(root: Path, config: ReviewflowConfig) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if path_matches(rel, config.exclude):
            continue
        if config.include and not path_matches(rel, config.include):
            continue
        if _looks_generated(rel):
            continue
        files.append(path)
    return files


def _partition_feature_files(
    key: str, files: list[str], max_files: int
) -> list[tuple[str, list[str]]]:
    if len(files) <= max_files:
        return [(key, files)]
    direct_files: list[str] = []
    buckets: dict[str, list[str]] = defaultdict(list)
    for file in files:
        relative = _relative_to_group(key, file)
        parts = relative.split("/")
        if len(parts) <= 1:
            direct_files.append(file)
        else:
            buckets[parts[0]].append(file)

    groups = _partition_direct_files(key, sorted(direct_files), max_files)
    for segment, bucket_files in sorted(buckets.items()):
        label = f"{key}/{segment}" if key != "root" else segment
        sorted_bucket = sorted(bucket_files)
        if len(sorted_bucket) <= max_files:
            groups.append((label, sorted_bucket))
        else:
            groups.extend(_partition_feature_files(label, sorted_bucket, max_files))
    return groups or _chunk_files(key, files, max_files)


def _partition_direct_files(
    label: str, files: list[str], max_files: int
) -> list[tuple[str, list[str]]]:
    if not files:
        return []
    if len(files) <= max_files:
        return [(label, files)]
    buckets: dict[str, list[str]] = defaultdict(list)
    fallback: list[str] = []
    for file in files:
        family = _direct_file_family(file)
        if family is None:
            fallback.append(file)
        else:
            buckets[family].append(file)

    groups: list[tuple[str, list[str]]] = []
    for family, bucket_files in sorted(buckets.items()):
        if len(bucket_files) < 2:
            fallback.extend(bucket_files)
        else:
            groups.extend(_chunk_files(f"{label}/:{family}", sorted(bucket_files), max_files))
    groups.extend(_chunk_files(label, sorted(fallback), max_files))
    return groups


def _chunk_files(label: str, files: list[str], max_files: int) -> list[tuple[str, list[str]]]:
    if not files:
        return []
    if len(files) <= max_files:
        return [(label, files)]
    return [
        (f"{label}#{index // max_files + 1}", files[index : index + max_files])
        for index in range(0, len(files), max_files)
    ]


def _relative_to_group(key: str, file: str) -> str:
    if key != "root" and file.startswith(f"{key}/"):
        return file[len(key) + 1 :]
    return file


def _direct_file_family(file: str) -> str | None:
    stem = Path(file).name
    while "." in stem:
        stem = stem.rsplit(".", 1)[0]
    prefix = stem.split(".", 1)[0].split("-", 1)[0].split("_", 1)[0].lower()
    if len(prefix) < 3 or prefix.isdigit() or prefix in _UNHELPFUL_FAMILIES:
        return None
    return prefix


def _associated_tests(source_files: list[str], tests: list[str]) -> list[str]:
    tokens = {
        _test_name_token(Path(file).stem)
        for file in source_files
        if _test_name_token(Path(file).stem)
    }
    matched: list[str] = []
    for test in sorted(tests):
        normalized = _test_name_token(test)
        if any(token and token in normalized for token in tokens):
            matched.append(test)
    return matched


def _test_name_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _node_package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "package-lock.json").exists():
        return "npm"
    return "npm"


def _package_scripts(package_json: Path) -> dict[str, str]:
    try:
        parsed = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = parsed.get("scripts", {})
    if not isinstance(scripts, dict):
        return {}
    return {key: str(value) for key, value in scripts.items() if isinstance(value, str)}


def _package_deps(package_json: Path) -> list[str]:
    try:
        parsed = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[str] = []
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        value = parsed.get(key, {})
        if isinstance(value, dict):
            out.extend(str(dep) for dep in value)
    return out


def _group_key(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) == 1:
        return "root"
    if parts[0] in {"apps", "packages", "crates", "cmd", "services", "extensions", "plugins"}:
        return "/".join(parts[:2]) if len(parts) > 1 else parts[0]
    if parts[0] in {"src", "lib", "app", "pages", "routes", "components", "tests", "test"}:
        return parts[0]
    return parts[0]


def _title_for_group(key: str, files: list[str]) -> str:
    if key == "root":
        return "Root source files"
    if key in {"tests", "test"}:
        return "Test suite"
    if any("/routes" in file or file.startswith(("app/", "pages/", "routes/")) for file in files):
        return f"Routes: {key}"
    return key.replace("/", " / ").replace("_", " ").title()


def _kind_for_group(key: str, files: list[str], tests: list[str]) -> str:
    if key in {"tests", "test"} or tests and all(_is_test_path(path) for path in files):
        return "test-suite"
    if any(file.startswith(("app/", "pages/", "routes/")) or "/routes/" in file for file in files):
        return "route"
    if any(file.endswith(("cli.py", "cli.ts", "cli.js")) or "/cli/" in file for file in files):
        return "cli-command"
    if any("job" in file.lower() or "worker" in file.lower() for file in files):
        return "job"
    return "library"


def _tags_for_files(files: list[str]) -> set[str]:
    tags: set[str] = set()
    for file in files:
        suffix = Path(file).suffix
        if suffix == ".py":
            tags.add("python")
        elif suffix in {".ts", ".tsx"}:
            tags.add("typescript")
        elif suffix in {".js", ".jsx"}:
            tags.add("javascript")
        elif suffix == ".go":
            tags.add("go")
        elif suffix == ".rs":
            tags.add("rust")
        elif suffix in {".java", ".kt", ".kts"}:
            tags.add("jvm")
        elif suffix in {".rb"}:
            tags.add("ruby")
        elif suffix in {".php"}:
            tags.add("php")
    return tags


def _trust_boundaries(root: Path, files: object) -> list[str]:
    boundaries: set[str] = set()
    for rel in files if isinstance(files, list) else []:
        if not isinstance(rel, str):
            continue
        text = read_text_bounded(root / rel, limit_chars=6000).lower()
        if any(token in text for token in ("request", "input(", "argv", "params", "body")):
            boundaries.add("user-input")
        if any(token in text for token in ("http", "fetch(", "requests.", "axios", "socket")):
            boundaries.add("network")
        if any(token in text for token in ("open(", "readfile", "writefile", "path", "fs.")):
            boundaries.add("filesystem")
        if any(token in text for token in ("token", "secret", "password", "api_key")):
            boundaries.add("secrets")
        if any(token in text for token in ("subprocess", "exec(", "spawn(", "system(")):
            boundaries.add("process-exec")
        if any(token in text for token in ("sql", "query", "database", "db.")):
            boundaries.add("database")
        if any(token in text for token in ("auth", "permission", "role")):
            boundaries.add("auth")
    return sorted(boundaries)


def _feature_fingerprint(feature: FeatureRecord) -> tuple[object, ...]:
    return (
        feature.title,
        feature.summary,
        feature.kind,
        tuple((item.path, item.reason) for item in feature.owned_files),
        tuple((item.path, item.reason) for item in feature.context_files),
        tuple((item.path, item.command) for item in feature.tests),
        tuple(feature.tags),
    )


def _is_test_path(rel: str) -> bool:
    lowered = rel.lower()
    parts = lowered.split("/")
    stem = Path(lowered).stem
    return (
        any(marker in parts for marker in TEST_MARKERS)
        or stem.startswith("test_")
        or stem.endswith(("_test", ".test", ".spec"))
    )


def _looks_generated(rel: str) -> bool:
    lowered = rel.lower()
    return any(
        marker in lowered
        for marker in (
            "/.venv/",
            "/__pycache__/",
            "/node_modules/",
            "/dist/",
            "/build/",
            "/target/",
            ".min.js",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "uv.lock",
        )
    )


__all__ = ["detect_project", "iter_repo_files", "map_features"]
