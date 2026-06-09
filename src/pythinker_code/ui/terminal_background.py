"""Terminal default-background probing for ``theme = "auto"``.

Ported from the Codex TUI reference (``codex-rs/tui/src/terminal_probe.rs`` /
``terminal_palette.rs``): query the terminal's default background color with
OSC 11, classify it as light or dark via BT.601 luma, and cache the answer
for the process lifetime. Probing is strictly best-effort — any failure
(non-tty, Windows, dumb terminal, timeout, unparsable reply) returns ``None``
so callers keep their configured fallback.
"""

from __future__ import annotations

import os
import re
import select
import sys
import time
from typing import TYPE_CHECKING, Literal

from pythinker_code.ui.color_utils import RGB, is_light

if TYPE_CHECKING:
    from pythinker_code.ui.theme import ThemeName

_OSC11_QUERY = "\x1b]11;?\x1b\\"
# Reply shape: ``ESC ] 11 ; rgb:RRRR/GGGG/BBBB`` terminated by BEL or ST.
# Components are 1-4 hex digits each (XParseColor scaling).
_OSC11_RESPONSE_RE = re.compile(
    r"\]11;rgb:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})"
)

_PROBE_TIMEOUT_S = 0.1

_cached_bg: RGB | None = None
_probe_attempted = False


def _scale_component(component: str) -> int:
    """Scale a 1-4 digit hex component to 0-255 (XParseColor semantics)."""
    max_value = (1 << (4 * len(component))) - 1
    return round(int(component, 16) * 255 / max_value)


def parse_osc11_response(payload: str) -> RGB | None:
    """Extract the background RGB from an OSC 11 reply, or ``None``."""
    match = _OSC11_RESPONSE_RE.search(payload)
    if match is None:
        return None
    return (
        _scale_component(match.group(1)),
        _scale_component(match.group(2)),
        _scale_component(match.group(3)),
    )


def _probe_uncached(timeout: float) -> RGB | None:
    if sys.platform == "win32":
        return None
    env = os.environ
    if env.get("PYTHINKER_NO_BG_PROBE"):
        return None
    if (env.get("TERM") or "").strip().lower() == "dumb":
        return None
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return None
        fd = sys.stdin.fileno()
    except (ValueError, OSError):
        return None

    import termios
    import tty

    try:
        old_attrs = termios.tcgetattr(fd)
    except (termios.error, OSError):
        return None
    try:
        tty.setcbreak(fd)
        sys.stdout.write(_OSC11_QUERY)
        sys.stdout.flush()
        deadline = time.monotonic() + timeout
        buf = ""
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            readable, _, _ = select.select([fd], [], [], max(0.0, remaining))
            if not readable:
                break
            chunk = os.read(fd, 64)
            if not chunk:
                break
            buf += chunk.decode("utf-8", "ignore")
            if "\x07" in buf or "\x1b\\" in buf:
                break
        return parse_osc11_response(buf)
    except OSError:
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)


def probe_terminal_background(timeout: float = _PROBE_TIMEOUT_S) -> RGB | None:
    """Return the terminal's default background RGB, cached per process.

    A failed probe is also cached (as ``None``) so the terminal is never
    queried twice in one session.
    """
    global _cached_bg, _probe_attempted
    if _probe_attempted:
        return _cached_bg
    _probe_attempted = True
    _cached_bg = _probe_uncached(timeout)
    return _cached_bg


def detect_background_theme() -> Literal["dark", "light"] | None:
    """Classify the probed background as ``"dark"``/``"light"``, or ``None``."""
    rgb = probe_terminal_background()
    if rgb is None:
        return None
    return "light" if is_light(rgb) else "dark"


def resolve_theme_name(configured: str) -> ThemeName:
    """Resolve a configured theme (``dark``/``light``/``auto``) to a concrete name.

    ``auto`` probes the terminal background; an unanswered or failed probe
    falls back to ``dark``.
    """
    if configured == "light":
        return "light"
    if configured == "auto":
        detected = detect_background_theme()
        if detected is not None:
            return detected
    return "dark"
