# pyright: reportPrivateUsage=false, reportUnusedFunction=false
"""Apply and remove the managed OpenAI provider/model configuration."""

from __future__ import annotations

from collections.abc import AsyncIterator

from pydantic import SecretStr

from pythinker_code.auth import OPENAI_API_PLATFORM_ID, OPENAI_CHATGPT_PLATFORM_ID
from pythinker_code.auth.oauth import OAuthEvent, delete_tokens
from pythinker_code.auth.openai._shared import _default_config_error
from pythinker_code.auth.openai.constants import OPENAI_CHATGPT_OAUTH_KEY
from pythinker_code.auth.platforms import ModelInfo, managed_model_key, managed_provider_key
from pythinker_code.config import Config, LLMModel, LLMProvider, OAuthRef, save_config
from pythinker_code.thinking import apply_login_thinking_defaults


def _apply_openai_config(
    config: Config,
    *,
    platform_id: str,
    provider_type: str,
    base_url: str,
    api_key: SecretStr,
    oauth_ref: OAuthRef | None,
    models: list[ModelInfo],
    selected_model: ModelInfo,
    thinking: bool,
) -> None:
    provider_key = managed_provider_key(platform_id)
    config.providers[provider_key] = LLMProvider.model_construct(
        type=provider_type,
        base_url=base_url,
        api_key=api_key,
        oauth=oauth_ref,
    )

    for model in models:
        config.models[managed_model_key(platform_id, model.id)] = LLMModel(
            provider=provider_key,
            model=model.id,
            max_context_size=model.context_length,
            capabilities=model.capabilities or None,
            display_name=model.display_name,
        )

    config.default_model = managed_model_key(platform_id, selected_model.id)
    apply_login_thinking_defaults(config, thinking=thinking, effort="high" if thinking else "off")


async def logout_openai(config: Config) -> AsyncIterator[OAuthEvent]:
    if (event := _default_config_error("Logout", config)) is not None:
        yield event
        return

    delete_tokens(OAuthRef(storage="file", key=OPENAI_CHATGPT_OAUTH_KEY))
    removed_default = False
    for platform_id in (OPENAI_API_PLATFORM_ID, OPENAI_CHATGPT_PLATFORM_ID):
        provider_key = managed_provider_key(platform_id)
        config.providers.pop(provider_key, None)
        for key, model in list(config.models.items()):
            if model.provider != provider_key:
                continue
            del config.models[key]
            if config.default_model == key:
                removed_default = True

    if removed_default or config.default_model not in config.models:
        config.default_model = next(iter(config.models), "")
    save_config(config)
    yield OAuthEvent("success", "Logged out of OpenAI successfully.")
