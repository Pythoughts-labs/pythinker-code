"""Model-keyed protocol-defense injection (sysprompt-1).

A model can carry quirks (e.g. Qwen-family drifting into Chinese) that warrant a
short, targeted reminder — without bloating the shared, cache-stable system
prompt for every other model. ModelDefenseInjectionProvider emits family-matched
fragments once per session via the existing dynamic-injection channel.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pythinker_code.soul.dynamic_injections.model_defense import (
    ModelDefenseFragment,
    ModelDefenseInjectionProvider,
)


def _soul(model_name: str) -> MagicMock:
    soul = MagicMock()
    soul.model_name = model_name
    return soul


async def test_emits_qwen_fragment_for_qwen_model() -> None:
    provider = ModelDefenseInjectionProvider()
    injections = await provider.get_injections([], _soul("qwen-3.7-max"))
    assert len(injections) == 1
    assert "qwen" in injections[0].type.lower()
    assert "chinese" in injections[0].content.lower()


async def test_no_fragment_for_non_matching_model() -> None:
    provider = ModelDefenseInjectionProvider()
    assert await provider.get_injections([], _soul("claude-opus-4-8")) == []


async def test_empty_model_name_emits_nothing() -> None:
    provider = ModelDefenseInjectionProvider()
    assert await provider.get_injections([], _soul("")) == []


async def test_one_shot_then_rearms_on_compaction() -> None:
    provider = ModelDefenseInjectionProvider()
    soul = _soul("qwen-max")
    assert len(await provider.get_injections([], soul)) == 1
    assert await provider.get_injections([], soul) == []  # one-shot per session
    await provider.on_context_compacted()
    assert len(await provider.get_injections([], soul)) == 1  # re-armed after compaction


def test_fragment_matches_with_patterns_and_excludes() -> None:
    fragment = ModelDefenseFragment(name="x", patterns=("qwen",), content="c", excludes=("-vl",))
    assert fragment.matches("Qwen-3-Max") is True  # case-insensitive
    assert fragment.matches("qwen-vl-plus") is False  # excluded variant
    assert fragment.matches("gpt-5.5") is False  # no pattern match


async def test_custom_fragment_registry() -> None:
    fragments = [ModelDefenseFragment(name="mini", patterns=("minimax",), content="mini-fix")]
    provider = ModelDefenseInjectionProvider(fragments)
    out = await provider.get_injections([], _soul("minimax-m3"))
    assert len(out) == 1
    assert out[0].content == "mini-fix"
