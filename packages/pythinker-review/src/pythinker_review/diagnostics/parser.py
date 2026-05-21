"""Bounded failure-log / stack-trace parser with secret redaction."""

from __future__ import annotations

import re

from pythinker_review.diagnostics.models import DiagnosticInput, StackFrame

_FRAME_RE = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<fn>\S+))?')
_EXCEPTION_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))(?::|$)")
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (
        re.compile(
            r"(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*([=:])\s*(['\"]?)[^\s'\"]{8,}\3"
        ),
        r"\1\2[REDACTED_SECRET]",
    ),
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._\-+/=]+"), r"\1[REDACTED_TOKEN]"),
)


def parse_diagnostic(
    text: str, *, command: str | None = None, max_chars: int = 20_000
) -> DiagnosticInput:
    bounded = redact_secrets(text)[:max_chars]
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


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern, replacement in _REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
