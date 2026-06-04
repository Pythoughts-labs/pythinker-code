from __future__ import annotations

from dataclasses import dataclass, field


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
    cwe: str | None = None
    severity_hint: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        marker = ".signal."
        tail = self.rule_id.split(marker, 1)[-1] if marker in self.rule_id else self.rule_id
        return tail.replace(".", "-").replace("_", "-")
