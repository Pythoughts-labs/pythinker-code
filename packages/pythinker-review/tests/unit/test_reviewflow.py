from __future__ import annotations

import pytest

from pythinker_review.reviewflow.mapping import detect_project, map_features
from pythinker_review.reviewflow.models import (
    EvidenceRef,
    FeatureLock,
    FeatureRecord,
    FindingRecord,
    PatchAttempt,
    ReviewflowConfig,
    RunRecord,
    derive_finding_triage,
)
from pythinker_review.reviewflow.reporting import next_finding, render_report
from pythinker_review.reviewflow.state import (
    claim_feature,
    ensure_state_dirs,
    read_feature,
    read_feature_lock_ids,
    read_finding,
    release_feature_lock,
    state_paths,
    write_feature,
    write_finding,
    write_patch_attempt,
    write_run,
)
from pythinker_review.reviewflow.utils import now_iso, stable_id
from pythinker_review.reviewflow.workflow import (
    ReviewflowWorkflowError,
    _validate_fix_diff_scope,
    init_project,
    load_project_state,
)


def test_reviewflow_models_preserve_camel_case_aliases() -> None:
    parsed = EvidenceRef.model_validate(
        {"path": "src/app.py", "startLine": 3, "endLine": 4, "quote": "return user"}
    )

    dumped = parsed.model_dump(by_alias=True)

    assert parsed.start_line == 3
    assert dumped["startLine"] == 3
    assert dumped["endLine"] == 4
    assert derive_finding_triage("security", "high") == "confirmed-bug"


def test_reviewflow_mapping_detects_project_and_features(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\n[project.scripts]\ndemo = 'app:run'\n", encoding="utf-8"
    )
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text(
        "import subprocess\n\ndef run(request):\n    return subprocess.run(request.args['cmd'])\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_app.py").write_text("def test_run(): pass\n", encoding="utf-8")

    config = ReviewflowConfig()
    project = detect_project(root, config)
    features, stats = map_features(root, project, config, existing=[])

    assert "python" in project.detected.languages
    assert project.detected.commands.test == "pytest"
    assert stats["created"] >= 2
    src_feature = next(feature for feature in features if feature.title == "Src")
    assert [ref.path for ref in src_feature.owned_files] == ["src/app.py"]
    assert [ref.path for ref in src_feature.tests] == ["tests/test_app.py"]
    assert "process-exec" in src_feature.trust_boundaries
    config_feature = next(
        feature for feature in features if feature.title == "Project configuration"
    )
    assert [ref.path for ref in config_feature.owned_files] == ["pyproject.toml"]
    cli_feature = next(
        feature for feature in features if feature.title == "Python CLI command demo"
    )
    assert [ref.path for ref in cli_feature.owned_files] == ["src/app.py"]
    assert cli_feature.entrypoints[0].command == "demo"
    assert cli_feature.entrypoints[0].symbol == "run"


def test_reviewflow_mapping_detects_python_routes_and_node_package_scripts(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "package.json").write_text(
        '{"name":"web","scripts":{"test":"vitest","build":"vite build"},'
        '"bin":{"webctl":"src/cli.ts"}}',
        encoding="utf-8",
    )
    (root / "src").mkdir()
    (root / "src" / "api.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n\n"
        "@app.post('/items')\n"
        "def create_item():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    (root / "src" / "cli.ts").write_text("console.log('ok')\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_api.py").write_text("def test_create_item(): pass\n", encoding="utf-8")

    config = ReviewflowConfig()
    project = detect_project(root, config)
    features, _stats = map_features(root, project, config, existing=[])

    route = next(feature for feature in features if feature.title == "Python route POST /items")
    assert route.kind == "route"
    assert route.entrypoints[0].route == "/items"
    assert route.entrypoints[0].symbol == "create_item"
    node_package = next(feature for feature in features if feature.title == "Node package web")
    assert [ref.path for ref in node_package.owned_files] == ["package.json"]
    script = next(feature for feature in features if feature.title == "Package script build")
    assert script.entrypoints[0].command == "build"
    cli = next(feature for feature in features if feature.title == "CLI command webctl")
    assert [ref.path for ref in cli.owned_files] == ["src/cli.ts"]


def test_reviewflow_mapping_partitions_large_source_groups(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (root / "src" / "auth").mkdir(parents=True)
    (root / "src" / "billing").mkdir(parents=True)
    for path in [
        "src/auth/login.py",
        "src/auth/session.py",
        "src/auth/token.py",
        "src/billing/invoice.py",
    ]:
        (root / path).write_text("pass\n", encoding="utf-8")

    config = ReviewflowConfig()
    config.review.max_owned_files = 2
    project = detect_project(root, config)
    features, _stats = map_features(root, project, config, existing=[])

    source_features = [feature for feature in features if feature.title.startswith("Src")]
    assert len(source_features) >= 3
    assert all(len(feature.owned_files) <= 2 for feature in source_features)
    assert any(feature.title.startswith("Src / Auth") for feature in source_features)
    assert any(feature.title == "Src / Billing" for feature in source_features)


def test_reviewflow_fix_diff_scope_handles_spaces_and_hunk_marker_content() -> None:
    diff = """diff --git a/src/file with spaces.py b/src/file with spaces.py
--- a/src/file with spaces.py
+++ b/src/file with spaces.py
@@ -1 +1,2 @@
 value = 1
++++ not a file header
"""

    _validate_fix_diff_scope(diff, allowed_paths={"src/file with spaces.py"})


def test_reviewflow_fix_diff_scope_rejects_out_of_scope_paths() -> None:
    diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-old
+new
"""

    with pytest.raises(ReviewflowWorkflowError, match="outside the selected"):
        _validate_fix_diff_scope(diff, allowed_paths={"src/other.py"})


def test_reviewflow_state_round_trip_and_locking(tmp_path) -> None:
    paths = state_paths(tmp_path / ".pythinker-review-flow")
    ensure_state_dirs(paths)
    now = now_iso()
    feature = FeatureRecord(
        feature_id=stable_id("feat", ["src/app.py"]),
        title="Src",
        summary="Source feature",
        kind="library",
        owned_files=[],
        created_at=now,
        updated_at=now,
    )
    finding = FindingRecord(
        finding_id=stable_id("finding", ["src/app.py", "3"]),
        feature_id=feature.feature_id,
        title="Unsafe command execution",
        category="security",
        severity="high",
        confidence="high",
        triage="confirmed-bug",
        evidence=[EvidenceRef(path="src/app.py", start_line=3, end_line=3)],
        reasoning="User input reaches subprocess.",
        recommendation="Avoid shelling out with user input.",
        signature="sig",
        created_by_run_id="run_1",
        created_at=now,
        updated_at=now,
    )

    write_feature(paths, feature)
    write_finding(paths, finding)
    claim_feature(paths, feature, '{"lockedByRunId":"run_1"}')

    assert read_feature(paths, feature.feature_id) == feature
    assert read_finding(paths, finding.finding_id) == finding
    assert read_feature_lock_ids(paths) == [feature.feature_id]
    with pytest.raises(RuntimeError, match="feature locked"):
        claim_feature(paths, feature, "{}")
    release_feature_lock(paths, feature.feature_id)
    assert read_feature_lock_ids(paths) == []


def test_reviewflow_state_models_match_reviewflow_json_shape(tmp_path) -> None:
    paths = state_paths(tmp_path / ".pythinker-review-flow")
    ensure_state_dirs(paths)
    now = now_iso()
    run = RunRecord(
        run_id="20260520120000-deadbeef",
        command="review",
        args=["--limit", "1"],
        root_path=str(tmp_path),
        head_sha="abc",
        started_at=now,
        status="running",
    )
    patch = PatchAttempt(
        patch_attempt_id="pat_1",
        finding_ids=["fnd_1"],
        feature_ids=["feat_1"],
        status="validated",
        plan="Fix it",
        created_at=now,
        updated_at=now,
    )

    write_run(paths, run)
    write_patch_attempt(paths, patch)

    run_json = (paths.runs / "20260520120000-deadbeef.json").read_text(encoding="utf-8")
    patch_json = (paths.patches / "pat_1.json").read_text(encoding="utf-8")
    assert '"command": "review"' in run_json
    assert '"claimedFeatureIds"' in run_json
    assert '"patchAttemptId": "pat_1"' in patch_json
    assert '"status": "validated"' in patch_json


def test_reviewflow_migrates_legacy_state_dir_to_reviewflow_brand(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")

    init_project(root=root, state_dir=".clawpatch")
    legacy_config = root / ".clawpatch" / "config.json"
    legacy_config.write_text(
        legacy_config.read_text(encoding="utf-8").replace(',\n    ".clawpatch/**"', ""),
        encoding="utf-8",
    )
    loaded = load_project_state(root=root)

    assert (root / ".clawpatch" / "project.json").exists()
    assert loaded.paths.state_dir == (root / ".pythinker-review-flow").resolve()
    assert loaded.config.state_dir == ".pythinker-review-flow"
    assert ".clawpatch/**" in loaded.config.exclude
    assert (root / ".pythinker-review-flow" / "project.json").exists()
    assert '"stateDir": ".pythinker-review-flow"' in (
        root / ".pythinker-review-flow" / "config.json"
    ).read_text(encoding="utf-8")


def test_reviewflow_refuses_legacy_state_with_nested_symlink(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    init_project(root=root, state_dir=".clawpatch")
    (root / ".clawpatch" / "leak.json").symlink_to(root / "pyproject.toml")

    with pytest.raises(ReviewflowWorkflowError, match="contains symlinks"):
        load_project_state(root=root)

    assert not (root / ".pythinker-review-flow").exists()


def test_clean_locks_clears_feature_and_lock_file(tmp_path) -> None:
    from pythinker_review.reviewflow.state import clear_feature_locks

    paths = state_paths(tmp_path / ".pythinker-review-flow")
    ensure_state_dirs(paths)
    now = now_iso()
    feature = FeatureRecord(
        feature_id="feat_locked",
        title="Locked",
        summary="Locked feature",
        created_at=now,
        updated_at=now,
    )
    write_feature(paths, feature)
    claim_feature(
        paths,
        feature,
        FeatureLock(locked_by_run_id="run_1", locked_at=now, hostname="host", pid=1),
        allow_non_pending=True,
    )

    cleared_features, cleared_files = clear_feature_locks(paths)

    unlocked = read_feature(paths, feature.feature_id)
    assert cleared_features == 1
    assert cleared_files == 1
    assert unlocked is not None
    assert unlocked.lock is None
    assert unlocked.status == "pending"
    assert read_feature_lock_ids(paths) == []


def test_reviewflow_report_ranks_next_open_finding() -> None:
    now = now_iso()
    feature = FeatureRecord(
        feature_id="feat_src",
        title="Source",
        summary="Source feature",
        created_at=now,
        updated_at=now,
    )
    low = FindingRecord(
        finding_id="finding_low",
        feature_id=feature.feature_id,
        title="Low issue",
        category="maintainability",
        severity="low",
        confidence="high",
        triage="risk",
        evidence=[],
        reasoning="Minor cleanup.",
        recommendation="Clean up.",
        signature="low",
        created_by_run_id="run_1",
        created_at=now,
        updated_at=now,
    )
    high = FindingRecord(
        finding_id="finding_high",
        feature_id=feature.feature_id,
        title="High issue",
        category="security",
        severity="high",
        confidence="medium",
        triage="risk",
        evidence=[EvidenceRef(path="src/app.py", start_line=1, end_line=1)],
        reasoning="Dangerous flow.",
        recommendation="Fix the flow.",
        signature="high",
        created_by_run_id="run_1",
        created_at=now,
        updated_at=now,
    )

    assert next_finding([low, high]) == high
    report = render_report([low, high], [feature])
    assert "# Pythinker Reviewflow Report" in report
    assert "HIGH · High issue" in report
    assert "low: 1" in report
