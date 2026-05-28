"""Canonical glyphs for shell TUI animations.

Single source for the loading-spinner frames and the reduced-motion glyph that
were previously duplicated between :mod:`pythinker_code.ui.shell.motion` and
:mod:`pythinker_code.ui.shell.spinner_words`.
"""

from __future__ import annotations

from typing import Final

#: Braille dotted spinner frames, rendered left-to-right per tick.
SPINNER_FRAMES: Final = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
#: Solid dot pulse for the Composing / Thinking activity lines instead of the
#: dotted braille spinner. The blank frame keeps the label column stable while
#: making the dot appear and disappear.
SHAPE_FRAMES: Final = ("●", " ")
#: Seconds each braille spinner frame stays on screen.
SPINNER_FRAME_INTERVAL_S: Final = 0.08
#: Seconds each solid-dot pulse frame stays on screen.
SHAPE_FRAME_INTERVAL_S: Final = 0.45
#: Static stand-in used when motion is disabled.
REDUCED_MOTION_GLYPH: Final = "●"
#: Pulsing-star frames for the active task/status marker. Ten one-cell frames
#: ease through neighboring star glyphs so the header twinkle changes smoothly
#: while keeping the label column stable.
STAR_SPINNER_FRAMES: Final = ("✦", "✧", "✶", "✷", "✸", "✹", "✸", "✷", "✶", "✧")
#: Seconds each star-spinner frame stays on screen.
STAR_SPINNER_FRAME_INTERVAL_S: Final = 0.08

#: Transcript row marker for assistant/tool-call lines.
TRANSCRIPT_ASSISTANT_MARKER: Final = "⏺"
#: Transcript prompt marker for submitted user input.
TRANSCRIPT_PROMPT_MARKER: Final = "❯"
#: Transcript marker for completed thinking/status timing rows.
TRANSCRIPT_STATUS_MARKER: Final = "✻"
#: Transcript marker for active task/status rows.
TRANSCRIPT_ACTIVE_MARKER: Final = "✶"
#: Transcript gutter marker for tool results.
TRANSCRIPT_TOOL_GUTTER: Final = "⎿"

__all__ = [
    "SPINNER_FRAMES",
    "SHAPE_FRAMES",
    "SPINNER_FRAME_INTERVAL_S",
    "SHAPE_FRAME_INTERVAL_S",
    "STAR_SPINNER_FRAMES",
    "STAR_SPINNER_FRAME_INTERVAL_S",
    "REDUCED_MOTION_GLYPH",
    "TRANSCRIPT_ASSISTANT_MARKER",
    "TRANSCRIPT_PROMPT_MARKER",
    "TRANSCRIPT_STATUS_MARKER",
    "TRANSCRIPT_ACTIVE_MARKER",
    "TRANSCRIPT_TOOL_GUTTER",
]
