"""Reports, exports, metrics, and status helpers for Python-native Pythinker Security Scan."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pythinker_review.security_scan.models import FileRecord, Finding
from pythinker_review.security_scan.paths import reports_dir
from pythinker_review.security_scan.store import load_all_file_records, read_project_config

_SEVERITY_ORDER = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "HIGH_BUG": 2, "BUG": 1, "LOW": 0}


@dataclass(frozen=True, slots=True)
class ProjectStatus:
    project_id: str
    root_path: str
    records: int
    pending: int
    analyzed: int
    errors: int
    candidates: int
    findings: int


def project_status(project_id: str, *, data_root: Path) -> ProjectStatus:
    project = read_project_config(project_id, data_root=data_root)
    records = load_all_file_records(project_id, data_root=data_root)
    status = Counter(record.status for record in records)
    return ProjectStatus(
        project_id=project_id,
        root_path=project.root_path,
        records=len(records),
        pending=status["pending"],
        analyzed=status["analyzed"],
        errors=status["error"],
        candidates=sum(len(record.candidates) for record in records),
        findings=sum(len(record.findings) for record in records),
    )


def findings_by_record(project_id: str, *, data_root: Path) -> list[tuple[FileRecord, Finding]]:
    out: list[tuple[FileRecord, Finding]] = []
    for record in load_all_file_records(project_id, data_root=data_root):
        for finding in record.findings:
            out.append((record, finding))
    return sorted(
        out,
        key=lambda item: (
            -_SEVERITY_ORDER[item[1].severity],
            item[0].file_path,
            min(item[1].line_numbers or [0]),
        ),
    )


def metrics(project_id: str, *, data_root: Path) -> dict[str, Any]:
    pairs = findings_by_record(project_id, data_root=data_root)
    by_severity = Counter(finding.severity for _record, finding in pairs)
    by_slug = Counter(finding.vuln_slug for _record, finding in pairs)
    revalidation = Counter(
        finding.revalidation.verdict
        for _record, finding in pairs
        if finding.revalidation is not None
    )
    return {
        "projectId": project_id,
        "findings": len(pairs),
        "bySeverity": dict(sorted(by_severity.items(), key=lambda item: -_SEVERITY_ORDER[item[0]])),
        "bySlug": dict(by_slug.most_common()),
        "revalidation": dict(revalidation),
    }


def render_markdown_report(project_id: str, *, data_root: Path) -> str:
    status = project_status(project_id, data_root=data_root)
    pairs = findings_by_record(project_id, data_root=data_root)
    lines = [
        f"# Pythinker Security Scan report: {project_id}",
        "",
        f"- Root: `{status.root_path}`",
        f"- Records: {status.records}",
        f"- Candidates: {status.candidates}",
        f"- Findings: {status.findings}",
        f"- Pending/analyzed/errors: {status.pending}/{status.analyzed}/{status.errors}",
        "",
        "## Findings",
        "",
    ]
    if not pairs:
        lines.append("No findings recorded.")
        return "\n".join(lines) + "\n"
    for record, finding in pairs:
        verdict = f" — {finding.revalidation.verdict}" if finding.revalidation else ""
        lines.extend(
            [
                f"### {finding.severity}: {finding.title}{verdict}",
                "",
                f"- File: `{record.file_path}:{', '.join(map(str, finding.line_numbers))}`",
                f"- Slug: `{finding.vuln_slug}`",
                f"- Confidence: {finding.confidence}",
                "",
                finding.description.strip(),
                "",
                "**Recommendation:** " + finding.recommendation.strip(),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_report(project_id: str, *, data_root: Path) -> tuple[Path, Path]:
    report_dir = reports_dir(project_id, data_root=data_root)
    report_dir.mkdir(parents=True, exist_ok=True)
    md_path = report_dir / "report.md"
    json_path = report_dir / "report.json"
    md_path.write_text(render_markdown_report(project_id, data_root=data_root), encoding="utf-8")
    json_path.write_text(
        json.dumps(metrics(project_id, data_root=data_root), indent=2) + "\n", encoding="utf-8"
    )
    return md_path, json_path


def export_findings(
    project_id: str,
    *,
    data_root: Path,
    fmt: Literal["json", "md-dir"],
    out: Path,
) -> Path:
    pairs = findings_by_record(project_id, data_root=data_root)
    if fmt == "json":
        payload = [
            {
                "filePath": record.file_path,
                **finding.model_dump(by_alias=True, exclude_none=True),
            }
            for record, finding in pairs
        ]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return out
    out.mkdir(parents=True, exist_ok=True)
    for idx, (record, finding) in enumerate(pairs, start=1):
        safe_slug = "".join(c if c.isalnum() or c in "._-" else "-" for c in finding.vuln_slug)
        path = out / f"{idx:04d}-{safe_slug}.md"
        path.write_text(_finding_markdown(record, finding), encoding="utf-8")
    return out


def _finding_markdown(record: FileRecord, finding: Finding) -> str:
    return (
        f"# {finding.severity}: {finding.title}\n\n"
        f"- File: `{record.file_path}:{', '.join(map(str, finding.line_numbers))}`\n"
        f"- Slug: `{finding.vuln_slug}`\n"
        f"- Confidence: {finding.confidence}\n\n"
        f"## Description\n\n{finding.description.strip()}\n\n"
        f"## Recommendation\n\n{finding.recommendation.strip()}\n"
    )
