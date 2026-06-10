"""Small color-math helpers for terminal-adaptive UI decisions.

Ported from the Codex TUI reference (``codex-rs/tui/src/color.rs``): linear
RGB blending plus an ITU-R BT.601 luma test used to classify terminal
backgrounds as light or dark. Pure functions, no terminal I/O.
"""

from __future__ import annotations

import re

type RGB = tuple[int, int, int]

_HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def parse_hex_color(value: str) -> RGB | None:
    """Parse ``#rrggbb`` (leading ``#`` optional) into an RGB tuple."""
    match = _HEX_COLOR_RE.match(value.strip())
    if match is None:
        return None
    raw = match.group(1)
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def to_hex_color(rgb: RGB) -> str:
    """Format an RGB tuple as ``#rrggbb``."""
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, c)) for c in rgb))


def blend(fg: RGB, bg: RGB, alpha: float) -> RGB:
    """Linearly blend *fg* over *bg*; ``alpha=1.0`` returns *fg*."""
    alpha = max(0.0, min(1.0, alpha))
    return (
        round(fg[0] * alpha + bg[0] * (1.0 - alpha)),
        round(fg[1] * alpha + bg[1] * (1.0 - alpha)),
        round(fg[2] * alpha + bg[2] * (1.0 - alpha)),
    )


def luma(rgb: RGB) -> float:
    """ITU-R BT.601 perceived brightness in the 0-255 range."""
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def is_light(rgb: RGB) -> bool:
    """Whether *rgb* reads as a light background (luma above midpoint)."""
    return luma(rgb) > 128.0
