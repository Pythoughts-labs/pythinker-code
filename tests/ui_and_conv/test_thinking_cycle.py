"""Tests for the Shift+Tab thinking-level cycle helper."""

from __future__ import annotations

import pytest

from pythinker_code.ui.shell.selectors.thinking import (
    THINKING_LEVELS,
    ThinkingLevel,
    next_thinking_level,
)


def test_thinking_levels_canonical_order() -> None:
    assert THINKING_LEVELS == ("off", "minimal", "low", "medium", "high", "xhigh")


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        ("off", "minimal"),
        ("minimal", "low"),
        ("low", "medium"),
        ("medium", "high"),
        ("high", "xhigh"),
        ("xhigh", "off"),  # wrap-around
    ],
)
def test_next_thinking_level_cycles_and_wraps(
    current: ThinkingLevel, expected: ThinkingLevel
) -> None:
    assert next_thinking_level(current) == expected


def test_thinking_frame_color_maps_each_level_dark() -> None:
    from pythinker_code.ui.theme import thinking_frame_color

    # Cold→hot gradient: slate off, cool blue/teal, warm amber/orange, dark red.
    assert thinking_frame_color("off", theme="dark") == "#64748b"  # slate-500
    assert thinking_frame_color("min", theme="dark") == "#60a5fa"  # blue-400 alias
    assert thinking_frame_color("minimal", theme="dark") == "#60a5fa"  # blue-400 canonical
    assert thinking_frame_color("low", theme="dark") == "#2dd4bf"  # teal-400
    assert thinking_frame_color("medium", theme="dark") == "#fbbf24"  # amber-400
    assert thinking_frame_color("high", theme="dark") == "#f97316"  # orange-500
    assert thinking_frame_color("xhigh", theme="dark") == "#b91c1c"  # red-700
    assert thinking_frame_color("max", theme="dark") == "#7f1d1d"  # red-900


def test_thinking_frame_color_light_uses_same_standard_scale() -> None:
    from pythinker_code.ui.theme import thinking_frame_color

    assert thinking_frame_color("high", theme="light") == "#f97316"
    assert thinking_frame_color("high", theme="light") == thinking_frame_color("high", theme="dark")


def test_thinking_frame_color_unknown_level_falls_back_to_border() -> None:
    from pythinker_code.ui.theme import get_tui_tokens, thinking_frame_color

    assert thinking_frame_color("bogus", theme="dark") == get_tui_tokens("dark").border


def test_thinking_frame_style_is_ptk_fg_directive() -> None:
    from pythinker_code.ui.color_utils import blend, parse_hex_color, to_hex_color
    from pythinker_code.ui.theme import thinking_frame_style

    # Input bars are chrome: the level color is dimmed 30% toward the theme's
    # background pole so the frame hints at effort without shouting.
    rgb = parse_hex_color("#f97316")
    assert rgb is not None
    expected = to_hex_color(blend(rgb, (0, 0, 0), 0.7))
    assert thinking_frame_style("high", theme="dark") == f"fg:{expected}"


def test_core_thinking_cycle_uses_available_model_levels() -> None:
    from pythinker_code.thinking import next_thinking_level

    assert next_thinking_level("off", ("off", "high", "xhigh")) == "high"
    assert next_thinking_level("high", ("off", "high", "xhigh")) == "xhigh"
    assert next_thinking_level("xhigh", ("off", "high", "xhigh")) == "off"


def test_core_thinking_clamps_unsupported_level_up_then_down() -> None:
    from pythinker_code.thinking import clamp_thinking_effort

    assert clamp_thinking_effort("low", ("off", "high")) == "high"
    assert clamp_thinking_effort("xhigh", ("off", "high")) == "high"
    assert clamp_thinking_effort("off", ("minimal", "low", "high")) == "minimal"


def test_effective_config_thinking_effort_treats_effort_as_source_of_truth() -> None:
    from pythinker_code.thinking import effective_config_thinking_effort

    # The explicit effort field wins whenever it is set (it is the SSOT; every
    # writer keeps the legacy bool in sync). The bool is only a fallback when the
    # effort is unset (configs written before the effort field existed).
    assert effective_config_thinking_effort(False, "high") == "high"
    assert effective_config_thinking_effort(True, None) == "high"
    # Explicit "off" must beat the legacy bool (was the Finding 3 regression).
    assert effective_config_thinking_effort(True, "off") == "off"
    assert effective_config_thinking_effort(True, "xhigh") == "xhigh"
    assert effective_config_thinking_effort(False, None) == "off"
