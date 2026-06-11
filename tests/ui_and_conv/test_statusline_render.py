"""Tests for statusline v2 rendering: theme tokens, bar, segments."""

from pythinker_code.ui.theme import StatusLineColors, get_statusline_colors


def test_statusline_colors_dark_palette():
    colors = get_statusline_colors()
    assert isinstance(colors, StatusLineColors)
    assert colors.model == "bold fg:#dcb4ff"
    assert colors.usage_ok == "fg:#64d2a0"
    assert colors.usage_crit == "fg:#ff5050"
    assert colors.dim == "fg:#505564"


from pythinker_code.ui.shell.statusline import smooth_bar, usage_level


def test_usage_level_thresholds():
    assert usage_level(0) == "ok"
    assert usage_level(49) == "ok"
    assert usage_level(50) == "mid"
    assert usage_level(69) == "mid"
    assert usage_level(70) == "high"
    assert usage_level(89) == "high"
    assert usage_level(90) == "crit"
    assert usage_level(200) == "crit"


def test_smooth_bar_eighth_blocks():
    assert smooth_bar(0, width=8) == "░" * 8
    assert smooth_bar(100, width=8) == "█" * 8
    # 18% of 10 cells = 1.8 cells = 1 full block + 6/8 partial + 8 empty
    assert smooth_bar(18, width=10) == "█▊" + "░" * 8
    # never exceeds width
    assert len(smooth_bar(99, width=10)) == 10


def test_smooth_bar_ascii_fallback():
    assert smooth_bar(50, width=8, ascii_only=True) == "####----"
    assert smooth_bar(0, width=8, ascii_only=True) == "--------"
