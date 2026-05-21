"""Bounded failure-log / stack-trace parser."""

from __future__ import annotations

import re

from pythinker_review.diagnostics.models import DiagnosticInput, StackFrame

_FRAME_RE = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<fn>\S+))?')
_EXCEPTION_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))(?::|$)")


def parse_diagnostic(
    text: str, *, command: str | None = None, max_chars: int = 20_000
) -> DiagnosticInput:
    bounded = text[:max_chars]
    frames: list[StackFrame] = []
    exception: str | None = None
    for line in bounded.splitlines():
        if match := _FRAME_RE.search(line):
            frames.append(
                StackFrame(
                    file=match.group("file"),
                    line=int(match.group("line")),
                    function=match.group("fn"),
                )
            )
        if exception is None and (em := _EXCEPTION_RE.match(line.strip())):
            exception = em.group("name")
    return DiagnosticInput(raw=bounded, command=command, exception=exception, frames=tuple(frames))
