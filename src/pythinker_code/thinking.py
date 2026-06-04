"""Shared reasoning/thinking effort helpers.

The UI exposes the same provider-neutral effort dial as pi-main. Provider
adapters may map or clamp unsupported levels internally, but callers should
preserve the user's requested level in config/session state and pass it through
to ``ChatProvider.with_thinking`` when the selected model advertises reasoning
support.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import TYPE_CHECKING

from pythinker_core.chat_provider import ThinkingEffort

if TYPE_CHECKING:
    from pythinker_code.config import Config

THINKING_LEVELS: tuple[ThinkingEffort, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)
"""Provider-neutral user-facing effort order used by /thinking and Shift+Tab."""

EXTENDED_THINKING_LEVELS: tuple[ThinkingEffort, ...] = (*THINKING_LEVELS, "max")
"""All accepted effort values, including provider-specific aliases."""

DEFAULT_THINKING_EFFORT: ThinkingEffort = "high"

LEVEL_DESCRIPTIONS: dict[ThinkingEffort, str] = {
    "off": "No reasoning",
    "minimal": "Very brief reasoning (~1k tokens)",
    "low": "Light reasoning (~2k tokens)",
    "medium": "Moderate reasoning (~8k tokens)",
    "high": "Deep reasoning (~16k tokens)",
    "xhigh": "Maximum reasoning (~32k tokens)",
    "max": "Provider maximum reasoning",
}


def bool_to_thinking_effort(thinking: bool | None) -> ThinkingEffort | None:
    """Map legacy boolean thinking state to an effort level."""
    if thinking is None:
        return None
    return DEFAULT_THINKING_EFFORT if thinking else "off"


def thinking_effort_enabled(effort: ThinkingEffort | None) -> bool:
    return effort is not None and effort != "off"


def apply_login_thinking_defaults(
    config: Config, *, thinking: bool, effort: ThinkingEffort
) -> None:
    """Initialize login-time thinking defaults without clobbering an explicit choice.

    A ``/login`` flow reconfigures the default provider/model, but the effort dial is a
    cross-session user preference. ``create_llm`` clamps effort to the chosen model's
    capabilities at use-time, so a previously-set value is always safe to keep; only an
    unset (``None``) effort is initialized here.

    Additionally, a user who explicitly enabled thinking (``default_thinking=True``)
    on the legacy boolean path is not silently downgraded when a provider defaults
    to ``thinking=False`` — their preference is preserved.
    """
    if config.default_thinking_effort is not None:
        return
    # Preserve an explicit user preference for thinking when the provider default
    # would downgrade it.  The user can still override per-session.
    if config.default_thinking and not thinking:
        return
    config.default_thinking = thinking
    config.default_thinking_effort = effort


def normalize_thinking_effort(value: str | None) -> ThinkingEffort | None:
    """Return a known user-facing effort level."""
    if value is None:
        return None
    if value in EXTENDED_THINKING_LEVELS:
        return value
    return None


def effective_config_thinking_effort(
    default_thinking: bool,
    default_thinking_effort: ThinkingEffort | None,
) -> ThinkingEffort:
    """Resolve persisted config fields into one effective default effort.

    ``default_thinking_effort`` is the source of truth: when it is set (including
    an explicit ``"off"``) it wins. The legacy ``default_thinking`` bool is only a
    backward-compat fallback for configs written before the effort field existed
    (effort is ``None``): true -> high, false -> off.
    """
    if default_thinking_effort is not None:
        return default_thinking_effort
    return DEFAULT_THINKING_EFFORT if default_thinking else "off"


def model_uses_native_thinking(capabilities: Collection[str] | None) -> bool:
    """Return true when reasoning is built into the model, not a user effort dial."""
    return bool(
        capabilities and "always_thinking" in capabilities and "thinking" not in capabilities
    )


def available_thinking_levels(capabilities: Collection[str] | None) -> tuple[ThinkingEffort, ...]:
    """Return selectable levels for a model capability set."""
    if not capabilities or "thinking" not in capabilities:
        return ("off",)
    if "always_thinking" in capabilities:
        return tuple(level for level in THINKING_LEVELS if level != "off")
    return THINKING_LEVELS


def clamp_thinking_effort(
    effort: ThinkingEffort,
    levels: Sequence[ThinkingEffort],
) -> ThinkingEffort:
    """Clamp *effort* to the nearest selectable entry in *levels*.

    Match pi-main's behavior: if the exact level is unsupported, first search
    upward for a stronger available level, then downward. This keeps requests
    like ``xhigh`` on high-only models useful without silently disabling
    thinking.
    """
    if not levels:
        return effort
    if effort in levels:
        return effort

    try:
        requested_index = EXTENDED_THINKING_LEVELS.index(effort)
    except ValueError:
        return levels[0]

    for candidate in EXTENDED_THINKING_LEVELS[requested_index + 1 :]:
        if candidate in levels:
            return candidate
    for candidate in reversed(EXTENDED_THINKING_LEVELS[:requested_index]):
        if candidate in levels:
            return candidate
    return levels[0]


def next_thinking_level(
    current: ThinkingEffort,
    levels: Sequence[ThinkingEffort] = THINKING_LEVELS,
) -> ThinkingEffort:
    """Return the next level in *levels*, wrapping at the end."""
    if not levels:
        return current
    if current not in levels:
        # Unselectable current state (e.g. ``off`` on an always-thinking model):
        # land on the lowest valid level rather than skipping past it.
        return levels[0]
    index = levels.index(current)
    return levels[(index + 1) % len(levels)]
