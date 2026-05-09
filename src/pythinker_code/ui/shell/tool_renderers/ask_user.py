"""Pythinker renderer for Pythinker's ``AskUserQuestion`` tool.

Shows the first question + its option labels in the call preview, plus
a count badge when there are multiple questions. The result preview is
the user's selection summary (or auto-dismiss note).
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
    invalid_arg,
    tool_title,
)

_TOOL_NAME = "AskUserQuestion"
_DEFAULT_COLLAPSED_LINES = 8


def _render_call(ctx: ToolRenderContext) -> RenderableType:
    args = ctx.args or {}
    questions = args.get("questions")

    header = Text()
    header.append_text(tool_title("ask user"))
    if not isinstance(questions, list) or not questions:
        if "questions" in args:
            return Group(header, invalid_arg())
        header.append_text(fg("muted", " ..."))
        return header

    questions_list = cast("list[Any]", questions)
    qs: list[dict[str, Any]] = [
        cast("dict[str, Any]", q) for q in questions_list if isinstance(q, dict)
    ]
    if len(qs) > 1:
        header.append_text(fg("muted", f" ({len(qs)} questions)"))

    children: list[RenderableType] = [header]
    for q in qs[:2]:
        question_text = as_str(q.get("question")) or ""
        if question_text:
            children.append(fg("accent", f"  ? {question_text}"))
        opts = q.get("options")
        if isinstance(opts, list):
            opts_list = cast("list[Any]", opts)
            for opt in opts_list[:4]:
                if not isinstance(opt, dict):
                    continue
                opt_dict = cast("dict[str, Any]", opt)
                label = as_str(opt_dict.get("label")) or "?"
                children.append(fg("dim", f"    • {label}"))
    if len(qs) > 2:
        children.append(fg("muted", f"  ... +{len(qs) - 2} more"))
    return Group(*children)


def _render_result(ctx: ToolRenderContext, result: ToolResultPayload) -> RenderableType | None:
    if not result.text:
        return None
    body, remaining = format_lines_block(
        result.text,
        expanded=ctx.expanded,
        collapsed_max_lines=_DEFAULT_COLLAPSED_LINES,
        style_token="error" if result.is_error else "tool_output",
    )
    if not body.plain:
        return None
    if remaining > 0:
        more = fg("muted", f"... ({remaining} more lines, ctrl+e to expand)")
        return Group(body, more)
    return body


ASK_USER_RENDERER = ToolRenderDefinition(
    name=_TOOL_NAME,
    label="ask user",
    render_shell="default",
    render_call=_render_call,
    render_result=_render_result,
)
