"""Helpers for formatting keybinding hints in Pythinker status lines."""

from __future__ import annotations

import sys

from rich.text import Text

from pythinker_code.ui.shell.keymap import key_text
from pythinker_code.ui.theme import tui_rich_style

__all__ = [
    "format_key_text",
    "key_display_text",
    "key_hint",
    "raw_key_hint",
]


def _format_key_part(part: str, *, capitalize: bool) -> str:
    display = "option" if sys.platform == "darwin" and part.lower() == "alt" else part
    if capitalize and display:
        return display[:1].upper() + display[1:]
    return display


def format_key_text(key: str, *, capitalize: bool = False) -> str:
    """Format a raw keybinding string for display.

    Mirrors the reference UI: alternatives stay separated with ``/`` and key
    chords stay separated with ``+``. On macOS, ``alt`` is shown as
    ``option`` to match terminal/user wording.
    """
    return "/".join(
        "+".join(_format_key_part(part, capitalize=capitalize) for part in chord.split("+"))
        for chord in key.split("/")
    )


def key_display_text(keybinding: str) -> str:
    """Resolve *keybinding* and return display text with capitalized parts."""
    return format_key_text(key_text(keybinding) or keybinding, capitalize=True)


def raw_key_hint(key: str, description: str) -> Text:
    """Format ``Esc cancel``-style hint with a raw key string."""
    out = Text()
    out.append(format_key_text(key), style=tui_rich_style("dim"))
    out.append(f" {description}", style=tui_rich_style("muted"))
    return out


def key_hint(key: str, description: str) -> Text:
    """Format a key hint, resolving semantic keybinding ids when available."""
    return raw_key_hint(key_text(key) or key, description)
