"""Tests for terminal-safe Rich Live rendering."""

from __future__ import annotations

from pythinker_code.ui.shell.visualize._live_view import _LIVE_VERTICAL_OVERFLOW


def test_live_view_does_not_render_past_terminal_viewport() -> None:
    """Non-interactive Rich Live mode must not visibly overflow the screen."""
    assert _LIVE_VERTICAL_OVERFLOW == "ellipsis"
