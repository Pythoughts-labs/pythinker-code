"""Minimal Pythinker keybinding registry.

Built-in keybinding registry
``modes/interactive/components/keybinding-hints.ts`` . the
full registry lists ~50 identifiers wired across model/session/tree
selectors, most of which Pythinker doesn't expose yet — we ship only the
semantic ids we currently use, with a `register_keybinding` hatch so
extensions or future features can add more without forking this file.

Two surfaces:

* :func:`key_text(name)` returns the printable representation
  (``"ctrl+e"``, ``"esc"``) — used inline in renderers.
* :func:`key_hint(name, description)` returns a Rich ``Text`` ready to
  drop into a card (``"ctrl+e expand"``, dim+muted styled).
"""

from __future__ import annotations

from rich.text import Text

from pythinker_code.ui.theme import tui_rich_style

__all__ = [
    "all_keybindings",
    "key_hint",
    "key_text",
    "register_keybinding",
]


# Default registry. Keys are Pythinker semantic ids ("app.tools.expand");
# values are the key chord(s) the host will dispatch.
_REGISTRY: dict[str, tuple[str, ...]] = {
    "app.interrupt": ("esc", "ctrl+c"),
    "app.exit": ("ctrl+d",),
    "app.suspend": ("ctrl+z",),
    "app.tools.expand": ("ctrl+e",),
    "app.message.followUp": ("alt+enter",),
    "app.editor.external": ("ctrl+x",),
    "app.session.new": ("ctrl+n",),
    "tui.select.cancel": ("esc",),
    "tui.select.confirm": ("enter",),
}


def register_keybinding(name: str, *keys: str) -> None:
    """Register or override the key chord(s) for *name*.

    Last writer wins — extensions calling this at startup can replace any
    builtin binding. Empty *keys* removes the binding entirely.
    """
    if not keys:
        _REGISTRY.pop(name, None)
        return
    _REGISTRY[name] = tuple(keys)


def all_keybindings() -> dict[str, tuple[str, ...]]:
    """Return a copy of the full registry — useful for `/keys` overlays."""
    return dict(_REGISTRY)


def key_text(name: str) -> str:
    """Render the chord(s) bound to *name* as ``"ctrl+e"`` or ``"esc/ctrl+c"``.

    Returns an empty string when *name* is unknown — callers can fall back
    to a hard-coded label.
    """
    keys = _REGISTRY.get(name)
    if not keys:
        return ""
    return "/".join(keys)


def key_hint(name: str, description: str) -> Text:
    """Build a ``"<keys> <description>"`` hint as styled Rich Text."""
    out = Text()
    label = key_text(name)
    if label:
        out.append(label, style=tui_rich_style("dim"))
        out.append(" ")
    out.append(description, style=tui_rich_style("muted"))
    return out
