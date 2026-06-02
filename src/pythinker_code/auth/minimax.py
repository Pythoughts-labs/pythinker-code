from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, cast

import aiohttp
from pydantic import SecretStr

from pythinker_code.auth import MINIMAX_PLATFORM_ID
from pythinker_code.auth.oauth import OAuthEvent
from pythinker_code.config import Config, LLMModel, LLMProvider, save_config
from pythinker_code.llm import ModelCapability
from pythinker_code.thinking import apply_login_thinking_defaults
from pythinker_code.utils.aiohttp import new_client_session

MINIMAX_ANTHROPIC_BASE_URL = "https://api.minimax.io/anthropic"
MINIMAX_OPENAI_BASE_URL = "https://api.minimax.io/v1"
MINIMAX_ANTHROPIC_MODELS_URL = f"{MINIMAX_ANTHROPIC_BASE_URL}/v1/models"
MINIMAX_OPENAI_MODELS_URL = f"{MINIMAX_OPENAI_BASE_URL}/models"
MINIMAX_ANTHROPIC_PROVIDER_KEY = "managed:minimax-anthropic"
MINIMAX_DEFAULT_MODEL_ALIAS = "minimax/m2.7"
MINIMAX_DEFAULT_CONTEXT = 192_000
MINIMAX_TOKEN_PLAN_KEY_PREFIX = "sk-cp-"
MINIMAX_MODEL_DISCOVERY_TIMEOUT = aiohttp.ClientTimeout(total=15, sock_connect=8, sock_read=10)
MINIMAX_NATIVE_THINKING_CAPABILITIES: frozenset[ModelCapability] = frozenset({"always_thinking"})


@dataclass(frozen=True, slots=True)
class MiniMaxModel:
    model_id: str
    alias_suffix: str
    display_name: str
    provider_key: str = MINIMAX_ANTHROPIC_PROVIDER_KEY
    max_context_size: int = MINIMAX_DEFAULT_CONTEXT
    capabilities: frozenset[ModelCapability] = MINIMAX_NATIVE_THINKING_CAPABILITIES

    @property
    def alias(self) -> str:
        return f"{MINIMAX_PLATFORM_ID}/{self.alias_suffix}"


MINIMAX_MODELS: tuple[MiniMaxModel, ...] = (
    MiniMaxModel("MiniMax-M2.7", "m2.7", "MiniMax M2.7"),
    MiniMaxModel("MiniMax-M2.7-highspeed", "m2.7-highspeed", "MiniMax M2.7 High-Speed"),
    MiniMaxModel("MiniMax-M2.5", "m2.5", "MiniMax M2.5"),
    MiniMaxModel("MiniMax-M2.5-highspeed", "m2.5-highspeed", "MiniMax M2.5 High-Speed"),
)


def get_minimax_api_key_from_env() -> str | None:
    value = os.getenv("MINIMAX_API_KEY")
    if value and value.strip():
        return value.strip()
    return None


def _apply_minimax_config(
    config: Config,
    api_key: SecretStr,
    models: tuple[MiniMaxModel, ...] = MINIMAX_MODELS,
) -> None:
    config.providers[MINIMAX_ANTHROPIC_PROVIDER_KEY] = LLMProvider(
        type="anthropic",
        base_url=MINIMAX_ANTHROPIC_BASE_URL,
        api_key=api_key,
    )

    provider_keys = {MINIMAX_ANTHROPIC_PROVIDER_KEY}
    for key, model in list(config.models.items()):
        if model.provider in provider_keys:
            del config.models[key]

    for model in models:
        config.models[model.alias] = LLMModel(
            provider=model.provider_key,
            model=model.model_id,
            max_context_size=model.max_context_size,
            capabilities=set(model.capabilities) or None,
            display_name=model.display_name,
        )

    if models:
        fallback = next(
            (m.alias for m in models),
            next(iter(config.models), ""),
        )
        if MINIMAX_DEFAULT_MODEL_ALIAS in config.models:
            config.default_model = MINIMAX_DEFAULT_MODEL_ALIAS
        else:
            config.default_model = fallback
    elif config.default_model not in config.models:
        config.default_model = next(iter(config.models), "")
    apply_login_thinking_defaults(config, thinking=False, effort="off")


def _model_by_id() -> dict[str, MiniMaxModel]:
    return {model.model_id: model for model in MINIMAX_MODELS}


def _is_supported_minimax_chat_model(model_id: str) -> bool:
    """Return whether a discovered model ID belongs on the chat provider.

    MiniMax's documented `/models` responses are account/key-specific and may
    change as plans gain or lose access. Keep that list authoritative while
    avoiding non-text modality models that would be invalid for the Anthropic
    messages provider configured below.
    """
    return model_id.startswith("MiniMax-M")


def _derive_alias_suffix(model_id: str) -> str:
    if model_id.startswith("MiniMax-"):
        model_id = model_id.removeprefix("MiniMax-")
    return model_id.strip().lower().replace(" ", "-")


def _derive_display_name(model_id: str) -> str:
    if model_id.startswith("MiniMax-"):
        model_id = model_id.replace("MiniMax-", "MiniMax ", 1)
    return model_id.replace("-", " ")


def _to_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _context_size_from_item(item: Mapping[str, Any], fallback: int) -> int:
    for key in ("context_length", "max_context_length", "max_tokens"):
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


def _parse_discovered_models(data: object) -> tuple[MiniMaxModel, ...]:
    if not isinstance(data, dict):
        return ()
    raw_items = cast(dict[str, Any], data).get("data")
    if not isinstance(raw_items, list):
        return ()

    known = _model_by_id()
    seen: set[str] = set()
    result: list[MiniMaxModel] = []
    for raw_item in cast(list[Any], raw_items):
        if not isinstance(raw_item, Mapping):
            continue
        item = cast(Mapping[str, Any], raw_item)
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        model_id = model_id.strip()
        if model_id in seen or not _is_supported_minimax_chat_model(model_id):
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
            current.max_context_size if current else MINIMAX_DEFAULT_CONTEXT,
        )
        result.append(
            MiniMaxModel(
                model_id=model_id,
                alias_suffix=alias_suffix,
                display_name=display_name,
                provider_key=current.provider_key if current else MINIMAX_ANTHROPIC_PROVIDER_KEY,
                max_context_size=max_context_size,
                capabilities=(
                    current.capabilities if current else MINIMAX_NATIVE_THINKING_CAPABILITIES
                ),
            )
        )
    return tuple(result)


async def _fetch_minimax_models(
    session: aiohttp.ClientSession,
    *,
    url: str,
    headers: Mapping[str, str],
) -> tuple[MiniMaxModel, ...]:
    async with session.get(url, headers=headers, raise_for_status=True) as response:
        payload = await response.json(content_type=None)
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected MiniMax models response for {url}")
    payload_map = cast(dict[str, Any], payload)
    if not isinstance(payload_map.get("data"), list):
        raise ValueError(f"Unexpected MiniMax models response for {url}")
    return _parse_discovered_models(payload_map)


async def _discover_minimax_models(api_key: str) -> tuple[MiniMaxModel, ...]:
    errors: list[Exception] = []
    auth_errors: list[aiohttp.ClientResponseError] = []
    async with new_client_session(timeout=MINIMAX_MODEL_DISCOVERY_TIMEOUT) as session:
        # Prefer the Anthropic-compatible model list because configured chat
        # traffic uses that provider shape. Fall back to the OpenAI-compatible
        # list, which MiniMax also documents and historically exposed first.
        for url, headers in (
            (MINIMAX_ANTHROPIC_MODELS_URL, {"X-Api-Key": api_key}),
            (MINIMAX_OPENAI_MODELS_URL, {"Authorization": f"Bearer {api_key}"}),
        ):
            try:
                models = await _fetch_minimax_models(session, url=url, headers=headers)
            except aiohttp.ClientResponseError as exc:
                if exc.status in {401, 403}:
                    auth_errors.append(exc)
                else:
                    errors.append(exc)
                continue
            except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                errors.append(exc)
                continue
            return models

    if auth_errors:
        raise auth_errors[0]
    if errors:
        raise errors[-1]
    return ()


def _minimax_api_key(config: Config) -> str | None:
    provider = config.providers.get(MINIMAX_ANTHROPIC_PROVIDER_KEY)
    if provider is None:
        return None
    value = provider.api_key.get_secret_value().strip()
    return value or None


def apply_minimax_models(config: Config, models: tuple[MiniMaxModel, ...]) -> bool:
    """Upsert the live MiniMax catalog and prune models no longer returned.

    Preserves user preferences unless the selected MiniMax model disappeared.
    The authenticated `/models` response is the authority for which models are
    available to the saved key, including Token Plan subscription keys.
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
                capabilities=set(model.capabilities) or None,
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
        capabilities = set(model.capabilities) or None
        if existing.capabilities != capabilities:
            existing.capabilities = capabilities
            changed = True
        if existing.display_name != model.display_name:
            existing.display_name = model.display_name
            changed = True

    alias_set = set(aliases)
    removed_default = False
    for alias, model_cfg in list(config.models.items()):
        if model_cfg.provider != MINIMAX_ANTHROPIC_PROVIDER_KEY:
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


async def refresh_minimax_models(config: Config) -> tuple[MiniMaxModel, ...] | None:
    api_key = _minimax_api_key(config)
    if api_key is None:
        return None
    return await _discover_minimax_models(api_key)


async def login_minimax_api_key(
    config: Config, api_key: str | None = None
) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Login requires the default config file; restart without --config/--config-file.",
        )
        return

    resolved_key = (api_key or get_minimax_api_key_from_env() or "").strip()
    if not resolved_key:
        yield OAuthEvent("error", "MiniMax API key is required.")
        return

    if resolved_key.startswith(MINIMAX_TOKEN_PLAN_KEY_PREFIX):
        yield OAuthEvent(
            "info",
            "MiniMax Token Plan key detected; requests are quota-metered "
            "(5-hour rolling window for text), not per-token billed.",
        )

    models = MINIMAX_MODELS
    try:
        models = await _discover_minimax_models(resolved_key)
    except aiohttp.ClientResponseError as exc:
        if exc.status in {401, 403}:
            yield OAuthEvent("error", "Invalid MiniMax API key; the key was not saved.")
            return
        yield OAuthEvent(
            "info",
            "MiniMax model listing is unavailable; using the built-in model list.",
        )
    except (aiohttp.ClientError, TimeoutError, ValueError):
        yield OAuthEvent(
            "info",
            "MiniMax model listing is unavailable; using the built-in model list.",
        )

    _apply_minimax_config(config, SecretStr(resolved_key), models=models)
    save_config(config)
    yield OAuthEvent("success", f"MiniMax configured with model {config.default_model}.")


async def logout_minimax(config: Config) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Logout requires the default config file; restart without --config/--config-file.",
        )
        return

    provider_keys = {MINIMAX_ANTHROPIC_PROVIDER_KEY}
    config.providers.pop(MINIMAX_ANTHROPIC_PROVIDER_KEY, None)
    for key, model in list(config.models.items()):
        if model.provider in provider_keys:
            del config.models[key]

    if config.default_model not in config.models:
        config.default_model = next(iter(config.models), "")
    save_config(config)
    yield OAuthEvent("success", "Logged out of MiniMax successfully.")
