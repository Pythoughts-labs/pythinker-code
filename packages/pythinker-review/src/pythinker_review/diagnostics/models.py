"""Diagnostic input models for root-cause review."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class StackFrame:
    file: str
    line: int
    function: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticInput:
    raw: str
    command: str | None = None
    exception: str | None = None
    frames: tuple[StackFrame, ...] = field(default_factory=tuple)
