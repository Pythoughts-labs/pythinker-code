"""Reviewflow-style validation for model-emitted findings.

The model is allowed to reason, but findings must stay anchored to the diff/context we actually
showed it. Invalid findings are dropped and surfaced as validation failures rather than being
silently persisted.
"""

from __future__ import annotations

import re
from pathlib import Path

from pythinker_review.engine.chunker import Chunk
from pythinker_review.reviewers.schema import RawFinding

_HUNK_HDR = re.compile(r"^@@ -(?:\d+)(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def validate_findings(
    *, repo: Path | None, chunk: Chunk, findings: tuple[RawFinding, ...]
) -> tuple[tuple[RawFinding, ...], tuple[str, ...]]:
    """Partition findings into valid findings and human-readable validation errors."""
    valid: list[RawFinding] = []
    errors: list[str] = []
    for idx, finding in enumerate(findings):
        error = _validate_one(repo=repo, chunk=chunk, finding=finding)
        if error is None:
            valid.append(finding)
        else:
            errors.append(f"findings[{idx}]: {error}")
    return tuple(valid), tuple(errors)


def _validate_one(*, repo: Path | None, chunk: Chunk, finding: RawFinding) -> str | None:
    normalized = _normalize_path(finding.file)
    if normalized is None:
        return f"finding file escapes repository root: {finding.file}"
    if normalized != chunk.file:
        return f"finding file was not included in this review chunk: {finding.file}"
    if not _range_intersects_chunk(finding.start_line, finding.end_line, chunk):
        return (
            "finding line range is outside the reviewed post-change hunk lines: "
            f"{finding.file}:{finding.start_line}-{finding.end_line}"
        )
    if finding.evidence_snippet and not _snippet_matches(
        repo=repo,
        file_path=normalized,
        start_line=finding.start_line,
        end_line=finding.end_line,
        snippet=finding.evidence_snippet,
        rendered=chunk.rendered,
    ):
        return f"evidence snippet does not match reviewed or current file contents: {finding.file}"
    return None


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_UNC = re.compile(r"^[\\/]{2}[^\\/]+[\\/]")


def _normalize_path(path: str) -> str | None:
    # Reject Windows-style absolute paths *before* normalizing slashes so the
    # check is unambiguous: drive letters (C:/foo, c:\foo) and UNC roots
    # (\\server\share) both escape the repo root on Windows.
    if _WINDOWS_DRIVE.match(path) or _WINDOWS_UNC.match(path):
        return None
    normalized = path.replace("\\", "/").removeprefix("./")
    if normalized.startswith("/") or normalized == ".." or normalized.startswith("../"):
        return None
    if "/../" in f"/{normalized}/" or normalized.startswith(".git/"):
        return None
    return normalized


def _range_intersects_chunk(start_line: int, end_line: int, chunk: Chunk) -> bool:
    ranges = tuple(_new_ranges(chunk))
    if not ranges:
        return True
    return any(start_line <= end and end_line >= start for start, end in ranges)


def _new_ranges(chunk: Chunk) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for hunk in chunk.hunks:
        match = _HUNK_HDR.match(hunk.header)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        # A pure insertion can report count=0 in odd diffs; keep one anchor line for validation.
        ranges.append((start, max(start, start + max(count, 1) - 1)))
    return ranges


def _snippet_matches(
    *,
    repo: Path | None,
    file_path: str,
    start_line: int,
    end_line: int,
    snippet: str,
    rendered: str,
) -> bool:
    target = snippet.strip()
    if not target:
        return True
    if _contains(rendered, target):
        return True
    if repo is None:
        return False
    try:
        content = (repo / file_path).read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return False
    lines = content.splitlines()
    if start_line < 1 or end_line > len(lines):
        return _contains(content, target)
    slice_text = "\n".join(lines[start_line - 1 : end_line])
    return _contains(slice_text, target)


def _contains(haystack: str, needle: str) -> bool:
    return needle in haystack or _compact(needle) in _compact(haystack)


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
