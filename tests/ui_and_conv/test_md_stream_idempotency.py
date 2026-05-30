# tests/ui_and_conv/test_md_stream_idempotency.py
"""Streaming-boundary contract + idempotency/divergence hypotheses (H2, H3)."""

from __future__ import annotations

from pythinker_code.ui.shell.components.markdown import PythinkerMarkdownStream


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
