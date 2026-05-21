from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Signal:
    rule_id: str
    file: str
    line: int
    snippet: str
    reason: str
    confidence: float
    source_kind: str | None = None
    sink_kind: str | None = None
    exploitability: str | None = None
    mitigation_hint: str | None = None
