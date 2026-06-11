"""Tests for statusline v2 rendering: theme tokens, bar, segments."""

from pythinker_code.ui.theme import StatusLineColors, get_statusline_colors


def test_statusline_colors_dark_palette():
    colors = get_statusline_colors()
    assert isinstance(colors, StatusLineColors)
    assert colors.model == "bold fg:#dcb4ff"
    assert colors.usage_ok == "fg:#64d2a0"
    assert colors.usage_crit == "fg:#ff5050"
    assert colors.dim == "fg:#505564"
