from __future__ import annotations

import hashlib
from collections.abc import Iterable

from pythinker_code.project_memory import scan_memory_content
from pythinker_code.session_state import SessionState


def content_hash(*, tier: str, title: str, body: str) -> str:
    normalized = "\n".join(part.strip().lower() for part in (tier, title, body))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _safe_recap_field(value: str) -> str:
    """Drop the field if it trips memory-content threat patterns.

    `files_read`, `files_modified`, `request`, and `scratch_blocks` flow into
    JOURNAL.md and from there into the recall injection bus. A poisoned path
    name or assistant string must not reach the next prompt's context.
    """
    value = value.strip()
    if not value:
        return ""
    if scan_memory_content(value) is not None:
        return ""
    # Compress newlines so a multi-line injection payload can't escape the
    # single-bullet Markdown layout used by the recap below.
    return " ".join(value.split())


def _safe_recap_fields(values: Iterable[str]) -> list[str]:
    return [cleaned for cleaned in (_safe_recap_field(v) for v in values) if cleaned]


def build_session_recap(
    *,
    state: SessionState,
    session_id: str,
    request: str = "",
    scratch_blocks: Iterable[str] = (),
    files_read: Iterable[str] = (),
    files_modified: Iterable[str] = (),
) -> str:
    """Build a stable-schema Markdown recap block for JOURNAL.md."""
    request = _safe_recap_field(request)
    scratch_blocks = _safe_recap_fields(scratch_blocks)
    files_read = _safe_recap_fields(files_read)
    files_modified = _safe_recap_fields(files_modified)
    open_todos = [todo.title for todo in state.todos if todo.status in {"pending", "in_progress"}]
    completed = [todo.title for todo in state.todos if todo.status == "done"]
    learned = [block.strip() for block in scratch_blocks if block.strip()]
    title = state.custom_title or session_id[:12]
    body_for_hash = "\n".join([request, *learned, *open_todos, *completed])
    digest = content_hash(tier="journal", title=title, body=body_for_hash)

    def bullets(items: Iterable[str]) -> str:
        lines = [f"- {item}" for item in items if item]
        return "\n".join(lines) if lines else "- none"

    return "\n".join(
        [
            f"session_id: {session_id}",
            f"title: {title}",
            f"content_hash: {digest}",
            "",
            "## request",
            request.strip() or "none",
            "",
            "## investigated",
            bullets(files_read),
            "",
            "## learned",
            bullets(learned),
            "",
            "## completed",
            bullets(completed),
            "",
            "## next_steps",
            bullets(open_todos),
            "",
            "## open_todos",
            bullets(open_todos),
            "",
            "## files_read",
            bullets(files_read),
            "",
            "## files_modified",
            bullets(files_modified),
            "",
            "## labels",
            f"- session:{session_id[:12]}",
        ]
    )
