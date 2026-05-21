"""Reviewflow durable workflow models.

The TypeScript Reviewflow repository stores camelCase JSON records under `.pythinker-review-flow/`.
These Pydantic models keep Python attribute names while serializing to that compatible
shape where practical.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]
FindingCategory = Literal[
    "bug",
    "security",
    "performance",
    "concurrency",
    "api-contract",
    "data-loss",
    "test-gap",
    "docs-gap",
    "build-release",
    "maintainability",
]
FindingTriage = Literal["confirmed-bug", "contract-mismatch", "risk", "test-gap", "docs-gap"]
FindingStatus = Literal["open", "false-positive", "fixed", "wont-fix", "uncertain"]
FeatureKind = Literal[
    "cli-command",
    "route",
    "ui-flow",
    "service",
    "job",
    "agent-tool",
    "library",
    "config",
    "release",
    "test-suite",
    "infra",
    "unknown",
]
FeatureStatus = Literal[
    "pending",
    "claimed",
    "reviewed",
    "needs-fix",
    "fixing",
    "fixed",
    "revalidated",
    "skipped",
    "error",
]
TrustBoundary = Literal[
    "user-input",
    "network",
    "filesystem",
    "secrets",
    "process-exec",
    "database",
    "auth",
    "permissions",
    "concurrency",
    "external-api",
    "serialization",
]
Severity = Literal["critical", "high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]
RunCommand = Literal["map", "review", "ci", "revalidate", "fix", "open-pr"]
RunStatus = Literal["running", "completed", "failed", "cancelled"]
PatchStatus = Literal["planned", "applying", "applied", "validated", "failed", "abandoned"]
MapSource = Literal["heuristic", "auto", "agent"]


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


class ReviewflowBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_camel)


class ProjectCommands(ReviewflowBaseModel):
    typecheck: str | None = None
    lint: str | None = None
    format: str | None = None
    test: str | None = None


class ProviderConfig(ReviewflowBaseModel):
    name: str = "pythinker"
    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None


class ReviewConfig(ReviewflowBaseModel):
    max_context_files: int = Field(default=24, ge=1)
    max_owned_files: int = Field(default=12, ge=1)
    max_findings_per_feature: int = Field(default=10, ge=1)
    min_confidence_to_fix: Confidence = "medium"


class GitConfig(ReviewflowBaseModel):
    require_clean_worktree_for_fix: bool = True
    commit: bool = False
    open_pr: bool = False


class ReviewflowConfig(ReviewflowBaseModel):
    schema_version: Literal[1] = 1
    state_dir: str = ".pythinker-review-flow"
    include: list[str] = Field(default_factory=lambda: ["**/*"])
    exclude: list[str] = Field(
        default_factory=lambda: [
            "node_modules/**",
            "dist/**",
            "build/**",
            "target/**",
            ".build/**",
            ".git/**",
            ".pythinker-review-flow/**",
            ".pythinker-review/**",
        ]
    )
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    commands: ProjectCommands = Field(default_factory=ProjectCommands)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    git: GitConfig = Field(default_factory=GitConfig)


class GitInfo(ReviewflowBaseModel):
    remote_url: str | None = None
    default_branch: str | None = None
    current_branch: str | None = None
    head_sha: str | None = None


class DetectedProject(ReviewflowBaseModel):
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    commands: ProjectCommands = Field(default_factory=ProjectCommands)


class ProjectRecord(ReviewflowBaseModel):
    schema_version: Literal[1] = 1
    project_id: str
    name: str
    root_path: str
    git: GitInfo = Field(default_factory=GitInfo)
    detected: DetectedProject = Field(default_factory=DetectedProject)
    created_at: str
    updated_at: str


class FeatureFileRef(ReviewflowBaseModel):
    path: str
    reason: str


class FeatureEntrypoint(ReviewflowBaseModel):
    path: str
    symbol: str | None = None
    route: str | None = None
    command: str | None = None


class FeatureTestRef(ReviewflowBaseModel):
    path: str
    command: str | None = None


class AnalysisEntry(ReviewflowBaseModel):
    run_id: str
    kind: str
    summary: str
    provider: str | None = None
    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    created_at: str


class FeatureLock(ReviewflowBaseModel):
    locked_by_run_id: str
    locked_at: str
    hostname: str
    pid: int


class FeatureRecord(ReviewflowBaseModel):
    schema_version: Literal[1] = 1
    feature_id: str
    title: str
    summary: str
    kind: FeatureKind = "unknown"
    source: str = "heuristic"
    confidence: Confidence = "medium"
    entrypoints: list[FeatureEntrypoint] = Field(default_factory=list)
    owned_files: list[FeatureFileRef] = Field(default_factory=list)
    context_files: list[FeatureFileRef] = Field(default_factory=list)
    tests: list[FeatureTestRef] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    trust_boundaries: list[TrustBoundary] = Field(default_factory=list)
    status: FeatureStatus = "pending"
    lock: FeatureLock | None = None
    finding_ids: list[str] = Field(default_factory=list)
    patch_attempt_ids: list[str] = Field(default_factory=list)
    analysis_history: list[AnalysisEntry] = Field(default_factory=list)
    created_at: str
    updated_at: str


class EvidenceRef(ReviewflowBaseModel):
    path: str
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None
    quote: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> EvidenceRef:
        if self.start_line is None or self.end_line is None:
            return self
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("invalid evidence line range")
        return self


class FindingHistoryEntry(ReviewflowBaseModel):
    run_id: str | None = None
    kind: str
    status: FindingStatus | None = None
    note: str | None = None
    reasoning: str | None = None
    commands: list[str] = Field(default_factory=list)
    created_at: str


class FindingRecord(ReviewflowBaseModel):
    schema_version: Literal[1] = 1
    finding_id: str
    feature_id: str
    title: str
    category: FindingCategory
    severity: Severity
    confidence: Confidence
    triage: FindingTriage | None = None
    evidence: list[EvidenceRef]
    reasoning: str
    reproduction: str | None = None
    recommendation: str
    why_tests_do_not_already_cover_this: str | None = None
    suggested_regression_test: str | None = None
    minimum_fix_scope: str | None = None
    status: FindingStatus = "open"
    history: list[FindingHistoryEntry] = Field(default_factory=list)
    signature: str
    linked_patch_attempt_ids: list[str] = Field(default_factory=list)
    created_by_run_id: str
    created_at: str
    updated_at: str


class CommandResult(ReviewflowBaseModel):
    command: str
    cwd: str = ""
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0


class PatchProvider(ReviewflowBaseModel):
    name: str
    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    request_id: str | None = None
    started_at: str
    finished_at: str


class PatchGit(ReviewflowBaseModel):
    base_sha: str | None = None
    commit_sha: str | None = None
    branch_name: str | None = None
    pr_url: str | None = None


class PatchAttempt(ReviewflowBaseModel):
    schema_version: Literal[1] = 1
    patch_attempt_id: str
    finding_ids: list[str]
    feature_ids: list[str]
    status: PatchStatus
    plan: str
    files_changed: list[str] = Field(default_factory=list)
    commands_run: list[CommandResult] = Field(default_factory=list)
    test_results: list[CommandResult] = Field(default_factory=list)
    provider: PatchProvider | None = None
    git: PatchGit = Field(default_factory=PatchGit)
    created_at: str
    updated_at: str


class RunError(ReviewflowBaseModel):
    message: str
    code: str | None = None


class RunRecord(ReviewflowBaseModel):
    schema_version: Literal[1] = 1
    run_id: str
    command: RunCommand
    args: list[str] = Field(default_factory=list)
    root_path: str
    head_sha: str | None = None
    started_at: str
    finished_at: str | None = None
    status: RunStatus
    claimed_feature_ids: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    patch_attempt_ids: list[str] = Field(default_factory=list)
    errors: list[RunError] = Field(default_factory=list)


class FeatureReviewFinding(ReviewflowBaseModel):
    title: str = Field(max_length=120)
    category: FindingCategory
    severity: Severity
    confidence: Confidence
    evidence: list[EvidenceRef]
    reasoning: str
    reproduction: str | None = None
    recommendation: str
    why_tests_do_not_already_cover_this: str | None = None
    suggested_regression_test: str | None = None
    minimum_fix_scope: str | None = None


class FeatureReviewOutput(ReviewflowBaseModel):
    findings: list[FeatureReviewFinding] = Field(default_factory=list)


class RevalidateOutput(ReviewflowBaseModel):
    outcome: FindingStatus
    reasoning: str
    commands: list[str] = Field(default_factory=list)


class FixPlanOutput(ReviewflowBaseModel):
    summary: str
    unified_diff: str | None = None
    commands: list[str] = Field(default_factory=list)


class CommandPayload(ReviewflowBaseModel):
    markdown: str | None = None
    output: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


def derive_finding_triage(category: FindingCategory, confidence: Confidence) -> FindingTriage:
    if category == "test-gap":
        return "test-gap"
    if category == "docs-gap":
        return "docs-gap"
    if category == "api-contract":
        return "contract-mismatch"
    if confidence == "high" and category in {"bug", "security", "data-loss", "concurrency"}:
        return "confirmed-bug"
    return "risk"


__all__ = [
    "AnalysisEntry",
    "ReviewflowConfig",
    "CommandResult",
    "Confidence",
    "DetectedProject",
    "EvidenceRef",
    "FeatureEntrypoint",
    "FeatureFileRef",
    "FeatureLock",
    "FeatureRecord",
    "FeatureReviewFinding",
    "FeatureReviewOutput",
    "FeatureStatus",
    "FeatureTestRef",
    "FindingCategory",
    "FindingHistoryEntry",
    "FindingRecord",
    "FindingStatus",
    "FixPlanOutput",
    "GitConfig",
    "GitInfo",
    "MapSource",
    "PatchAttempt",
    "ProjectCommands",
    "ProjectRecord",
    "ProviderConfig",
    "ReasoningEffort",
    "RevalidateOutput",
    "ReviewConfig",
    "RunCommand",
    "RunError",
    "RunRecord",
    "Severity",
    "derive_finding_triage",
]
