from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Mapping, cast

import aiohttp
from pydantic import SecretStr

from pythinker_code.auth import ZAI_PLATFORM_ID
from pythinker_code.auth.oauth import OAuthEvent
from pythinker_code.config import Config, LLMModel, LLMProvider, save_config
from pythinker_code.thinking import apply_login_thinking_defaults
from pythinker_code.utils.aiohttp import new_client_session

ZAI_BASE_URL = "https://api.z.ai/api/anthropic"
ZAI_MODELS_URL = "https://api.z.ai/api/anthropic/v1/models"
ZAI_PROVIDER_KEY = "managed:z-ai"
ZAI_DEFAULT_MODEL_ALIAS = "z-ai/glm-5.1"
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
