"""Resolve the active TUI style from env var or loaded config.

Single accessor used by call sites to decide between the legacy
``pythinker`` worklog rendering path and the new ``card`` style. Keeps the
flag-resolution logic in one place so the migration's escape hatch can be
removed cleanly once the card style stabilizes.

The legacy ``"pi"`` value is still accepted on input as an alias for
``"card"`` so older configs and ``PYTHINKER_TUI_STYLE`` env vars don't
break — they're transparently mapped on read.
"""

from __future__ import annotations

import os
from typing import Literal

TUIStyle = Literal["pythinker", "card"]

_ENV_VAR = "PYTHINKER_TUI_STYLE"
_VALID: frozenset[str] = frozenset(("pythinker", "card"))
_LEGACY_ALIASES: dict[str, TUIStyle] = {"pi": "card"}

_active_tui_style: TUIStyle = "pythinker"
"""Process-level active style. Set at shell startup from ``Config.tui.style``;
used as the fallback when neither env var nor a per-call ``configured`` value
is provided."""


def _normalize(value: str | None) -> TUIStyle | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if cleaned in _VALID:
        return cleaned  # type: ignore[return-value]
    if cleaned in _LEGACY_ALIASES:
        return _LEGACY_ALIASES[cleaned]
    return None


def _from_env() -> TUIStyle | None:
    """Read the env var override. Returns None when unset or invalid."""
    return _normalize(os.environ.get(_ENV_VAR))


def set_active_tui_style(style: TUIStyle | str | None) -> None:
    """Set the process-level active style.

    Called once at shell startup from the loaded config. Invalid or None
    values fall back to ``"pythinker"`` so a stale config can't break the
    shell. Legacy ``"pi"`` is silently mapped to ``"card"``.
    """
    global _active_tui_style
    normalized = _normalize(style if isinstance(style, str) else None)
    _active_tui_style = normalized if normalized is not None else "pythinker"


def get_active_tui_style() -> TUIStyle:
    """Return the process-level active style (without env override)."""
    return _active_tui_style


def get_tui_style(configured: TUIStyle | str | None = None) -> TUIStyle:
    """Return the effective TUI style.

    Resolution order (first match wins):
      1. ``PYTHINKER_TUI_STYLE`` env var, if set to a valid value
      2. *configured* argument (when provided and valid)
      3. Process-level active style set via :func:`set_active_tui_style`
      4. ``"pythinker"`` (initial default)

    Unrecognized values fall through to the next layer rather than raising,
    so a stale env var or older config can't break the shell.
    """
    env = _from_env()
    if env is not None:
        return env
    if isinstance(configured, str):
        normalized = _normalize(configured)
        if normalized is not None:
            return normalized
    return _active_tui_style


def is_card_style(configured: TUIStyle | str | None = None) -> bool:
    """Convenience predicate for ``get_tui_style(...) == "card"``."""
    return get_tui_style(configured) == "card"
