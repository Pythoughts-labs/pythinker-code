"""Helpers for formatting keybinding hints in Pythinker status lines."""

from __future__ import annotations

from rich.text import Text


def raw_key_hint(key: str, description: str) -> Text:
    """Format ``Esc cancel``-style hint with a raw key string.

    Use when no semantic keybinding is registered yet (or the binding is
    fixed at the OS/terminal level, e.g. ``Esc``).
    """
    out = Text()
    out.append(key, style="grey50")
    out.append(f" {description}", style="grey39")
    return out


def key_hint(key: str, description: str) -> Text:
    """Format a key hint. Currently aliased to :func:`raw_key_hint`.

    Reserved for a future keymap registry — once Phase 10 lands, this will
    look up *key* in a central registry instead of taking it verbatim. The
    public API is split now so call sites don't churn later.
    """
    return raw_key_hint(key, description)
