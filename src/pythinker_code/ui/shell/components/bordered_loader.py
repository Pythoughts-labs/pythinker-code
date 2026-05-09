"""Bordered spinner card with optional cancel hint.

A Rich-friendly stand-in for the bordered loader pattern used elsewhere in
the TUI — top/bottom rules in the active accent color, a centered spinner +
message, and an optional ``esc to cancel`` line. Stateless: callers pass a
:class:`BorderedLoaderState` and re-call :func:`render_bordered_loader`
each tick.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.spinner import Spinner
from rich.text import Text

from pythinker_code.ui.shell.keymap import key_text
from pythinker_code.ui.theme import tui_rich_style

__all__ = [
    "BorderedLoaderState",
    "render_bordered_loader",
]


@dataclass(frozen=True, slots=True)
class BorderedLoaderState:
    """Inputs for :func:`render_bordered_loader`.

    Attributes:
        message: Status text shown next to the spinner.
        cancellable: When ``True``, append a ``<esc> cancel`` hint line.
        spinner: Spinner style passed to ``rich.spinner.Spinner``.
        accent_token: TUI token name for the border + spinner color.
    """

    message: str
    cancellable: bool = True
    spinner: str = "dots"
    accent_token: str = "border_accent"


def render_bordered_loader(state: BorderedLoaderState) -> RenderableType:
    """Build the bordered loader renderable for *state*."""
    accent = tui_rich_style(state.accent_token)
    muted = tui_rich_style("muted")

    spinner = Spinner(state.spinner, text=Text(state.message, style=muted), style=accent)

    children: list[RenderableType] = [Rule(style=accent), spinner]
    if state.cancellable:
        cancel_key = key_text("tui.select.cancel") or "esc"
        hint = Text()
        hint.append(cancel_key, style=tui_rich_style("dim"))
        hint.append(" cancel", style=muted)
        children.append(hint)
    children.append(Rule(style=accent))
    return Group(*children)
