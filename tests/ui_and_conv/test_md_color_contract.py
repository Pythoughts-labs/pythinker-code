# tests/ui_and_conv/test_md_color_contract.py
"""Tier-1 ANSI/color contract tests (spec area 4).

Uses the truecolor-preserving capture so we can assert on SGR sequences,
exactly like tests/ui_and_conv/test_tui_render_snapshots.py.
"""

from __future__ import annotations

import re

from rich.console import Console
from rich.style import Style as RichStyle
from rich.text import Text

from pythinker_code.ui.shell.components.markdown import pythinker_markdown
from pythinker_code.ui.theme import get_markdown_colors
from tests.ui_and_conv._md_contract_helpers import render_ansi


def _sgr_fg(color: str) -> str:
    """Return the exact SGR escape Rich emits for ``color`` as a foreground.

    Works for both ``#rrggbb`` (truecolor ``38;2;..``) and ANSI names such as
    ``"cyan"`` (``36``) — markdown code/links now use terminal ANSI names.
    """
    console = Console(force_terminal=True, color_system="truecolor", width=10)
    with console.capture() as cap:
        console.print(Text("X", style=RichStyle(color=color)), end="")
    match = re.search(r"\x1b\[[0-9;]*m", cap.get())
    return match.group(0) if match else ""


def test_blockquote_and_ordered_markers_render_ansi_colors():
    """Blockquotes render green and ordered-list markers render bright_blue in
    the actual output (not just at the palette level)."""
    md = "> quoted line\n\n1. first item\n2. second item\n"
    out = render_ansi(pythinker_markdown(md), width=40)
    assert re.search(r"\x1b\[(?:\d+;)*32m", out), "blockquote text is not green"
    assert re.search(r"\x1b\[(?:\d+;)*94m", out), "ordered marker is not bright_blue"


def test_code_block_border_does_not_use_inline_code_color():
    """Bug class: 'border colors inheriting code-span color'.

    The bordered code block frame uses code_block_border; inline code uses
    inline_code. They must be distinct colors, and the captured frame must not
    paint the border in the inline-code color.
    """
    colors = get_markdown_colors("dark")
    assert colors.code_block_border != colors.inline_code, (
        "precondition: palette must distinguish border from inline code"
    )
    md = "Here is `inline` and a block:\n\n```python\nx = 1\n```\n"
    coloured = render_ansi(pythinker_markdown(md), width=60)
    # The rounded frame characters must not carry the inline-code foreground.
    inline_fg = _sgr_fg(colors.inline_code)
    for frame_char in ("╭", "╰", "─"):
        found_count = 0
        start = 0
        while True:
            idx = coloured.find(frame_char, start)
            if idx == -1:
                break
            found_count += 1
            window = coloured[max(0, idx - 24) : idx]
            assert inline_fg not in window, "border frame inherited inline-code color"
            start = idx + 1
        assert found_count > 0, f"missing expected frame glyph {frame_char!r}"
