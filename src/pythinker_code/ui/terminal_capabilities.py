"""Terminal capability helpers for portable shell UI rendering.

The shell UI has to work in modern terminals, PowerShell, CI logs, SSH panes,
and deliberately minimal terminals. Keep environment-based decisions here so
color, glyph, and motion fallbacks stay consistent across Rich and
prompt_toolkit renderers.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import TextIO

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "always"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "never"})


def _env(environ: Mapping[str, str] | None = None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def _clean(value: str | None) -> str:
    return "" if value is None else value.strip().lower()


def env_flag(name: str, *, environ: Mapping[str, str] | None = None) -> bool:
    """Return true when *name* is set to a conventional truthy value."""
    return _clean(_env(environ).get(name)) in _TRUE_VALUES


def colors_disabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether terminal color should be suppressed.

    Follows the widely-used CLI conventions from clig.dev and no-color.org:
    ``NO_COLOR`` wins when non-empty, ``TERM=dumb`` means no formatting, and
    ``CLICOLOR=0`` disables color for tools that support the BSD convention.
    ``PYTHINKER_NO_COLOR`` is the app-specific override for users who want one.
    """
    env = _env(environ)
    if env.get("NO_COLOR"):
        return True
    if env_flag("PYTHINKER_NO_COLOR", environ=env):
        return True
    if _clean(env.get("TERM")) == "dumb":
        return True
    return _clean(env.get("CLICOLOR")) == "0"


def ascii_glyphs_enabled(
    environ: Mapping[str, str] | None = None, stdout: TextIO | None = None
) -> bool:
    """Return whether the TUI should use ASCII-only glyphs.

    Modern Windows Terminal and PowerShell are Unicode-capable, so Windows alone
    is not a reason to degrade. We fall back for explicit user requests,
    ``TERM=dumb``, or non-UTF stdout encodings such as legacy Windows code pages.
    """
    env = _env(environ)
    stdout = sys.stdout if stdout is None else stdout
    mode = _clean(env.get("PYTHINKER_TUI_GLYPHS"))
    if mode in {"ascii", "safe"}:
        return True
    if mode in {"unicode", "rich"}:
        return False
    if env_flag("PYTHINKER_ASCII_UI", environ=env) or env_flag(
        "PYTHINKER_SAFE_GLYPHS", environ=env
    ):
        return True
    if _clean(env.get("TERM")) == "dumb":
        return True

    encoding = _clean(getattr(stdout, "encoding", None))
    return bool(encoding and "utf" not in encoding and "65001" not in encoding)


def motion_disabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether animated terminal affordances should collapse to static."""
    env = _env(environ)
    if _clean(env.get("TERM")) == "dumb":
        return True
    return any(
        env_flag(name, environ=env)
        for name in (
            "PYTHINKER_REDUCED_MOTION",
            "PYTHINKER_NO_ANIMATION",
            "PYTHINKER_STATIC_OUTPUT",
        )
    )
