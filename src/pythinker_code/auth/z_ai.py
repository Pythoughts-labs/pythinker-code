from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, cast

import aiohttp
from pydantic import SecretStr

from pythinker_code.auth import ZAI_PLATFORM_ID
from pythinker_code.auth.oauth import OAuthEvent
from pythinker_code.auth.platforms import managed_model_key, managed_provider_key
from pythinker_code.config import Config, LLMModel, LLMProvider, save_config
from pythinker_code.thinking import apply_login_thinking_defaults
from pythinker_code.utils.aiohttp import new_client_session

ZAI_BASE_URL = "https://api.z.ai/api/anthropic"
ZAI_MODELS_URL = "https://api.z.ai/api/anthropic/v1/models"
ZAI_PROVIDER_KEY = managed_provider_key(ZAI_PLATFORM_ID)
ZAI_DEFAULT_MODEL_ALIAS = managed_model_key(ZAI_PLATFORM_ID, "glm-5.1")
ZAI_MODEL_DISCOVERY_TIMEOUT = aiohttp.ClientTimeout(total=15, sock_connect=8, sock_read=10)


@dataclass(frozen=True, slots=True)
class ZaiModel:
    model_id: str
    alias_suffix: str
    display_name: str
    provider_key: str = ZAI_PROVIDER_KEY
    max_context_size: int = 131_072

    @property
    def alias(self) -> str:
        return f"{ZAI_PLATFORM_ID}/{self.alias_suffix}"


ZAI_MODELS: tuple[ZaiModel, ...] = (
    ZaiModel("glm-5.1", "glm-5.1", "GLM-5.1", max_context_size=204_800),
    ZaiModel("glm-5", "glm-5", "GLM-5"),
    ZaiModel("glm-5-turbo", "glm-5-turbo", "GLM-5-Turbo"),
    ZaiModel("glm-4.7", "glm-4.7", "GLM-4.7"),
    ZaiModel("glm-4.5-air", "glm-4.5-air", "GLM-4.5-Air", max_context_size=98_304),
)


def get_z_ai_api_key_from_env() -> str | None:
    value = os.getenv("ZAI_API_KEY")
    if value and value.strip():
        return value.strip()
    return None


def _is_supported_z_ai_model(model_id: str) -> bool:
    return model_id.lower().startswith("glm-")


def _model_by_id() -> dict[str, ZaiModel]:
    return {model.model_id: model for model in ZAI_MODELS}


def _derive_alias_suffix(model_id: str) -> str:
    return model_id.lower().strip()


def _derive_display_name(model_id: str) -> str:
    parts = model_id.split("-")
    return "-".join(p.upper() if p.lower() == "glm" else p.capitalize() for p in parts)


def _to_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _context_size_from_item(item: Mapping[str, Any], fallback: int) -> int:
    for key in ("context_length", "max_context_length", "context_window"):
        parsed = _to_positive_int(item.get(key))
        if parsed is not None:
            return parsed
    return fallback


def _display_name_from_item(item: Mapping[str, Any], fallback: str) -> str:
    for key in ("display_name", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _parse_discovered_models(data: object) -> tuple[ZaiModel, ...] | None:
    """Return parsed models, or None if the payload is structurally invalid."""
    if not isinstance(data, dict):
        return None
    raw_items = cast(dict[str, Any], data).get("data")
    if not isinstance(raw_items, list):
        return None

    known = _model_by_id()
    seen: set[str] = set()
    result: list[ZaiModel] = []
    for raw_item in cast(list[Any], raw_items):
        if not isinstance(raw_item, Mapping):
            continue
        item = cast(Mapping[str, Any], raw_item)
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        model_id = model_id.strip()
        if model_id in seen or not _is_supported_z_ai_model(model_id):
            continue
        seen.add(model_id)

        current = known.get(model_id)
        alias_suffix = current.alias_suffix if current else _derive_alias_suffix(model_id)
        display_name = _display_name_from_item(
            item,
            current.display_name if current else _derive_display_name(model_id),
        )
        max_context_size = _context_size_from_item(
            item,
            current.max_context_size if current else 131_072,
        )
        result.append(
            ZaiModel(
                model_id=model_id,
                alias_suffix=alias_suffix,
                display_name=display_name,
                provider_key=current.provider_key if current else ZAI_PROVIDER_KEY,
                max_context_size=max_context_size,
            )
        )
    return tuple(result)


async def _discover_z_ai_models(api_key: str) -> tuple[ZaiModel, ...] | None:
    async with (
        new_client_session(timeout=ZAI_MODEL_DISCOVERY_TIMEOUT) as session,
        session.get(
            ZAI_MODELS_URL,
            headers={"x-api-key": api_key},
            raise_for_status=True,
        ) as response,
    ):
        payload = await response.json(content_type=None)
    return _parse_discovered_models(payload)


def _apply_z_ai_config(
    config: Config,
    api_key: SecretStr,
    models: tuple[ZaiModel, ...] = ZAI_MODELS,
) -> None:
    config.providers[ZAI_PROVIDER_KEY] = LLMProvider(
        type="anthropic",
        base_url=ZAI_BASE_URL,
        api_key=api_key,
    )

    provider_keys = {ZAI_PROVIDER_KEY}
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
    if ZAI_DEFAULT_MODEL_ALIAS in config.models:
        config.default_model = ZAI_DEFAULT_MODEL_ALIAS
    else:
        config.default_model = fallback
    apply_login_thinking_defaults(config, thinking=False, effort="off")


async def login_z_ai_api_key(
    config: Config, api_key: str | None = None
) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Login requires the default config file; restart without --config/--config-file.",
        )
        return

    resolved_key = (api_key or get_z_ai_api_key_from_env() or "").strip()
    if not resolved_key:
        yield OAuthEvent("error", "Z AI API key is required.")
        return

    models = ZAI_MODELS
    try:
        discovered = await _discover_z_ai_models(resolved_key)
        if discovered is not None and discovered:
            models = discovered
    except aiohttp.ClientResponseError as exc:
        if exc.status in {401, 403}:
            yield OAuthEvent("error", "Invalid Z AI API key; the key was not saved.")
            return
        yield OAuthEvent(
            "info",
            "Z AI model listing is unavailable; using the built-in model list.",
        )
    except (aiohttp.ClientError, TimeoutError, ValueError):
        yield OAuthEvent(
            "info",
            "Z AI model listing is unavailable; using the built-in model list.",
        )

    _apply_z_ai_config(config, SecretStr(resolved_key), models=models)
    save_config(config)
    yield OAuthEvent("success", f"Z AI configured with model {config.default_model}.")


async def logout_z_ai(config: Config) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Logout requires the default config file; restart without --config/--config-file.",
        )
        return

    provider_keys = {ZAI_PROVIDER_KEY}
    config.providers.pop(ZAI_PROVIDER_KEY, None)
    for key, model in list(config.models.items()):
        if model.provider in provider_keys:
            del config.models[key]

    if config.default_model not in config.models:
        config.default_model = next(iter(config.models), "")
    save_config(config)
    yield OAuthEvent("success", "Logged out of Z AI successfully.")


def apply_z_ai_models(config: Config, models: tuple[ZaiModel, ...]) -> bool:
    """Upsert the live Z AI catalog and prune models no longer returned.

    Preserves user preferences unless the selected Z AI model disappeared.
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
        if model_cfg.provider != ZAI_PROVIDER_KEY:
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


def _z_ai_api_key(config: Config) -> str | None:
    provider = config.providers.get(ZAI_PROVIDER_KEY)
    if provider is None:
        return None
    value = provider.api_key.get_secret_value().strip()
    return value or None


async def refresh_z_ai_models(config: Config) -> tuple[ZaiModel, ...] | None:
    api_key = _z_ai_api_key(config)
    if api_key is None:
        return None
    return await _discover_z_ai_models(api_key)
