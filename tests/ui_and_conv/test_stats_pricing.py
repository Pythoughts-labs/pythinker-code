from __future__ import annotations

from pythinker_core.chat_provider import TokenUsage

from pythinker_code.ui.shell.stats_pricing import get_cost_usd


def _usage(input_other=0, output=0, cache_read=0, cache_write=0) -> TokenUsage:
    return TokenUsage(
        input_other=input_other,
        output=output,
        input_cache_read=cache_read,
        input_cache_creation=cache_write,
    )


def test_known_model_cost():
    # claude-sonnet-4-5: input=$3/M, output=$15/M
    usage = _usage(input_other=1_000_000, output=1_000_000)
    cost = get_cost_usd("claude-sonnet-4-5", usage)
    assert abs(cost - 18.0) < 0.001


def test_cache_read_cost():
    usage = _usage(cache_read=1_000_000)
    cost = get_cost_usd("claude-sonnet-4-5", usage)
    assert abs(cost - 0.3) < 0.001


def test_cache_write_cost():
    usage = _usage(cache_write=1_000_000)
    cost = get_cost_usd("claude-sonnet-4-5", usage)
    assert abs(cost - 3.75) < 0.001


def test_unknown_model_returns_zero():
    usage = _usage(input_other=1_000_000, output=1_000_000)
    cost = get_cost_usd("totally-unknown-model-xyz", usage)
    assert cost == 0.0


def test_prefix_match_fallback():
    # "claude-sonnet-4-5-20250929" should fall back to "claude-sonnet-4-5" prefix
    usage = _usage(input_other=1_000_000, output=1_000_000)
    cost = get_cost_usd("claude-sonnet-4-5-20250929", usage)
    assert cost > 0.0


def test_zero_usage_returns_zero():
    usage = _usage()
    cost = get_cost_usd("claude-opus-4-1", usage)
    assert cost == 0.0
