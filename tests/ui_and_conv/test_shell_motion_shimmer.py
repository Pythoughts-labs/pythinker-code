"""Structural tests for the activity-verb shimmer.

The motion is a calm bidirectional sheen: wave right-to-left, settle beat,
wave left-to-right, settle beat, repeat. On truecolor terminals the sheen is
a continuous cosine blend; the 256-color tier keeps the discrete three-step
base/mid/highlight ramp. Tests pin the color tier explicitly so they don't
depend on the host terminal's COLORTERM.
"""

import pytest
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

_SETTLE_LEN = 4


@pytest.fixture
def discrete_tier(monkeypatch):
    """Pin the discrete (256-color) sheen for deterministic ramp assertions."""
    monkeypatch.delenv("PYTHINKER_REDUCED_MOTION", raising=False)
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")


@pytest.fixture
def truecolor_tier(monkeypatch):
    monkeypatch.delenv("PYTHINKER_REDUCED_MOTION", raising=False)
    monkeypatch.setenv("COLORTERM", "truecolor")


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


def test_shimmer_varies_over_time_when_motion_enabled(discrete_tier):
    set_active_theme("dark")
    first = _color_hex(shimmer_spinner_style(0.0, reduced_motion=False).color)
    later = _color_hex(shimmer_spinner_style(0.22, reduced_motion=False).color)
    # At least one sampled frame differs from the base when animating.
    assert first != later or first != _SHIMMER_BASE.lower()


def test_prompt_shimmer_fragments_share_ember_ramp_palette(discrete_tier):
    set_active_theme("dark")

    fragments = shimmer_prompt_fragments("Schlepping…", 0.88)
    styles = {style.lower() for style, text in fragments if text.strip()}

    assert f"fg:{_SHIMMER_BASE.lower()}" in styles
    assert f"fg:{_SHIMMER_MID.lower()}" in styles
    assert f"fg:{_SHIMMER_HIGHLIGHT.lower()}" in styles
    assert "".join(text for _style, text in fragments) == "Schlepping…"


def test_shimmer_fragments_use_light_theme_activity_tokens(discrete_tier):
    from pythinker_code.ui.theme import get_tui_tokens

    set_active_theme("light")
    try:
        fragments = shimmer_prompt_fragments("Schlepping…", 0.88)
    finally:
        set_active_theme("dark")
    styles = {style.lower() for style, text in fragments if text.strip()}
    tokens = get_tui_tokens("light")

    assert f"fg:{tokens.activity_verb.lower()}" in styles
    assert f"fg:{tokens.activity_verb_mid.lower()}" in styles
    assert f"fg:{tokens.activity_verb_highlight.lower()}" in styles
    assert "".join(text for _style, text in fragments) == "Schlepping…"


def test_settle_beat_holds_base_between_sweeps(discrete_tier):
    set_active_theme("dark")
    label = "abcdefg"
    wave_len = len(label) + 6

    for offset in range(_SETTLE_LEN):
        colors = _frame_colors(label, wave_len + offset)
        assert set(colors) == {_SHIMMER_BASE}


def test_return_sweep_mirrors_first_sweep(discrete_tier):
    set_active_theme("dark")
    label = "abcdefg"
    n = len(label)
    wave_len = n + 6

    # First sweep (right-to-left) and return sweep (left-to-right), head at 3.
    phase_a = _frame_colors(label, n + 2 - 3)
    phase_c = _frame_colors(label, wave_len + _SETTLE_LEN + (3 + 2))

    assert phase_a[3] == _SHIMMER_HIGHLIGHT
    assert phase_c[3] == _SHIMMER_HIGHLIGHT

    a_mid = [i for i, c in enumerate(phase_a) if c == _SHIMMER_MID]
    c_mid = [i for i, c in enumerate(phase_c) if c == _SHIMMER_MID]
    # First sweep's trail leans right of the head; return sweep mirrors left.
    assert max(a_mid) > 3
    assert min(c_mid) < 3
    assert a_mid != c_mid


def test_cycle_returns_to_start(discrete_tier):
    set_active_theme("dark")
    label = "Reticulating"
    cycle_len = 2 * (len(label) + 6 + _SETTLE_LEN)

    assert _frame_colors(label, 3) == _frame_colors(label, 3 + cycle_len)
    # A frame mid-cycle differs from the start (the animation actually moves).
    assert _frame_colors(label, 3) != _frame_colors(label, 3 + cycle_len // 2)


def test_truecolor_sheen_blends_smoothly(truecolor_tier):
    set_active_theme("dark")
    label = "abcdefghij"
    # Mid-sweep frame: cosine falloff yields intermediate tones beyond the
    # discrete ramp, with the head still hitting the exact highlight.
    colors = [c for c in _frame_colors(label, 6) if c is not None]
    distinct = set(colors)
    assert _SHIMMER_HIGHLIGHT.lower() in {c.lower() for c in distinct}
    assert len(distinct) > 3
    assert any(
        c.lower() not in {x.lower() for x in (_SHIMMER_BASE, _SHIMMER_MID, _SHIMMER_HIGHLIGHT)}
        for c in distinct
    )
