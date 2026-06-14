from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

import aiohttp
from pydantic import SecretStr

from pythinker_code.auth import MOONSHOT_PLATFORM_ID
from pythinker_code.auth.oauth import OAuthEvent
from pythinker_code.auth.platforms import managed_model_key, managed_provider_key
from pythinker_code.config import Config, LLMModel, LLMProvider, save_config
from pythinker_code.thinking import apply_login_thinking_defaults
from pythinker_code.utils.aiohttp import new_client_session

MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"
MOONSHOT_PROVIDER_KEY = managed_provider_key(MOONSHOT_PLATFORM_ID)
MOONSHOT_DEFAULT_MODEL_ALIAS = managed_model_key(MOONSHOT_PLATFORM_ID, "kimi-k2.7-code")


@dataclass(frozen=True, slots=True)
class MoonshotModel:
    model_id: str
    alias_suffix: str
    display_name: str
    provider_key: str = MOONSHOT_PROVIDER_KEY
    max_context_size: int = 262_144

    @property
    def alias(self) -> str:
        return f"{MOONSHOT_PLATFORM_ID}/{self.alias_suffix}"


MOONSHOT_MODELS: tuple[MoonshotModel, ...] = (
    MoonshotModel("kimi-k2.7-code", "kimi-k2.7-code", "Kimi K2.7 Code"),
    MoonshotModel("kimi-k2.6", "kimi-k2.6", "Kimi K2.6"),
    MoonshotModel("kimi-k2.5", "kimi-k2.5", "Kimi K2.5"),
    MoonshotModel("kimi-k2-thinking", "kimi-k2-thinking", "Kimi K2 Thinking"),
)


def get_moonshot_api_key_from_env() -> str | None:
    raw = os.environ.get("MOONSHOT_API_KEY", "")
    if not raw:
        return None
    return raw.strip()


def _apply_moonshot_config(
    config: Config,
    api_key: SecretStr,
    models: tuple[MoonshotModel, ...] = MOONSHOT_MODELS,
) -> None:
    config.providers[MOONSHOT_PROVIDER_KEY] = LLMProvider(
        type="openai_legacy",
        base_url=MOONSHOT_BASE_URL,
        api_key=api_key,
    )

    provider_keys = {MOONSHOT_PROVIDER_KEY}
    for key, model in list(config.models.items()):
        if model.provider in provider_keys:
            del config.models[key]

    for model in models:
        config.models[model.alias] = LLMModel(
            provider=model.provider_key,
            model=model.model_id,
            max_context_size=model.max_context_size,
            display_name=model.display_name,
        )

    fallback = next(
        (m.alias for m in models),
        next(iter(config.models), ""),
    )
    if MOONSHOT_DEFAULT_MODEL_ALIAS in config.models:
        config.default_model = MOONSHOT_DEFAULT_MODEL_ALIAS
    else:
        config.default_model = fallback
    apply_login_thinking_defaults(config, thinking=False, effort="off")


def _model_by_id() -> dict[str, MoonshotModel]:
    return {model.model_id: model for model in MOONSHOT_MODELS}


def _parse_discovered_models(data: object) -> tuple[MoonshotModel, ...] | None:
    """Return parsed models, or None if the payload is structurally invalid."""
    if not isinstance(data, dict):
        return None
    d = cast(dict[str, Any], data)
    items = d.get("data")
    if not isinstance(items, list):
        return None
    catalog = _model_by_id()
    results: list[MoonshotModel] = []
    for raw_item in items:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, Any], raw_item)
        model_id = item.get("id")
        if not isinstance(model_id, str) or model_id not in catalog:
            continue
        base = catalog[model_id]
        ctx = item.get("context_length")
        max_ctx = base.max_context_size
        if isinstance(ctx, int) and ctx > 0:
            max_ctx = ctx
        display_name = base.display_name
        api_name = item.get("display_name")
        if isinstance(api_name, str) and api_name:
            display_name = api_name
        results.append(
            MoonshotModel(
                model_id=base.model_id,
                alias_suffix=base.alias_suffix,
                display_name=display_name,
                provider_key=base.provider_key,
                max_context_size=max_ctx,
            )
        )
    return tuple(results)


async def _discover_moonshot_models(
    api_key: str,
) -> tuple[MoonshotModel, ...] | None:
    async with (
        new_client_session() as session,
        session.get(
            f"{MOONSHOT_BASE_URL}/models",
            headers={"Authorization": f"Bearer {api_key}"},
        ) as resp,
    ):
        resp.raise_for_status()
        payload: object = await resp.json()
        return _parse_discovered_models(payload)


async def login_moonshot_api_key(
    config: Config, api_key: str | None = None
) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Login requires the default config file; restart without --config/--config-file.",
        )
        return

    resolved_key = (api_key or get_moonshot_api_key_from_env() or "").strip()
    if not resolved_key:
        yield OAuthEvent("error", "Moonshot API key is required.")
        return

    models = MOONSHOT_MODELS
    try:
        discovered = await _discover_moonshot_models(resolved_key)
        if discovered is not None and discovered:
            models = discovered
    except aiohttp.ClientResponseError as exc:
        if exc.status in {401, 403}:
            yield OAuthEvent("error", "Invalid Moonshot API key; the key was not saved.")
            return
        yield OAuthEvent(
            "info",
            "Moonshot model listing is unavailable; using the built-in model list.",
        )
    except (aiohttp.ClientError, TimeoutError, ValueError):
        yield OAuthEvent(
            "info",
            "Moonshot model listing is unavailable; using the built-in model list.",
        )

    _apply_moonshot_config(config, SecretStr(resolved_key), models=models)
    save_config(config)
    yield OAuthEvent("success", f"Moonshot configured with model {config.default_model}.")


async def logout_moonshot(config: Config) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Logout requires the default config file; restart without --config/--config-file.",
        )
        return

    provider_keys = {MOONSHOT_PROVIDER_KEY}
    config.providers.pop(MOONSHOT_PROVIDER_KEY, None)
    for key, model in list(config.models.items()):
        if model.provider in provider_keys:
            del config.models[key]

    if config.default_model not in config.models:
        config.default_model = next(iter(config.models), "")
    save_config(config)
    yield OAuthEvent("success", "Logged out of Moonshot successfully.")
