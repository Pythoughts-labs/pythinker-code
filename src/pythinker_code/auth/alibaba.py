from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

import aiohttp
from pydantic import SecretStr

from pythinker_code.auth import ALIBABA_PLATFORM_ID
from pythinker_code.auth.oauth import OAuthEvent
from pythinker_code.auth.platforms import managed_provider_key
from pythinker_code.config import Config, LLMModel, LLMProvider, save_config
from pythinker_code.llm import ModelCapability
from pythinker_code.thinking import apply_login_thinking_defaults
from pythinker_code.utils.aiohttp import new_client_session

ALIBABA_BASE_URL = "https://dashscope-us.aliyuncs.com/compatible-mode/v1"
ALIBABA_CHINA_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
ALIBABA_PROVIDER_KEY = managed_provider_key(ALIBABA_PLATFORM_ID)
ALIBABA_DEFAULT_MODEL_ALIAS = f"{ALIBABA_PLATFORM_ID}/qwen3.6-plus"
ALIBABA_MODEL_DISCOVERY_TIMEOUT = aiohttp.ClientTimeout(total=15, sock_connect=8, sock_read=10)


@dataclass(frozen=True, slots=True)
class AlibabaModel:
    model_id: str
    alias_suffix: str
    display_name: str
    provider_key: str = ALIBABA_PROVIDER_KEY
    max_context_size: int = 131_072
    capabilities: frozenset[ModelCapability] | None = None

    @property
    def alias(self) -> str:
        return f"{ALIBABA_PLATFORM_ID}/{self.alias_suffix}"


ALIBABA_MODELS: tuple[AlibabaModel, ...] = (
    AlibabaModel(
        model_id="qwen3.7-max",
        alias_suffix="qwen3.7-max",
        display_name="Qwen3.7 Max",
        max_context_size=262_144,
        capabilities=frozenset[ModelCapability]({"thinking"}),
    ),
    AlibabaModel(
        model_id="qwen3.6-plus",
        alias_suffix="qwen3.6-plus",
        display_name="Qwen3.6 Plus",
        max_context_size=1_000_000,
        capabilities=frozenset[ModelCapability]({"thinking", "image_in"}),
    ),
    AlibabaModel(
        model_id="qwen3.6-flash",
        alias_suffix="qwen3.6-flash",
        display_name="Qwen3.6 Flash",
        max_context_size=1_000_000,
        capabilities=frozenset[ModelCapability]({"thinking", "image_in"}),
    ),
    AlibabaModel(
        model_id="deepseek-v4-pro",
        alias_suffix="deepseek-v4-pro",
        display_name="DeepSeek V4 Pro",
        max_context_size=128_000,
        capabilities=frozenset[ModelCapability]({"thinking"}),
    ),
    AlibabaModel(
        model_id="deepseek-v4-flash",
        alias_suffix="deepseek-v4-flash",
        display_name="DeepSeek V4 Flash",
        max_context_size=128_000,
        capabilities=frozenset[ModelCapability]({"thinking"}),
    ),
    AlibabaModel(
        model_id="deepseek-v3.2",
        alias_suffix="deepseek-v3.2",
        display_name="DeepSeek V3.2",
        max_context_size=128_000,
        capabilities=frozenset[ModelCapability]({"thinking"}),
    ),
    AlibabaModel(
        model_id="kimi-k2.6",
        alias_suffix="kimi-k2.6",
        display_name="Kimi K2.6",
        max_context_size=262_144,
        capabilities=frozenset[ModelCapability]({"thinking", "image_in"}),
    ),
    AlibabaModel(
        model_id="kimi-k2.5",
        alias_suffix="kimi-k2.5",
        display_name="Kimi K2.5",
        max_context_size=262_144,
        capabilities=frozenset[ModelCapability]({"thinking", "image_in"}),
    ),
    AlibabaModel(
        model_id="glm-5.1",
        alias_suffix="glm-5.1",
        display_name="GLM-5.1",
        max_context_size=262_144,
        capabilities=frozenset[ModelCapability]({"always_thinking"}),
    ),
    AlibabaModel(
        model_id="glm-5",
        alias_suffix="glm-5",
        display_name="GLM-5",
        max_context_size=262_144,
        capabilities=frozenset[ModelCapability]({"always_thinking"}),
    ),
    AlibabaModel(
        model_id="MiniMax-M2.5",
        alias_suffix="minimax-m2.5",
        display_name="MiniMax M2.5",
        max_context_size=204_800,
        capabilities=frozenset[ModelCapability]({"thinking"}),
    ),
)


def get_alibaba_api_key_from_env() -> str | None:
    for env_var in ("DASHSCOPE_API_KEY", "ALIBABA_API_KEY"):
        value = os.getenv(env_var)
        if value and value.strip():
            return value.strip()
    return None


def _normalize_alibaba_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    if not base_url:
        return ALIBABA_BASE_URL
    if "://" not in base_url:
        base_url = f"https://{base_url}"
    if base_url.endswith("/api/v1"):
        return f"{base_url.removesuffix('/api/v1')}/compatible-mode/v1"
    if base_url.endswith("/compatible-mode/v1"):
        return base_url
    return f"{base_url}/compatible-mode/v1"


def get_alibaba_base_url_from_env() -> str:
    for env_var in ("DASHSCOPE_BASE_URL", "ALIBABA_BASE_URL"):
        value = os.getenv(env_var)
        if value and value.strip():
            return _normalize_alibaba_base_url(value)
    return ALIBABA_BASE_URL


def _apply_alibaba_config(
    config: Config,
    api_key: SecretStr,
    models: tuple[AlibabaModel, ...] = ALIBABA_MODELS,
    base_url: str | None = None,
) -> None:
    config.providers[ALIBABA_PROVIDER_KEY] = LLMProvider(
        type="openai_legacy",
        base_url=base_url if base_url is not None else get_alibaba_base_url_from_env(),
        api_key=api_key,
    )

    provider_keys = {ALIBABA_PROVIDER_KEY}
    for key, model in list(config.models.items()):
        if model.provider in provider_keys:
            del config.models[key]

    for model in models:
        config.models[model.alias] = LLMModel(
            provider=model.provider_key,
            model=model.model_id,
            max_context_size=model.max_context_size,
            capabilities=set(model.capabilities) if model.capabilities else None,
            display_name=model.display_name,
        )

    fallback = next(
        (m.alias for m in models),
        next(iter(config.models), ""),
    )
    if ALIBABA_DEFAULT_MODEL_ALIAS in config.models:
        config.default_model = ALIBABA_DEFAULT_MODEL_ALIAS
    else:
        config.default_model = fallback
    apply_login_thinking_defaults(config, thinking=True, effort="high")


def _model_by_id() -> dict[str, AlibabaModel]:
    return {model.model_id: model for model in ALIBABA_MODELS}


def _parse_discovered_models(data: object) -> tuple[AlibabaModel, ...]:
    if not isinstance(data, dict):
        return ()
    d = cast(dict[str, Any], data)
    items = d.get("data")
    if not isinstance(items, list):
        return ()
    catalog = _model_by_id()
    results: list[AlibabaModel] = []
    for raw_item in cast(list[object], items):
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
        display_name_raw = item.get("display_name")
        display_name = (
            display_name_raw
            if isinstance(display_name_raw, str) and display_name_raw
            else base.display_name
        )
        results.append(
            AlibabaModel(
                model_id=base.model_id,
                alias_suffix=base.alias_suffix,
                display_name=display_name,
                provider_key=base.provider_key,
                max_context_size=max_ctx,
                capabilities=base.capabilities,
            )
        )
    return tuple(results)


async def _discover_alibaba_models(api_key: str) -> tuple[AlibabaModel, ...]:
    async with (
        new_client_session(timeout=ALIBABA_MODEL_DISCOVERY_TIMEOUT) as session,
        session.get(
            f"{get_alibaba_base_url_from_env()}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            raise_for_status=True,
        ) as response,
    ):
        payload = await response.json(content_type=None)
    return _parse_discovered_models(payload)


async def login_alibaba_api_key(
    config: Config, api_key: str | None = None
) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Login requires the default config file; restart without --config/--config-file.",
        )
        return

    resolved_key = (api_key or get_alibaba_api_key_from_env() or "").strip()
    if not resolved_key:
        yield OAuthEvent("error", "Alibaba API key is required.")
        return

    models = ALIBABA_MODELS
    try:
        discovered = await _discover_alibaba_models(resolved_key)
        if discovered:
            models = discovered
    except aiohttp.ClientResponseError as exc:
        if exc.status in {401, 403}:
            yield OAuthEvent("error", "Invalid Alibaba API key; the key was not saved.")
            return
        yield OAuthEvent(
            "info",
            "Alibaba model listing is unavailable; using the built-in model list.",
        )
    except (aiohttp.ClientError, TimeoutError, ValueError):
        yield OAuthEvent(
            "info",
            "Alibaba model listing is unavailable; using the built-in model list.",
        )

    _apply_alibaba_config(config, SecretStr(resolved_key), models=models)
    save_config(config)
    yield OAuthEvent("success", f"Alibaba configured with model {config.default_model}.")


async def logout_alibaba(config: Config) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Logout requires the default config file; restart without --config/--config-file.",
        )
        return

    provider_keys = {ALIBABA_PROVIDER_KEY}
    config.providers.pop(ALIBABA_PROVIDER_KEY, None)
    for key, model in list(config.models.items()):
        if model.provider in provider_keys:
            del config.models[key]

    if config.default_model not in config.models:
        config.default_model = next(iter(config.models), "")
    save_config(config)
    yield OAuthEvent("success", "Logged out of Alibaba successfully.")
