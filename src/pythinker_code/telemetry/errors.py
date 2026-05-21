"""Helper for reporting handled exceptions to Sentry/Bugsink + OTel.

Use this at any except-block site that intentionally turns an exception into
a graceful user-facing error result (a ``ToolError``, a TUI message, a logged
warning). The site keeps its existing failure-rendering behaviour; the helper
additionally informs the monitoring stack so dashboards can see the failure
rate, class, and bucket.

Privacy posture
---------------
Only pass primitive enum-like attributes through ``**attrs`` (tool name,
class names, mode flags). The OTel ``error`` event is forwarded verbatim, so
**never** pass user input, file paths, or code snippets there. Sentry is fine
with full exception data — its ``before_send`` hook already scrubs paths and
strips PII before transmission.

Both forwarding paths are wrapped in :func:`contextlib.suppress` because
telemetry must never break the host program.
"""

from __future__ import annotations

import contextlib
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from pythinker_code.telemetry import sentry as _sentry
from pythinker_code.telemetry import track

# ---------------------------------------------------------------------------
# Process-local ring buffer of recent errors
# ---------------------------------------------------------------------------
# Keeps just enough metadata to populate the ``/report-error`` slash command
# without retaining the full exception object (which can hold large frames
# and references). Class name + a short, redacted message is what shows in
# the buffer; the *full* scrubbed stack is already in Sentry/Bugsink.

_RECENT_BUFFER_SIZE = 10
_ABSOLUTE_PATH_RE = re.compile(r"(?<!\w)(?:/[\w .~+@%=-]+)+|[A-Za-z]:\\(?:[^\\\r\n]+\\?)+")


def _redact_recent_message(message: str) -> str:
    return _ABSOLUTE_PATH_RE.sub("<path>", message)[:200]


@dataclass(frozen=True, slots=True)
class RecentError:
    timestamp: float
    site: str
    exc_class: str
    message: str  # truncated to 200 chars
    tool: str | None


_recent: deque[RecentError] = deque(maxlen=_RECENT_BUFFER_SIZE)


def recent_errors() -> list[RecentError]:
    """Snapshot of the most-recent reported errors (oldest first)."""
    return list(_recent)


def clear_recent_errors() -> None:
    """Drop the recent-errors buffer. Used by tests and by ``/report-error``
    after a successful submission."""
    _recent.clear()


def report_handled_error(
    exc: BaseException,
    *,
    site: str,
    tool: str | None = None,
    **attrs: bool | int | float | str | None,
) -> None:
    """Forward a caught-and-rendered exception to Sentry + the OTel error stream.

    Args:
        exc: The exception that was caught at the call site.
        site: Stable identifier for the catch site, e.g. ``"tool.read"`` or
            ``"auth.oauth.refresh"``. Used to bucket failures in dashboards.
            Must be a stable enum-like string, not a free-form message.
        tool: Optional tool name when the site is a tool implementation
            (e.g. ``"ReadFile"``). Forwarded as a separate property so SigNoz
            queries can group by tool without parsing ``site``.
        **attrs: Additional primitive enum-like attributes. Booleans, numbers
            and short strings only. Values must not contain user input,
            absolute paths, or code snippets.
    """
    properties: dict[str, Any] = {
        "site": site,
        "exc_class": type(exc).__name__,
    }
    if tool is not None:
        properties["tool"] = tool
    properties.update(attrs)
    with contextlib.suppress(Exception):
        track("error", **properties)
    with contextlib.suppress(Exception):
        _sentry.capture_exception(exc)
    with contextlib.suppress(Exception):
        _recent.append(
            RecentError(
                timestamp=time.time(),
                site=site,
                exc_class=type(exc).__name__,
                message=_redact_recent_message(str(exc)),
                tool=tool,
            )
        )
