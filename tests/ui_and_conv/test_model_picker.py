from __future__ import annotations

from pythinker_code.config import LLMModel
from pythinker_code.ui.shell.model_picker import (
    ModelEntry,
    ProviderGroup,
    _build_model_selector_config,  # type: ignore[reportPrivateUsage]
    build_provider_groups,
)
from pythinker_code.ui.shell.selector import (  # type: ignore[reportPrivateUsage]
    SelectorHeader,
    SelectorItem,
    _SelectorState,
)


def test_build_provider_groups_sorts_by_provider_label_and_model_display():
    groups = build_provider_groups(
        config_models={
            "z": LLMModel(
                provider="managed:b", model="zeta", display_name="Zeta", max_context_size=1000
            ),
            "a": LLMModel(
                provider="managed:a", model="alpha", display_name="Alpha", max_context_size=1000
            ),
            "m": LLMModel(
                provider="managed:b", model="middle", display_name="Middle", max_context_size=1000
            ),
        },
        label_for=lambda key: {"managed:a": "Alpha Provider", "managed:b": "Beta Provider"}[key],
    )

    assert [group.label for group in groups] == ["Alpha Provider", "Beta Provider"]
    assert [entry.display for entry in groups[1].models] == ["Middle", "Zeta"]


def test_model_selector_config_uses_group_headers_and_marks_current():
    config = _build_model_selector_config(
        [
            ProviderGroup(
                key="managed:test",
                label="Test Provider",
                models=(
                    ModelEntry(name="fast", display="Fast", model_id="provider/fast"),
                    ModelEntry(name="slow", display="Slow", model_id="Slow"),
                ),
            )
        ],
        current_model_name="slow",
    )

    assert config.title == "Select model"
    assert isinstance(config.items[0], SelectorHeader)
    assert config.items[0].label == "Test Provider · 2"
    selectable = [item for item in config.items if isinstance(item, SelectorItem)]
    assert [item.value for item in selectable] == ["fast", "slow"]
    assert selectable[0].description == "provider/fast  Test Provider  managed:test"
    assert selectable[1].is_current is True


def test_model_selector_filter_matches_provider_description():
    config = _build_model_selector_config(
        [
            ProviderGroup(
                key="managed:openrouter",
                label="OpenRouter",
                models=(
                    ModelEntry(name="sonnet", display="Claude Sonnet", model_id="claude-sonnet"),
                ),
            )
        ],
        current_model_name=None,
    )
    state = _SelectorState(config)
    state.append_filter("openrouter")

    visible = [item for item in state.visible if isinstance(item, SelectorItem)]
    assert [item.value for item in visible] == ["sonnet"]
