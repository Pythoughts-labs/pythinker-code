"""Rotating CLI-feature tips shown under the spinner during longer waits."""

from __future__ import annotations

import time
from typing import Final

#: Short feature hints surfaced while the agent is working. Keep each one
#: actionable and tied to a real Pythinker feature / shortcut.
FEATURE_TIPS: Final = (
    "Shift+Tab changes thinking effort levels",
    "Subagents keep your main context clean",
    "/verify before declaring work done",
    "/learn captures a lesson after a correction",
    "@-mention files to attach them to the next message",
    "/feedback sends a note to the Pythinker team",
    "/theme switches between dark and light",
    "Ctrl+O expands truncated output",
    "Use /resume to pick up a previous session",
)

#: Seconds a single tip stays on screen before rotating to the next.
TIP_ROTATE_INTERVAL_S: Final = 30.0

__all__ = ["FEATURE_TIPS", "TIP_ROTATE_INTERVAL_S", "current_tip"]


def current_tip(now: float | None = None, *, seed: int = 0) -> str:
    """Return the tip to show now, rotating slowly so it does not flicker."""
    t = time.monotonic() if now is None else now
    index = (int(t / TIP_ROTATE_INTERVAL_S) + seed) % len(FEATURE_TIPS)
    return FEATURE_TIPS[index]
