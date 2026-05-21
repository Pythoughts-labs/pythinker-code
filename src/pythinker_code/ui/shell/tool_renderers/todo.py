"""Pythinker renderer for Pythinker's ``SetTodoList`` tool.

Renders the todo list with aligned status icons:

* ``○`` pending
* ``◐`` in_progress (highlighted)
* ``●`` done (success)
"""

from __future__ import annotations

from typing import Any, cast

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from pythinker_code.ui.shell.tool_renderers import (
    ToolRenderContext,
    ToolRenderDefinition,
    ToolResultPayload,
)
from pythinker_code.ui.shell.tool_renderers._render_utils import (
    as_str,
    fg,
    format_lines_block,
    tool_title,
)

_TOOL_NAME = "SetTodoList"
_DEFAULT_COLLAPSED_LINES = 12

_ICONS = {
    "pending": "○",
    "in_progress": "◐",
    "done": "●",
}


def _icon_token(status: str) -> str:
    if status == "done":
        return "success"
    if status == "in_progress":
        return "accent"
    return "muted"


def _render_call(ctx: ToolRenderContext) -> RenderableType:
    args = ctx.args or {}
    todos = args.get("todos")

    header = Text()
    header.append_text(tool_title("todos"))

    if todos is None:
        header.append_text(fg("muted", " (read)"))
        return header

    if not isinstance(todos, list):
        header.append_text(fg("muted", " ..."))
        return header

    todos_list = cast("list[Any]", todos)
    items: list[dict[str, Any]] = [
        cast("dict[str, Any]", t) for t in todos_list if isinstance(t, dict)
    ]
    counts = {"pending": 0, "in_progress": 0, "done": 0}
    for item in items:
        status = as_str(item.get("status")) or "pending"
        if status in counts:
            counts[status] += 1

    badge = f" {counts['done']}/{len(items)} done"
    header.append_text(fg("muted", badge))

    visible = items if ctx.expanded else items[:_DEFAULT_COLLAPSED_LINES]
    table = Table.grid(padding=0)
    table.add_column(width=2, no_wrap=True)
    table.add_column(ratio=1)
    for item in visible:
        status = as_str(item.get("status")) or "pending"
        title = as_str(item.get("title")) or ""
        icon = _ICONS.get(status, "○")
        icon_text = fg(_icon_token(status), icon)
        if status == "done":
            title_text = fg("muted", title)
        elif status == "in_progress":
            title_text = fg("accent", title)
        else:
            title_text = fg("tool_output", title)
        table.add_row(icon_text, title_text)

    rows: list[RenderableType] = [header, table]
    if not ctx.expanded and len(items) > len(visible):
        rows.append(fg("muted", f"   ... +{len(items) - len(visible)} more (ctrl+e to expand)"))
    return Group(*rows)


def _render_result(ctx: ToolRenderContext, result: ToolResultPayload) -> RenderableType | None:
    if not result.text or not result.is_error:
        return None
    body, _ = format_lines_block(
        result.text,
        expanded=True,
        collapsed_max_lines=0,
        style_token="error",
    )
    return body if body.plain else None


TODO_RENDERER = ToolRenderDefinition(
    name=_TOOL_NAME,
    label="todos",
    render_shell="default",
    render_call=_render_call,
    render_result=_render_result,
)
