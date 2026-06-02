"""Pythinker Security Scan advisor prompt context assembly."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pythinker_review.engine.token_budget import clip_text
from pythinker_review.security_scan.knowledge import TECH_HIGHLIGHTS
from pythinker_review.security_scan.tech import detect_tech, language_for_path
from pythinker_review.signals.models import Signal

_FRAMEWORK_BUDGET = 6_000

_SLUG_NOTES: dict[str, str] = {
    "missing-auth-public-handler": "Check handler-level auth, not only edge middleware.",
    "sql-injection-python-concat": "Report only if attacker input reaches raw SQL.",
    "sql-injection-js-template": "Report only if attacker input reaches raw SQL.",
    "ssrf-variable-url": "Look for scheme/host allowlists and private-network blocking.",
    "xss-unsafe-html": "Trace user-controlled HTML and escaping at the render sink.",
    "path-traversal-file-join-user-input": "Check path normalization and base containment.",
    "jwt-handling-algorithm-confusion": "Check signature verification and algorithm pinning.",
    "agentic-untrusted-prompt-input-prompt-injection": "Treat external text as data.",
}


def build_advisor_context(*, repo: Path, signals_by_file: dict[str, list[Signal]]) -> str:
    tech = detect_tech(repo)
    batch_slugs = sorted(
        {signal.slug for signals in signals_by_file.values() for signal in signals}
    )
    batch_languages = sorted(
        {
            lang
            for path, signals in signals_by_file.items()
            if signals and (lang := language_for_path(path)) is not None
        }
    )
    sections = [
        "## Security advisor context",
        f"Detected tech tags: {', '.join(tech.tags) if tech.tags else 'unknown'}",
        "Detected languages in signaled batch: "
        f"{', '.join(batch_languages) if batch_languages else 'unknown'}",
        f"Sentinel files: {', '.join(tech.sentinels) if tech.sentinels else 'none'}",
    ]
    if highlights := _framework_highlights(tech.tags, batch_languages):
        sections.append(highlights)
    if slug_notes := _slug_notes(batch_slugs):
        sections.append(slug_notes)
    return "\n\n".join(sections)


def _framework_highlights(tags: Sequence[str], languages: list[str]) -> str:
    lang_set = set(languages)
    blocks: list[str] = []
    included: list[str] = []
    for tag in tags:
        highlight = TECH_HIGHLIGHTS.get(tag)
        if highlight is None:
            continue
        title, allowed_languages, bullets = highlight
        if lang_set and not lang_set.intersection(allowed_languages):
            continue
        included.append(title)
        blocks.append("### " + title + "\n" + "\n".join(f"- {bullet}" for bullet in bullets))
    if not blocks:
        return ""
    full = "## Threat highlights for this repo's tech stack\n\n" + "\n\n".join(blocks)
    if len(full) <= _FRAMEWORK_BUDGET:
        return full
    return clip_text(
        "## Tech in this repo\n\n"
        f"This repo uses {len(included)} known security-relevant stacks: {', '.join(included)}. "
        "Apply standard auth, input validation, authorization, and trust-boundary checks.",
        _FRAMEWORK_BUDGET,
    )


def _slug_notes(slugs: list[str]) -> str:
    lines = [f"- `{slug}`: {_SLUG_NOTES[slug]}" for slug in slugs if slug in _SLUG_NOTES]
    if not lines:
        return ""
    return "## Slug-specific reviewer notes\n\n" + "\n".join(lines)
