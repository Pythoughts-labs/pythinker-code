"""Blackbox-inspired motion helpers for the shell TUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rich.color import Color
from rich.style import Style
from rich.text import Text

from pythinker_code.soul import format_token_count
from pythinker_code.ui.shell.components.render_utils import cell_width
from pythinker_code.ui.shell.design_system import ShellTone, shell_style
from pythinker_code.ui.shell.glyphs import (
    ACTIVE_MARKER_FRAME_INTERVAL_S,
    ACTIVE_MARKER_FRAMES,
    REDUCED_MOTION_GLYPH,
    SHAPE_FRAME_INTERVAL_S,
    SHAPE_FRAMES,
    SPINNER_FRAME_INTERVAL_S,
    SPINNER_FRAMES,
    TRANSCRIPT_ACTIVE_MARKER,
)
from pythinker_code.ui.terminal_capabilities import colors_disabled, motion_disabled
from pythinker_code.ui.theme import tui_rich_style
from pythinker_code.utils.datetime import format_elapsed

_FRAMES = SPINNER_FRAMES
_FRAME_INTERVAL_S = SPINNER_FRAME_INTERVAL_S


def verb_spinner_style() -> Style:
    """Warm amber style for the active verb spinner word."""
    if colors_disabled():
        return Style()
    return Style(color=Color.parse(_SHIMMER_BASE))


# Terminal-native shimmer: a restrained amber-to-pink-violet sweep on the active verb only.
_SHIMMER_BASE = "#E6B450"  # brand-exception: warm amber shimmer literal
_SHIMMER_MID = "#E8876A"  # brand-exception: muted orange-coral shimmer literal
_SHIMMER_HIGHLIGHT = "#C084D8"  # brand-exception: soft pink-violet shimmer literal
_SHIMMER_INTERVAL_S = 0.22
_SPINNER_SILVER_STYLE = Style(color=Color.parse("#C0C0C0"))  # brand-exception: silver spinner


def shimmer_spinner_style(elapsed_s: float, *, reduced_motion: bool = False) -> Style:
    """Clean warm shimmer color for active verb text.

    Reduced motion pins to the base amber so the word stays calm.
    """
    if colors_disabled():
        return Style()
    if reduced_motion or reduced_motion_enabled():
        return Style(color=Color.parse(_SHIMMER_BASE))
    palette = (_SHIMMER_BASE, _SHIMMER_MID, _SHIMMER_HIGHLIGHT, _SHIMMER_MID)
    idx = int(max(0.0, elapsed_s) / _SHIMMER_INTERVAL_S) % len(palette)
    return Style(color=Color.parse(palette[idx]))


def _wave_colors(chars: list[str], local_phase: int, *, rightward: bool) -> list[str | None]:
    """Per-character colors for a single traveling-wave sweep.

    One bright highlight crosses the label with an asymmetric, slightly wider
    trail behind it — an angled sheen rather than a flat pulse. ``rightward``
    flips both the travel direction and the trailing side so the trail always
    lags behind the head.
    """
    n = len(chars)
    if rightward:
        head = local_phase - 2
        trail = (1, -1, -2, -3)
    else:
        head = n + 2 - local_phase
        trail = (-1, 1, 2, 3)
    colors: list[str | None] = []
    for i, char in enumerate(chars):
        if char.isspace():
            colors.append(None)
            continue
        offset = i - head
        if offset == 0:
            colors.append(_SHIMMER_HIGHLIGHT)
        elif offset in trail:
            colors.append(_SHIMMER_MID)
        else:
            colors.append(_SHIMMER_BASE)
    return colors


def _splash_colors(chars: list[str], local_phase: int) -> list[str | None]:
    """Per-character colors for the center-out splash bloom.

    A wavefront expands from the middle of the label toward both edges, leaving
    a filled coral interior behind it, then settles the whole word to base amber.
    """
    n = len(chars)
    fill_frames = (n + 1) // 2 + 1  # frames for the wavefront to clear both edges
    center = (n - 1) / 2
    if local_phase >= fill_frames:  # settle beat before the next wave launches
        return [None if char.isspace() else _SHIMMER_BASE for char in chars]
    radius = local_phase
    colors: list[str | None] = []
    for i, char in enumerate(chars):
        if char.isspace():
            colors.append(None)
            continue
        dist = abs(i - center)
        if radius - 0.5 <= dist <= radius + 0.5:
            colors.append(_SHIMMER_HIGHLIGHT)
        elif dist < radius - 0.5:
            colors.append(_SHIMMER_MID)
        else:
            colors.append(_SHIMMER_BASE)
    return colors


def _shimmer_segments(
    label: str, elapsed_s: float, *, reduced_motion: bool
) -> list[tuple[str | None, str]]:
    """Return coalesced ``(hex_color, text)`` shimmer segments.

    This is shared by Rich renderables and prompt_toolkit fragments so every
    active-work label uses the same visual language. The motion is a four-phase
    loop that reads like traveling waves: a wave sweeps right-to-left, splashes
    outward from the middle, sweeps back left-to-right, splashes again, repeat.
    """
    if not label:
        return []
    if colors_disabled():
        return [(None, label)]
    if reduced_motion or reduced_motion_enabled():
        return [(_SHIMMER_BASE, label)]

    chars = list(label)
    n = len(chars)
    wave_len = n + 6
    splash_len = (n + 1) // 2 + 3
    cycle_len = 2 * wave_len + 2 * splash_len
    frame = int(max(0.0, elapsed_s) / _SHIMMER_INTERVAL_S) % cycle_len
    if frame < wave_len:
        colors = _wave_colors(chars, frame, rightward=False)
    elif frame < wave_len + splash_len:
        colors = _splash_colors(chars, frame - wave_len)
    elif frame < 2 * wave_len + splash_len:
        colors = _wave_colors(chars, frame - wave_len - splash_len, rightward=True)
    else:
        colors = _splash_colors(chars, frame - 2 * wave_len - splash_len)

    segments: list[tuple[str | None, str]] = []
    for char, color in zip(chars, colors, strict=True):
        if segments and segments[-1][0] == color:
            segments[-1] = (color, segments[-1][1] + char)
        else:
            segments.append((color, char))
    return segments


def shimmer_text(label: str, elapsed_s: float, *, reduced_motion: bool = False) -> Text:
    """Return subtle per-character shimmer text for any active work label."""
    rendered = Text()
    for color, text in _shimmer_segments(label, elapsed_s, reduced_motion=reduced_motion):
        if color is None:
            rendered.append(text)
        else:
            rendered.append(text, style=Style(color=Color.parse(color)))
    return rendered


def shimmer_prompt_fragments(
    label: str, elapsed_s: float, *, reduced_motion: bool = False
) -> list[tuple[str, str]]:
    """Return prompt_toolkit fragments using the same shimmer as ``shimmer_text``."""
    return [
        (f"fg:{color}" if color is not None else "", text)
        for color, text in _shimmer_segments(label, elapsed_s, reduced_motion=reduced_motion)
    ]


# Backwards-compatible private name used by older callers/tests.
def _shimmer_label_text(label: str, elapsed_s: float, *, reduced_motion: bool) -> Text:
    return shimmer_text(label, elapsed_s, reduced_motion=reduced_motion)


@dataclass(frozen=True, slots=True)
class ActivitySnapshot:
    label: str
    elapsed_s: float
    tokens: int = 0
    token_rate: int | None = None
    stalled: bool = False
    interrupt_hint: str = ""
    reduced_motion: bool = False
    label_style: Style | None = None
    # "braille" = dotted spinner (default); "shape" = morphing filled shape.
    spinner: Literal["braille", "shape"] = "braille"


def reduced_motion_enabled() -> bool:
    return motion_disabled()


def spinner_frame_at(
    elapsed_s: float,
    *,
    reduced_motion: bool = False,
    frames: tuple[str, ...] = _FRAMES,
    interval_s: float = _FRAME_INTERVAL_S,
) -> str:
    if reduced_motion:
        return REDUCED_MOTION_GLYPH
    index = int(max(0.0, elapsed_s) / interval_s) % len(frames)
    return frames[index]


def active_marker_frame(elapsed_s: float, *, reduced_motion: bool = False) -> str:
    """Return the current braille dotted frame for the active task marker.

    Reduced motion pins to the static dot so the marker stays calm.
    """
    if reduced_motion or reduced_motion_enabled():
        return TRANSCRIPT_ACTIVE_MARKER
    return spinner_frame_at(
        elapsed_s,
        frames=ACTIVE_MARKER_FRAMES,
        interval_s=ACTIVE_MARKER_FRAME_INTERVAL_S,
    )


def _candidate_parts(snapshot: ActivitySnapshot) -> list[str]:
    parts = [format_elapsed(snapshot.elapsed_s)]
    if snapshot.tokens:
        parts.append(f"↓ {format_token_count(snapshot.tokens)} tokens")
    if snapshot.token_rate:
        parts.append(f"{snapshot.token_rate} t/s")
    if snapshot.interrupt_hint:
        hint = "esc" if snapshot.interrupt_hint == "esc to interrupt" else snapshot.interrupt_hint
        parts.append(hint)
    return parts


def _activity_label(label: str) -> str:
    stripped = label.rstrip()
    if stripped.endswith(("…", "...")):
        return stripped
    return f"{stripped}…"


def activity_status_line(snapshot: ActivitySnapshot, *, width: int | None = None) -> Text:
    reduced = snapshot.reduced_motion or reduced_motion_enabled()
    thinking_style = tui_rich_style("thinking_text")
    if snapshot.stalled:
        glyph_style = shell_style(ShellTone.WARNING)
    elif snapshot.spinner == "shape":
        # Composing / Thinking: neutral muted grey, not the bright coral verb accent.
        glyph_style = thinking_style
    else:
        # The dotted braille spinner is a marker; keep it silver while the verb shimmers.
        glyph_style = Style() if colors_disabled() else _SPINNER_SILVER_STYLE
    if snapshot.label_style is not None:
        label_style = snapshot.label_style
    elif snapshot.spinner == "shape":
        label_style = thinking_style
    else:
        label_style = shimmer_spinner_style(snapshot.elapsed_s, reduced_motion=reduced)
    if snapshot.label.lower() == "thinking":
        label_style += Style(italic=True)
    if snapshot.spinner == "shape":
        frames, interval_s = SHAPE_FRAMES, SHAPE_FRAME_INTERVAL_S
    else:
        frames, interval_s = _FRAMES, _FRAME_INTERVAL_S
    text = Text(
        spinner_frame_at(
            snapshot.elapsed_s, reduced_motion=reduced, frames=frames, interval_s=interval_s
        ),
        style=glyph_style,
    )
    text.append(" ")
    label_text = _activity_label(snapshot.label)
    if snapshot.label_style is None and snapshot.spinner != "shape":
        shimmered = _shimmer_label_text(label_text, snapshot.elapsed_s, reduced_motion=reduced)
        if snapshot.label.lower() == "thinking":
            shimmered.stylize(Style(italic=True))
        text.append_text(shimmered)
    else:
        text.append(label_text, style=label_style)

    parts = _candidate_parts(snapshot)
    if width is not None:
        base_width = cell_width(text.plain)
        kept: list[str] = []
        for part in parts:
            candidate = " · ".join([*kept, part])
            if base_width + 3 + cell_width(candidate) <= width:
                kept.append(part)
        parts = kept
    if parts:
        secondary_style = thinking_style
        text.append(" ", style=secondary_style)
        text.append("· ", style=secondary_style)
        text.append(" · ".join(parts), style=secondary_style)
    return text
