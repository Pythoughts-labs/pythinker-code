"""Stable Finding IDs and dedupe rules."""

from __future__ import annotations

import hashlib
from datetime import datetime

from pythinker_review.reviewers.schema import RawFinding
from pythinker_review.store.models import SEVERITY_ORDER, Finding, Location, Pass


def finding_id(rule_id: str, file: str, start_line: int, title: str) -> str:
    digest = hashlib.sha256(f"{rule_id}|{file}|{start_line}|{title}".encode()).hexdigest()
    return digest[:12]


def dedupe_findings(
    tagged: list[tuple[Pass, RawFinding]], *, run_id: str, head_sha: str, created_at: datetime
) -> list[Finding]:
    bucket: dict[tuple[str, int, int, str], tuple[Pass, RawFinding]] = {}
    pass_rank: dict[Pass, int] = {"security_review": 2, "code_review": 1, "debug_review": 0}
    for p, finding in tagged:
        key = (finding.file, finding.start_line, finding.end_line, finding.rule_id)
        current = bucket.get(key)
        if current is None:
            bucket[key] = (p, finding)
            continue
        current_p, current_finding = current
        if (
            SEVERITY_ORDER[finding.severity] > SEVERITY_ORDER[current_finding.severity]
            or (
                finding.severity == current_finding.severity
                and finding.confidence > current_finding.confidence
            )
            or (
                finding.severity == current_finding.severity
                and finding.confidence == current_finding.confidence
                and pass_rank[p] > pass_rank[current_p]
            )
        ):
            bucket[key] = (p, finding)

    out: list[Finding] = []
    for p, finding in bucket.values():
        out.append(
            Finding.model_validate(
                {
                    "id": finding_id(
                        finding.rule_id, finding.file, finding.start_line, finding.title
                    ),
                    "rule_id": finding.rule_id,
                    "title": finding.title,
                    "rationale": finding.rationale,
                    "category": finding.category,
                    "severity": finding.severity,
                    "location": Location(
                        file=finding.file,
                        start_line=finding.start_line,
                        end_line=finding.end_line,
                        sha=head_sha,
                    ),
                    "suggestion": finding.suggestion,
                    "evidence_snippet": finding.evidence_snippet,
                    "confidence": finding.confidence,
                    "confidence_reason": finding.confidence_reason,
                    "exploitability": finding.exploitability,
                    "reproduction": finding.reproduction,
                    "created_at": created_at,
                    "run_id": run_id,
                    "pass": p,
                }
            )
        )
    return out
