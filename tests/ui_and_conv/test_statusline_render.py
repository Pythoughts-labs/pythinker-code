"""Tests for statusline v2 rendering: theme tokens, bar, segments."""

from pythinker_code.ui.theme import StatusLineColors, get_statusline_colors


def test_statusline_colors_dark_palette():
    colors = get_statusline_colors()
    assert isinstance(colors, StatusLineColors)
    assert colors.model == "bold fg:#dcb4ff"
    assert colors.usage_ok == "fg:#64d2a0"
    assert colors.usage_crit == "fg:#ff5050"
    assert colors.dim == "fg:#505564"


from pythinker_code.ui.shell.statusline import smooth_bar, usage_level


def test_usage_level_thresholds():
    assert usage_level(0) == "ok"
    assert usage_level(49) == "ok"
    assert usage_level(50) == "mid"
    assert usage_level(69) == "mid"
    assert usage_level(70) == "high"
    assert usage_level(89) == "high"
    assert usage_level(90) == "crit"
    assert usage_level(200) == "crit"


def test_smooth_bar_eighth_blocks():
    assert smooth_bar(0, width=8) == "░" * 8
    assert smooth_bar(100, width=8) == "█" * 8
    # 18% of 10 cells = 1.8 cells = 1 full block + 6/8 partial + 8 empty
    assert smooth_bar(18, width=10) == "█▊" + "░" * 8
    # never exceeds width
    assert len(smooth_bar(99, width=10)) == 10


def test_smooth_bar_ascii_fallback():
    assert smooth_bar(50, width=8, ascii_only=True) == "####----"
    assert smooth_bar(0, width=8, ascii_only=True) == "--------"


from pythinker_code.config import StatusLineConfig
from pythinker_code.ui.shell.statusline import (
    SEGMENT_REGISTRY,
    GitInfo,
    StatusFlags,
    StatusLineContext,
    split_zones,
)


def make_ctx(**overrides):
    """A minimal idle context; tests override what they exercise."""
    defaults = dict(
        columns=120,
        working=False,
        frame=0,
        model_name="claude-fable-5",
        provider_label=None,
        effort=None,
        rate_in=None,
        rate_out=None,
        session_cost_usd=0.0,
        cost_budget_usd=None,
        context_tokens=36_000,
        max_context_tokens=200_000,
        elapsed_s=72.0,
        clock="14:32",
        cwd="pythinker-code-main",
        git=None,
        diff_added=None,
        diff_removed=None,
        flags=StatusFlags(yolo=False, auto=False, plan=False),
        limits=None,
        ascii_only=False,
        style="fancy",
        bar_width=10,
    )
    defaults.update(overrides)
    return StatusLineContext(**defaults)


def test_registry_covers_all_config_ids():
    from pythinker_code.config import STATUSLINE_SEGMENT_IDS

    assert set(SEGMENT_REGISTRY) == set(STATUSLINE_SEGMENT_IDS)


def test_split_zones_preserves_user_order():
    cfg = StatusLineConfig(segments=["clock", "model", "spinner", "context"])
    zones = split_zones(cfg.segments)
    assert zones.line1 == ["model", "spinner"]
    assert zones.line2_right == ["clock", "context"]


def test_split_zones_ignores_unknown_ids():
    zones = split_zones(["model", "hologram"])
    assert zones.line1 == ["model"]
