"""Build bounded structured-diff context for PR assistant artifact commands."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from pythinker_review.engine.chunker import build_chunks
from pythinker_review.engine.diff_source import DiffMode, ResolvedDiff, resolve_diff
from pythinker_review.engine.structured_diff import render_structured_diff
from pythinker_review.engine.token_budget import clip_text


@dataclass(frozen=True, slots=True)
class ArtifactDiffContext:
    resolved: ResolvedDiff
    rendered_diff: str
    chunks_total: int
    metadata: dict[str, str]


def build_artifact_context(
    *,
    repo: Path,
    mode: DiffMode,
    base_ref: str,
    rev_range: str | None,
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
    skip_vendored: bool,
    budget_chars: int,
) -> ArtifactDiffContext:
    """Resolve, structure, filter, and clip the diff for non-finding PR workflows."""
    resolved = resolve_diff(repo, mode=mode, base_ref=base_ref, rev_range=rev_range)
    structured_files = render_structured_diff(resolved.patch_text)
    chunks = build_chunks(
        structured_files,
        includes=includes,
        excludes=excludes,
        skip_vendored=skip_vendored,
        budget_chars=max(500, budget_chars),
    )
    rendered = "\n\n".join(chunk.rendered for chunk in chunks)
    rendered = clip_text(rendered, budget_chars)
    metadata = {
        "branch": _branch_name(repo) or "",
        "base_ref": resolved.base_ref,
        "source_label": resolved.source_label,
        "changed_files": ", ".join(resolved.changed_files),
        "head_sha": resolved.head_sha,
        "base_sha": resolved.base_sha,
        "requested_base_ref": resolved.requested_base_ref,
        "fallback_reason": resolved.fallback_reason or "",
        "commit_messages": _commit_messages(repo, resolved) or "",
    }
    return ArtifactDiffContext(
        resolved=resolved,
        rendered_diff=rendered,
        chunks_total=len(chunks),
        metadata=metadata,
    )


def _commit_messages(repo: Path, resolved: ResolvedDiff) -> str | None:
    rev_range = f"{resolved.base_sha}..{resolved.head_sha}"
    try:
        proc = subprocess.run(
            ["git", "log", "--format=%s", "--max-count=20", rev_range],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    messages = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return "\n".join(messages) or None


def _branch_name(repo: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    branch = proc.stdout.strip()
    return branch or None


__all__ = ["ArtifactDiffContext", "build_artifact_context"]
