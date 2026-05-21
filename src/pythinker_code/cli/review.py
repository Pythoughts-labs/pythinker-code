"""`pythinker review` — delegates to pythinker-review with active-model wiring."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast

from pydantic import SecretStr
from pythinker_review.cli import review as upstream_review
from pythinker_review.llm.protocol import ReviewLLM

cli = upstream_review.app


@dataclass(slots=True)
class PythinkerActiveLLM:
    """Bridge pythinker-core's configured provider to the ReviewLLM protocol."""

    chat_provider: Any
    model_display_name: str

    async def complete_json(self, *, system: str, user: str, timeout_s: float) -> str:
        from pythinker_core import generate
        from pythinker_core.message import Message
        from pythinker_core.tooling.empty import EmptyToolset

        result = await asyncio.wait_for(
            generate(
                self.chat_provider,
                system,
                EmptyToolset().tools,
                [Message(role="user", content=user)],
            ),
            timeout=timeout_s,
        )
        return result.message.extract_text()


def build_active_llm(*, model_name: str | None = None) -> ReviewLLM | None:
    """Build a ReviewLLM from the current Pythinker config, returning None when unset."""
    from pythinker_code.auth.oauth import OAuthManager
    from pythinker_code.config import LLMModel, LLMProvider, load_config
    from pythinker_code.llm import augment_provider_with_env_vars, create_llm, model_display_name

    config = load_config()
    selected = model_name or config.default_model
    if selected and selected in config.models:
        model = config.models[selected].model_copy(deep=True)
        provider = config.providers[model.provider].model_copy(deep=True)
    else:
        model = LLMModel(provider="", model="", max_context_size=100_000)
        provider = LLMProvider(type="pythinker", base_url="", api_key=SecretStr(""))
    augment_provider_with_env_vars(provider, model, provider_key=model.provider)
    llm = create_llm(
        provider,
        model,
        thinking=config.default_thinking,
        session_id=None,
        oauth=OAuthManager(config),
    )
    if llm is None:
        return None
    display = model_display_name(model.model, model)
    return PythinkerActiveLLM(
        chat_provider=cast(Any, llm.chat_provider), model_display_name=display
    )


def _resolve_llm_with_active_model() -> ReviewLLM | None:
    return build_active_llm()


upstream_review.set_llm_resolver(_resolve_llm_with_active_model)
