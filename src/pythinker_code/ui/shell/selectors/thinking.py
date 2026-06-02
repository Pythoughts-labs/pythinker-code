from __future__ import annotations

from typing import Literal, cast

from pythinker_code.thinking import (
    LEVEL_DESCRIPTIONS,
)
from pythinker_code.thinking import (
    THINKING_LEVELS as CORE_THINKING_LEVELS,
)
from pythinker_code.thinking import (
    next_thinking_level as _next_thinking_level,
)
from pythinker_code.ui.shell.selector import SelectorConfig, SelectorItem, run_selector

ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]

THINKING_LEVELS: tuple[ThinkingLevel, ...] = cast(tuple[ThinkingLevel, ...], CORE_THINKING_LEVELS)
"""Canonical low→high order used by the Shift+Tab cycle."""


def next_thinking_level(current: ThinkingLevel) -> ThinkingLevel:
    """Return the next level in the cycle, wrapping ``xhigh`` back to ``off``."""
    return cast(ThinkingLevel, _next_thinking_level(current, THINKING_LEVELS))


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
