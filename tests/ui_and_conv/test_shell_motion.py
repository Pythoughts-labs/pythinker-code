from __future__ import annotations

from rich.color import Color
from rich.console import Console
from rich.style import Style

from pythinker_code.ui.shell.glyphs import (
    ACTIVE_MARKER_FRAME_INTERVAL_S,
    ACTIVE_MARKER_FRAMES,
    REDUCED_MOTION_GLYPH,
    SHAPE_FRAME_INTERVAL_S,
    SPINNER_FRAME_INTERVAL_S,
    SPINNER_FRAMES,
)
from pythinker_code.ui.shell.motion import (
    _SHIMMER_BASE,
    _SHIMMER_HIGHLIGHT,
    _SHIMMER_MID,
    ActivitySnapshot,
    active_marker_frame,
    activity_status_line,
    spinner_frame_at,
)

_SHIMMER_HEXES = {_SHIMMER_BASE.lower(), _SHIMMER_MID.lower(), _SHIMMER_HIGHLIGHT.lower()}


def _plain(renderable) -> str:
    console = Console(record=True, width=100, color_system=None)
    console.print(renderable)
    return console.export_text()


def _ansi(renderable) -> str:
    console = Console(record=True, width=100, color_system="truecolor")
    console.print(renderable)
    return console.export_text(styles=True)


def _style_for(renderable, text: str) -> Style:
    start = renderable.plain.index(text)
    end = start + len(text)
    span = next(span for span in renderable.spans if span.start <= start and span.end >= end)
    return Style.parse(span.style) if isinstance(span.style, str) else span.style


def _color_hex(color: Color | None) -> str:
    assert color is not None
    triplet = color.triplet
    assert triplet is not None
    return triplet.hex.lower()


def _span_colors_for(renderable, text: str) -> set[str]:
    start = renderable.plain.index(text)
    end = start + len(text)
    colors: set[str] = set()
    for span in renderable.spans:
        if span.end <= start or span.start >= end:
            continue
        style = Style.parse(span.style) if isinstance(span.style, str) else span.style
        if style.color is not None:
            colors.add(_color_hex(style.color))
    return colors


def test_spinner_frame_changes_with_time():
    assert spinner_frame_at(0.0) != spinner_frame_at(0.2)


def test_active_glyphs_use_text_safe_solid_circle():
    from pythinker_code.ui.shell.glyphs import SHAPE_FRAMES, TRANSCRIPT_ASSISTANT_MARKER

    # The transcript row marker is the reference-CLI record button on
    # macOS/Linux (Windows keeps the text circle); the pulse/reduced-motion
    # glyphs stay on the text-safe solid circle.
    assert TRANSCRIPT_ASSISTANT_MARKER == "⏺"
    assert SHAPE_FRAMES[0] == "●"
    assert REDUCED_MOTION_GLYPH == "●"


def test_reduced_motion_uses_static_glyph():
    assert spinner_frame_at(0.2, reduced_motion=True) == "●"


def test_active_marker_frame_animates_through_braille_dot_frames():
    seen = {
        active_marker_frame(i * ACTIVE_MARKER_FRAME_INTERVAL_S)
        for i in range(len(ACTIVE_MARKER_FRAMES))
    }
    assert ACTIVE_MARKER_FRAMES is SPINNER_FRAMES
    assert ACTIVE_MARKER_FRAME_INTERVAL_S == SPINNER_FRAME_INTERVAL_S
    assert "⠸" in ACTIVE_MARKER_FRAMES
    assert seen == set(ACTIVE_MARKER_FRAMES)
    assert all(len(frame) == 1 for frame in ACTIVE_MARKER_FRAMES)


def test_active_marker_frame_reduced_motion_pins_static_dot():
    assert active_marker_frame(0.5, reduced_motion=True) == REDUCED_MOTION_GLYPH


def test_activity_status_line_contains_label_elapsed_tokens_and_interrupt_hint():
    line = activity_status_line(
        ActivitySnapshot(
            label="Thinking",
            elapsed_s=12.0,
            tokens=2400,
            token_rate=42,
            interrupt_hint="esc to interrupt",
        )
    )
    output = _plain(line)
    assert "Thinking…" in output
    assert "(12s, ↓ 2.4k tokens, 42 t/s, esc)" in output
    assert "esc to interrupt" not in output


def test_activity_status_line_hides_secondary_parts_at_narrow_width():
    line = activity_status_line(
        ActivitySnapshot(label="Thinking", elapsed_s=12.0, tokens=2400, token_rate=42),
        width=24,
    )
    output = _plain(line)
    assert "Thinking" in output
    assert "42 t/s" not in output


def test_activity_status_line_uses_clean_metadata_separator():
    line = activity_status_line(ActivitySnapshot(label="Pythinking", elapsed_s=30.0, tokens=1300))

    output = _plain(line).strip()

    # Parenthesized, comma-separated metadata — same design as the pinned-todo
    # activity header, no middle-dot separators.
    assert "Pythinking… (30s, ↓ 1.3k tokens)" in output


def test_activity_status_line_uses_platinum_spinner_and_champagne_verb(monkeypatch):
    from pythinker_code.ui.theme import set_active_theme, tui_rich_style

    # Pin the discrete three-step sheen (256-color tier) for determinism.
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    set_active_theme("dark")
    start = activity_status_line(ActivitySnapshot(label="Cultivating", elapsed_s=0.0))
    sheen = activity_status_line(ActivitySnapshot(label="Cultivating", elapsed_s=0.88))
    later_sheen = activity_status_line(ActivitySnapshot(label="Cultivating", elapsed_s=1.10))

    base_style = Style.parse(start.style) if isinstance(start.style, str) else start.style
    assert base_style.color == tui_rich_style("activity_spinner").color
    assert _span_colors_for(sheen, "Cultivating") >= _SHIMMER_HEXES
    assert _span_colors_for(later_sheen, "Cultivating") >= _SHIMMER_HEXES
    assert "Cultivating…" in _plain(start)


def test_truecolor_shimmer_blends_a_smooth_sheen(monkeypatch):
    from pythinker_code.ui.shell.motion import shimmer_text
    from pythinker_code.ui.theme import set_active_theme

    monkeypatch.setenv("COLORTERM", "truecolor")
    set_active_theme("dark")
    # Mid-sweep frame: the cosine falloff should produce blended intermediate
    # tones beyond the discrete base/mid/highlight ramp.
    colors = _span_colors_for(shimmer_text("Cultivating", 0.88), "Cultivating")
    assert len(colors) > 3
    blended = colors - _SHIMMER_HEXES
    assert blended, "expected cosine-blended tones outside the discrete ramp"


def test_shimmer_settles_between_sweeps(monkeypatch):
    from pythinker_code.ui.shell.motion import _SHIMMER_BASE, shimmer_text
    from pythinker_code.ui.theme import set_active_theme

    monkeypatch.setenv("COLORTERM", "truecolor")
    set_active_theme("dark")
    label = "Cultivating"
    # Frame inside the settle beat right after the first sweep clears.
    wave_len = len(label) + 6
    settle_elapsed = (wave_len + 1) * 0.15
    colors = _span_colors_for(shimmer_text(label, settle_elapsed), label)
    assert colors == {_SHIMMER_BASE.lower()}


def test_shape_activity_status_line_pulses_solid_dot():
    visible = activity_status_line(
        ActivitySnapshot(label="Composing", elapsed_s=0.0, spinner="shape")
    )
    hidden = activity_status_line(
        ActivitySnapshot(label="Composing", elapsed_s=SHAPE_FRAME_INTERVAL_S, spinner="shape")
    )

    assert visible.plain.startswith("● Composing…")
    assert hidden.plain.startswith("  Composing…")


def test_shape_activity_status_line_defaults_to_neutral_thinking_grey():
    from pythinker_code.ui.theme import tui_rich_style

    thinking_grey = tui_rich_style("thinking_text").color
    purple_muted = tui_rich_style("muted").color

    for label in ("Composing", "Thinking"):
        line = activity_status_line(ActivitySnapshot(label=label, elapsed_s=1.0, spinner="shape"))
        base_style = Style.parse(line.style) if isinstance(line.style, str) else line.style
        assert base_style.color == thinking_grey
        assert base_style.color != purple_muted
        assert _style_for(line, label).color == thinking_grey
