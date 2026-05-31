from __future__ import annotations

import importlib
from types import SimpleNamespace

from pythinker_code.ui.terminal_capabilities import (
    ascii_glyphs_enabled,
    colors_disabled,
    motion_disabled,
)


def test_color_capability_honors_standard_env_vars() -> None:
    assert colors_disabled({"NO_COLOR": "1"})
    assert colors_disabled({"TERM": "dumb"})
    assert colors_disabled({"CLICOLOR": "0"})
    assert colors_disabled({"PYTHINKER_NO_COLOR": "true"})
    assert not colors_disabled({"TERM": "xterm-256color"})


def test_ascii_glyphs_are_opt_in_or_minimal_terminal() -> None:
    assert ascii_glyphs_enabled({"PYTHINKER_TUI_GLYPHS": "ascii"})
    assert ascii_glyphs_enabled({"PYTHINKER_ASCII_UI": "1"})
    assert ascii_glyphs_enabled({"TERM": "dumb"})
    assert ascii_glyphs_enabled({"TERM": "xterm"}, stdout=SimpleNamespace(encoding="cp1252"))
    assert not ascii_glyphs_enabled({"PYTHINKER_TUI_GLYPHS": "unicode", "TERM": "dumb"})


def test_motion_capability_honors_static_output_env_vars() -> None:
    assert motion_disabled({"TERM": "dumb"})
    assert motion_disabled({"PYTHINKER_REDUCED_MOTION": "1"})
    assert motion_disabled({"PYTHINKER_NO_ANIMATION": "true"})
    assert motion_disabled({"PYTHINKER_STATIC_OUTPUT": "yes"})
    assert not motion_disabled({"TERM": "xterm-256color"})


def test_theme_resolvers_strip_colors_when_no_color_is_set(monkeypatch) -> None:
    from pythinker_code.ui.theme import (
        _strip_ptk_colors,
        get_diff_colors,
        get_toolbar_colors,
        markdown_rich_style,
        tui_rich_style,
    )

    monkeypatch.setenv("NO_COLOR", "1")

    assert tui_rich_style("accent").color is None
    assert tui_rich_style("tool_error_bg").bgcolor is None
    assert markdown_rich_style("link").color is None
    assert get_diff_colors().add_bg.bgcolor is None
    assert get_toolbar_colors().tip_key == "bold"
    assert _strip_ptk_colors("bg:#112233 fg:#abcdef bold italic") == "bold italic"


def test_ascii_glyph_mode_uses_plain_fallbacks(monkeypatch) -> None:
    import pythinker_code.ui.shell.glyphs as glyphs

    monkeypatch.setenv("PYTHINKER_TUI_GLYPHS", "ascii")
    ascii_glyphs = importlib.reload(glyphs)
    try:
        assert ascii_glyphs.SPINNER_FRAMES == ("-", "\\", "|", "/")
        assert ascii_glyphs.REDUCED_MOTION_GLYPH == "*"
        assert ascii_glyphs.TRANSCRIPT_PROMPT_MARKER == ">"
        assert ascii_glyphs.TRANSCRIPT_TOOL_GUTTER == "|"
    finally:
        monkeypatch.delenv("PYTHINKER_TUI_GLYPHS", raising=False)
        importlib.reload(glyphs)
