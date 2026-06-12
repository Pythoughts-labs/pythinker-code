"""Provider API error classification shared by the soul loop and compaction.

Lives in its own module so compaction can classify context-overflow
rejections without importing the soul (which imports compaction).
"""

from __future__ import annotations

from pythinker_core.chat_provider import (
    APIConnectionError,
    APIEmptyResponseError,
    APIStatusError,
    APITimeoutError,
)

_CONTEXT_OVERFLOW_MARKERS = (
    "context length",
    "context_length",
    "max tokens",
    "maximum context",
    "too many tokens",
)


def classify_api_error(e: Exception) -> tuple[str, int | None]:
    """Classify an LLM API exception into (error_type, status_code).

    Exposed at module level so telemetry tests can import the real function
    instead of duplicating the classification table.

    Returns:
        (error_type, status_code) where status_code is None for non-HTTP errors.
    """
    status_code: int | None = None
    if isinstance(e, APIStatusError):
        status = getattr(e, "status_code", getattr(e, "status", 0))
        status_code = int(status) if status else None
        if status == 429:
            return "rate_limit", status_code
        if status in (401, 403):
            return "auth", status_code
        if status >= 500:
            return "5xx_server", status_code
        if 400 <= status < 500:
            msg_lower = str(e).lower()
            if any(marker in msg_lower for marker in _CONTEXT_OVERFLOW_MARKERS):
                return "context_overflow", status_code
            return "4xx_client", status_code
        return "api", status_code
    if isinstance(e, APIConnectionError):
        return "network", None
    if isinstance(e, (APITimeoutError, TimeoutError)):
        return "timeout", None
    if isinstance(e, APIEmptyResponseError):
        return "empty_response", None
    return "other", None


def is_context_overflow_error(e: Exception) -> bool:
    """Whether *e* is a provider rejection for exceeding the context window."""
    return classify_api_error(e)[0] == "context_overflow"
