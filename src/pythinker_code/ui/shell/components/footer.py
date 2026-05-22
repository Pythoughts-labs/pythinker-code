"""Pythinker footer component.


plus its data provider: a two- or three-line status block with cwd/git/session
on top, usage stats + context%/model on the right, and optional extension
status lines.

This module is intentionally state-source-agnostic. Callers populate a
:class:`FooterState` dataclass from wherever the truth lives (Pythinker's
session manager, soul state, runtime config) and pass it to
:func:`render_footer`. Wiring into ``prompt.py`` is a separate task.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Group, RenderableType
from rich.text import Text

from pythinker_code.ui.shell.components.render_utils import truncate_to_width
from pythinker_code.ui.shell.design_system import ShellTone, render_segment_line
from pythinker_code.ui.theme import tui_rich_style

__all__ = [
    "FooterState",
    "FooterUsage",
    "format_tokens",
    "render_footer",
]


_WHITESPACE_RE = re.compile(r"[\r\n\t]+")
_MULTI_SPACE_RE = re.compile(r" +")


@dataclass(frozen=True, slots=True)
class FooterUsage:
    """Cumulative usage stats over the session.

    Mirrors the ``message.usage`` aggregate. All counts are token totals.
    ``cost_total`` is in dollars (equivalent to summing message-level cost.total).
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_total: float = 0.0


@dataclass(frozen=True, slots=True)
class FooterState:
    """Inputs for :func:`render_footer`.

    Attributes:
        cwd: Working directory (will be home-shortened with ``~``).
        git_branch: Current branch name, or ``None`` to omit.
        session_name: Friendly session label, or ``None``.
        usage: Cumulative usage; pass an empty :class:`FooterUsage` to
            suppress all token counters.
        context_percent: ``0..100`` percentage of context window used, or
            ``None`` if unknown post-compaction.
        context_window: Total context window size for the active model.
        auto_compact_enabled: Adds the ``(auto)`` suffix on the context %.
        model_id: Display name of the active model, or ``None``.
        model_provider: Provider id, only shown when ``show_provider`` is
            ``True`` and there's room.
        show_provider: Set to ``True`` when more than one provider is
            available — keeps the footer terse otherwise.
        thinking_level: ``"off" | "low" | "medium" | "high"`` or ``None``;
            renders as ``model • <level>`` when set.
        oauth_subscription: Adds ``(sub)`` next to the cost.
        extension_statuses: Optional map of extension id → status text.
            Sorted alphabetically and emitted as a third line.
    """

    cwd: str
    git_branch: str | None = None
    session_name: str | None = None
    usage: FooterUsage = field(default_factory=FooterUsage)
    context_percent: float | None = None
    context_window: int = 0
    auto_compact_enabled: bool = True
    model_id: str | None = None
    model_provider: str | None = None
    show_provider: bool = False
    thinking_level: str | None = None
    oauth_subscription: bool = False
    extension_statuses: dict[str, str] = field(default_factory=dict[str, str])


def format_tokens(count: int) -> str:
    """Pythinker's compact token formatter: ``1234`` → ``1.2k``."""
    if count < 1_000:
        return str(count)
    if count < 10_000:
        return f"{count / 1000:.1f}k"
    if count < 1_000_000:
        return f"{round(count / 1000)}k"
    if count < 10_000_000:
        return f"{count / 1_000_000:.1f}M"
    return f"{round(count / 1_000_000)}M"


def _sanitize(text: str) -> str:
    return _MULTI_SPACE_RE.sub(" ", _WHITESPACE_RE.sub(" ", text)).strip()


def _shorten_home(cwd: str) -> str:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if not home:
        return cwd
    try:
        rel = Path(cwd).relative_to(home)
        rel_str = str(rel)
        return "~" if rel_str == "." else f"~/{rel_str}"
    except ValueError:
        return cwd


def _build_pwd_line(state: FooterState) -> str:
    pwd = _shorten_home(state.cwd)
    if state.git_branch:
        pwd = f"{pwd} ({state.git_branch})"
    if state.session_name:
        pwd = f"{pwd} • {state.session_name}"
    return pwd


def _build_stats_left(state: FooterState) -> tuple[Text, str]:
    """Return ``(rendered_left_text, plain_left_text)``.

    The plain text is needed for width math when laying out the right side.
    """
    parts: list[tuple[str, str]] = []  # (text, token)
    u = state.usage
    if u.input_tokens:
        parts.append((f"↑{format_tokens(u.input_tokens)}", "dim"))
    if u.output_tokens:
        parts.append((f"↓{format_tokens(u.output_tokens)}", "dim"))
    if u.cache_read_tokens:
        parts.append((f"R{format_tokens(u.cache_read_tokens)}", "dim"))
    if u.cache_write_tokens:
        parts.append((f"W{format_tokens(u.cache_write_tokens)}", "dim"))
    if u.cost_total or state.oauth_subscription:
        sub = " (sub)" if state.oauth_subscription else ""
        parts.append((f"${u.cost_total:.3f}{sub}", "dim"))

    auto = " (auto)" if state.auto_compact_enabled else ""
    if state.context_percent is None:
        ctx_text = f"?/{format_tokens(state.context_window)}{auto}"
        ctx_token = "dim"
    else:
        ctx_text = f"{state.context_percent:.1f}%/{format_tokens(state.context_window)}{auto}"
        if state.context_percent > 90:
            ctx_token = "error"
        elif state.context_percent > 70:
            ctx_token = "warning"
        else:
            ctx_token = "dim"
    parts.append((ctx_text, ctx_token))

    rendered = Text()
    plain_parts: list[str] = []
    for i, (text, token) in enumerate(parts):
        if i:
            rendered.append(" ", style=tui_rich_style("dim"))
            plain_parts.append(" ")
        rendered.append(text, style=tui_rich_style(token))
        plain_parts.append(text)
    return rendered, "".join(plain_parts)


def _build_right_side(state: FooterState, *, plain_left_width: int, width: int) -> str:
    if not state.model_id:
        return ""
    right = state.model_id
    if state.thinking_level:
        right = f"{state.model_id} • {state.thinking_level}"
    if state.show_provider and state.model_provider:
        candidate = f"({state.model_provider}) {right}"
        if plain_left_width + 2 + len(candidate) <= width:
            right = candidate
    return right


def render_footer(state: FooterState, *, width: int) -> RenderableType:
    """Build the multi-line footer renderable for *state* at *width*."""
    dim = tui_rich_style("dim")

    pwd = _build_pwd_line(state)
    pwd_truncated = truncate_to_width(pwd, max(1, width))
    pwd_text = Text(pwd_truncated, style=dim)

    _, stats_left_plain = _build_stats_left(state)
    if len(stats_left_plain) > width:
        truncated = truncate_to_width(stats_left_plain, width)
        stats_left_plain = truncated

    right = _build_right_side(state, plain_left_width=len(stats_left_plain), width=width)
    stats_line = render_segment_line(
        left=[stats_left_plain],
        right=[right],
        width=width,
        tone=ShellTone.MUTED,
    )
    if state.context_percent is not None and state.context_percent > 70:
        stats_line.stylize(tui_rich_style("warning" if state.context_percent <= 90 else "error"))

    children: list[RenderableType] = [pwd_text, stats_line]
    if state.extension_statuses:
        ordered = sorted(state.extension_statuses.items(), key=lambda kv: kv[0])
        joined = " ".join(_sanitize(text) for _, text in ordered)
        ext = truncate_to_width(joined, width)
        children.append(Text(ext, style=dim))
    return Group(*children)
