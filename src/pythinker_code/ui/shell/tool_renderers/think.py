"""Pythinker renderer for Pythinker's ``Think`` tool.

Pythinker has no direct ``think`` core tool; we model the call preview after
the ``hidden-thinking-label`` extension — a muted custom-message style
that shows the thought without making the output box loud.
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
    tool_title,
)

_TOOL_NAME = "Think"
_DEFAULT_COLLAPSED_LINES = 6


def _render_call(ctx: ToolRenderContext) -> RenderableType:
    args = ctx.args or {}
    thought = as_str(args.get("thought"))

    header = Text()
    header.append_text(tool_title("think"))
    if thought is None:
        if "thought" in args:
            return Group(header, invalid_arg())
        if ctx.has_result:
            return Group(header, missing_required_arg("thought"))
        header.append_text(fg("muted", " ..."))
        return header

    if not thought:
        return header
    body, remaining = format_lines_block(
        thought,
        expanded=ctx.expanded,
        collapsed_max_lines=_DEFAULT_COLLAPSED_LINES,
        style_token="muted",
    )
    children: list[RenderableType] = [header, body]
    if remaining > 0:
        children.append(fg("muted", f"... ({remaining} more lines, ctrl+e to expand)"))
    return Group(*children)


def _render_result(_ctx: ToolRenderContext, _result: ToolResultPayload) -> RenderableType | None:
    return None


THINK_RENDERER = ToolRenderDefinition(
    name=_TOOL_NAME,
    label="think",
    render_shell="default",
    render_call=_render_call,
    render_result=_render_result,
)
