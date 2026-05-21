"""Gather bounded current/base file context around hunks."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_WINDOW_HALF = 50


@dataclass(frozen=True, slots=True)
class ContextWindow:
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True, slots=True)
class FileContext:
    path: str
    current_full: str | None = None
    current_windows: tuple[ContextWindow, ...] = field(default_factory=tuple)
    base_windows: tuple[ContextWindow, ...] = field(default_factory=tuple)


def gather_context(
    *,
    repo: Path,
    file_path: str,
    hunks_post_lines: list[int],
    budget_chars: int,
    base_sha: str | None,
) -> FileContext:
    full = _read_current(repo, file_path)
    if full is not None and len(full) <= budget_chars:
        return FileContext(path=file_path, current_full=full)
    if full is None:
        return FileContext(path=file_path)
    windows = tuple(_windows_from_lines(full, hunks_post_lines))
    base_windows: tuple[ContextWindow, ...] = ()
    if base_sha:
        base_text = _read_base(repo, base_sha, file_path)
        if base_text:
            base_windows = tuple(_windows_from_lines(base_text, hunks_post_lines))
    return FileContext(path=file_path, current_windows=windows, base_windows=base_windows)


def _read_current(repo: Path, rel_path: str) -> str | None:
    try:
        return (repo / rel_path).read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return None


def _read_base(repo: Path, sha: str, rel_path: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "show", f"{sha}:{rel_path}"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=10.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _windows_from_lines(text: str, line_anchors: list[int]) -> list[ContextWindow]:
    lines = text.splitlines()
    spans: list[tuple[int, int]] = []
    for anchor in sorted(set(line_anchors)):
        start = max(1, anchor - _WINDOW_HALF)
        end = min(len(lines), anchor + _WINDOW_HALF)
        if end >= start:
            spans.append((start, end))
    return [
        ContextWindow(start_line=s, end_line=e, text="\n".join(lines[s - 1 : e]))
        for s, e in _merge_spans(spans)
    ]


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans.sort()
    out = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = out[-1]
        if start <= last_end + 1:
            out[-1] = (last_start, max(last_end, end))
        else:
            out.append((start, end))
    return out
