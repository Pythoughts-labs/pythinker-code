"""Shift+Tab is rebound from plan-toggle to thinking-cycle (plan moves to /plan)."""

from __future__ import annotations

from pythinker_code.ui.shell.keymap import (
    all_keybindings,
    keybinding_description,
    key_text,
)


def test_shift_tab_bound_to_thinking_cycle_not_plan() -> None:
    assert key_text("app.thinking.cycle") == "shift+tab"
    # plan mode moved to the /plan slash command; no keybinding remains
    assert "app.plan.toggle" not in all_keybindings()
    assert key_text("app.plan.toggle") == ""


def test_thinking_cycle_has_help_description() -> None:
    assert keybinding_description("app.thinking.cycle") == "cycle thinking level"
