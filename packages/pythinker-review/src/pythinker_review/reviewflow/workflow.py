"""Stateful Reviewflow workflow commands."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pythinker_review.llm.protocol import ReviewLLM
from pythinker_review.reviewflow.mapping import detect_project, map_features
from pythinker_review.reviewflow.models import (
    AnalysisEntry,
    EvidenceRef,
    FeatureLock,
    FeatureRecord,
    FindingHistoryEntry,
    FindingRecord,
    FixPlanOutput,
    PatchAttempt,
    PatchGit,
    PatchProvider,
    ProjectRecord,
    ReviewflowConfig,
    RunError,
    RunRecord,
    derive_finding_triage,
)
from pythinker_review.reviewflow.provider import (
    ReviewDrop,
    ReviewPromptManifest,
    plan_fix,
    revalidate_finding,
    review_feature_partitioned,
    validation_commands_for_feature,
)
from pythinker_review.reviewflow.reporting import (
    finding_summary,
    next_finding,
    render_finding_detail,
    render_report,
)
from pythinker_review.reviewflow.state import (
    StatePaths,
    claim_feature,
    clear_feature_locks,
    ensure_state_dirs,
    read_config,
    read_feature,
    read_feature_lock_ids,
    read_features,
    read_finding,
    read_findings,
    read_patch_attempt,
    read_patch_attempts,
    read_project,
    read_runs,
    release_feature_lock,
    state_paths,
    write_config,
    write_feature,
    write_finding,
    write_patch_attempt,
    write_project,
    write_run,
)
from pythinker_review.reviewflow.utils import (
    changed_files_since,
    dirty_files,
    discover_git,
    git_output,
    now_iso,
    run_id,
    run_process,
    run_shell_command,
    run_untrusted_command,
    source_dirty,
    stable_id,
)


@dataclass(frozen=True, slots=True)
class LoadedState:
    root: Path
    config: ReviewflowConfig
    paths: StatePaths
    project: ProjectRecord


class ReviewflowWorkflowError(RuntimeError):
    def __init__(self, message: str, code: str = "workflow-error") -> None:
        super().__init__(message)
        self.code = code


class _AsyncRateLimiter:
    """Small in-process start-rate limiter for provider calls."""

    def __init__(self, per_minute: int | None) -> None:
        self._interval_s = 0.0 if per_minute is None or per_minute <= 0 else 60.0 / per_minute
        self._lock = asyncio.Lock()
        self._next_start_at = 0.0

    async def wait(self) -> None:
        if self._interval_s <= 0:
            return
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            if self._next_start_at > now:
                await asyncio.sleep(self._next_start_at - now)
                now = loop.time()
            self._next_start_at = max(self._next_start_at, now) + self._interval_s


_NONFATAL_REVIEW_ERROR_CODES = {"schema-drop", "validation-drop"}
_DEFAULT_STATE_DIR = ".pythinker-review-flow"
_LEGACY_STATE_DIR = ".clawpatch"


def _migrate_legacy_state_dir(*, root: Path, paths: StatePaths) -> None:
    legacy = root / _LEGACY_STATE_DIR
    if (
        paths.state_dir.exists()
        or not legacy.exists()
        or not legacy.is_dir()
        or legacy.is_symlink()
    ):
        return
    if any(path.is_symlink() for path in legacy.rglob("*")):
        raise ReviewflowWorkflowError(
            "legacy Reviewflow state contains symlinks; refusing automatic migration",
            "state-migration-failed",
        )
    try:
        shutil.copytree(legacy, paths.state_dir, symlinks=True)
    except OSError as exc:
        raise ReviewflowWorkflowError(
            f"failed to migrate legacy Reviewflow state to {_DEFAULT_STATE_DIR}: {exc}",
            "state-migration-failed",
        ) from exc
    stored = read_config(paths)
    if stored is not None:
        stored.state_dir = _DEFAULT_STATE_DIR
        stored.exclude = _merged_default_excludes(stored.exclude)
        write_config(paths, stored)


def _merged_default_excludes(existing: list[str]) -> list[str]:
    merged = list(dict.fromkeys(existing))
    for pattern in ReviewflowConfig().exclude:
        if pattern not in merged:
            merged.append(pattern)
    return merged


def resolve_paths(
    *, root: Path, state_dir: str | None = None, config_path: Path | None = None
) -> tuple[ReviewflowConfig, StatePaths]:
    base = ReviewflowConfig()
    if config_path and config_path.exists():
        base = ReviewflowConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    env_state = os.environ.get("PYTHINKER_REVIEWFLOW_STATE_DIR") or os.environ.get(
        "CLAWPATCH_STATE_DIR"
    )
    configured_state = state_dir or env_state or base.state_dir
    paths = state_paths((root / configured_state).resolve())
    if state_dir is None and env_state is None and config_path is None:
        _migrate_legacy_state_dir(root=root, paths=paths)
    stored = read_config(paths)
    if stored is not None and config_path is None:
        base = stored
    config = base.model_copy(deep=True)
    config.state_dir = configured_state
    provider = os.environ.get("PYTHINKER_REVIEWFLOW_PROVIDER") or os.environ.get(
        "CLAWPATCH_PROVIDER"
    )
    model = os.environ.get("PYTHINKER_REVIEWFLOW_MODEL") or os.environ.get("CLAWPATCH_MODEL")
    reasoning_effort = os.environ.get("PYTHINKER_REVIEWFLOW_REASONING_EFFORT") or os.environ.get(
        "CLAWPATCH_REASONING_EFFORT"
    )
    if provider:
        config.provider.name = provider
    if model:
        config.provider.model = model
    if reasoning_effort:
        value = reasoning_effort
        if value not in {"none", "minimal", "low", "medium", "high", "xhigh"}:
            raise ReviewflowWorkflowError(f"invalid reasoning effort: {value}", "invalid-usage")
        config.provider.reasoning_effort = value  # type: ignore[assignment]
    return config, paths


def load_project_state(
    *, root: Path, state_dir: str | None = None, config_path: Path | None = None
) -> LoadedState:
    config, paths = resolve_paths(root=root, state_dir=state_dir, config_path=config_path)
    project = read_project(paths)
    if project is None:
        raise ReviewflowWorkflowError(
            "project not initialized; run `pythinker review init`", "not-initialized"
        )
    return LoadedState(root=root, config=config, paths=paths, project=project)


def init_project(
    *,
    root: Path,
    state_dir: str | None = None,
    config_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    config, paths = resolve_paths(root=root, state_dir=state_dir, config_path=config_path)
    ensure_state_dirs(paths)
    previous = read_project(paths)
    if previous is not None and not force:
        raise ReviewflowWorkflowError(
            "project already initialized; use --force", "already-initialized"
        )
    project = detect_project(root, config)
    if previous is not None:
        project.created_at = previous.created_at
    config.commands = project.detected.commands
    write_project(paths, project)
    write_config(paths, config)
    return {
        "created": previous is None,
        "project": project.model_dump(by_alias=True),
        "paths": [str(paths.project), str(paths.config)],
        "next": "pythinker review map",
    }


def map_project(
    *,
    root: Path,
    state_dir: str | None = None,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    loaded = load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    existing = read_features(loaded.paths)
    features, stats = map_features(loaded.root, loaded.project, loaded.config, existing)
    active_ids = {feature.feature_id for feature in features}
    if not dry_run:
        for feature in features:
            write_feature(loaded.paths, feature)
        for feature in existing:
            if feature.feature_id not in active_ids:
                feature.status = "skipped"
                feature.lock = None
                feature.updated_at = now_iso()
                write_feature(loaded.paths, feature)
    return {
        "dryRun": dry_run,
        "features": len(features),
        "new": stats["created"],
        "changed": stats["changed"],
        "stale": stats["stale"],
        "source": "heuristic",
        "usedAgent": False,
        "reason": "pure-python heuristic mapper",
        "next": "pythinker review review --limit 3",
    }


def status_project(
    *, root: Path, state_dir: str | None = None, config_path: Path | None = None
) -> dict[str, Any]:
    loaded = load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    features = read_features(loaded.paths)
    findings = read_findings(loaded.paths)
    runs = read_runs(loaded.paths)
    locks = set(read_feature_lock_ids(loaded.paths))
    locks.update(feature.feature_id for feature in features if feature.lock is not None)
    _git_root, _remote, _default, branch, _head, dirty = discover_git(loaded.root)
    return {
        "project": loaded.project.name,
        "branch": branch,
        "dirty": dirty,
        "features": len(features),
        "findings": len(findings),
        "openFindings": len([finding for finding in findings if finding.status == "open"]),
        "activeLocks": len(locks),
        "lockFiles": len(read_feature_lock_ids(loaded.paths)),
        "lastRun": runs[-1].run_id if runs else None,
    }


def select_review_features(
    loaded: LoadedState,
    *,
    feature_id: str | None = None,
    project_filter: str | None = None,
    since: str | None = None,
    include_dirty: bool = False,
    limit: int | None = None,
) -> list[FeatureRecord]:
    features = [feature for feature in read_features(loaded.paths) if feature.status != "skipped"]
    if feature_id:
        features = [feature for feature in features if feature.feature_id == feature_id]
    if project_filter:
        lowered = project_filter.lower()
        features = [
            feature
            for feature in features
            if lowered in feature.title.lower()
            or any(ref.path.startswith(project_filter) for ref in feature.owned_files)
        ]
    changed: set[str] = set()
    if since:
        changed.update(changed_files_since(loaded.root, since))
    if include_dirty:
        changed.update(dirty_files(loaded.root))
    if changed:
        features = [feature for feature in features if _feature_touches(feature, changed)]
    features = sorted(
        features, key=lambda feature: (feature.status != "pending", feature.updated_at)
    )
    if limit is not None:
        features = features[:limit]
    return features


async def review_project(
    *,
    llm: ReviewLLM,
    root: Path,
    state_dir: str | None = None,
    config_path: Path | None = None,
    feature_id: str | None = None,
    project_filter: str | None = None,
    since: str | None = None,
    include_dirty: bool = False,
    limit: int | None = None,
    jobs: int = 1,
    mode: str = "default",
    dry_run: bool = False,
    per_feature_timeout_s: float = 180.0,
    custom_prompt: str | None = None,
    rate_limit_per_minute: int | None = None,
) -> dict[str, Any]:
    loaded = load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    features = select_review_features(
        loaded,
        feature_id=feature_id,
        project_filter=project_filter,
        since=since,
        include_dirty=include_dirty,
        limit=limit,
    )
    if dry_run:
        return {
            "dryRun": True,
            "wouldReview": len(features),
            "mode": mode,
            "jobs": jobs,
            "featureIds": [feature.feature_id for feature in features],
        }
    current_run_id = run_id()
    run = _new_run("review", loaded, current_run_id)
    run.claimed_feature_ids = [feature.feature_id for feature in features]
    write_run(loaded.paths, run)
    semaphore = asyncio.Semaphore(max(1, min(jobs, max(len(features), 1))))
    limiter = _AsyncRateLimiter(rate_limit_per_minute)
    finding_ids: list[str] = []
    errors: list[RunError] = []

    async def worker(feature: FeatureRecord) -> None:
        async with semaphore:
            locked: FeatureRecord | None = None
            try:
                locked = claim_feature(
                    loaded.paths,
                    feature,
                    FeatureLock(
                        locked_by_run_id=current_run_id,
                        locked_at=now_iso(),
                        hostname=socket.gethostname(),
                        pid=os.getpid(),
                    ),
                    allow_non_pending=feature_id is not None,
                )
                await limiter.wait()
                produced = await review_feature_partitioned(
                    llm=llm,
                    root=loaded.root,
                    feature=locked,
                    config=loaded.config,
                    mode=mode,
                    timeout_s=per_feature_timeout_s,
                    custom_prompt=custom_prompt,
                )
                valid, validation_drops = _validated_review_findings(
                    loaded.root,
                    produced.manifest,
                    produced.output.findings,
                )
                for drop in (*produced.dropped_findings, *validation_drops):
                    errors.append(_drop_run_error(locked.feature_id, drop))
                ids = _merge_review_findings(loaded, locked, valid, current_run_id)
                finding_ids.extend(ids)
                _mark_feature_reviewed(
                    loaded,
                    locked,
                    ids,
                    current_run_id,
                    provider=llm.model_display_name,
                    manifest=produced.manifest,
                    dropped=len(produced.dropped_findings) + len(validation_drops),
                )
                release_feature_lock(loaded.paths, locked.feature_id)
                locked = None
            except Exception as exc:  # noqa: BLE001 - provider boundary
                errors.append(RunError(message=str(exc), code="review-failed"))
                if locked is not None:
                    locked.status = "error"
                    locked.lock = None
                    locked.updated_at = now_iso()
                    write_feature(loaded.paths, locked)
                    release_feature_lock(loaded.paths, locked.feature_id)
                else:
                    feature.status = "error"
                    feature.updated_at = now_iso()
                    write_feature(loaded.paths, feature)

    await asyncio.gather(*(worker(feature) for feature in features))
    fatal_errors = [error for error in errors if error.code not in _NONFATAL_REVIEW_ERROR_CODES]
    run.status = "failed" if fatal_errors else "completed"
    run.finished_at = now_iso()
    run.finding_ids = finding_ids
    run.errors = errors
    write_run(loaded.paths, run)
    report_path = _write_markdown_report(
        loaded.paths, read_findings(loaded.paths), read_features(loaded.paths)
    )
    if fatal_errors:
        raise ReviewflowWorkflowError(
            fatal_errors[0].message, fatal_errors[0].code or "review-failed"
        )
    return {
        "run": current_run_id,
        "reviewed": len(features),
        "findings": len(finding_ids),
        "jobs": max(1, min(jobs, max(len(features), 1))),
        "report": str(report_path),
        "next": f"pythinker review fix --finding {finding_ids[0]}"
        if finding_ids
        else "pythinker review status",
    }


def report_project(
    *,
    root: Path,
    state_dir: str | None = None,
    config_path: Path | None = None,
    status: str | None = None,
    severity: str | None = None,
    feature_id: str | None = None,
    project_filter: str | None = None,
    category: str | None = None,
    triage: str | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    loaded = load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    features = read_features(loaded.paths)
    filtered = filter_findings(
        read_findings(loaded.paths),
        features=features,
        status=status,
        severity=severity,
        feature_id=feature_id,
        project_filter=project_filter,
        category=category,
        triage=triage,
    )
    markdown = render_report(filtered, features)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
    return {
        "markdown": markdown,
        "output": str(output) if output else None,
        "findings": len(filtered),
        "total": len(filtered),
        "items": [finding_summary(item, _feature_for(item, features)) for item in filtered],
        "results": [finding_summary(item, _feature_for(item, features)) for item in filtered],
    }


def show_finding_project(
    *, root: Path, finding_id: str, state_dir: str | None = None, config_path: Path | None = None
) -> dict[str, Any]:
    loaded = load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    finding = read_finding(loaded.paths, finding_id)
    if finding is None:
        raise ReviewflowWorkflowError(f"finding not found: {finding_id}", "finding-not-found")
    features = read_features(loaded.paths)
    feature = _feature_for(finding, features)
    patches = [
        patch for patch in read_patch_attempts(loaded.paths) if finding_id in patch.finding_ids
    ]
    markdown = render_finding_detail(finding, feature, patches)
    return {
        "markdown": markdown,
        "finding": finding_summary(finding, feature),
        "feature": feature.model_dump(by_alias=True) if feature else None,
        "patchAttempts": [patch.model_dump(by_alias=True) for patch in patches],
        "next": f"pythinker review triage --finding {finding.finding_id} --status <status>",
    }


def next_project(
    *, root: Path, state_dir: str | None = None, config_path: Path | None = None
) -> dict[str, Any]:
    loaded = load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    finding = next_finding(read_findings(loaded.paths))
    if finding is None:
        return {"finding": None, "status": "open", "next": "pythinker review report --status open"}
    feature = _feature_for(finding, read_features(loaded.paths))
    return {
        "finding": finding_summary(finding, feature),
        "next": f"pythinker review show --finding {finding.finding_id}",
    }


def triage_project(
    *,
    root: Path,
    finding_id: str,
    status: str,
    note: str | None = None,
    state_dir: str | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    if status not in {"open", "false-positive", "fixed", "wont-fix", "uncertain"}:
        raise ReviewflowWorkflowError("invalid status", "invalid-usage")
    loaded = load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    finding = read_finding(loaded.paths, finding_id)
    if finding is None:
        raise ReviewflowWorkflowError(f"finding not found: {finding_id}", "finding-not-found")
    finding.status = status  # type: ignore[assignment]
    finding.updated_at = now_iso()
    finding.history.append(
        FindingHistoryEntry(kind="triage", status=status, note=note, created_at=now_iso())  # type: ignore[arg-type]
    )
    write_finding(loaded.paths, finding)
    _refresh_feature_status(loaded.paths, finding.feature_id)
    return {"finding": finding_id, "status": status, "note": note, "next": "pythinker review next"}


async def revalidate_project(
    *,
    llm: ReviewLLM,
    root: Path,
    state_dir: str | None = None,
    config_path: Path | None = None,
    finding_id: str | None = None,
    all_findings: bool = False,
    status: str | None = "open",
    limit: int | None = None,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    loaded = load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    findings = read_findings(loaded.paths)
    if finding_id:
        findings = [finding for finding in findings if finding.finding_id == finding_id]
    elif all_findings:
        if status:
            findings = [finding for finding in findings if finding.status == status]
    else:
        raise ReviewflowWorkflowError("use --finding or --all", "invalid-usage")
    if limit is not None:
        findings = findings[:limit]
    current_run_id = run_id()
    run = _new_run("revalidate", loaded, current_run_id)
    run.finding_ids = [finding.finding_id for finding in findings]
    write_run(loaded.paths, run)
    results: list[dict[str, str]] = []
    try:
        for finding in findings:
            output = await revalidate_finding(
                llm=llm, root=loaded.root, finding=finding, timeout_s=timeout_s
            )
            finding.status = output.outcome
            finding.updated_at = now_iso()
            finding.history.append(
                FindingHistoryEntry(
                    run_id=current_run_id,
                    kind="revalidate",
                    status=output.outcome,
                    reasoning=output.reasoning,
                    commands=output.commands,
                    created_at=now_iso(),
                )
            )
            write_finding(loaded.paths, finding)
            _refresh_feature_status(loaded.paths, finding.feature_id)
            results.append(
                {
                    "finding": finding.finding_id,
                    "outcome": output.outcome,
                    "reasoning": output.reasoning,
                }
            )
        run.status = "completed"
        run.finished_at = now_iso()
        write_run(loaded.paths, run)
    except Exception as exc:  # noqa: BLE001 - provider boundary
        run.status = "failed"
        run.finished_at = now_iso()
        run.errors = [RunError(message=str(exc), code="revalidate-failed")]
        write_run(loaded.paths, run)
        raise
    return {
        "revalidated": len(results),
        "open": len([item for item in results if item["outcome"] == "open"]),
        "fixed": len([item for item in results if item["outcome"] == "fixed"]),
        "falsePositive": len([item for item in results if item["outcome"] == "false-positive"]),
        "uncertain": len([item for item in results if item["outcome"] == "uncertain"]),
        "results": results,
        "next": "pythinker review next",
    }


async def fix_project(
    *,
    llm: ReviewLLM,
    root: Path,
    finding_id: str,
    state_dir: str | None = None,
    config_path: Path | None = None,
    dry_run: bool = False,
    timeout_s: float = 240.0,
) -> dict[str, Any]:
    loaded = load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    if (
        loaded.config.git.require_clean_worktree_for_fix
        and source_dirty(loaded.root, state_dir=loaded.paths.state_dir)
        and not dry_run
    ):
        raise ReviewflowWorkflowError(
            "dirty worktree blocks fix; commit/stash first or use --dry-run", "dirty-worktree"
        )
    finding = read_finding(loaded.paths, finding_id)
    if finding is None:
        raise ReviewflowWorkflowError(f"finding not found: {finding_id}", "finding-not-found")
    feature = read_feature(loaded.paths, finding.feature_id)
    if feature is None:
        raise ReviewflowWorkflowError(
            f"feature not found: {finding.feature_id}", "feature-not-found"
        )
    patch_id = stable_id("pat", [finding.finding_id, now_iso()])
    _git_root, _remote, _default, branch, head, _dirty = discover_git(loaded.root)
    initial = PatchAttempt(
        patch_attempt_id=patch_id,
        finding_ids=[finding.finding_id],
        feature_ids=[feature.feature_id],
        status="planned",
        plan=f"Fix {finding.title}",
        git=PatchGit(base_sha=head, branch_name=branch),
        created_at=now_iso(),
        updated_at=now_iso(),
    )
    commands = validation_commands_for_feature(feature, loaded.config)
    if dry_run:
        return {
            "finding": finding.finding_id,
            "dryRun": True,
            "patchAttempt": patch_id,
            "plan": initial.plan,
            "validation": "; ".join(commands) if commands else "none",
        }
    write_patch_attempt(loaded.paths, initial)
    initial.status = "applying"
    initial.updated_at = now_iso()
    write_patch_attempt(loaded.paths, initial)
    provider_started = now_iso()
    try:
        output = await plan_fix(
            llm=llm,
            root=loaded.root,
            finding=finding,
            feature=feature,
            config=loaded.config,
            timeout_s=timeout_s,
        )
        _apply_fix_plan(
            loaded.root,
            output,
            allowed_paths=_fix_allowed_paths(feature=feature, finding=finding),
        )
    except Exception as exc:  # noqa: BLE001 - provider boundary
        initial.status = "failed"
        initial.plan = f"{initial.plan}\n\nProvider/apply failed: {exc}"
        initial.provider = PatchProvider(
            name=loaded.config.provider.name,
            model=loaded.config.provider.model or llm.model_display_name,
            reasoning_effort=loaded.config.provider.reasoning_effort,
            started_at=provider_started,
            finished_at=now_iso(),
        )
        initial.updated_at = now_iso()
        write_patch_attempt(loaded.paths, initial)
        finding.linked_patch_attempt_ids = sorted({*finding.linked_patch_attempt_ids, patch_id})
        finding.updated_at = now_iso()
        write_finding(loaded.paths, finding)
        raise ReviewflowWorkflowError(str(exc), "fix-failed") from exc

    # Split commands by trust: user-configured commands run with the shell so
    # composed lines like `pnpm lint && pnpm test` work. Model-suggested
    # commands (output.commands) run via shlex.split + shell=False with a
    # binary allow-list derived from the configured commands — the model
    # cannot introduce a new binary or inject shell metacharacters.
    trusted_commands = _dedupe_commands(commands)
    allowed_binaries = _binary_allowlist(trusted_commands)
    trusted_results = [run_shell_command(command, cwd=loaded.root) for command in trusted_commands]
    model_results = [
        run_untrusted_command(command, cwd=loaded.root, allowed_binaries=allowed_binaries)
        for command in _dedupe_commands(output.commands)
        if command not in trusted_commands
    ]
    command_results = trusted_results + model_results
    changed_files = _changed_source_files(loaded.root, loaded.paths.state_dir)
    failed = any(result.exit_code not in {0} for result in command_results)
    patch_data = initial.model_dump()
    patch_data.update(
        {
            "status": "failed" if failed else ("validated" if command_results else "applied"),
            "plan": output.summary,
            "files_changed": changed_files,
            "commands_run": command_results,
            "test_results": command_results,
            "provider": PatchProvider(
                name=loaded.config.provider.name,
                model=loaded.config.provider.model or llm.model_display_name,
                reasoning_effort=loaded.config.provider.reasoning_effort,
                started_at=provider_started,
                finished_at=now_iso(),
            ),
            "updated_at": now_iso(),
        }
    )
    patch = PatchAttempt.model_validate(patch_data)
    write_patch_attempt(loaded.paths, patch)
    finding.linked_patch_attempt_ids = sorted({*finding.linked_patch_attempt_ids, patch_id})
    finding.status = "open" if failed else "uncertain"
    finding.updated_at = now_iso()
    finding.history.append(
        FindingHistoryEntry(
            kind="fix",
            status=finding.status,
            note=f"patch attempt {patch_id}",
            commands=[result.command for result in command_results],
            created_at=now_iso(),
        )
    )
    write_finding(loaded.paths, finding)
    _refresh_feature_status(loaded.paths, feature.feature_id)
    if failed:
        raise ReviewflowWorkflowError("validation failed after applying fix", "validation-failed")
    return {
        "finding": finding.finding_id,
        "dryRun": False,
        "patchAttempt": patch_id,
        "status": patch.status,
        "filesChanged": len(changed_files),
        "changedFiles": ", ".join(changed_files) if changed_files else "none",
        "commands": len(command_results),
        "validation": "; ".join(
            f"{result.command} => {result.exit_code if result.exit_code is not None else 'unknown'}"
            for result in command_results
        )
        or "none",
        "next": f"pythinker review revalidate --finding {finding.finding_id}",
    }


def open_pr_project(
    *,
    root: Path,
    patch_id: str,
    state_dir: str | None = None,
    config_path: Path | None = None,
    base: str | None = None,
    branch: str | None = None,
    title: str | None = None,
    draft: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    loaded = load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    patch = read_patch_attempt(loaded.paths, patch_id)
    if patch is None:
        raise ReviewflowWorkflowError(f"patch attempt not found: {patch_id}", "patch-not-found")
    if patch.status not in {"applied", "validated"} and not force:
        raise ReviewflowWorkflowError(
            "patch is not applied; use --force to override", "invalid-usage"
        )
    git_root, _remote, default_branch, current_branch, _head, _dirty = discover_git(loaded.root)
    if git_root is None:
        raise ReviewflowWorkflowError("open-pr requires a git repository", "not-git-repository")
    base_branch = _validate_git_ref(base or default_branch or "main", field="base")
    pr_branch = _validate_git_ref(
        branch or patch.git.branch_name or f"pythinker/{patch.patch_attempt_id}", field="branch"
    )
    pr_title = _validate_single_line(
        title or patch.plan.splitlines()[0][:72] or f"Fix {patch.patch_attempt_id}",
        field="title",
    )
    files_to_add = _validate_repo_paths(patch.files_changed, field="filesChanged")
    add_args = ["git", "add", "--", *files_to_add] if files_to_add else ["git", "add", "-A"]
    pr_args_preview = _pr_create_args(base_branch, pr_branch, pr_title, draft, body=_pr_body(patch))
    commands = [
        shlex.join(["git", "checkout", "-B", pr_branch]),
        shlex.join(add_args),
        shlex.join(["git", "commit", "-m", pr_title]),
        shlex.join(["git", "push", "-u", "origin", pr_branch]),
        shlex.join(pr_args_preview),
    ]
    if dry_run:
        return {
            "patchAttempt": patch.patch_attempt_id,
            "branch": pr_branch,
            "base": base_branch,
            "title": pr_title,
            "dryRun": True,
            "commands": commands,
        }
    if current_branch != pr_branch:
        _check(run_process(["git", "checkout", "-B", pr_branch], cwd=loaded.root), "git checkout")
    _check(run_process(add_args, cwd=loaded.root), "git add")
    commit = run_process(["git", "commit", "-m", pr_title], cwd=loaded.root, timeout_s=120.0)
    _check(commit, "git commit")
    commit_sha = git_output(loaded.root, ["rev-parse", "HEAD"])
    _check(
        run_process(["git", "push", "-u", "origin", pr_branch], cwd=loaded.root, timeout_s=300.0),
        "git push",
    )
    pr_args = _pr_create_args(base_branch, pr_branch, pr_title, draft, body=_pr_body(patch))
    pr = run_process(pr_args, cwd=loaded.root, timeout_s=120.0)
    _check(pr, "gh pr create")
    patch.git.commit_sha = commit_sha
    patch.git.branch_name = pr_branch
    patch.git.pr_url = pr.stdout.strip() or None
    patch.updated_at = now_iso()
    write_patch_attempt(loaded.paths, patch)
    return {
        "patchAttempt": patch.patch_attempt_id,
        "branch": pr_branch,
        "base": base_branch,
        "commit": commit_sha,
        "pr": patch.git.pr_url,
    }


async def ci_project(
    *,
    llm: ReviewLLM,
    root: Path,
    state_dir: str | None = None,
    config_path: Path | None = None,
    limit: int | None = None,
    since: str | None = None,
    jobs: int = 1,
    output: Path | None = None,
    include_dirty: bool = False,
) -> dict[str, Any]:
    initialized = False
    try:
        load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    except ReviewflowWorkflowError:
        init_project(root=root, state_dir=state_dir, config_path=config_path)
        initialized = True
    mapped = map_project(root=root, state_dir=state_dir, config_path=config_path)
    reviewed = await review_project(
        llm=llm,
        root=root,
        state_dir=state_dir,
        config_path=config_path,
        since=since,
        include_dirty=include_dirty,
        limit=limit,
        jobs=jobs,
    )
    report = report_project(root=root, state_dir=state_dir, config_path=config_path, output=output)
    summary = report["markdown"]
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with Path(step_summary).open("a", encoding="utf-8") as handle:
            handle.write(str(summary))
    return {
        "initialized": initialized,
        "mapped": mapped["features"],
        "reviewed": reviewed["reviewed"],
        "findings": reviewed["findings"],
        "reportFindings": report["findings"],
        "report": report["output"],
        "githubStepSummary": step_summary,
        "next": reviewed["next"],
    }


def doctor_project(*, llm: ReviewLLM | None = None, root: Path) -> dict[str, Any]:
    git_ok = git_output(root.resolve(), ["--version"]) is not None
    gh_ok = _binary_available(root, "gh")
    return {
        "git": "ok" if git_ok else "missing",
        "gh": "ok" if gh_ok else "missing",
        "provider": "ok" if llm is not None else "missing",
        "model": llm.model_display_name if llm is not None else None,
    }


def clean_locks_project(
    *, root: Path, state_dir: str | None = None, config_path: Path | None = None
) -> dict[str, Any]:
    loaded = load_project_state(root=root.resolve(), state_dir=state_dir, config_path=config_path)
    cleared, lock_files_cleared = clear_feature_locks(loaded.paths)
    return {"cleared": cleared, "lockFilesCleared": lock_files_cleared}


def filter_findings(
    findings: list[FindingRecord],
    *,
    features: list[FeatureRecord],
    status: str | None = None,
    severity: str | None = None,
    feature_id: str | None = None,
    project_filter: str | None = None,
    category: str | None = None,
    triage: str | None = None,
) -> list[FindingRecord]:
    feature_by_id = {feature.feature_id: feature for feature in features}
    out = findings
    if status:
        out = [finding for finding in out if finding.status == status]
    if severity:
        out = [finding for finding in out if finding.severity == severity]
    if feature_id:
        out = [finding for finding in out if finding.feature_id == feature_id]
    if category:
        out = [finding for finding in out if finding.category == category]
    if triage:
        out = [finding for finding in out if finding.triage == triage]
    if project_filter:
        lowered = project_filter.lower()
        out = [
            finding
            for finding in out
            if (feature := feature_by_id.get(finding.feature_id)) is not None
            and (
                lowered in feature.title.lower()
                or any(ref.path.startswith(project_filter) for ref in feature.owned_files)
            )
        ]
    return out


def _new_run(command: str, loaded: LoadedState, current_run_id: str) -> RunRecord:
    _git_root, _remote, _default, _branch, head, _dirty = discover_git(loaded.root)
    return RunRecord(
        run_id=current_run_id,
        command=command,  # type: ignore[arg-type]
        args=[],
        status="running",
        root_path=str(loaded.root),
        head_sha=head,
        started_at=now_iso(),
    )


def _drop_run_error(feature_id: str, drop: ReviewDrop) -> RunError:
    return RunError(
        message=(
            f"dropped 1 finding from feature {feature_id} at "
            f"{'.'.join(str(item) for item in drop.path)}: {drop.message}"
        ),
        code=f"{drop.layer}-drop",
    )


def _validated_review_findings(
    root: Path,
    manifest: ReviewPromptManifest,
    findings: list[Any],
) -> tuple[list[Any], list[ReviewDrop]]:
    out: list[Any] = []
    drops: list[ReviewDrop] = []
    for idx, finding in enumerate(findings):
        if not finding.evidence:
            drops.append(
                ReviewDrop(
                    path=("findings", idx, "evidence"),
                    message="finding has no evidence",
                    layer="validation",
                )
            )
            continue
        failures = [
            reason
            for evidence in finding.evidence
            if (reason := _evidence_validation_failure(root, evidence, manifest)) is not None
        ]
        if failures:
            drops.append(
                ReviewDrop(
                    path=("findings", idx, "evidence"),
                    message=failures[0],
                    layer="validation",
                )
            )
            continue
        out.append(finding)
    return out, drops


def _evidence_validation_failure(
    root: Path, evidence: EvidenceRef, manifest: ReviewPromptManifest
) -> str | None:
    prompt_file = next(
        (
            file
            for file in manifest.included_files
            if file.path == _normalize_repo_path(evidence.path)
        ),
        None,
    )
    if prompt_file is None:
        return f"evidence file was not included in review context: {evidence.path}"
    if not prompt_file.readable:
        return f"evidence file was not readable in review context: {evidence.path}"
    try:
        resolved = (root / evidence.path).resolve()
        resolved.relative_to(root.resolve())
    except ValueError:
        return f"evidence file escapes repository root: {evidence.path}"
    if not resolved.is_file():
        return f"evidence file is not readable inside repository: {evidence.path}"
    text = resolved.read_text(encoding="utf-8", errors="replace")
    if evidence.start_line is None and evidence.end_line is None:
        if not evidence.quote or not evidence.quote.strip():
            return f"evidence must include a line range or quote: {evidence.path}"
    elif evidence.start_line is None or evidence.end_line is None:
        return f"evidence line range must include both startLine and endLine: {evidence.path}"
    else:
        if evidence.start_line > evidence.end_line:
            return f"evidence line range is inverted: {evidence.path}"
        if evidence.end_line > _review_line_count(text):
            return f"evidence line range exceeds file length: {evidence.path}"
        if not _range_included(evidence.start_line, evidence.end_line, prompt_file):
            return f"evidence line range was not included in review context: {evidence.path}"
    if evidence.quote and evidence.quote.strip():
        target = prompt_file.included_text
        if evidence.start_line is not None and evidence.end_line is not None:
            target = "\n".join(text.splitlines()[evidence.start_line - 1 : evidence.end_line])
        if evidence.quote not in target and _compact_whitespace(
            evidence.quote
        ) not in _compact_whitespace(target):
            return f"evidence quote does not match file contents: {evidence.path}"
    return None


def _review_line_count(contents: str) -> int:
    if contents == "":
        return 1
    count = contents.count("\n")
    return count if contents.endswith("\n") else count + 1


def _range_included(start_line: int, end_line: int, prompt_file: Any) -> bool:
    return any(
        start_line >= line_range.start_line and end_line <= line_range.end_line
        for line_range in prompt_file.included_line_ranges
    )


def _compact_whitespace(value: str) -> str:
    return " ".join(value.split())


def _merge_review_findings(
    loaded: LoadedState, feature: FeatureRecord, findings: list[Any], run_id_value: str
) -> list[str]:
    existing = read_findings(loaded.paths)
    by_signature = {finding.signature: finding for finding in existing}
    ids: list[str] = []
    for raw in findings:
        signature = stable_id(
            "sig",
            [
                feature.feature_id,
                raw.title,
                raw.category,
                json.dumps(
                    [evidence.model_dump(by_alias=True) for evidence in raw.evidence],
                    sort_keys=True,
                ),
            ],
            length=16,
        )
        prior = by_signature.get(signature)
        finding_id = prior.finding_id if prior else stable_id("fnd", [signature])
        created_at = prior.created_at if prior else now_iso()
        history = prior.history if prior else []
        linked = prior.linked_patch_attempt_ids if prior else []
        status = prior.status if prior else "open"
        record = FindingRecord(
            finding_id=finding_id,
            feature_id=feature.feature_id,
            title=raw.title,
            category=raw.category,
            severity=raw.severity,
            confidence=raw.confidence,
            triage=derive_finding_triage(raw.category, raw.confidence),
            evidence=raw.evidence,
            reasoning=raw.reasoning,
            reproduction=raw.reproduction,
            recommendation=raw.recommendation,
            why_tests_do_not_already_cover_this=raw.why_tests_do_not_already_cover_this,
            suggested_regression_test=raw.suggested_regression_test,
            minimum_fix_scope=raw.minimum_fix_scope,
            status=status,
            history=history,
            signature=signature,
            linked_patch_attempt_ids=linked,
            created_by_run_id=prior.created_by_run_id if prior else run_id_value,
            created_at=created_at,
            updated_at=now_iso(),
        )
        write_finding(loaded.paths, record)
        ids.append(finding_id)
    return ids


def _mark_feature_reviewed(
    loaded: LoadedState,
    feature: FeatureRecord,
    finding_ids: list[str],
    run_id_value: str,
    *,
    provider: str,
    manifest: ReviewPromptManifest,
    dropped: int,
) -> None:
    all_ids = sorted({*feature.finding_ids, *finding_ids})
    feature.finding_ids = all_ids
    feature.status = "needs-fix" if finding_ids else "reviewed"
    feature.lock = None
    feature.updated_at = now_iso()
    feature.analysis_history.append(
        AnalysisEntry(
            run_id=run_id_value,
            kind="review",
            summary=(
                f"Reviewed with {len(finding_ids)} findings; dropped {dropped}; "
                f"context {len(manifest.included_files)} files, "
                f"~{manifest.approximate_tokens} tokens."
            ),
            provider=provider,
            model=loaded.config.provider.model,
            reasoning_effort=loaded.config.provider.reasoning_effort,
            created_at=now_iso(),
        )
    )
    write_feature(loaded.paths, feature)


def _write_markdown_report(
    paths: StatePaths, findings: list[FindingRecord], features: list[FeatureRecord]
) -> Path:
    path = paths.reports / f"{run_id()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(findings, features), encoding="utf-8")
    return path


def _feature_touches(feature: FeatureRecord, changed: set[str]) -> bool:
    paths = {ref.path for ref in feature.owned_files} | {ref.path for ref in feature.context_files}
    return bool(paths & changed)


def _feature_for(finding: FindingRecord, features: list[FeatureRecord]) -> FeatureRecord | None:
    return next((feature for feature in features if feature.feature_id == finding.feature_id), None)


def _dedupe_commands(commands: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for command in commands:
        if command in seen:
            continue
        seen.add(command)
        out.append(command)
    return out


def _binary_allowlist(trusted_commands: list[str]) -> tuple[str, ...]:
    """Extract the binary basenames the user has approved via configured commands.

    Model-suggested commands are only permitted to invoke a binary from this
    set, so a model can request `pytest -xvs tests/foo.py` but cannot request
    `curl evil.com`.
    """
    import shlex
    from pathlib import Path as _Path

    binaries: set[str] = set()
    for raw in trusted_commands:
        try:
            tokens = shlex.split(raw, posix=True)
        except ValueError:
            continue
        for token in tokens:
            if token in {"&&", "||", "|", ";"} or "=" in token:
                continue
            name = _Path(token).name
            if name and not name.startswith("-"):
                binaries.add(name)
                break  # only the leading binary of each pipeline segment
    return tuple(sorted(binaries))


def _changed_source_files(root: Path, state_dir: Path) -> list[str]:
    paths = dirty_files(root)
    state_rel = state_dir.relative_to(root).as_posix() if state_dir.is_relative_to(root) else ""
    if not state_rel:
        return sorted(paths)
    return sorted(
        path for path in paths if not (path == state_rel or path.startswith(f"{state_rel}/"))
    )


def _fix_allowed_paths(*, feature: FeatureRecord, finding: FindingRecord) -> set[str]:
    paths = {ref.path for ref in feature.owned_files}
    paths.update(test.path for test in feature.tests)
    paths.update(evidence.path for evidence in finding.evidence)
    normalized: set[str] = set()
    for path in paths:
        value = _normalize_repo_path(path)
        if value is not None:
            normalized.add(value)
    return normalized


def _normalize_repo_path(path: str) -> str | None:
    normalized = path.replace("\\", "/").removeprefix("./")
    if (
        not normalized
        or normalized == "/dev/null"
        or normalized.startswith("/")
        or normalized == ".."
        or normalized.startswith("../")
        or "/../" in f"/{normalized}/"
        or "\0" in normalized
        or normalized.startswith(".git/")
        or normalized.startswith(".pythinker-review-flow/")
        or normalized.startswith(".pythinker-review/")
        or normalized.startswith(".clawpatch/")
    ):
        return None
    return normalized


_DIFF_GIT_RE = re.compile(r"^diff --git[ \t]+a/(?P<old>.+?)[ \t]+b/(?P<new>.+)$")


def _diff_paths(diff: str) -> set[str]:
    paths: set[str] = set()
    in_hunk = False
    for raw_line in diff.splitlines():
        line = raw_line.rstrip("\n")
        if line.startswith("diff --git "):
            in_hunk = False
            match = _DIFF_GIT_RE.match(line)
            if match:
                for value in (match.group("old"), match.group("new")):
                    normalized = _normalize_diff_path(value)
                    if normalized is not None:
                        paths.add(normalized)
            continue
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk and line.startswith(("--- ", "+++ ")):
            value = line[4:].split("\t", 1)[0].strip()
            normalized = _normalize_diff_path(value)
            if normalized is not None:
                paths.add(normalized)
    return paths


def _normalize_diff_path(value: str) -> str | None:
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if value == "/dev/null":
        return None
    if value.startswith(("a/", "b/")):
        value = value[2:]
    return _normalize_repo_path(value)


def _validate_fix_diff_scope(diff: str, *, allowed_paths: set[str]) -> None:
    changed = _diff_paths(diff)
    if not changed:
        raise ReviewflowWorkflowError(
            "fix provider returned a diff with no file paths", "empty-patch"
        )
    disallowed = sorted(path for path in changed if path not in allowed_paths)
    if disallowed:
        raise ReviewflowWorkflowError(
            "fix provider diff touches files outside the selected finding/feature scope: "
            + ", ".join(disallowed),
            "patch-scope-violation",
        )


_GIT_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _validate_git_ref(value: str, *, field: str) -> str:
    if (
        not value
        or value == "@"
        or value.startswith("-")
        or value.startswith("/")
        or value.endswith("/")
        or value.endswith(".")
        or ".." in value
        or "@{" in value
        or "//" in value
        or not _GIT_REF_RE.fullmatch(value)
    ):
        raise ReviewflowWorkflowError(f"unsafe git {field}: {value!r}", "invalid-usage")
    components = value.split("/")
    for component in components:
        if component.startswith(".") or component.endswith(".lock"):
            raise ReviewflowWorkflowError(f"unsafe git {field}: {value!r}", "invalid-usage")
    return value


def _validate_single_line(value: str, *, field: str) -> str:
    if any(ch in value for ch in "\r\n\0"):
        raise ReviewflowWorkflowError(f"unsafe {field}: must be a single line", "invalid-usage")
    stripped = value.strip()
    if not stripped:
        raise ReviewflowWorkflowError(f"unsafe {field}: must not be empty", "invalid-usage")
    return stripped


def _validate_repo_paths(paths: list[str], *, field: str) -> list[str]:
    normalized_paths: list[str] = []
    for path in paths:
        if any(ch in path for ch in "\r\n\0"):
            raise ReviewflowWorkflowError(f"unsafe {field}: {path!r}", "invalid-usage")
        normalized = _normalize_repo_path(path)
        if normalized is None:
            raise ReviewflowWorkflowError(f"unsafe {field}: {path!r}", "invalid-usage")
        normalized_paths.append(normalized)
    return normalized_paths


def _pr_create_args(
    base_branch: str, pr_branch: str, pr_title: str, draft: bool, *, body: str
) -> list[str]:
    args = [
        "gh",
        "pr",
        "create",
        "--base",
        base_branch,
        "--head",
        pr_branch,
        "--title",
        pr_title,
        "--body",
        body,
    ]
    if draft:
        args.append("--draft")
    return args


def _refresh_feature_status(paths: StatePaths, feature_id: str) -> None:
    feature = read_feature(paths, feature_id)
    if feature is None:
        return
    findings = [finding for finding in read_findings(paths) if finding.feature_id == feature_id]
    if any(finding.status == "open" for finding in findings):
        feature.status = "needs-fix"
    elif findings and all(finding.status == "fixed" for finding in findings):
        feature.status = "fixed"
    elif findings:
        feature.status = "revalidated"
    else:
        feature.status = "reviewed"
    feature.updated_at = now_iso()
    write_feature(paths, feature)


def _apply_fix_plan(root: Path, output: FixPlanOutput, *, allowed_paths: set[str]) -> None:
    diff = output.unified_diff
    if not diff or not diff.strip():
        raise ReviewflowWorkflowError("fix provider returned no unifiedDiff", "empty-patch")
    _validate_fix_diff_scope(diff, allowed_paths=allowed_paths)
    proc = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        cwd=root,
        input=diff,
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if proc.returncode != 0:
        raise ReviewflowWorkflowError(
            proc.stderr.strip() or "git apply failed", "patch-apply-failed"
        )


def _check(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if proc.returncode != 0:
        raise ReviewflowWorkflowError(
            f"{label} failed: {proc.stderr.strip() or proc.stdout.strip()}", "command-failed"
        )


def _pr_body(patch: PatchAttempt) -> str:
    return (
        f"Patch attempt: `{patch.patch_attempt_id}`\n\n"
        f"Status: `{patch.status}`\n\n"
        f"Files changed:\n" + "\n".join(f"- `{path}`" for path in patch.files_changed)
    )


def _binary_available(root: Path, name: str) -> bool:
    try:
        proc = run_process([name, "--version"], cwd=root, timeout_s=5.0)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


__all__ = [
    "ReviewflowWorkflowError",
    "ci_project",
    "clean_locks_project",
    "doctor_project",
    "fix_project",
    "init_project",
    "map_project",
    "next_project",
    "open_pr_project",
    "report_project",
    "revalidate_project",
    "review_project",
    "show_finding_project",
    "status_project",
    "triage_project",
]
