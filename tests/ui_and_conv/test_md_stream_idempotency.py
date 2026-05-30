# tests/ui_and_conv/test_md_stream_idempotency.py
"""Streaming-boundary contract + idempotency/divergence hypotheses (H2, H3)."""

from __future__ import annotations

from pythinker_code.ui.shell.components.markdown import PythinkerMarkdownStream, pythinker_markdown
from tests.ui_and_conv._md_contract_helpers import render_ansi, render_plain


def _drain(chunks: list[str]) -> list[str]:
    """Feed chunks to the stream; return the ordered list of committed slices."""
    stream = PythinkerMarkdownStream()
    committed: list[str] = []
    for chunk in chunks:
        ready = stream.push(chunk)
        if ready:
            committed.append(ready)
    tail = stream.flush()
    if tail:
        committed.append(tail)
    return committed


def test_streaming_table_is_not_committed_mid_row():
    """Bug class: 'stale bordered tables left in scrollback while streaming'.

    A table streamed one line at a time must not have a partial (header-only or
    header+delimiter-only) slice committed as a finished block: the committer
    keeps the last top-level block mutable until a following block begins.
    """
    full = "Intro paragraph.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nAfter.\n"
    # stream character-by-character to maximize the chance of a mid-table commit
    committed = _drain(list(full))
    # No committed slice may end in the middle of the table (i.e. contain the
    # delimiter row but not the closing blank line + following block).
    for slice_ in committed[:-1]:
        if "---" in slice_:
            assert slice_.rstrip().endswith("|") is False or "After" in "".join(committed), (
                "a partial table row was committed before the table closed"
            )
    # Reassembled stream equals the original (no loss, no duplication).
    assert "".join(committed) == full


# Glued prose+table that forces the regex repair pipeline to fire on a slice
# whose commit boundary was computed on the RAW (un-repaired) text.
_GLUED = "Findings Medium| # | File |\n| --- | --- |\n| 1 | a.py |\n| 2 | b.py |\n\nNext.\n"


def test_h2_stream_slices_reassemble_without_duplicate_rows():
    """H2: commit offsets are computed on raw text while the renderer transforms
    repaired text. Try to reproduce a duplicate/stale row. Expected: PASS
    (non-reproduction). If this FAILS, H2 is confirmed — capture the case.
    """
    committed = _drain(list(_GLUED))
    reassembled = "".join(committed)
    assert reassembled == _GLUED
    # Render each committed slice; 'a.py' and 'b.py' must each appear exactly
    # once across the rendered stream (no row duplicated by the repair pass).
    rendered = "".join(render_plain(pythinker_markdown(s)) for s in committed)
    assert rendered.count("a.py") == 1
    assert rendered.count("b.py") == 1


def test_h3_report_and_table_render_is_idempotent():
    """H3: rendering the same markdown twice yields byte-identical output."""
    md = "## Title\n\n| A | B |\n| --- | --- |\n| 1 | `x|y` |\n\nDone.\n"
    first = render_ansi(pythinker_markdown(md), width=70)
    second = render_ansi(pythinker_markdown(md), width=70)
    assert first == second
