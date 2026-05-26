"""Cross-config render matrix: width x NO_COLOR x reduced-motion.

Guards the spacing/diff/markdown work in the TUI render tracks against
config-specific regressions (narrow terminals, NO_COLOR, reduced motion).
"""

from __future__ import annotations

import pytest
from rich.console import Console

from pythinker_code.ui.shell.components import render_diff
from pythinker_code.ui.shell.components.markdown import pythinker_markdown
from pythinker_code.ui.shell.motion import ActivitySnapshot, activity_status_line

WIDTHS = [40, 80, 120]
_DIFF = "  10 import time\n+ 11 import asyncio\n- 13 old = 1\n+ 13 new = 2"
_BOX_CHARS = set("╭╮╰╯│─┌┐└┘├┤┬┴┼")


def _render(renderable, *, width: int, no_color: bool) -> str:
    console = Console(width=width, record=True, highlight=False, no_color=no_color)
    console.print(renderable)
    return console.export_text()


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("no_color", [False, True])
def test_inline_diff_renders_boxless_across_configs(width: int, no_color: bool) -> None:
    out = _render(render_diff(_DIFF), width=width, no_color=no_color)
    assert out.strip()
    assert not (_BOX_CHARS & set(out)), "inline diff must stay boxless (the screenshot look)"
    assert "+" in out and "-" in out  # markers survive


@pytest.mark.parametrize("width", WIDTHS)
def test_inline_diff_content_stable_under_color_toggle(width: int) -> None:
    colored = _render(render_diff(_DIFF), width=width, no_color=False)
    plain = _render(render_diff(_DIFF), width=width, no_color=True)
    assert colored == plain  # NO_COLOR changes styling, never content


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("no_color", [False, True])
def test_markdown_renders_across_configs(width: int, no_color: bool) -> None:
    md = pythinker_markdown("# Title\n## Section\n\n- item one\n- `code`\n\n> quote\n")
    out = _render(md, width=width, no_color=no_color)
    assert "Title" in out and "Section" in out and "item one" in out


@pytest.mark.parametrize("width", WIDTHS)
def test_markdown_code_fences_use_aligned_panel_frame(width: int) -> None:
    out = _render(
        pythinker_markdown("```bash\npythinker mcp list\n```"),
        width=width,
        no_color=True,
    )
    lines = [line for line in out.splitlines() if line]

    assert lines[0].startswith("╭─ bash ")
    assert lines[0].endswith("╮")
    assert lines[1].startswith("│ pythinker mcp list")
    assert lines[1].endswith("│")
    assert lines[2].startswith("╰")
    assert lines[2].endswith("╯")


@pytest.mark.parametrize("width", WIDTHS)
def test_activity_line_reduced_motion_uses_static_glyph(width: int) -> None:
    snap = ActivitySnapshot(label="Working", elapsed_s=3.0, reduced_motion=True)
    out = _render(activity_status_line(snap, width=width), width=width, no_color=True)
    assert "●" in out  # static dot, not an animated braille frame
    assert "Working" in out


@pytest.mark.parametrize("width", WIDTHS)
def test_activity_line_full_motion_uses_braille_frame(width: int) -> None:
    snap = ActivitySnapshot(label="Working", elapsed_s=0.0, reduced_motion=False)
    out = _render(activity_status_line(snap, width=width), width=width, no_color=True)
    assert "●" not in out
    assert any(frame in out for frame in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
