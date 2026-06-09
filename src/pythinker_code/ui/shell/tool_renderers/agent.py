"""Pythinker renderer for the ``Agent`` (subagent) tool."""

from __future__ import annotations

from typing import cast

from rich.console import Group, RenderableType
from rich.style import Style as RichStyle
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
    loading_marker,
    missing_required_arg,
    pending_tool_call_header,
    running_spinner,
    tool_call_header,
)
from pythinker_code.ui.theme import tui_rich_style

_TOOL_NAME = "Agent"
_RUN_AGENTS_TOOL_NAME = "RunAgents"
_DEFAULT_COLLAPSED_LINES = 6
_RUN_AGENTS_ERROR_COLLAPSED_LINES = 8
_RUN_AGENTS_SUMMARY_PREVIEW_CHARS = 160
_BACKGROUND_ACTIVE_STATUSES = frozenset({"created", "starting", "running", "awaiting_approval"})


def _subagent_loader(_ctx: ToolRenderContext) -> Text:
    """Return the muted pulsating transcript marker used for active subagent rows."""
    return loading_marker(style_token="muted")


def _render_call(ctx: ToolRenderContext) -> RenderableType:
    args = ctx.args or {}
    subagent_type = as_str(args.get("subagent_type")) or "coder"
    description = as_str(args.get("description"))
    prompt = as_str(args.get("prompt"))
    resume = as_str(args.get("resume"))
    run_bg = bool(args.get("run_in_background"))
    model = as_str(args.get("model"))

    secondary_token = "thinking_text"
    summary = Text()
    summary.append_text(fg("border_accent", subagent_type))
    if description:
        summary.append_text(fg(secondary_token, f" · {description}"))
    if model:
        summary.append_text(fg("dim", f" · {model}"))
    if run_bg:
        summary.append_text(fg(secondary_token, " · background"))
    if resume:
        summary.append_text(fg(secondary_token, f" · resume {resume[:8]}"))

    style_token = "error" if ctx.is_error else "success" if ctx.has_result else "muted"
    header = tool_call_header(
        "Agent", summary, style_token=style_token, summary_style_token=secondary_token
    )

    missing: list[RenderableType] = []
    if description is None and ctx.has_result:
        missing.append(missing_required_arg("description"))
    if prompt is None:
        if "prompt" in args:
            missing.append(invalid_arg())
        elif ctx.has_result:
            missing.append(missing_required_arg("prompt"))
        rendered = Group(header, *missing) if missing else header
        return running_spinner(
            rendered,
            execution_started=ctx.execution_started,
            has_result=ctx.has_result,
            marker_style_token="muted",
        )

    rendered = Group(header, *missing) if missing else header
    return running_spinner(
        rendered,
        execution_started=ctx.execution_started,
        has_result=ctx.has_result,
        marker_style_token="muted",
    )


def _line_value(text: str, key: str) -> str | None:
    prefix = f"{key}:"
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def _background_status(text: str) -> str | None:
    kind = _line_value(text, "kind")
    status = _line_value(text, "status")
    if kind == "agent" and status in _BACKGROUND_ACTIVE_STATUSES:
        return status
    return None


def _compact_inline(text: str, *, max_chars: int = 80) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    if max_chars <= 1:
        return "…"
    return compact[: max_chars - 1].rstrip() + "…"


def _plural(count: int, singular: str) -> str:
    return f"{count} {singular}" if count == 1 else f"{count} {singular}s"


def _run_agent_arg_summaries(args: dict[str, object]) -> list[tuple[str, str]] | None:
    raw_agents_value = args.get("agents")
    if not isinstance(raw_agents_value, list):
        return None
    raw_agents = cast(list[object], raw_agents_value)
    summaries: list[tuple[str, str]] = []
    for index, raw_agent in enumerate(raw_agents, start=1):
        if not isinstance(raw_agent, dict):
            summaries.append((f"agent-{index}", "coder"))
            continue
        raw_agent_dict = cast(dict[str, object], raw_agent)
        name = as_str(raw_agent_dict.get("name")) or f"agent-{index}"
        subagent_type = as_str(raw_agent_dict.get("subagent_type")) or "coder"
        summaries.append(
            (
                _compact_inline(name, max_chars=24),
                _compact_inline(subagent_type, max_chars=24),
            )
        )
    return summaries


def _render_run_agents_call(ctx: ToolRenderContext) -> RenderableType:
    args = ctx.args or {}
    agent_summaries = _run_agent_arg_summaries(args)
    summary_text = Text()
    if agent_summaries is None:
        if ctx.has_result:
            summary_text.append_text(missing_required_arg("agents"))
        else:
            header = pending_tool_call_header(_RUN_AGENTS_TOOL_NAME)
            return running_spinner(
                header,
                execution_started=ctx.execution_started,
                has_result=ctx.has_result,
                marker_style_token="muted",
            )
    else:
        summary_text.append_text(fg("border_accent", _plural(len(agent_summaries), "agent")))

    mode = "foreground" if args.get("run_in_background") is False else "background"
    if summary_text.plain:
        summary_text.append_text(fg("thinking_text", f" · {mode}"))

    run_summary = as_str(args.get("summary"))
    if run_summary:
        summary_text.append_text(fg("dim", f" · {_compact_inline(run_summary, max_chars=70)}"))

    style_token = "error" if ctx.is_error else "success" if ctx.has_result else "muted"
    header = tool_call_header(
        _RUN_AGENTS_TOOL_NAME,
        summary_text if summary_text.plain else None,
        style_token=style_token,
    )

    children: list[RenderableType] = [header]
    missing: list[RenderableType] = []
    if ctx.has_result and run_summary is None:
        missing.append(missing_required_arg("summary"))
    if missing:
        children.extend(missing)
    if agent_summaries:
        listed = ", ".join(f"{name}:{subagent_type}" for name, subagent_type in agent_summaries[:4])
        if len(agent_summaries) > 4:
            listed = f"{listed}, +{len(agent_summaries) - 4} more"
        children.append(fg("dim", f"agents: {listed}"))

    rendered: RenderableType = Group(*children) if len(children) > 1 else header
    return running_spinner(
        rendered,
        execution_started=ctx.execution_started,
        has_result=ctx.has_result,
        marker_style_token="muted",
    )


def _split_key_value(line: str) -> tuple[str | None, str | None]:
    if ":" not in line:
        return None, None
    key, value = line.split(":", 1)
    key = key.strip()
    if not key or " " in key:
        return None, None
    return key, value.strip()


def _run_agent_summary_preview(result_text: str) -> str | None:
    lines = result_text.splitlines()
    try:
        start = lines.index("[summary]") + 1
    except ValueError:
        start = 0

    metadata_keys = {
        "agent_id",
        "actual_subagent_type",
        "automatic_notification",
        "budget_seconds",
        "dependencies",
        "description",
        "isolation",
        "kind",
        "next_step",
        "resumed",
        "resume_hint",
        "synthesis_state",
        "task_id",
        "tool_status",
    }
    pieces: list[str] = []
    for raw_line in lines[start:]:
        line = raw_line.strip()
        if not line or line == "[summary]":
            continue
        key, _ = _split_key_value(line)
        if key is not None and key.lower() in metadata_keys:
            continue
        heading = line.strip("#*: ").upper()
        if not pieces and heading in {"SUMMARY", "FINDINGS", "RISKS", "OVERALL"}:
            continue
        pieces.append(line)
        if len(" ".join(pieces)) >= _RUN_AGENTS_SUMMARY_PREVIEW_CHARS or len(pieces) >= 2:
            break
    if not pieces:
        return None
    return _compact_inline(
        " ".join(pieces),
        max_chars=_RUN_AGENTS_SUMMARY_PREVIEW_CHARS,
    )


def _hydrate_run_agent_result(agent: dict[str, str]) -> None:
    result_text = agent.get("result_text", "")
    if not result_text:
        return
    for key in (
        "task_id",
        "agent_id",
        "kind",
        "status",
        "description",
        "actual_subagent_type",
    ):
        value = _line_value(result_text, key)
        if not value:
            continue
        if key == "status":
            agent["detail_status"] = value
        elif key == "actual_subagent_type" and not agent.get("subagent_type"):
            agent["subagent_type"] = value
        else:
            agent.setdefault(key, value)
    preview = _run_agent_summary_preview(result_text)
    if preview:
        agent["summary_preview"] = preview


def _parse_run_agents_output(text: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    top: dict[str, str] = {}
    agents: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    result_lines: list[str] = []
    in_result = False

    def finish_result() -> None:
        nonlocal in_result, result_lines
        if current is not None and result_lines:
            current["result_text"] = "\n".join(result_lines)
            _hydrate_run_agent_result(current)
        result_lines = []
        in_result = False

    def finish_agent() -> None:
        finish_result()
        if current is not None:
            agents.append(current)

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if line.startswith("- name: "):
            finish_agent()
            current = {"name": line.removeprefix("- name: ").strip()}
            continue

        if current is None:
            key, value = _split_key_value(line)
            if key is not None and value is not None:
                top[key] = value
            continue

        if in_result:
            if line == "":
                result_lines.append("")
                continue
            if line.startswith("    "):
                result_lines.append(line[4:])
                continue
            finish_result()

        if not line.startswith("  "):
            continue
        stripped = line[2:]
        if stripped == "result: |":
            in_result = True
            result_lines = []
            continue
        key, value = _split_key_value(stripped)
        if key is not None and value is not None:
            current[key] = value

    finish_agent()
    return top, agents


def _status_style_token(status: str) -> str:
    normalized = status.lower()
    if normalized in {"error", "failed", "failure"}:
        return "error"
    if normalized in {"completed", "success", "succeeded"}:
        return "success"
    if normalized in {"created", "starting", "running", "awaiting_approval", "launched"}:
        return "accent"
    return "muted"


def _top_status_label(status: str) -> str:
    if status == "success":
        return "completed"
    if status == "failure":
        return "failed"
    return status or "completed"


def _render_run_agents_text_result(
    ctx: ToolRenderContext, result: ToolResultPayload
) -> RenderableType | None:
    text = (result.text or "").rstrip("\n")
    if not text:
        return None
    ctx.state["__suppress_generic_expand_hint__"] = True
    body, remaining = format_lines_block(
        text,
        expanded=ctx.expanded,
        collapsed_max_lines=_RUN_AGENTS_ERROR_COLLAPSED_LINES,
        style_token="error" if result.is_error else "tool_output",
    )
    if remaining > 0:
        return Group(body, fg("muted", f"… ({remaining} more lines preserved)"))
    return body


def _render_run_agents_result(
    ctx: ToolRenderContext, result: ToolResultPayload
) -> RenderableType | None:
    if not result.text:
        return None
    if result.is_error:
        return _render_run_agents_text_result(ctx, result)

    top, agents = _parse_run_agents_output(result.text)
    if not agents:
        return _render_run_agents_text_result(ctx, result)

    ctx.state["__suppress_generic_expand_hint__"] = True
    status = _top_status_label(top.get("tool_status", "success"))
    count = top.get("agent_count") or str(len(agents))
    mode = top.get("mode")
    approval = top.get("orchestration_approval")

    summary = Text()
    summary.append(f"agents {status}", style=tui_rich_style(_status_style_token(status)))
    summary.append(f" · {count} total", style=tui_rich_style("dim"))
    if mode:
        summary.append(f" · {mode}", style=tui_rich_style("dim"))
    if approval:
        summary.append(f" · approval {approval}", style=tui_rich_style("dim"))

    rows: list[RenderableType] = [summary]
    for index, agent in enumerate(agents):
        is_last = index == len(agents) - 1
        branch = "└─" if is_last else "├─"
        name = agent.get("name") or f"agent-{index + 1}"
        subagent_type = agent.get("subagent_type") or agent.get("actual_subagent_type") or "coder"
        agent_status = agent.get("detail_status") or agent.get("status") or "unknown"
        task_id = agent.get("task_id")

        row = Text(f"{branch} ", style=tui_rich_style("muted"))
        row.append(name, style=tui_rich_style("tool_title") + RichStyle(bold=True))
        row.append(f" · {subagent_type}", style=tui_rich_style("dim"))
        row.append(f" · {agent_status}", style=tui_rich_style(_status_style_token(agent_status)))
        if task_id:
            row.append(f" · {task_id}", style=tui_rich_style("dim"))
        rows.append(row)

        preview = agent.get("summary_preview")
        if agent_status in {"error", "failed", "failure"}:
            preview = agent.get("message") or agent.get("brief") or preview
        if preview:
            prefix = "   " if is_last else "│  "
            rows.append(fg("dim", f"{prefix}{_compact_inline(preview, max_chars=100)}"))

    return Group(*rows)


def _render_result(ctx: ToolRenderContext, result: ToolResultPayload) -> RenderableType | None:
    if not result.text:
        return None
    background_status = None if result.is_error else _background_status(result.text)
    if background_status is not None:
        description = as_str(ctx.args.get("description"))
        label = "background subagent working"
        if description:
            label = f"{label}: {description}"
        line = _subagent_loader(ctx)
        line.append(label, style=tui_rich_style("accent") + RichStyle(bold=True))
        # Hang-indent the detail row under the label (past the 2-cell marker)
        # so the block nests cleanly inside the result gutter.
        return Group(line, fg("dim", f"  status: {background_status}"))

    body, remaining = format_lines_block(
        result.text,
        expanded=ctx.expanded,
        collapsed_max_lines=_DEFAULT_COLLAPSED_LINES,
        style_token="error" if result.is_error else "tool_output",
    )
    if not body.plain:
        return fg("error", "Agent failed") if result.is_error else None
    if remaining > 0:
        more = fg("muted", f"... ({remaining} more lines, ctrl+o to expand)")
        return Group(body, more)
    return body


AGENT_RENDERER = ToolRenderDefinition(
    name=_TOOL_NAME,
    label="subagent",
    render_shell="default",
    render_call=_render_call,
    render_result=_render_result,
)

RUN_AGENTS_RENDERER = ToolRenderDefinition(
    name=_RUN_AGENTS_TOOL_NAME,
    label="subagents",
    render_shell="default",
    render_call=_render_run_agents_call,
    render_result=_render_run_agents_result,
)
