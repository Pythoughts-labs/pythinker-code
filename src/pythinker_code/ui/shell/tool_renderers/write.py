"""Pythinker renderer for Pythinker's ``WriteFile`` tool.

 .

This renderer could incrementally syntax-highlights streaming content via a
lookahead cache. We skip the cache for now and rely on plain text plus a
trailing truncation hint — highlighting can be layered on later via
``rich.syntax.Syntax``.
"""

from __future__ import annotations

from rich.console import Group, RenderableType
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
    invalid_arg,
    missing_required_arg,
    running_spinner,
    shorten_path,
    tool_title,
)

_TOOL_NAME = "WriteFile"
_DEFAULT_PREVIEW_LINES = 10


def _render_call(ctx: ToolRenderContext) -> RenderableType:
    args = ctx.args or {}
    raw_path = as_str(args.get("path"))
    raw_content = as_str(args.get("content"))
    mode = args.get("mode")

    title = tool_title("write" if mode != "append" else "append")
    line = Text()
    line.append_text(title)
    line.append(" ")

    if raw_path is None:
        if "path" in args:
            line.append_text(invalid_arg())
        elif ctx.has_result:
            line.append_text(missing_required_arg("path"))
        else:
            line.append_text(fg("tool_output", "..."))
    else:
        line.append_text(fg("accent", shorten_path(raw_path, cwd=ctx.cwd)))

    head = running_spinner(line, execution_started=ctx.execution_started, has_result=ctx.has_result)

    if raw_content is None:
        if "content" in args:
            return Group(
                head,
                fg("error", "[invalid content arg - expected string]"),
            )
        if ctx.has_result:
            return Group(head, missing_required_arg("content"))
        return head

    if not raw_content:
        return head

    body, remaining = format_lines_block(
        raw_content,
        expanded=ctx.expanded,
        collapsed_max_lines=_DEFAULT_PREVIEW_LINES,
        style_token="tool_output",
    )
    if not body.plain:
        return head
    if remaining > 0:
        total = raw_content.count("\n") + 1
        more = fg("muted", f"... ({remaining} more lines, {total} total, ctrl+e to expand)")
        return Group(head, Text(""), body, more)
    return Group(head, Text(""), body)


def _render_result(ctx: ToolRenderContext, result: ToolResultPayload) -> RenderableType | None:
    # Render the result when it's an error. On success, the call
    # preview already shows the full payload.
    if not result.is_error or not result.text:
        return None
    body, _ = format_lines_block(
        result.text,
        expanded=True,
        collapsed_max_lines=0,
        style_token="error",
    )
    return body if body.plain else None


WRITE_RENDERER = ToolRenderDefinition(
    name=_TOOL_NAME,
    label="write",
    render_shell="default",
    render_call=_render_call,
    render_result=_render_result,
)
