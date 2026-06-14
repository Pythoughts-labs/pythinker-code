from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, cast

import aiohttp
from pydantic import SecretStr

from pythinker_code.auth import KIMI_PLATFORM_ID
from pythinker_code.auth.oauth import OAuthEvent
from pythinker_code.auth.platforms import managed_model_key, managed_provider_key
from pythinker_code.config import Config, LLMModel, LLMProvider, save_config
from pythinker_code.thinking import apply_login_thinking_defaults
from pythinker_code.utils.aiohttp import new_client_session

# The Kimi coding plan is served from Moonshot's Anthropic-compatible endpoint
# (ANTHROPIC_BASE_URL in the Claude Code integration guide) and authenticates
# with the same Moonshot API key. It is a distinct plan from the OpenAI-compatible
# Moonshot provider (`auth/moonshot.py`), which targets `api.moonshot.ai/v1`.
KIMI_BASE_URL = "https://api.moonshot.ai/anthropic"
KIMI_MODELS_URL = "https://api.moonshot.ai/anthropic/v1/models"
KIMI_PROVIDER_KEY = managed_provider_key(KIMI_PLATFORM_ID)
KIMI_DEFAULT_MODEL_ALIAS = managed_model_key(KIMI_PLATFORM_ID, "kimi-k2.7-code")
KIMI_MODEL_DISCOVERY_TIMEOUT = aiohttp.ClientTimeout(total=15, sock_connect=8, sock_read=10)


@dataclass(frozen=True, slots=True)
class KimiModel:
    model_id: str
    alias_suffix: str
    display_name: str
    provider_key: str = KIMI_PROVIDER_KEY
    max_context_size: int = 262_144

    @property
    def alias(self) -> str:
        return f"{KIMI_PLATFORM_ID}/{self.alias_suffix}"


KIMI_MODELS: tuple[KimiModel, ...] = (
    KimiModel("kimi-k2.7-code", "kimi-k2.7-code", "Kimi K2.7 Code"),
)


def get_kimi_api_key_from_env() -> str | None:
    # The coding plan reuses the Moonshot API key; accept either name.
    for var in ("KIMI_API_KEY", "MOONSHOT_API_KEY"):
        value = os.getenv(var)
        if value and value.strip():
            return value.strip()
    return None


def _model_by_id() -> dict[str, KimiModel]:
    return {model.model_id: model for model in KIMI_MODELS}


def _parse_discovered_models(data: object) -> tuple[KimiModel, ...] | None:
    """Return parsed models, or None if the payload is structurally invalid.

    Only models already in the curated catalog are kept: the coding plan is
    focused on `kimi-k2.7-code`, and discovery is used to refresh its context
    window/display name, not to widen the plan.
    """
    if not isinstance(data, dict):
        return None
    raw_items = cast(dict[str, Any], data).get("data")
    if not isinstance(raw_items, list):
        return None

    catalog = _model_by_id()
    seen: set[str] = set()
    result: list[KimiModel] = []
    for raw_item in cast(list[Any], raw_items):
        if not isinstance(raw_item, Mapping):
            continue
        item = cast(Mapping[str, Any], raw_item)
        model_id = item.get("id")
        if not isinstance(model_id, str) or model_id not in catalog or model_id in seen:
            continue
        seen.add(model_id)
        base = catalog[model_id]
        max_ctx = base.max_context_size
        ctx = item.get("context_length")
        if isinstance(ctx, int) and ctx > 0:
            max_ctx = ctx
        display_name = base.display_name
        api_name = item.get("display_name")
        if isinstance(api_name, str) and api_name.strip():
            display_name = api_name.strip()
        result.append(
            KimiModel(
                model_id=base.model_id,
                alias_suffix=base.alias_suffix,
                display_name=display_name,
                provider_key=base.provider_key,
                max_context_size=max_ctx,
            )
        )
    return tuple(result)


async def _discover_kimi_models(api_key: str) -> tuple[KimiModel, ...] | None:
    async with (
        new_client_session(timeout=KIMI_MODEL_DISCOVERY_TIMEOUT) as session,
        session.get(
            KIMI_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}", "x-api-key": api_key},
            raise_for_status=True,
        ) as response,
    ):
        payload = await response.json(content_type=None)
    return _parse_discovered_models(payload)


def _apply_kimi_config(
    config: Config,
    api_key: SecretStr,
    models: tuple[KimiModel, ...] = KIMI_MODELS,
) -> None:
    config.providers[KIMI_PROVIDER_KEY] = LLMProvider(
        type="anthropic",
        base_url=KIMI_BASE_URL,
        api_key=api_key,
    )

    provider_keys = {KIMI_PROVIDER_KEY}
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
    if KIMI_DEFAULT_MODEL_ALIAS in config.models:
        config.default_model = KIMI_DEFAULT_MODEL_ALIAS
    else:
        config.default_model = fallback
    apply_login_thinking_defaults(config, thinking=False, effort="off")


async def login_kimi_api_key(
    config: Config, api_key: str | None = None
) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Login requires the default config file; restart without --config/--config-file.",
        )
        return

    resolved_key = (api_key or get_kimi_api_key_from_env() or "").strip()
    if not resolved_key:
        yield OAuthEvent("error", "Kimi API key is required.")
        return

    models = KIMI_MODELS
    try:
        discovered = await _discover_kimi_models(resolved_key)
        if discovered is not None and discovered:
            models = discovered
    except aiohttp.ClientResponseError as exc:
        if exc.status in {401, 403}:
            yield OAuthEvent("error", "Invalid Kimi API key; the key was not saved.")
            return
        yield OAuthEvent(
            "info",
            "Kimi model listing is unavailable; using the built-in model list.",
        )
    except (aiohttp.ClientError, TimeoutError, ValueError):
        yield OAuthEvent(
            "info",
            "Kimi model listing is unavailable; using the built-in model list.",
        )

    _apply_kimi_config(config, SecretStr(resolved_key), models=models)
    save_config(config)
    yield OAuthEvent("success", f"Kimi configured with model {config.default_model}.")


async def logout_kimi(config: Config) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Logout requires the default config file; restart without --config/--config-file.",
        )
        return

    provider_keys = {KIMI_PROVIDER_KEY}
    config.providers.pop(KIMI_PROVIDER_KEY, None)
    for key, model in list(config.models.items()):
        if model.provider in provider_keys:
            del config.models[key]

    if config.default_model not in config.models:
        config.default_model = next(iter(config.models), "")
    save_config(config)
    yield OAuthEvent("success", "Logged out of Kimi successfully.")


def apply_kimi_models(config: Config, models: tuple[KimiModel, ...]) -> bool:
    """Upsert the live Kimi catalog and prune models no longer returned.

    Preserves user preferences unless the selected Kimi model disappeared.
    """
    changed = False
    aliases: list[str] = []
    for model in models:
        alias = model.alias
        aliases.append(alias)
        existing = config.models.get(alias)
        if existing is None:
            config.models[alias] = LLMModel(
                provider=model.provider_key,
                model=model.model_id,
                max_context_size=model.max_context_size,
                display_name=model.display_name,
            )
            changed = True
            continue
        if existing.provider != model.provider_key:
            existing.provider = model.provider_key
            changed = True
        if existing.model != model.model_id:
            existing.model = model.model_id
            changed = True
        if existing.max_context_size != model.max_context_size:
            existing.max_context_size = model.max_context_size
            changed = True
        if existing.display_name != model.display_name:
            existing.display_name = model.display_name
            changed = True

    alias_set = set(aliases)
    removed_default = False
    for alias, model_cfg in list(config.models.items()):
        if model_cfg.provider != KIMI_PROVIDER_KEY:
            continue
        if alias in alias_set:
            continue
        del config.models[alias]
        if config.default_model == alias:
            removed_default = True
        changed = True

    if removed_default:
        config.default_model = aliases[0] if aliases else next(iter(config.models), "")
        changed = True
    elif config.default_model and config.default_model not in config.models:
        config.default_model = next(iter(config.models), "")
        changed = True
    return changed


def _kimi_api_key(config: Config) -> str | None:
    provider = config.providers.get(KIMI_PROVIDER_KEY)
    if provider is None:
        return None
    value = provider.api_key.get_secret_value().strip()
    return value or None


async def refresh_kimi_models(config: Config) -> tuple[KimiModel, ...] | None:
    api_key = _kimi_api_key(config)
    if api_key is None:
        return None
    return await _discover_kimi_models(api_key)
