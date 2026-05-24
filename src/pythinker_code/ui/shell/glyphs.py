"""Canonical glyphs for shell TUI animations.

Single source for the loading-spinner frames and the reduced-motion glyph that
were previously duplicated between :mod:`pythinker_code.ui.shell.motion` and
:mod:`pythinker_code.ui.shell.spinner_words`.
"""

from __future__ import annotations

from typing import Final

#: Braille dotted spinner frames, rendered left-to-right per tick.
SPINNER_FRAMES: Final = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
#: Solid animated shape frames — the filled glyph morphs circle → diamond →
#: cube → diamond for the Composing / Thinking activity lines instead of the
#: dotted braille spinner. Filled, single-cell glyphs so the label never shifts.
SHAPE_FRAMES: Final = ("●", "◆", "■", "◆")
#: Seconds each braille spinner frame stays on screen.
SPINNER_FRAME_INTERVAL_S: Final = 0.08
#: Seconds each shape frame stays on screen — slower, calmer morph.
SHAPE_FRAME_INTERVAL_S: Final = 0.3
#: Static stand-in used when motion is disabled.
REDUCED_MOTION_GLYPH: Final = "●"

__all__ = [
    "SPINNER_FRAMES",
    "SHAPE_FRAMES",
    "SPINNER_FRAME_INTERVAL_S",
    "SHAPE_FRAME_INTERVAL_S",
    "REDUCED_MOTION_GLYPH",
]
