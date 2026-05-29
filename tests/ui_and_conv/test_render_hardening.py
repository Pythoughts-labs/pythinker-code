"""Regression guards for the TUI render-standardization work.

These lock in the theme-token and glyph-dedup cleanup so the raw literals do
not creep back into the modules that were standardized.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pythinker_code.ui.shell import glyphs, motion, spinner_words
from pythinker_code.ui.shell.visualize import _blocks

# Modules that were swept of raw ``grey50`` color literals.
_TOKENIZED_MODULES = [_blocks]


@pytest.mark.parametrize("module", _TOKENIZED_MODULES)
def test_no_raw_grey50_literal(module) -> None:
    src = Path(module.__file__).read_text(encoding="utf-8")
    assert "grey50" not in src, (
        f"{module.__name__} reintroduced a raw 'grey50' literal — "
        "use tui_rich_style('muted'/'thinking_text') instead"
    )


def test_spinner_frames_have_single_source() -> None:
    # All three modules must reference the same frames object — no copies.
    assert motion._FRAMES is glyphs.SPINNER_FRAMES
    assert spinner_words.SPINNER_FRAMES is glyphs.SPINNER_FRAMES
    assert glyphs.ACTIVE_MARKER_FRAMES is glyphs.SPINNER_FRAMES
    assert motion._FRAME_INTERVAL_S == glyphs.SPINNER_FRAME_INTERVAL_S
    assert glyphs.ACTIVE_MARKER_FRAME_INTERVAL_S == glyphs.SPINNER_FRAME_INTERVAL_S


def test_reduced_motion_glyph_centralized() -> None:
    assert motion.spinner_frame_at(0.0, reduced_motion=True) == glyphs.REDUCED_MOTION_GLYPH
