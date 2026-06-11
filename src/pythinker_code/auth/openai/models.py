# pyright: reportUnusedFunction=false
"""Model discovery and catalog parsing for the OpenAI ChatGPT Codex backend."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, cast

from pythinker_code.auth.oauth import OAuthError
from pythinker_code.auth.openai.constants import OPENAI_CHATGPT_BASE_URL
from pythinker_code.auth.platforms import ModelInfo
from pythinker_code.constant import USER_AGENT
from pythinker_code.utils.aiohttp import new_client_session

type JsonObject = Mapping[str, Any]


def _as_json_object(value: object) -> JsonObject | None:
    if isinstance(value, dict):
        return cast(JsonObject, value)
    return None


def _iter_json_objects(value: object) -> Iterator[JsonObject]:
    if not isinstance(value, list):
        return
    for item in cast(list[object], value):
        json_object = _as_json_object(item)
        if json_object is not None:
            yield json_object


def build_chatgpt_codex_headers(
    *, access_token: str | None = None, account_id: str | None = None
) -> dict[str, str]:
    """Headers expected by the ChatGPT-backed Codex endpoint.

    The ChatGPT Codex backend is account-scoped. The bearer token carries the
    subscription, and ``ChatGPT-Account-ID`` disambiguates the active ChatGPT
    account when OpenAI returns it in the OAuth claims.
    """
    headers = {
        "User-Agent": f"codex_cli_rs/0.0.0 ({USER_AGENT})",
        "originator": "codex_cli_rs",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if account_id:
        headers["ChatGPT-Account-ID"] = account_id
    return headers


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _optional_int(value: object) -> int | None:
    # bool is an int subclass: a JSON ``true`` is a flag, not the integer 1.
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _first_present_field(item: JsonObject, *names: str) -> object:
    for name in names:
        if name in item and item[name] is not None:
            return item[name]
    return None


def _first_non_empty_string_field(item: JsonObject, *names: str) -> str | None:
    value = _first_present_field(item, *names)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _looks_like_reasoning_model(model_id: str) -> bool:
    normalized = model_id.lower()
    return normalized.startswith(("gpt-5", "o1", "o3", "o4")) or "codex" in normalized


def _chatgpt_model_context(model_id: str, item: JsonObject) -> int:
    value = _optional_int(
        _first_present_field(
            item,
            "context_window",
            "contextWindow",
            "context_length",
            "contextLength",
            "max_context_size",
        )
    )
    if value and value > 0:
        return value
    return 128_000 if model_id.lower().endswith("spark") else 272_000


def _chatgpt_model_supports_image(model_id: str, item: JsonObject) -> bool:
    value = _optional_bool(
        _first_present_field(
            item,
            "supports_image_in",
            "supportsImageIn",
            "supports_vision",
            "supportsVision",
            "vision",
        )
    )
    if value is not None:
        return value
    # OpenAI documents Spark as a text-only research-preview model.
    return not model_id.lower().endswith("spark")


def _is_visible_chatgpt_model(item: JsonObject) -> bool:
    visibility = item.get("visibility")
    if isinstance(visibility, str) and visibility.strip().lower() in {"hide", "hidden"}:
        return False
    for key in ("disabled", "unavailable"):
        if item.get(key) is True:
            return False
    return all(item.get(key) is not False for key in ("available", "is_available", "isAvailable"))


def _parse_chatgpt_model_item(item: JsonObject) -> ModelInfo | None:
    model_id = _first_non_empty_string_field(item, "slug", "id")
    if not model_id or not _is_visible_chatgpt_model(item):
        return None
    reasoning = _optional_bool(
        _first_present_field(item, "supports_reasoning", "supportsReasoning", "reasoning")
    )
    supports_reasoning = (
        reasoning if reasoning is not None else _looks_like_reasoning_model(model_id)
    )
    display_name = _first_non_empty_string_field(
        item, "display_name", "displayName", "name", "title"
    )
    return ModelInfo(
        id=model_id,
        context_length=_chatgpt_model_context(model_id, item),
        supports_reasoning=supports_reasoning,
        supports_image_in=_chatgpt_model_supports_image(model_id, item),
        supports_video_in=_optional_bool(
            _first_present_field(
                item,
                "supports_video_in",
                "supportsVideoIn",
                "supports_video",
                "supportsVideo",
            )
        )
        is True,
        display_name=display_name,
    )


def _parse_chatgpt_models_payload(payload: object) -> list[ModelInfo]:
    payload_object = _as_json_object(payload)
    if payload_object is None:
        raise ValueError("Unexpected OpenAI ChatGPT Codex models response.")
    raw_models = payload_object.get("models")
    if not isinstance(raw_models, list):
        # Keep a small compatibility path in case OpenAI ever aligns this with
        # the public /v1/models shape. The ChatGPT endpoint currently returns
        # {"models": [{"slug": ...}]}.
        raw_models = payload_object.get("data")
    if not isinstance(raw_models, list):
        raise ValueError("OpenAI ChatGPT Codex models response did not include models.")

    sortable: list[tuple[int, int, ModelInfo]] = []
    seen: set[str] = set()
    for index, item in enumerate(_iter_json_objects(cast(list[object], raw_models))):
        model = _parse_chatgpt_model_item(item)
        if model is None or model.id in seen:
            continue
        seen.add(model.id)
        priority = _optional_int(item.get("priority"))
        sortable.append((priority if priority is not None else 10_000, index, model))

    sortable.sort(key=lambda entry: (entry[0], entry[1]))
    models = [model for _, _, model in sortable]
    if not models:
        raise ValueError("No OpenAI ChatGPT Codex models are available for this account.")
    return models


def _chatgpt_models_url(base_url: str | None = None) -> str:
    root = (base_url or OPENAI_CHATGPT_BASE_URL).rstrip("/")
    return f"{root}/models?client_version=1.0.0"


async def discover_chatgpt_models(
    access_token: str,
    *,
    account_id: str | None = None,
    base_url: str | None = None,
) -> list[ModelInfo]:
    async with (
        new_client_session() as session,
        session.get(
            _chatgpt_models_url(base_url),
            headers=build_chatgpt_codex_headers(
                access_token=access_token,
                account_id=account_id,
            ),
            raise_for_status=True,
        ) as response,
    ):
        payload = await response.json(content_type=None)
    return _parse_chatgpt_models_payload(payload)


def _select_default_openai_model(models: list[ModelInfo]) -> tuple[ModelInfo, bool]:
    if not models:
        raise OAuthError("No OpenAI models available.")

    for model in models:
        if model.id.lower() == "gpt-5.5":
            return model, model.supports_reasoning

    for model in models:
        if "codex" in model.id.lower():
            return model, model.supports_reasoning
    for model in models:
        if model.id.lower().startswith("gpt-5"):
            return model, False
    for model in models:
        if model.id.lower().startswith("gpt"):
            return model, False
    return models[0], False
