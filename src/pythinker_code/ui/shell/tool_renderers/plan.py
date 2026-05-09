"""Pythinker renderers for Pythinker's plan-mode tools.

Covers ``EnterPlanMode`` (no args) and ``ExitPlanMode`` (optional alternatives
list). Both produce single-line headers; ExitPlanMode also lists the options
inline since they're short.
"""

from __future__ import annotations

from typing import Any, cast

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
    tool_title,
)

# ---------------------------------------------------------------------------
# EnterPlanMode
# ---------------------------------------------------------------------------


def _render_enter_call(_ctx: ToolRenderContext) -> RenderableType:
    line = Text()
    line.append_text(tool_title("plan mode"))
    line.append_text(fg("muted", " (entering)"))
    return line


def _render_plan_result(ctx: ToolRenderContext, result: ToolResultPayload) -> RenderableType | None:
    if not result.text:
        return None
    body, remaining = format_lines_block(
        result.text,
        expanded=ctx.expanded,
        collapsed_max_lines=8,
        style_token="error" if result.is_error else "tool_output",
    )
    if not body.plain:
        return None
    if remaining > 0:
        return Group(body, fg("muted", f"... ({remaining} more lines, ctrl+e to expand)"))
    return body


ENTER_PLAN_RENDERER = ToolRenderDefinition(
    name="EnterPlanMode",
    label="plan mode",
    render_shell="default",
    render_call=_render_enter_call,
    render_result=_render_plan_result,
)


# ---------------------------------------------------------------------------
# ExitPlanMode
# ---------------------------------------------------------------------------


def _render_exit_call(ctx: ToolRenderContext) -> RenderableType:
    args = ctx.args or {}
    options = args.get("options")
    line = Text()
    line.append_text(tool_title("plan mode"))
    line.append_text(fg("muted", " (exiting)"))

    if not isinstance(options, list) or not options:
        return line
    options_list = cast("list[Any]", options)
    opts: list[dict[str, Any]] = [
        cast("dict[str, Any]", o) for o in options_list if isinstance(o, dict)
    ]
    if not opts:
        return line

    children: list[RenderableType] = [line]
    for opt in opts[:3]:
        label = as_str(opt.get("label")) or "?"
        children.append(fg("accent", f"  • {label}"))
    return Group(*children)


EXIT_PLAN_RENDERER = ToolRenderDefinition(
    name="ExitPlanMode",
    label="plan mode",
    render_shell="default",
    render_call=_render_exit_call,
    render_result=_render_plan_result,
)
