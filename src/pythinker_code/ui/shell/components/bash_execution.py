"""Pythinker bash execution component.



Render bash as a self-contained card with a dynamic top/bottom border,
a ``$ <command>`` header, streaming output, and a footer with status.
We model the same shape as a stateless Rich renderable factory so callers
(the bash tool renderer or future ``Shell`` history) can drive it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.style import Style as RichStyle
from rich.text import Text

from pythinker_code.ui.shell.components.render_utils import sanitize_ansi
from pythinker_code.ui.theme import tui_rich_style

__all__ = [
    "BashExecutionState",
    "render_bash_execution",
]

PREVIEW_LINES = 20

BashStatus = Literal["pending", "running", "complete", "error", "cancelled"]


@dataclass(frozen=True, slots=True)
class BashExecutionState:
    """Inputs for :func:`render_bash_execution`.

    Attributes:
        command: The shell command being executed.
        output: Combined stdout/stderr captured so far. Streaming-friendly —
            callers may pass partial output on every redraw.
        status: Lifecycle state. ``"pending"`` and ``"running"`` show the
            spinner placeholder line; ``"complete"`` / ``"error"`` /
            ``"cancelled"`` add a footer note.
        exit_code: Exit code for the finished process (only used in the
            ``"error"`` footer line).
        expanded: When ``True`` the full output is shown; otherwise the
            tail is truncated to ``PREVIEW_LINES`` lines.
        truncated: ``True`` when ``output`` was already byte-truncated
            upstream (for the LLM context cap). Drives the trailing hint.
        full_output_path: Optional spill-file path for very long output.
        exclude_from_context: ``!!`` prefix mode — render in dim instead of
            the bash-mode accent.
    """

    command: str
    output: str = ""
    status: BashStatus = "running"
    exit_code: int | None = None
    expanded: bool = False
    truncated: bool = False
    full_output_path: str | None = None
    exclude_from_context: bool = False
    header_suffix: str = ""
    """Muted metadata appended after the command (e.g. ``" (timeout 600s)"``)."""


def _accent_style(state: BashExecutionState) -> RichStyle:
    return tui_rich_style("muted" if state.exclude_from_context else "bash_mode")


def _output_lines(output: str) -> list[str]:
    cleaned = sanitize_ansi(output).replace("\r\n", "\n").replace("\r", "\n")
    if cleaned == "":
        return []
    return cleaned.split("\n")


def render_bash_execution(state: BashExecutionState) -> RenderableType:
    """Build the bash card renderable for *state*."""
    accent = _accent_style(state)
    header = Text(f"$ {state.command}", style=accent + RichStyle(bold=True))
    if state.header_suffix:
        header.append(state.header_suffix, style=tui_rich_style("muted"))

    lines = _output_lines(state.output)
    if state.expanded or len(lines) <= PREVIEW_LINES:
        display = lines
        hidden = 0
    else:
        display = lines[-PREVIEW_LINES:]
        hidden = len(lines) - len(display)

    output_block: RenderableType | None = None
    if display:
        muted = tui_rich_style("muted")
        body = Text("\n".join(display))
        body.stylize(muted)
        output_block = body

    footer_lines: list[Text] = []
    if hidden > 0:
        if state.expanded:
            footer_lines.append(
                Text(
                    "(ctrl+e to collapse)",
                    style=tui_rich_style("muted"),
                )
            )
        else:
            footer_lines.append(
                Text(
                    f"... {hidden} more lines (ctrl+e to expand)",
                    style=tui_rich_style("muted"),
                )
            )
    if state.status == "cancelled":
        footer_lines.append(Text("(cancelled)", style=tui_rich_style("warning")))
    elif state.status == "error":
        code = state.exit_code if state.exit_code is not None else "?"
        footer_lines.append(Text(f"(exit {code})", style=tui_rich_style("error")))
    elif state.status in ("pending", "running"):
        footer_lines.append(Text("Running... (esc to cancel)", style=tui_rich_style("muted")))

    if state.truncated and state.full_output_path:
        footer_lines.append(
            Text(
                f"Output truncated. Full output: {state.full_output_path}",
                style=tui_rich_style("warning"),
            )
        )

    children: list[RenderableType] = [Rule(style=accent), header]
    if output_block is not None:
        children.append(output_block)
    children.extend(footer_lines)
    children.append(Rule(style=accent))
    return Group(*children)
