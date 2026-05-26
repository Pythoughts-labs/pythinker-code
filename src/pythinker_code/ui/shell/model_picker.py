"""Interactive model picker built on the shared selector chrome.

The picker keeps the public ``ModelPickerApp(...).run()`` API used by the
``/model`` slash command, but delegates rendering and keyboard behavior to the
same professional selector component used by theme/thinking/oauth pickers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pythinker_code.config import LLMModel
from pythinker_code.ui.shell.selector import (
    SelectorConfig,
    SelectorHeader,
    SelectorItem,
    run_selector,
)


@dataclass(frozen=True, slots=True)
class ModelEntry:
    name: str  # config key (selection result)
    display: str  # display name shown to the user
    model_id: str  # raw model id (for matching)


@dataclass(frozen=True, slots=True)
class ProviderGroup:
    key: str  # raw provider key (e.g. "managed:lm-studio")
    label: str  # humanized label
    models: tuple[ModelEntry, ...]


class ModelPickerApp:
    """Grouped model picker with type-to-filter and shared TUI styling."""

    def __init__(
        self,
        *,
        groups: list[ProviderGroup],
        current_model_name: str | None,
    ) -> None:
        self._groups = groups
        self._current = current_model_name

    async def run(self) -> str | None:
        return await run_selector(_build_model_selector_config(self._groups, self._current))


def _build_model_selector_config(
    groups: list[ProviderGroup],
    current_model_name: str | None,
) -> SelectorConfig[str]:
    rows: list[SelectorItem[str] | SelectorHeader] = []
    for group in groups:
        visible_models = tuple(sorted(group.models, key=lambda m: m.display.lower()))
        if not visible_models:
            continue
        rows.append(SelectorHeader(label=f"{group.label} · {len(visible_models)}"))
        for model in visible_models:
            description_parts: list[str] = []
            if model.model_id != model.display:
                description_parts.append(model.model_id)
            description_parts.append(group.label)
            if group.key != group.label:
                description_parts.append(group.key)
            rows.append(
                SelectorItem(
                    value=model.name,
                    label=model.display,
                    description="  ".join(description_parts),
                    is_current=(model.name == current_model_name),
                )
            )

    return SelectorConfig(
        title="Select model",
        items=rows,
        hint="↑↓ navigate · PgUp/PgDn jump · Enter select · Esc cancel · type to filter",
        max_visible=14,
    )


def build_provider_groups(
    *,
    config_models: Mapping[str, LLMModel],
    label_for: Callable[[str], str],
) -> list[ProviderGroup]:
    """Group config.models by provider key, alpha-sorted by label/display.

    ``label_for(provider_key) -> str`` resolves the human label for a provider.
    """
    grouped: dict[str, list[ModelEntry]] = {}
    for name in sorted(config_models):
        cfg = config_models[name]
        provider_key = cfg.provider
        model_id = cfg.model
        display = cfg.display_name or model_id
        grouped.setdefault(provider_key, []).append(
            ModelEntry(name=name, display=display, model_id=model_id)
        )

    groups = [
        ProviderGroup(
            key=key,
            label=label_for(key),
            models=tuple(sorted(entries, key=lambda entry: entry.display.lower())),
        )
        for key, entries in grouped.items()
    ]
    groups.sort(key=lambda g: g.label.lower())
    return groups
