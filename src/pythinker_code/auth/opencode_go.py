from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

import aiohttp
from pydantic import SecretStr

from pythinker_code.auth import OPENCODE_GO_PLATFORM_ID
from pythinker_code.auth.oauth import OAuthEvent
from pythinker_code.config import Config, LLMModel, LLMProvider, save_config
from pythinker_code.utils.aiohttp import new_client_session

# OpenAI-compatible base: the OpenAI SDK appends "/chat/completions" (and the
# "/models" discovery path), so it includes the "/v1" segment.
OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1"
# Anthropic-compatible base: the Anthropic SDK appends "/v1/messages" itself, so
# this base must NOT include "/v1" or requests 404 at ".../go/v1/v1/messages".
OPENCODE_GO_ANTHROPIC_BASE_URL = "https://opencode.ai/zen/go"
OPENCODE_GO_OPENAI_PROVIDER_KEY = "managed:opencode-go-openai"
OPENCODE_GO_ANTHROPIC_PROVIDER_KEY = "managed:opencode-go-anthropic"
OPENCODE_GO_DEFAULT_MODEL_ALIAS = "opencode-go/kimi-k2.6"
OPENCODE_GO_DEFAULT_CONTEXT = 262_000

# models.dev is OpenCode's own source of truth for model metadata (context
# window, display name). The Go /models endpoint returns ids only, so we
# enrich ids not in the curated catalog below from this catalog.
MODELS_DEV_API_URL = "https://models.dev/api.json"
MODELS_DEV_PROVIDER_ID = "opencode-go"
# The models.dev fetch is best-effort enrichment, so it must not stall login on
# the 120s default. A tight cap means a slow/partial endpoint degrades quickly
# to the curated catalog instead of holding the user for up to two minutes.
MODELS_DEV_TIMEOUT = aiohttp.ClientTimeout(total=15, sock_connect=8, sock_read=10)


@dataclass(frozen=True, slots=True)
class OpenCodeGoModel:
    model_id: str
    display_name: str
    provider_key: str
    max_context_size: int = 262_000

    @property
    def alias(self) -> str:
        return f"{OPENCODE_GO_PLATFORM_ID}/{self.model_id}"


OPENCODE_GO_MODELS: tuple[OpenCodeGoModel, ...] = (
    OpenCodeGoModel("glm-5", "GLM-5", OPENCODE_GO_OPENAI_PROVIDER_KEY),
    OpenCodeGoModel("glm-5.1", "GLM-5.1", OPENCODE_GO_OPENAI_PROVIDER_KEY),
    OpenCodeGoModel("kimi-k2.5", "Kimi K2.5", OPENCODE_GO_OPENAI_PROVIDER_KEY),
    OpenCodeGoModel("kimi-k2.6", "Kimi K2.6", OPENCODE_GO_OPENAI_PROVIDER_KEY),
    OpenCodeGoModel("deepseek-v4-pro", "DeepSeek V4 Pro", OPENCODE_GO_OPENAI_PROVIDER_KEY),
    OpenCodeGoModel("deepseek-v4-flash", "DeepSeek V4 Flash", OPENCODE_GO_OPENAI_PROVIDER_KEY),
    OpenCodeGoModel("mimo-v2-pro", "MiMo-V2-Pro", OPENCODE_GO_OPENAI_PROVIDER_KEY),
    OpenCodeGoModel("mimo-v2-omni", "MiMo-V2-Omni", OPENCODE_GO_OPENAI_PROVIDER_KEY),
    OpenCodeGoModel("mimo-v2.5-pro", "MiMo-V2.5-Pro", OPENCODE_GO_OPENAI_PROVIDER_KEY, 1_000_000),
    OpenCodeGoModel("mimo-v2.5", "MiMo-V2.5", OPENCODE_GO_OPENAI_PROVIDER_KEY, 1_000_000),
    # Qwen models speak the Anthropic-shaped endpoint (models.dev routes them
    # via @ai-sdk/anthropic); the OpenAI-shaped endpoint rejects them with
    # "not supported for format oa-compat".
    OpenCodeGoModel("qwen3.5-plus", "Qwen3.5 Plus", OPENCODE_GO_ANTHROPIC_PROVIDER_KEY, 262_000),
    OpenCodeGoModel("qwen3.6-plus", "Qwen3.6 Plus", OPENCODE_GO_ANTHROPIC_PROVIDER_KEY, 262_000),
    OpenCodeGoModel("qwen3.7-max", "Qwen3.7 Max", OPENCODE_GO_ANTHROPIC_PROVIDER_KEY, 1_000_000),
    OpenCodeGoModel("minimax-m2.5", "MiniMax M2.5", OPENCODE_GO_ANTHROPIC_PROVIDER_KEY, 205_000),
    OpenCodeGoModel("minimax-m2.7", "MiniMax M2.7", OPENCODE_GO_ANTHROPIC_PROVIDER_KEY, 205_000),
)


def get_opencode_go_api_key_from_env() -> str | None:
    for name in ("OPENCODE_GO_API_KEY", "OPENCODE_API_KEY", "OPENCODE_ZEN_API_KEY"):
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _apply_opencode_go_config(
    config: Config,
    api_key: SecretStr,
    models: tuple[OpenCodeGoModel, ...] = OPENCODE_GO_MODELS,
) -> None:
    config.providers[OPENCODE_GO_OPENAI_PROVIDER_KEY] = LLMProvider(
        type="openai_legacy",
        base_url=OPENCODE_GO_BASE_URL,
        api_key=api_key,
    )
    config.providers[OPENCODE_GO_ANTHROPIC_PROVIDER_KEY] = LLMProvider(
        type="anthropic",
        base_url=OPENCODE_GO_ANTHROPIC_BASE_URL,
        api_key=api_key,
    )

    provider_keys = {OPENCODE_GO_OPENAI_PROVIDER_KEY, OPENCODE_GO_ANTHROPIC_PROVIDER_KEY}
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

    if OPENCODE_GO_DEFAULT_MODEL_ALIAS in config.models:
        config.default_model = OPENCODE_GO_DEFAULT_MODEL_ALIAS
    else:
        fallback = next((model.alias for model in models), next(iter(config.models), ""))
        config.default_model = fallback
    config.default_thinking = False


def _model_by_id() -> dict[str, OpenCodeGoModel]:
    return {model.model_id: model for model in OPENCODE_GO_MODELS}


@dataclass(frozen=True, slots=True)
class _ModelsDevMeta:
    """The slice of models.dev metadata we consume for a single model id.

    ``is_anthropic`` is the authoritative API-shape signal: models.dev marks
    Anthropic-shaped models with ``provider.npm == "@ai-sdk/anthropic"`` and
    leaves the rest on the provider default (``@ai-sdk/openai-compatible``).
    ``None`` means models.dev had no entry to derive a shape from.
    """

    display_name: str | None
    max_context: int | None
    is_anthropic: bool | None


MODELS_DEV_ANTHROPIC_NPM = "@ai-sdk/anthropic"


def _heuristic_provider_key(model_id: str) -> str:
    """Last-ditch shape guess when models.dev and the catalog are both silent.

    OpenAI-compatible is the safe default (most Go models use it); only the
    stable ``minimax-`` family is reliably Anthropic-shaped by name.
    """
    if model_id.startswith("minimax-"):
        return OPENCODE_GO_ANTHROPIC_PROVIDER_KEY
    return OPENCODE_GO_OPENAI_PROVIDER_KEY


def _resolve_provider_key(
    model_id: str, meta: _ModelsDevMeta | None, catalog: OpenCodeGoModel | None
) -> str:
    """Pick the provider (API shape) for a model.

    models.dev is authoritative; the curated catalog is the offline fallback;
    the name heuristic is the last resort. This is the fix for Qwen models
    being rejected as ``not supported for format oa-compat`` — they are
    Anthropic-shaped, which only models.dev (or the corrected catalog) knows.
    """
    if meta is not None and meta.is_anthropic is not None:
        return (
            OPENCODE_GO_ANTHROPIC_PROVIDER_KEY
            if meta.is_anthropic
            else (OPENCODE_GO_OPENAI_PROVIDER_KEY)
        )
    if catalog is not None:
        return catalog.provider_key
    return _heuristic_provider_key(model_id)


def _derive_display_name(model_id: str) -> str:
    return model_id.replace("-", " ").title()


def _extract_model_ids(data: object) -> list[str]:
    """Pull the ordered list of model ids from the /models payload."""
    if not isinstance(data, dict):
        return []
    raw_items = cast(dict[str, Any], data).get("data")
    if not isinstance(raw_items, list):
        return []
    ids: list[str] = []
    for item in cast(list[Any], raw_items):
        if not isinstance(item, dict):
            continue
        model_id = cast(dict[str, Any], item).get("id")
        if isinstance(model_id, str) and model_id:
            ids.append(model_id)
    return ids


def _parse_models_dev_metadata(data: object) -> dict[str, _ModelsDevMeta]:
    """Extract display name, context, and API shape per opencode-go model id."""
    if not isinstance(data, dict):
        return {}
    provider = cast(dict[str, Any], data).get(MODELS_DEV_PROVIDER_ID)
    if not isinstance(provider, dict):
        return {}
    models = cast(dict[str, Any], provider).get("models")
    if not isinstance(models, dict):
        return {}
    default_npm = cast(dict[str, Any], provider).get("npm")
    result: dict[str, _ModelsDevMeta] = {}
    for model_id, entry in cast(dict[str, Any], models).items():
        if not isinstance(entry, dict):
            continue
        entry_d = cast(dict[str, Any], entry)
        name = entry_d.get("name")
        display_name = name if isinstance(name, str) and name else None
        limit = entry_d.get("limit")
        context = cast(dict[str, Any], limit).get("context") if isinstance(limit, dict) else None
        max_context = context if isinstance(context, int) and context > 0 else None
        model_provider = entry_d.get("provider")
        npm = cast(dict[str, Any], model_provider).get("npm") if isinstance(model_provider, dict) else None
        effective_npm = npm or default_npm
        is_anthropic = (
            effective_npm == MODELS_DEV_ANTHROPIC_NPM if isinstance(effective_npm, str) else None
        )
        result[model_id] = _ModelsDevMeta(display_name, max_context, is_anthropic)
    return result


def _build_models(
    model_ids: list[str],
    metadata: dict[str, _ModelsDevMeta],
) -> tuple[OpenCodeGoModel, ...]:
    """Turn discovered ids into models.

    The /models list is authoritative for *which* models exist. For each id,
    properties resolve in order: models.dev → curated catalog → default. This
    lets the live path self-correct shape/context even if the catalog drifts.
    """
    known = _model_by_id()
    result: list[OpenCodeGoModel] = []
    for model_id in model_ids:
        catalog = known.get(model_id)
        meta = metadata.get(model_id)
        display_name = (
            (meta.display_name if meta else None)
            or (catalog.display_name if catalog else None)
            or _derive_display_name(model_id)
        )
        max_context = (
            (meta.max_context if meta else None)
            or (catalog.max_context_size if catalog else None)
            or OPENCODE_GO_DEFAULT_CONTEXT
        )
        result.append(
            OpenCodeGoModel(
                model_id,
                display_name,
                _resolve_provider_key(model_id, meta, catalog),
                max_context,
            )
        )
    return tuple(result)


async def _fetch_models_dev_metadata() -> dict[str, _ModelsDevMeta]:
    """Best-effort metadata fetch. Returns {} on any failure so login still
    succeeds (falling back to the curated catalog) when models.dev is
    unreachable."""
    try:
        async with (
            new_client_session(timeout=MODELS_DEV_TIMEOUT) as session,
            session.get(MODELS_DEV_API_URL, raise_for_status=True) as response,
        ):
            payload = await response.json(content_type=None)
    except (TimeoutError, aiohttp.ClientError, ValueError):
        return {}
    return _parse_models_dev_metadata(payload)


async def _discover_opencode_go_models(api_key: str) -> tuple[OpenCodeGoModel, ...]:
    async with (
        new_client_session() as session,
        session.get(
            f"{OPENCODE_GO_BASE_URL}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            raise_for_status=True,
        ) as response,
    ):
        payload = await response.json(content_type=None)

    model_ids = _extract_model_ids(payload)
    if not model_ids:
        return ()

    # models.dev is the authority for API shape + context; fetch it on every
    # login (best-effort) so the live list self-corrects even when our curated
    # catalog drifts. Falls back to the catalog when models.dev is unreachable.
    metadata = await _fetch_models_dev_metadata()
    return _build_models(model_ids, metadata)


async def login_opencode_go_api_key(
    config: Config, api_key: str | None = None
) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Login requires the default config file; restart without --config/--config-file.",
        )
        return

    resolved_key = (api_key or get_opencode_go_api_key_from_env() or "").strip()
    if not resolved_key:
        yield OAuthEvent("error", "OpenCode Go API key is required.")
        return

    models = OPENCODE_GO_MODELS
    try:
        discovered = await _discover_opencode_go_models(resolved_key)
        if discovered:
            models = discovered
    except aiohttp.ClientResponseError as exc:
        if exc.status in {401, 403}:
            yield OAuthEvent("error", "Invalid OpenCode Go API key; the key was not saved.")
            return
        yield OAuthEvent(
            "info",
            "OpenCode Go model listing is unavailable; using the built-in model list.",
        )
    except (TimeoutError, aiohttp.ClientError, ValueError):
        yield OAuthEvent(
            "info",
            "OpenCode Go model listing is unavailable; using the built-in model list.",
        )

    _apply_opencode_go_config(config, SecretStr(resolved_key), models=models)
    save_config(config)
    yield OAuthEvent("success", f"OpenCode Go configured with model {config.default_model}.")


async def logout_opencode_go(config: Config) -> AsyncIterator[OAuthEvent]:
    if not config.is_from_default_location:
        yield OAuthEvent(
            "error",
            "Logout requires the default config file; restart without --config/--config-file.",
        )
        return

    provider_keys = {OPENCODE_GO_OPENAI_PROVIDER_KEY, OPENCODE_GO_ANTHROPIC_PROVIDER_KEY}
    for provider_key in provider_keys:
        config.providers.pop(provider_key, None)
    for key, model in list(config.models.items()):
        if model.provider in provider_keys:
            del config.models[key]

    if config.default_model not in config.models:
        config.default_model = next(iter(config.models), "")
    save_config(config)
    yield OAuthEvent("success", "Logged out of OpenCode Go successfully.")
