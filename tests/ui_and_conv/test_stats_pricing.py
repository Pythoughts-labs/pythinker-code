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
    # "claude-sonnet-4-5-20251999" is NOT in _PRICE_TABLE, so must hit prefix fallback
    usage = _usage(input_other=1_000_000, output=1_000_000)
    cost = get_cost_usd("claude-sonnet-4-5-20251999", usage)
    assert cost > 0.0


def test_zero_usage_returns_zero():
    usage = _usage()
    cost = get_cost_usd("claude-opus-4-1", usage)
    assert cost == 0.0


# ---------------------------------------------------------------------------
# catalog-path tests
# ---------------------------------------------------------------------------


def test_get_cost_usd_uses_catalog_when_available(monkeypatch):
    from pythinker_code import models_dev
    from pythinker_code.models_dev import ModelPrice

    fake_catalog = {
        "claude-sonnet-4-6": ModelPrice(input=1.0, output=2.0, cache_read=0.1, cache_write=0.2)
    }
    monkeypatch.setattr(models_dev, "load_catalog", lambda: fake_catalog)
    usage = _usage(input_other=1_000_000, output=1_000_000)
    cost = get_cost_usd("claude-sonnet-4-6", usage)
    assert abs(cost - 3.0) < 0.001  # 1.0 + 2.0 per 1M


def test_get_cost_usd_catalog_prefix_match(monkeypatch):
    from pythinker_code import models_dev
    from pythinker_code.models_dev import ModelPrice

    fake_catalog = {
        "claude-sonnet-4-6": ModelPrice(input=9.0, output=9.0, cache_read=0.0, cache_write=0.0)
    }
    monkeypatch.setattr(models_dev, "load_catalog", lambda: fake_catalog)
    usage = _usage(input_other=1_000_000)
    # versioned id not in catalog, but prefix matches
    cost = get_cost_usd("claude-sonnet-4-6-20251001", usage)
    assert abs(cost - 9.0) < 0.001


def test_get_cost_usd_falls_back_to_hardcoded_when_catalog_empty(monkeypatch):
    from pythinker_code import models_dev

    monkeypatch.setattr(models_dev, "load_catalog", lambda: {})
    usage = _usage(input_other=1_000_000, output=1_000_000)
    # claude-sonnet-4-5 is in _PRICE_TABLE: input=3, output=15
    cost = get_cost_usd("claude-sonnet-4-5", usage)
    assert abs(cost - 18.0) < 0.001


def test_get_cost_usd_catalog_beats_hardcoded(monkeypatch):
    from pythinker_code import models_dev
    from pythinker_code.models_dev import ModelPrice

    # Override a model that IS in _PRICE_TABLE with a different catalog price
    fake_catalog = {
        "claude-sonnet-4-5": ModelPrice(input=99.0, output=99.0, cache_read=0.0, cache_write=0.0)
    }
    monkeypatch.setattr(models_dev, "load_catalog", lambda: fake_catalog)
    usage = _usage(input_other=1_000_000)
    cost = get_cost_usd("claude-sonnet-4-5", usage)
    assert abs(cost - 99.0) < 0.001  # catalog wins


def test_get_cost_usd_unknown_model_returns_zero(monkeypatch):
    from pythinker_code import models_dev

    monkeypatch.setattr(models_dev, "load_catalog", lambda: {})
    usage = _usage(input_other=1_000_000)
    assert get_cost_usd("completely-unknown-xyz-model", usage) == 0.0
