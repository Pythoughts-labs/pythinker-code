"""Markdown and summary rendering for Reviewflow records."""

from __future__ import annotations

from collections import Counter

from pythinker_review.reviewflow.models import FeatureRecord, FindingRecord, PatchAttempt

SEVERITY_SCORE = {"critical": 4, "high": 3, "medium": 2, "low": 1}
CONFIDENCE_SCORE = {"high": 3, "medium": 2, "low": 1}


def rank_findings(findings: list[FindingRecord]) -> list[FindingRecord]:
    return sorted(
        findings,
        key=lambda finding: (
            SEVERITY_SCORE[finding.severity],
            CONFIDENCE_SCORE[finding.confidence],
            finding.updated_at,
        ),
        reverse=True,
    )


def next_finding(findings: list[FindingRecord]) -> FindingRecord | None:
    open_findings = [finding for finding in findings if finding.status == "open"]
    return rank_findings(open_findings)[0] if open_findings else None


def finding_summary(finding: FindingRecord, feature: FeatureRecord | None) -> dict[str, object]:
    first = finding.evidence[0] if finding.evidence else None
    return {
        "id": finding.finding_id,
        "findingId": finding.finding_id,
        "title": finding.title,
        "category": finding.category,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "triage": finding.triage,
        "status": finding.status,
        "featureId": finding.feature_id,
        "feature": feature.title if feature else finding.feature_id,
        "location": None
        if first is None
        else {
            "path": first.path,
            "startLine": first.start_line,
            "endLine": first.end_line,
            "symbol": first.symbol,
        },
        "updatedAt": finding.updated_at,
    }


def render_report(findings: list[FindingRecord], features: list[FeatureRecord]) -> str:
    feature_by_id = {feature.feature_id: feature for feature in features}
    ranked = rank_findings(findings)
    counts = Counter(finding.status for finding in findings)
    severity = Counter(finding.severity for finding in findings)
    lines = [
        "# Pythinker Reviewflow Report",
        "",
        "## Summary",
        "",
        f"- Findings: {len(findings)}",
        f"- Open: {counts.get('open', 0)}",
        f"- Fixed: {counts.get('fixed', 0)}",
        f"- False positive: {counts.get('false-positive', 0)}",
        f"- Won't fix: {counts.get('wont-fix', 0)}",
        f"- Uncertain: {counts.get('uncertain', 0)}",
        "",
        "## Severity",
        "",
    ]
    for key in ("critical", "high", "medium", "low"):
        lines.append(f"- {key}: {severity.get(key, 0)}")
    lines.extend(["", "## Findings", ""])
    if not ranked:
        lines.append("No findings.")
        return "\n".join(lines).rstrip() + "\n"
    for finding in ranked:
        feature = feature_by_id.get(finding.feature_id)
        lines.extend(_render_finding(finding, feature))
    return "\n".join(lines).rstrip() + "\n"


def render_finding_detail(
    finding: FindingRecord, feature: FeatureRecord | None, patches: list[PatchAttempt]
) -> str:
    lines = _render_finding(finding, feature)
    lines.extend(["", "### Patch attempts"])
    if not patches:
        lines.append("- none")
    for patch in patches:
        lines.append(
            f"- `{patch.patch_attempt_id}` — {patch.status}; files: "
            f"{', '.join(patch.files_changed) or 'none'}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_finding(finding: FindingRecord, feature: FeatureRecord | None) -> list[str]:
    lines = [
        f"### {finding.severity.upper()} · {finding.title}",
        "",
        f"- ID: `{finding.finding_id}`",
        f"- Feature: {feature.title if feature else finding.feature_id}",
        f"- Category: {finding.category}",
        f"- Confidence: {finding.confidence}",
        f"- Triage: {finding.triage or 'unset'}",
        f"- Status: {finding.status}",
        "",
        "**Evidence**",
    ]
    if finding.evidence:
        for evidence in finding.evidence:
            if evidence.start_line is None:
                loc = evidence.path
            elif evidence.end_line == evidence.start_line:
                loc = f"{evidence.path}:{evidence.start_line}"
            else:
                loc = f"{evidence.path}:{evidence.start_line}-{evidence.end_line}"
            lines.append(f"- `{loc}`{f' — {evidence.quote}' if evidence.quote else ''}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "**Reasoning**",
            "",
            finding.reasoning,
            "",
            "**Recommendation**",
            "",
            finding.recommendation,
        ]
    )
    if finding.reproduction:
        lines.extend(["", "**Reproduction**", "", finding.reproduction])
    if finding.suggested_regression_test:
        lines.extend(["", "**Suggested regression test**", "", finding.suggested_regression_test])
    if finding.minimum_fix_scope:
        lines.extend(["", "**Minimum fix scope**", "", finding.minimum_fix_scope])
    lines.append("")
    return lines


__all__ = [
    "finding_summary",
    "next_finding",
    "rank_findings",
    "render_finding_detail",
    "render_report",
]
