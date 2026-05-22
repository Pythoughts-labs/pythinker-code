"""Shared transcript rows for live and flushed shell output."""

from __future__ import annotations

from typing import Literal

from rich.console import Group, RenderableType
from rich.text import Text

from pythinker_code.ui.shell.design_system import ShellTone, shell_style, status_icon

Role = Literal["user", "assistant", "tool", "system", "notification"]
Status = Literal["running", "completed", "failed", "denied", "interrupted", "waiting"]

_ROLE_LABELS: dict[Role, str] = {
    "user": "You",
    "assistant": "Assistant",
    "tool": "Tool",
    "system": "System",
    "notification": "Notice",
}


def render_transcript_row(
    role: Role,
    content: str | RenderableType,
    *,
    status: Status | None = None,
) -> RenderableType:
    label = _ROLE_LABELS[role]
    prefix = Text()
    if status:
        prefix.append_text(status_icon(status))
        prefix.append(" ")
    prefix.append(label, style=shell_style(ShellTone.MUTED))
    if isinstance(content, str):
        body: RenderableType = Text(content)
    else:
        body = content
    return Group(prefix, body)
