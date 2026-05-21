"""Pure-Python Pythinker Security Scan scanner: repo-wide regex candidates, file records, run meta."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pythinker_review.security_scan.matchers import (
    MatcherSpec,
    create_default_registry,
    evaluate_gate,
    files_for_matcher,
)
from pythinker_review.security_scan.models import CandidateMatch, FileRecord, now_iso
from pythinker_review.security_scan.store import (
    complete_run,
    create_run_meta,
    ensure_project,
    read_file_record,
    read_project_settings,
    write_file_record,
    write_run_meta,
)
from pythinker_review.security_scan.tech import (
    LANGUAGE_EXTENSIONS,
    detect_tech,
    language_for_path,
    write_tech_json,
)

IGNORE_DIRS = [
    "**/node_modules/**",
    "**/.git/**",
    "**/.security-scan/data/**",
    "**/.pythinker-review/security-scan/data/**",
    "**/dist/**",
    "**/build/**",
    "**/.next/**",
    "**/coverage/**",
    "**/.turbo/**",
    "**/vendor/**",
    "**/__tests__/**",
    "**/*.test.{ts,tsx,js,jsx,py,go,rs}",
    "**/*.spec.{ts,tsx,js,jsx,py,go,rs}",
    "**/test/**",
    "**/tests/**",
    "**/fixtures/**",
    "**/testserver/**",
    "**/*.d.ts",
    "**/*.mdx",
    "**/*.md",
    "**/content/docs/**",
    "**/content/docs-wip/**",
]


@dataclass(frozen=True, slots=True)
class ScanProgress:
    type: str
    message: str
    matcher_slug: str | None = None
    file_path: str | None = None
    match_count: int | None = None
    matcher_index: int | None = None
    matcher_total: int | None = None


@dataclass(frozen=True, slots=True)
class LanguageStats:
    language: str
    scanned_files: int
    candidates: int
    match_rate: float


@dataclass(frozen=True, slots=True)
class ScanResult:
    run_id: str
    candidate_count: int
    files_with_candidates: int
    files_scanned: int
    active_matchers: list[str]
    skipped_matchers: list[str]
    language_stats: list[LanguageStats]


ProgressCallback = Callable[[ScanProgress], None]


def scan_project(
    *,
    project_id: str,
    root: Path,
    data_root: Path,
    matcher_slugs: list[str] | None = None,
    ignore_paths: list[str] | None = None,
    on_progress: ProgressCallback | None = None,
) -> ScanResult:
    root = root.resolve()
    ensure_project(project_id, root, data_root=data_root)
    settings = read_project_settings(project_id, data_root=data_root)
    detected = detect_tech(root)
    write_tech_json(project_id, detected, data_root=data_root)

    registry = create_default_registry()
    selected = registry.get_by_slugs(matcher_slugs) if matcher_slugs else registry.get_all()
    if not selected:
        raise ValueError("No matchers selected")

    honor_gates = matcher_slugs is not None
    active: list[MatcherSpec] = []
    skipped: list[str] = []
    for matcher in selected:
        if honor_gates or evaluate_gate(matcher, detected, root):
            active.append(matcher)
        else:
            skipped.append(matcher.slug)

    run = create_run_meta(
        project_id=project_id,
        root_path=root,
        run_type="scan",
        scanner_config={"matcherSlugs": [matcher.slug for matcher in active], "mode": "full"},
    )
    write_run_meta(run, data_root=data_root)

    ignore = [*IGNORE_DIRS, *(settings.ignore_paths if ignore_paths is None else ignore_paths)]
    content_cache: dict[str, str | None] = {}
    matches_by_path: dict[str, list[CandidateMatch]] = {}
    scanned_paths: set[str] = set()

    for index, matcher in enumerate(active, start=1):
        _emit(
            on_progress,
            ScanProgress(
                type="matcher_started",
                message=f"Running matcher {index}/{len(active)}: {matcher.slug}",
                matcher_slug=matcher.slug,
                matcher_index=index,
                matcher_total=len(active),
            ),
        )
        files = files_for_matcher(root, matcher, ignore)
        match_count = 0
        for rel in files:
            content = content_cache.get(rel)
            if content is None and rel not in content_cache:
                content = _read_source(root / rel)
                content_cache[rel] = content
            if content is None:
                continue
            scanned_paths.add(rel)
            if not content:
                continue
            matches = matcher.match(content, rel)
            if not matches:
                continue
            match_count += len(matches)
            matches_by_path.setdefault(rel, []).extend(matches)
            _emit(
                on_progress,
                ScanProgress(
                    type="file_scanned",
                    message=f"Found {len(matches)} match(es) in {rel}",
                    matcher_slug=matcher.slug,
                    file_path=rel,
                    match_count=len(matches),
                ),
            )
        _emit(
            on_progress,
            ScanProgress(
                type="matcher_done",
                message=f"Matcher {matcher.slug}: {match_count} match(es)",
                matcher_slug=matcher.slug,
                match_count=match_count,
                matcher_index=index,
                matcher_total=len(active),
            ),
        )

    active_slugs = {matcher.slug for matcher in active}
    records: dict[str, FileRecord] = {}
    for rel in sorted(scanned_paths):
        content = content_cache.get(rel)
        if content is None:
            continue
        record = read_file_record(project_id, rel, data_root=data_root)
        if record is None and rel not in matches_by_path:
            continue
        if record is None:
            record = FileRecord.model_validate(
                {
                    "filePath": rel,
                    "projectId": project_id,
                    "candidates": [],
                    "findings": [],
                    "analysisHistory": [],
                    "status": "pending",
                }
            )
        previous_hash = record.file_hash
        previous_candidates = _candidate_keys(record.candidates)
        preserved = [
            candidate for candidate in record.candidates if candidate.vuln_slug not in active_slugs
        ]
        record.candidates = preserved + _dedupe_candidates(matches_by_path.get(rel, []))
        record.last_scanned_at = now_iso()
        record.last_scanned_run_id = run.run_id
        record.file_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
        candidates_changed = _candidate_keys(record.candidates) != previous_candidates
        content_changed = record.file_hash != previous_hash
        if record.status == "error" or content_changed or candidates_changed:
            record.status = "pending"
            record.locked_by_run_id = None
            record.locked_at = None
            if content_changed or candidates_changed:
                record.findings = []
        records[rel] = record
        write_file_record(record, data_root=data_root)

    records_with_candidates = [record for record in records.values() if record.candidates]
    language_stats = _language_stats(scanned_paths, records_with_candidates)
    candidate_count = sum(len(record.candidates) for record in records_with_candidates)
    complete_run(
        project_id,
        run.run_id,
        "done",
        data_root=data_root,
        stats={"filesScanned": len(scanned_paths), "candidatesFound": candidate_count},
    )
    return ScanResult(
        run_id=run.run_id,
        candidate_count=candidate_count,
        files_with_candidates=len(records_with_candidates),
        files_scanned=len(scanned_paths),
        active_matchers=[matcher.slug for matcher in active],
        skipped_matchers=skipped,
        language_stats=language_stats,
    )


def _read_source(path: Path) -> str | None:
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


def _candidate_keys(matches: list[CandidateMatch]) -> set[tuple[str, str, tuple[int, ...], str]]:
    return {
        (match.vuln_slug, match.matched_pattern, tuple(match.line_numbers), match.snippet)
        for match in matches
    }


def _dedupe_candidates(matches: list[CandidateMatch]) -> list[CandidateMatch]:
    seen: set[tuple[str, str, tuple[int, ...]]] = set()
    out: list[CandidateMatch] = []
    for match in matches:
        key = (match.vuln_slug, match.matched_pattern, tuple(match.line_numbers))
        if key not in seen:
            out.append(match)
            seen.add(key)
    return out


def _language_stats(scanned_paths: set[str], records: list[FileRecord]) -> list[LanguageStats]:
    scanned_by_lang: dict[str, int] = {}
    candidates_by_lang: dict[str, int] = {}
    for rel in scanned_paths:
        lang = language_for_path(rel)
        if lang:
            scanned_by_lang[lang] = scanned_by_lang.get(lang, 0) + 1
    for record in records:
        lang = language_for_path(record.file_path)
        if lang:
            candidates_by_lang[lang] = candidates_by_lang.get(lang, 0) + len(record.candidates)
    stats: list[LanguageStats] = []
    for language in LANGUAGE_EXTENSIONS:
        scanned = scanned_by_lang.get(language, 0)
        if scanned:
            candidates = candidates_by_lang.get(language, 0)
            stats.append(
                LanguageStats(
                    language=language,
                    scanned_files=scanned,
                    candidates=candidates,
                    match_rate=candidates / scanned,
                )
            )
    return stats


def _emit(callback: ProgressCallback | None, progress: ScanProgress) -> None:
    if callback is None:
        return
    try:
        callback(progress)
    except Exception:
        return
