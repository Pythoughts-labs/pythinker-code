# pyright: reportUnusedFunction=false
"""Shared OAuth event helpers for the OpenAI login and logout flows."""

from __future__ import annotations

from pythinker_code.auth.oauth import OAuthEvent
from pythinker_code.config import Config


def _default_config_error(action: str, config: Config) -> OAuthEvent | None:
    if config.is_from_default_location:
        return None
    return OAuthEvent(
        "error",
        f"{action} requires the default config file; restart without --config/--config-file.",
    )


def _handled_error_event(exc: Exception, *, site: str, message: str) -> OAuthEvent:
    from pythinker_code.telemetry.errors import report_handled_error

    report_handled_error(exc, site=site)
    return OAuthEvent("error", message)
