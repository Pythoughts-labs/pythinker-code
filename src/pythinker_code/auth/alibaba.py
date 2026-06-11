from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlparse

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
# Shared international (Team Edition) Token Plan endpoint — the default for plan keys.
ALIBABA_TOKEN_PLAN_BASE_URL = (
    "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
)
ALIBABA_PROVIDER_KEY = managed_provider_key(ALIBABA_PLATFORM_ID)
ALIBABA_DEFAULT_MODEL_ALIAS = f"{ALIBABA_PLATFORM_ID}/qwen3.7-plus"
ALIBABA_DEFAULT_CONTEXT = 131_072
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
        max_context_size=1_000_000,
        capabilities=frozenset[ModelCapability]({"always_thinking", "image_in"}),
    ),
    AlibabaModel(
        model_id="qwen3.7-plus",
        alias_suffix="qwen3.7-plus",
        display_name="Qwen3.7 Plus",
        max_context_size=1_000_000,
        capabilities=frozenset[ModelCapability]({"always_thinking", "image_in"}),
    ),
    AlibabaModel(
        model_id="qwen3.6-plus",
        alias_suffix="qwen3.6-plus",
        display_name="Qwen3.6 Plus",
        max_context_size=1_000_000,
        capabilities=frozenset[ModelCapability]({"always_thinking", "image_in"}),
    ),
    AlibabaModel(
        model_id="qwen3.6-flash",
        alias_suffix="qwen3.6-flash",
        display_name="Qwen3.6 Flash",
        max_context_size=1_000_000,
        capabilities=frozenset[ModelCapability]({"always_thinking", "image_in"}),
    ),
    AlibabaModel(
        model_id="qwen3-coder-plus",
        alias_suffix="qwen3-coder-plus",
        display_name="Qwen3 Coder Plus",
        max_context_size=1_000_000,
        capabilities=frozenset[ModelCapability]({"always_thinking"}),
    ),
    AlibabaModel(
        model_id="qwen3-coder-flash",
        alias_suffix="qwen3-coder-flash",
        display_name="Qwen3 Coder Flash",
        max_context_size=1_000_000,
        capabilities=frozenset[ModelCapability]({"always_thinking"}),
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
        model_id="glm-5.1",
        alias_suffix="glm-5.1",
        display_name="GLM-5.1",
        max_context_size=262_144,
        capabilities=frozenset[ModelCapability]({"always_thinking"}),
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


# Non-chat model ids returned by /models that can't serve as the agent LLM (image/audio/
# video generation, embeddings, rerankers, omni/realtime). Mirrors pi-alibaba-models.
_NON_CHAT_MODEL_RE = re.compile(
    r"image|audio|video|tts|asr|embed|vector|rerank|wan|omni|livetranslate|realtime",
    re.IGNORECASE,
)
_VISION_RE = re.compile(r"vl|vision", re.IGNORECASE)
_QWEN_PLUS_RE = re.compile(r"^qwen3\.\d+-plus\b", re.IGNORECASE)
_REASONING_RE = re.compile(r"qwq|max|thinking|deepseek|minimax|kimi|glm|3\.[5-9]", re.IGNORECASE)
_QWEN_BIG_CTX_RE = re.compile(r"^qwen3\.([7-9]|\d{2,})-(plus|max)\b", re.IGNORECASE)


def _is_non_chat_model(model_id: str) -> bool:
    return bool(_NON_CHAT_MODEL_RE.search(model_id))


def _infer_capabilities(model_id: str) -> frozenset[ModelCapability] | None:
    """The /models API returns only ids, so infer capabilities from the id (pi heuristics)."""
    mid = model_id.lower()
    caps: set[ModelCapability] = set()
    if _VISION_RE.search(mid) or _QWEN_PLUS_RE.search(mid) or "kimi" in mid:
        caps.add("image_in")
    if _REASONING_RE.search(mid):
        # DeepSeek/Moonshot expose a thinking dial; Qwen/GLM/MiniMax reason natively.
        caps.add("thinking" if ("deepseek" in mid or "kimi" in mid) else "always_thinking")
    return frozenset(caps) or None


def _infer_context_window(model_id: str) -> int:
    mid = model_id.lower()
    if "flash" in mid:
        return 131_072
    if "kimi" in mid:
        return 262_144
    if mid.startswith("qwen3.6-max"):
        return 262_144
    if mid.startswith("qwen3.6-plus") or _QWEN_BIG_CTX_RE.search(mid):
        return 1_048_576
    return ALIBABA_DEFAULT_CONTEXT


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
        if not isinstance(model_id, str) or not model_id:
            continue
        if _is_non_chat_model(model_id):
            continue
        # Accept every chat model the endpoint returns; enrich known ones from the
        # built-in catalog and infer capabilities/context from the id for the rest.
        base = catalog.get(model_id)
        ctx = item.get("context_length")
        if isinstance(ctx, int) and ctx > 0:
            max_ctx = ctx
        elif base is not None:
            max_ctx = base.max_context_size
        else:
            max_ctx = _infer_context_window(model_id)
        display_name_raw = item.get("display_name")
        if isinstance(display_name_raw, str) and display_name_raw:
            display_name = display_name_raw
        elif base is not None:
            display_name = base.display_name
        else:
            display_name = model_id
        capabilities = base.capabilities if base is not None else _infer_capabilities(model_id)
        results.append(
            AlibabaModel(
                model_id=model_id,
                alias_suffix=base.alias_suffix if base is not None else model_id,
                display_name=display_name,
                max_context_size=max_ctx,
                capabilities=capabilities,
            )
        )
    return tuple(results)


def _is_workspace_endpoint(base_url: str) -> bool:
    hostname = urlparse(base_url).hostname or ""
    return hostname.startswith("ws-") and hostname.endswith(".maas.aliyuncs.com")


async def _discover_alibaba_models(api_key: str, base_url: str) -> tuple[AlibabaModel, ...]:
    async with (
        new_client_session(timeout=ALIBABA_MODEL_DISCOVERY_TIMEOUT) as session,
        session.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            raise_for_status=True,
        ) as response,
    ):
        payload = await response.json(content_type=None)
    return _parse_discovered_models(payload)


async def login_alibaba_api_key(
    config: Config, api_key: str | None = None, base_url: str | None = None
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

    # Subscription "plan" keys (Coding Plan / Token Plan) all authenticate against the
    # shared Token Plan endpoint — sk-sp-, sk-tok-, and sk-ws- route there. Generic sk-
    # keys are pay-as-you-go Cloud (DashScope) keys routed to the regional endpoint.
    is_token_plan = resolved_key.startswith(("sk-sp-", "sk-tok-", "sk-ws-"))

    # Default plan keys to the shared international Token Plan endpoint; a dedicated
    # workspace URL can still be supplied via base_url / DASHSCOPE_BASE_URL.
    default_url = ALIBABA_TOKEN_PLAN_BASE_URL if is_token_plan else ALIBABA_BASE_URL
    env_base_url = os.getenv("DASHSCOPE_BASE_URL") or os.getenv("ALIBABA_BASE_URL")

    if base_url and base_url.strip():
        primary_url = _normalize_alibaba_base_url(base_url)
    elif env_base_url:
        primary_url = _normalize_alibaba_base_url(env_base_url)
    else:
        primary_url = default_url

    active_url = primary_url
    models = ALIBABA_MODELS

    try:
        discovered = await _discover_alibaba_models(resolved_key, primary_url)
        if discovered:
            models = discovered
    except aiohttp.ClientResponseError as exc:
        if exc.status in {401, 403}:
            if is_token_plan:
                yield OAuthEvent(
                    "error",
                    "Alibaba Token Plan API key was not accepted. Ensure the key is active "
                    "and assigned to a Token Plan seat. Set DASHSCOPE_BASE_URL only when "
                    "Alibaba provides a different endpoint for your plan.",
                )
                return
            # Pay-as-you-go Cloud key: when we used the default US endpoint, probe the
            # China endpoint to auto-detect a China-region key before giving up.
            if primary_url == ALIBABA_BASE_URL:
                try:
                    discovered = await _discover_alibaba_models(
                        resolved_key, ALIBABA_CHINA_BASE_URL
                    )
                    active_url = ALIBABA_CHINA_BASE_URL
                    if discovered:
                        models = discovered
                    yield OAuthEvent(
                        "info",
                        "Detected China-region DashScope key; "
                        "configured for China (Beijing) endpoint.",
                    )
                except aiohttp.ClientResponseError as china_exc:
                    if china_exc.status in {401, 403}:
                        yield OAuthEvent(
                            "error",
                            "Alibaba API key was not accepted. Ensure your key is valid and "
                            "comes from the Alibaba Cloud Model Studio console "
                            "(https://bailian.console.aliyun.com). "
                            "Set DASHSCOPE_BASE_URL to override the endpoint if needed.",
                        )
                        return
                    yield OAuthEvent(
                        "error",
                        "The default US endpoint rejected the key and the China endpoint "
                        "could not be reached. Check network access or set "
                        "DASHSCOPE_BASE_URL to the correct endpoint and try again.",
                    )
                    return
                except (aiohttp.ClientError, TimeoutError, ValueError):
                    yield OAuthEvent(
                        "error",
                        "The default US endpoint rejected the key and the China endpoint "
                        "could not be reached. Check network access or set "
                        "DASHSCOPE_BASE_URL to the correct endpoint and try again.",
                    )
                    return
            else:
                yield OAuthEvent(
                    "error",
                    "Alibaba API key was not accepted. Ensure your key is valid and "
                    "that DASHSCOPE_BASE_URL points to the correct endpoint.",
                )
                return
        else:
            yield OAuthEvent(
                "info",
                "Alibaba model listing is unavailable; using the built-in model list.",
            )
    except (aiohttp.ClientError, TimeoutError, ValueError):
        yield OAuthEvent(
            "info",
            "Alibaba model listing is unavailable; using the built-in model list.",
        )

    if _is_workspace_endpoint(active_url):
        models = tuple(model for model in models if model.model_id != "kimi-k2.6")

    _apply_alibaba_config(config, SecretStr(resolved_key), models=models, base_url=active_url)
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
