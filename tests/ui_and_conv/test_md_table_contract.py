# tests/ui_and_conv/test_md_table_contract.py
"""Tier-1 contract tests for Markdown table rendering (spec area 3).

Each test names the bug class it guards. These assert the EXISTING stack
(pythinker_markdown over markdown-it + Rich) already meets the contract; a
failure is a real regression to surface, not to silence.
"""

from __future__ import annotations

import pytest

from pythinker_code.ui.shell.components.markdown import (
    _escape_code_span_pipes,
    pythinker_markdown,
)
from tests.ui_and_conv._md_contract_helpers import WIDTHS, render_plain

# Box-drawing glyphs the bordered grid uses for edges, junctions, and rules.
# Stripped (alongside whitespace) when asserting cell content survived a wrap.
_BOX_DRAWING_GLYPHS = "┌┬┐├┼┤└┴┘─│"


def test_table_with_piped_inline_code_keeps_columns():
    """Bug class: 'tables breaking on piped inline code'."""
    md = "| Expr | Meaning |\n| --- | --- |\n| `a | b` | bitwise or |\n| plain | text |\n"
    out = render_plain(pythinker_markdown(md), width=80)
    lines = [line for line in out.splitlines() if line.strip()]

    # Both data rows survive as distinct table rows; this is stronger than
    # checking content presence, which could also pass for a collapsed paragraph.
    assert any("Expr" in line and "Meaning" in line for line in lines)
    code_row = [line for line in lines if "a | b" in line and "bitwise or" in line]
    plain_row = [line for line in lines if "plain" in line and "text" in line]
    assert code_row
    assert plain_row
    assert code_row[0] != plain_row[0]


def test_table_with_escaped_pipes_keeps_literal_pipe():
    """Bug class: escaped pipe must render as a literal '|', not split a cell."""
    md = "| Col |\n| --- |\n| a \\| b |\n"
    out = render_plain(pythinker_markdown(md), width=80)
    assert "a | b" in out  # literal pipe preserved
    assert "a \\| b" not in out
    assert "Col" in out


def test_escape_code_span_pipes_standard_case():
    # raw pipe inside a single-backtick code span gets escaped; outer table pipes untouched
    assert _escape_code_span_pipes("| `a | b` | bitwise or |") == "| `a \\| b` | bitwise or |"


def test_escape_code_span_pipes_double_backticks():
    assert _escape_code_span_pipes("| ``a | b`` | target |") == "| ``a \\| b`` | target |"


def test_escape_code_span_pipes_already_escaped_is_idempotent():
    # must NOT double-escape an existing \| -> \\|
    assert _escape_code_span_pipes("| `a \\| b` | target |") == "| `a \\| b` | target |"


def test_escape_code_span_pipes_no_code_span_unchanged():
    assert _escape_code_span_pipes("| regular | cell |") == "| regular | cell |"


def test_escape_code_span_pipes_leaves_lone_backtick_delimiters_alone():
    # A single unbalanced backtick is not a code span, so the real '|' delimiters
    # must be preserved (no closing run -> no match -> no escaping).
    assert _escape_code_span_pipes("| a ` b | c |") == "| a ` b | c |"


def test_escape_code_span_pipes_characterizes_mismatched_longer_closing_run():
    # This helper is an LLM-output repair heuristic for table rows, not a full
    # GFM code-span parser. Keep the current tolerant behavior explicit: a
    # longer closing run still protects the pipe before markdown-it sees the row.
    assert _escape_code_span_pipes("| `a | b`` | target |") == "| `a \\| b`` | target |"


def test_prose_inline_code_pipe_is_not_corrupted_with_backslash():
    """Scope guarantee: the escaper only runs on table rows. Inline code in plain
    prose must render its pipe literally, never gain a stray backslash (which a
    CommonMark code span would show verbatim)."""
    out = render_plain(pythinker_markdown("Use `a | b` for bitwise or.\n"), width=80)
    assert "a | b" in out
    assert "\\|" not in out


def _value_column_offset(separator: str, *, width: int = 40) -> int:
    """Render a single wide column holding the value ``x`` under *separator*
    alignment, and return the column at which ``x`` lands.

    Geometry (header text, column width, padding) is identical across calls, so
    the only thing that can move ``x`` is the alignment marker in *separator*.
    """
    md = f"| AveryWideHeaderColumn |\n| {separator} |\n| x |\n"
    out = render_plain(pythinker_markdown(md), width=width)
    for line in out.splitlines():
        if "x" in line and "Header" not in line and set(line.strip()) != {"━"}:
            return line.index("x")
    raise AssertionError("table data row with the value was not rendered")


def test_table_alignment_markers_position_value_left_center_right():
    """Bug class: 'alignment markers (:---:, ---:) silently ignored'.

    Spacing carries meaning in tables, so the renderer must honor GFM column
    alignment. With identical column geometry, the value's position must move
    strictly rightward as the alignment goes left -> center -> right.
    """
    left = _value_column_offset(":---")
    center = _value_column_offset(":---:")
    right = _value_column_offset("---:")

    assert left < center < right, (left, center, right)
    # Left-aligned hugs the column start: the bordered grid's left edge (│) plus
    # the single cell of left padding are the only columns that precede it.
    assert left == 2


@pytest.mark.parametrize("width", WIDTHS)
def test_table_alignment_ordering_holds_across_widths(width):
    """The left/center/right ordering must survive reflow at every width where
    the column is wider than the value, not just one convenient width."""
    left = _value_column_offset(":---", width=width)
    center = _value_column_offset(":---:", width=width)
    right = _value_column_offset("---:", width=width)

    assert left <= center <= right, (width, left, center, right)
    assert left < right, (width, left, right)


def test_table_default_alignment_is_left():
    """An un-marked column (``---``) must render left-aligned, matching GFM."""
    assert _value_column_offset("---") == _value_column_offset(":---")


def test_table_empty_header_cell_does_not_mislabel():
    """Bug class: 'empty header cells mislabeled in narrow stacked layout'."""
    md = "| | Value |\n| --- | --- |\n| key | 42 |\n"
    out = render_plain(pythinker_markdown(md), width=30)
    assert "Value" in out
    assert "key" in out
    assert "42" in out


@pytest.mark.parametrize("width", WIDTHS)
def test_table_long_cell_wraps_without_dropping_content(width):
    """Bug class: very long cells at narrow widths must wrap, not truncate.

    This pins the *data-integrity* contract the bug class names ("wrap, not
    truncate"): every character of the long cell survives in order, regardless
    of how the bordered grid folds it. The grid draws a vertical separator (│)
    between a cell's fold lines, so we strip box-drawing glyphs as well as
    whitespace before comparing — a wrap (at a word boundary or, at very narrow
    widths, mid-word) still counts as survival; wrapping is not data loss.
    """
    long_cell = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    md = f"| Name | Note |\n| --- | --- |\n| item | {long_cell} |\n"
    out = render_plain(pythinker_markdown(md), width=width)
    # No character of the long cell is dropped (truncation), independent of how
    # the bordered grid wraps and separates the fold lines.
    cleaned = out.translate({ord(glyph): None for glyph in _BOX_DRAWING_GLYPHS})
    stripped_cell = "".join(long_cell.split())
    stripped_out = "".join(cleaned.split())
    assert stripped_cell in stripped_out, f"long cell content truncated at width={width}"
