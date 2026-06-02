from rich.color import Color

from pythinker_code.ui.shell.motion import (
    _SHIMMER_BASE,
    _SHIMMER_HIGHLIGHT,
    _SHIMMER_INTERVAL_S,
    _SHIMMER_MID,
    _shimmer_segments,
    shimmer_prompt_fragments,
    shimmer_spinner_style,
)
from pythinker_code.ui.theme import set_active_theme


def _frame_colors(label: str, frame: int) -> list[str | None]:
    """Per-character colors at a given integer animation frame."""
    elapsed = (frame + 0.5) * _SHIMMER_INTERVAL_S
    colors: list[str | None] = []
    for color, text in _shimmer_segments(label, elapsed, reduced_motion=False):
        colors.extend([color] * len(text))
    return colors


def _color_hex(color: Color | None) -> str:
    assert color is not None
    triplet = color.triplet
    assert triplet is not None
    return triplet.hex.lower()


def test_shimmer_returns_base_accent_when_reduced_motion():
    set_active_theme("dark")
    s = shimmer_spinner_style(0.0, reduced_motion=True)
    assert _color_hex(s.color) == _SHIMMER_BASE.lower()


def test_shimmer_varies_over_time_when_motion_enabled(monkeypatch):
    monkeypatch.delenv("PYTHINKER_REDUCED_MOTION", raising=False)
    set_active_theme("dark")
    first = _color_hex(shimmer_spinner_style(0.0, reduced_motion=False).color)
    later = _color_hex(shimmer_spinner_style(0.22, reduced_motion=False).color)
    # At least one sampled frame differs from the base when animating.
    assert first != later or first != _SHIMMER_BASE.lower()


def test_prompt_shimmer_fragments_share_silver_sheen_palette(monkeypatch):
    monkeypatch.delenv("PYTHINKER_REDUCED_MOTION", raising=False)

    fragments = shimmer_prompt_fragments("Schlepping…", 0.88)
    styles = {style.lower() for style, text in fragments if text.strip()}

    assert f"fg:{_SHIMMER_BASE.lower()}" in styles
    assert f"fg:{_SHIMMER_MID.lower()}" in styles
    assert f"fg:{_SHIMMER_HIGHLIGHT.lower()}" in styles
    assert "".join(text for _style, text in fragments) == "Schlepping…"


def test_splash_originates_at_center_and_widens(monkeypatch):
    monkeypatch.delenv("PYTHINKER_REDUCED_MOTION", raising=False)
    label = "abcdefg"  # n=7, center index 3, no spaces
    wave_len = len(label) + 6  # phase B (first splash) starts here

    first = _frame_colors(label, wave_len)
    highlighted_first = [i for i, c in enumerate(first) if c == _SHIMMER_HIGHLIGHT]
    assert highlighted_first == [3]  # bloom begins at the center char

    second = _frame_colors(label, wave_len + 1)
    highlighted_second = [i for i, c in enumerate(second) if c == _SHIMMER_HIGHLIGHT]
    assert highlighted_second == [2, 4]  # wavefront expands symmetrically outward
    assert second[3] == _SHIMMER_MID  # interior fills behind the front


def test_phase_c_trail_mirrors_phase_a(monkeypatch):
    monkeypatch.delenv("PYTHINKER_REDUCED_MOTION", raising=False)
    label = "abcdefg"
    n = len(label)
    wave_len = n + 6
    splash_len = (n + 1) // 2 + 3

    # Phase A (right-to-left) and phase C (left-to-right) with the head at index 3.
    phase_a = _frame_colors(label, n + 2 - 3)
    phase_c = _frame_colors(label, wave_len + splash_len + (3 + 2))

    assert phase_a[3] == _SHIMMER_HIGHLIGHT
    assert phase_c[3] == _SHIMMER_HIGHLIGHT

    a_mid = [i for i, c in enumerate(phase_a) if c == _SHIMMER_MID]
    c_mid = [i for i, c in enumerate(phase_c) if c == _SHIMMER_MID]
    # Phase A trail leans right of the head; phase C trail is mirrored to the left.
    assert max(a_mid) > 3
    assert min(c_mid) < 3
    assert a_mid != c_mid


def test_cycle_returns_to_start(monkeypatch):
    monkeypatch.delenv("PYTHINKER_REDUCED_MOTION", raising=False)
    label = "Reticulating"
    n = len(label)
    cycle_len = 2 * (n + 6) + 2 * ((n + 1) // 2 + 3)

    assert _frame_colors(label, 3) == _frame_colors(label, 3 + cycle_len)
    # A frame mid-cycle differs from the start (the animation actually moves).
    assert _frame_colors(label, 3) != _frame_colors(label, 3 + cycle_len // 2)
