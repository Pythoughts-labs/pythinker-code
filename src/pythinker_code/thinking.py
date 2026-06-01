"""Shared reasoning/thinking effort helpers.

The UI exposes the same provider-neutral effort dial as pi-main. Provider
adapters may map or clamp unsupported levels internally, but callers should
preserve the user's requested level in config/session state and pass it through
to ``ChatProvider.with_thinking`` when the selected model advertises reasoning
support.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import cast

from pythinker_core.chat_provider import ThinkingEffort

THINKING_LEVELS: tuple[ThinkingEffort, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)
"""Provider-neutral effort order used by /thinking and Shift+Tab."""

DEFAULT_THINKING_EFFORT: ThinkingEffort = "high"


def bool_to_thinking_effort(thinking: bool | None) -> ThinkingEffort | None:
    """Map legacy boolean thinking state to an effort level."""
    if thinking is None:
        return None
    return DEFAULT_THINKING_EFFORT if thinking else "off"


def thinking_effort_enabled(effort: ThinkingEffort | None) -> bool:
    return effort is not None and effort != "off"


def normalize_thinking_effort(value: str | None) -> ThinkingEffort | None:
    """Return a known user-facing effort level."""
    if value is None:
        return None
    if value in THINKING_LEVELS:
        return cast(ThinkingEffort, value)
    # ``max`` can still appear from provider internals for Claude models that
    # map pi's xhigh to Anthropic's max effort. Keep it accepted, but don't put
    # it in the UI cycle.
    if value == "max":
        return "max"
    return None


def effective_config_thinking_effort(
    default_thinking: bool,
    default_thinking_effort: ThinkingEffort | None,
) -> ThinkingEffort:
    """Resolve persisted config fields into one effective default effort.

    ``default_thinking`` is the legacy bool. Keep it authoritative when false so
    older code paths that only clear the bool do not leave a stale non-off effort
    active. When true and no explicit effort has been saved yet, default to high
    to match the old behavior.
    """
    if default_thinking_effort == "off":
        return "off"
    if default_thinking:
        return default_thinking_effort or DEFAULT_THINKING_EFFORT
    return "off"


def available_thinking_levels(capabilities: Collection[str] | None) -> tuple[ThinkingEffort, ...]:
    """Return selectable levels for a model capability set."""
    if not capabilities or "thinking" not in capabilities:
        return ("off",)
    if "always_thinking" in capabilities:
        return tuple(level for level in THINKING_LEVELS if level != "off")
    return THINKING_LEVELS


def next_thinking_level(
    current: ThinkingEffort,
    levels: Sequence[ThinkingEffort] = THINKING_LEVELS,
) -> ThinkingEffort:
    """Return the next level in *levels*, wrapping at the end."""
    if not levels:
        return current
    if current not in levels:
        return levels[0]
    index = levels.index(current)
    return levels[(index + 1) % len(levels)]
