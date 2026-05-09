from __future__ import annotations

from typing import Literal

from pythinker_code.ui.shell.selector import SelectorConfig, SelectorItem, run_selector

ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]

LEVEL_DESCRIPTIONS: dict[str, str] = {
    "off": "No reasoning",
    "minimal": "Very brief reasoning (~1k tokens)",
    "low": "Light reasoning (~2k tokens)",
    "medium": "Moderate reasoning (~8k tokens)",
    "high": "Deep reasoning (~16k tokens)",
    "xhigh": "Maximum reasoning (~32k tokens)",
}


def _build_thinking_config(
    current_level: ThinkingLevel,
    available_levels: list[ThinkingLevel],
) -> SelectorConfig[ThinkingLevel]:
    return SelectorConfig(
        title="Select thinking level",
        items=[
            SelectorItem(
                value=level,
                label=level,
                description=LEVEL_DESCRIPTIONS.get(level, ""),
                is_current=(level == current_level),
            )
            for level in available_levels
        ],
        hint="↑↓ navigate · Enter select · Esc cancel",
    )


async def run_thinking_selector(
    current_level: ThinkingLevel,
    available_levels: list[ThinkingLevel],
) -> ThinkingLevel | None:
    return await run_selector(_build_thinking_config(current_level, available_levels))
