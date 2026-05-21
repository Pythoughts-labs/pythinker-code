"""Compliance checklist loading for code-reviewr-derived PR checks."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CHECKLIST = "default_compliance.yaml"


class ComplianceChecklistError(ValueError):
    """Raised when a compliance checklist cannot be loaded safely."""


def load_compliance_context(
    *, checklist_path: Path | None = None, ticket_text: str = "", ticket_file: Path | None = None
) -> str:
    """Load checklist and optional ticket text into a bounded prompt context."""
    checklist = _load_checklist_yaml(checklist_path)
    ticket_parts: list[str] = []
    if ticket_text.strip():
        ticket_parts.append(ticket_text.strip())
    if ticket_file is not None:
        try:
            ticket_parts.append(ticket_file.read_text(encoding="utf-8", errors="replace").strip())
        except OSError as exc:
            raise ComplianceChecklistError(f"failed to read ticket file: {ticket_file}") from exc
    ticket = "\n\n".join(part for part in ticket_parts if part)
    parts = ["Compliance checklist:", yaml.safe_dump(checklist, sort_keys=False).strip()]
    if ticket:
        parts.extend(["", "Ticket / acceptance criteria context:", _clip(ticket, 20_000)])
    return "\n".join(parts).strip()


def _load_checklist_yaml(path: Path | None) -> dict[str, Any]:
    try:
        if path is None:
            text = (
                resources.files("pythinker_review.reviewers")
                .joinpath(_DEFAULT_CHECKLIST)
                .read_text(encoding="utf-8")
            )
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ComplianceChecklistError(f"failed to read compliance checklist: {path}") from exc
    try:
        parsed = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ComplianceChecklistError("compliance checklist must be valid YAML") from exc
    if not isinstance(parsed, dict):
        raise ComplianceChecklistError("compliance checklist root must be a mapping")
    items = parsed.get("pr_compliances", [])
    if not isinstance(items, list):
        raise ComplianceChecklistError("compliance checklist `pr_compliances` must be a list")
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ComplianceChecklistError(f"compliance item {idx} must be a mapping")
        if not str(item.get("title", "")).strip():
            raise ComplianceChecklistError(f"compliance item {idx} is missing `title`")
    return parsed


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... [truncated]"


__all__ = ["ComplianceChecklistError", "load_compliance_context"]
