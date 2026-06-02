"""Prompt assembly for the Python-native Pythinker Security Scan processor."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from pythinker_review.engine.token_budget import clip_text
from pythinker_review.security_scan.knowledge import SLUG_NOTES, TECH_HIGHLIGHTS
from pythinker_review.security_scan.models import FileRecord
from pythinker_review.security_scan.tech import languages_for_paths

_FRAMEWORK_SECTION_CHAR_BUDGET = 6_000
_DEFAULT_FILE_CHAR_BUDGET = 8_000


@dataclass(frozen=True, slots=True)
class PromptAssembly:
    system: str
    user: str
    included_tags: list[str]
    slugs_with_notes: int
    total_chars: int


def load_base_system_prompt() -> str:
    return (
        resources.files("pythinker_review.security_scan.prompts")
        .joinpath("system.md")
        .read_text(encoding="utf-8")
        .strip()
    )


def assemble_prompt(
    *,
    detected_tags: list[str],
    batch_slugs: list[str],
    batch_languages: list[str],
    project_info: str = "",
    prompt_append: str | None = None,
    records: list[FileRecord],
    project_root: Path,
    file_char_budget: int = _DEFAULT_FILE_CHAR_BUDGET,
) -> PromptAssembly:
    sections = [load_base_system_prompt()]
    highlights, included_tags = _framework_section(detected_tags, batch_languages)
    if highlights:
        sections.append(highlights)
    slug_section = _slug_section(batch_slugs)
    if slug_section:
        sections.append(slug_section)
    if project_info.strip():
        sections.append("## Project-specific context\n\n" + project_info.strip())
    if prompt_append and prompt_append.strip():
        sections.append("## Additional project policy\n\n" + prompt_append.strip())

    user = build_user_prompt(
        records=records, project_root=project_root, file_char_budget=file_char_budget
    )
    system = "\n\n---\n\n".join(sections)
    return PromptAssembly(
        system=system,
        user=user,
        included_tags=included_tags,
        slugs_with_notes=slug_section.count("\n- `") + (1 if slug_section.startswith("- `") else 0),
        total_chars=len(system) + len(user),
    )


def build_user_prompt(
    *, records: list[FileRecord], project_root: Path, file_char_budget: int
) -> str:
    file_sections: list[str] = []
    for record in records:
        candidates = "\n".join(
            f"  - [{candidate.vuln_slug}] "
            f"L{', '.join(map(str, candidate.line_numbers))}: "
            f"{candidate.matched_pattern}\n"
            f"    snippet: {candidate.snippet[:500]}"
            for candidate in record.candidates
        )
        if not candidates:
            candidates = "  - no scanner hits; holistic security review requested"
        content = _read_file(project_root / record.file_path)
        rendered_content = (
            clip_text(content, file_char_budget) if content else "[unreadable or binary]"
        )
        file_sections.append(
            f"## File: {record.file_path}\n\n"
            f"### Candidate matcher hits\n{candidates}\n\n"
            f"### File content\n```\n{rendered_content}\n```"
        )
    return (
        "Review the following Pythinker Security Scan target batch. Include every file in the JSON output.\n\n"
        + "\n\n---\n\n".join(file_sections)
    )


def batch_languages(records: list[FileRecord]) -> list[str]:
    return languages_for_paths([record.file_path for record in records])


def _framework_section(tags: list[str], languages: list[str]) -> tuple[str, list[str]]:
    lang_set = set(languages)
    blocks: list[str] = []
    included: list[str] = []
    for tag in tags:
        item = TECH_HIGHLIGHTS.get(tag)
        if item is None:
            continue
        title, allowed_languages, bullets = item
        if lang_set and not lang_set.intersection(allowed_languages):
            continue
        included.append(tag)
        blocks.append("### " + title + "\n" + "\n".join(f"- {bullet}" for bullet in bullets))
    if not blocks:
        return "", []
    full = "## Threat highlights for this repo's tech stack\n\n" + "\n\n".join(blocks)
    if len(full) <= _FRAMEWORK_SECTION_CHAR_BUDGET:
        return full, included
    return (
        clip_text(
            "## Tech in this repo\n\n"
            f"Detected {len(included)} security-relevant stacks: {', '.join(included)}. "
            "Apply auth, input validation, authorization, output escaping, and trust-boundary checks.",
            _FRAMEWORK_SECTION_CHAR_BUDGET,
        ),
        included,
    )


def _slug_section(slugs: list[str]) -> str:
    lines = [f"- `{slug}`: {SLUG_NOTES[slug]}" for slug in sorted(set(slugs)) if slug in SLUG_NOTES]
    return "## Slug-specific reviewer notes\n\n" + "\n".join(lines) if lines else ""


def _read_file(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return None
