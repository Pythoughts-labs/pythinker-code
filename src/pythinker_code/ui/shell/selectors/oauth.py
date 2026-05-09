from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pythinker_code.ui.shell.selector import SelectorConfig, SelectorItem, run_selector


@dataclass(frozen=True, slots=True)
class OAuthProviderEntry:
    id: str
    name: str
    auth_type: Literal["oauth", "api_key"]


@dataclass(frozen=True, slots=True)
class OAuthProviderStatus:
    source: Literal[
        "environment",
        "runtime",
        "fallback",
        "models_json_key",
        "models_json_command",
        "configured",
        "unconfigured",
    ]
    label: str | None = None


def _format_status_indicator(status: OAuthProviderStatus) -> str:
    if status.source == "unconfigured":
        return "• unconfigured"
    if status.source == "environment":
        return f"✓ env: {status.label or 'API key'}"
    return f"✓ {status.label or 'configured'}"


def _build_oauth_config(
    providers: list[OAuthProviderEntry],
    get_status: Callable[[str], OAuthProviderStatus],
    *,
    action: Literal["login", "logout"] = "login",
) -> SelectorConfig[str]:
    items = [
        SelectorItem(
            value=provider.id,
            label=provider.name,
            description=_format_status_indicator(get_status(provider.id)),
        )
        for provider in providers
    ]
    title = "Select provider to log in" if action == "login" else "Select provider to log out"
    return SelectorConfig(title=title, items=items)


async def run_oauth_selector(
    providers: list[OAuthProviderEntry],
    get_status: Callable[[str], OAuthProviderStatus],
    *,
    action: Literal["login", "logout"] = "login",
) -> str | None:
    return await run_selector(_build_oauth_config(providers, get_status, action=action))
