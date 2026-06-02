"""Paced reveal of streamed composing text (smooth streaming).

Bursty LLM deltas are buffered and revealed gradually by ``reveal_tick`` so text
flows smoothly instead of landing in delta-sized clumps, while keeping up with a
fast model. Unpaced and thinking blocks reveal immediately (legacy behavior).
"""

from __future__ import annotations

import pytest

from pythinker_code.ui.shell.visualize._blocks import (
    _ContentBlock,
    set_smooth_streaming,
    smooth_streaming_enabled,
)

# Single markdown block (no committable boundary) so reveal never triggers a
# console.print() commit during the test.
_TEXT = "the quick brown fox jumps over the lazy dog several times in a row"


@pytest.fixture(autouse=True)
def _restore_smooth_streaming_flag():
    """Keep the process-global smooth-streaming flag isolated for future tests."""
    previous = smooth_streaming_enabled()
    try:
        yield
    finally:
        set_smooth_streaming(previous)


def _drain(block: _ContentBlock) -> None:
    """Tick until fully revealed (bounded loop guards against a stuck cursor)."""
    for _ in range(10_000):
        if not block.reveal_tick():
            return
    raise AssertionError("reveal_tick did not converge")


def test_paced_block_buffers_until_ticked() -> None:
    block = _ContentBlock(is_think=False, paced=True)
    block.append(_TEXT)
    # Nothing is revealed until a tick fires.
    assert block._revealed_len == 0
    assert block._pending_text() == ""

    assert block.reveal_tick() is True
    assert 0 < block._revealed_len < len(_TEXT)


def test_paced_reveal_is_monotonic_and_bounded() -> None:
    block = _ContentBlock(is_think=False, paced=True)
    block.append(_TEXT)
    last = 0
    for _ in range(50):
        block.reveal_tick()
        assert last <= block._revealed_len <= len(block.raw_text)
        last = block._revealed_len
    assert block._revealed_len == len(_TEXT)


def test_paced_reveal_advances_by_display_cells_for_cjk() -> None:
    from rich.cells import cell_len

    block = _ContentBlock(is_think=False, paced=True)
    block.append("你好")

    assert block.reveal_tick() is True
    revealed = block.raw_text[: block._revealed_len]
    assert revealed == "你"
    assert cell_len(revealed) == 2


def test_paced_reveal_eventually_shows_all_text() -> None:
    block = _ContentBlock(is_think=False, paced=True)
    block.append(_TEXT)
    _drain(block)
    assert block._revealed_len == len(_TEXT)
    # No text is stranded: committed prefix + revealed pending == full buffer.
    assert block.raw_text[: block._committed_len] + block._pending_text() == _TEXT


def test_reveal_all_reveals_everything() -> None:
    block = _ContentBlock(is_think=False, paced=True)
    block.append(_TEXT)
    block.reveal_tick()
    assert block._revealed_len < len(_TEXT)

    assert block.reveal_all() is True
    assert block._revealed_len == len(_TEXT)
    # Already revealed -> no further change.
    assert block.reveal_all() is False


def test_unpaced_block_reveals_immediately() -> None:
    block = _ContentBlock(is_think=False, paced=False)
    block.append(_TEXT)
    assert block._revealed_len == len(_TEXT)
    # Unpaced blocks ignore the reveal tick entirely.
    assert block.reveal_tick() is False


def test_thinking_block_is_never_paced() -> None:
    # paced=True is requested, but thinking blocks opt out (text reveals at once).
    block = _ContentBlock(is_think=True, paced=True)
    block.append(_TEXT)
    assert block._revealed_len == len(_TEXT)
    assert block.reveal_tick() is False
