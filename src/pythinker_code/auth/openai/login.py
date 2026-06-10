# pyright: reportPrivateUsage=false
"""OpenAI login entry points: browser, device-code, and API-key flows."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import aiohttp
from pydantic import SecretStr

from pythinker_code.auth import OPENAI_API_PLATFORM_ID, OPENAI_CHATGPT_PLATFORM_ID
from pythinker_code.auth.oauth import OAuthEvent, load_tokens, save_tokens
from pythinker_code.auth.openai._shared import _default_config_error, _handled_error_event
from pythinker_code.auth.openai.browser_flow import _wait_for_browser_code
from pythinker_code.auth.openai.catalog import OPENAI_API_FALLBACK_MODELS
from pythinker_code.auth.openai.config_apply import _apply_openai_config
from pythinker_code.auth.openai.constants import (
    OPENAI_API_BASE_URL,
    OPENAI_CHATGPT_BASE_URL,
    OPENAI_CHATGPT_OAUTH_KEY,
    OPENAI_DEVICE_REDIRECT_URI,
    OPENAI_DEVICE_VERIFICATION_URL,
)
from pythinker_code.auth.openai.models import _select_default_openai_model, discover_chatgpt_models
from pythinker_code.auth.openai.oauth_client import (
    _exchange_code_for_tokens,
    _exchange_id_token_for_api_key,
    _poll_device_code,
    _request_device_code,
    _token_from_openai_response,
)
from pythinker_code.auth.platforms import list_models
from pythinker_code.config import Config, OAuthRef, save_config


async def _finish_chatgpt_login(
    config: Config, token_payload: dict[str, Any]
) -> AsyncIterator[OAuthEvent]:
    token = _token_from_openai_response(token_payload)
    # Capture the previously logged-in account before overwriting it so we can
    # tell the user whether `/login` actually switched accounts.
    previous = load_tokens(OAuthRef(storage="file", key=OPENAI_CHATGPT_OAUTH_KEY))
    previous_account_id = previous.account_id if previous else None
    oauth_ref = save_tokens(OAuthRef(storage="file", key=OPENAI_CHATGPT_OAUTH_KEY), token)

    try:
        api_key = ""
        if id_token := token_payload.get("id_token"):
            api_key = await _exchange_id_token_for_api_key(str(id_token))
        models = await discover_chatgpt_models(token.access_token, account_id=token.account_id)
        selected_model, thinking = _select_default_openai_model(models)
    except Exception as exc:
        yield _handled_error_event(
            exc,
            site="auth.openai.discover_chatgpt_models",
            message=f"Failed to discover OpenAI ChatGPT models: {exc}",
        )
        return

    _apply_openai_config(
        config,
        platform_id=OPENAI_CHATGPT_PLATFORM_ID,
        provider_type="openai_codex",
        base_url=OPENAI_CHATGPT_BASE_URL,
        api_key=SecretStr(api_key),
        oauth_ref=oauth_ref,
        models=models,
        selected_model=selected_model,
        thinking=thinking,
    )
    save_config(config)

    new_account_id = token.account_id
    if previous_account_id and new_account_id and previous_account_id == new_account_id:
        yield OAuthEvent(
            "info",
            "Signed in as the same ChatGPT account as before. To switch accounts, sign out "
            "of ChatGPT in your browser or use a private/incognito window (or the device-code "
            "option), then run /login again.",
        )
    account_suffix = f" for account {new_account_id[:8]}" if new_account_id else ""
    yield OAuthEvent(
        "success",
        f"OpenAI ChatGPT configured{account_suffix} with model {selected_model.id}.",
    )


async def login_openai_browser(
    config: Config, open_browser: bool = True
) -> AsyncIterator[OAuthEvent]:
    if (event := _default_config_error("Login", config)) is not None:
        yield event
        return

    yield OAuthEvent(
        "verification_url",
        "Opening OpenAI ChatGPT login in your browser.",
    )

    try:
        code, verifier, redirect_uri = await _wait_for_browser_code(open_browser=open_browser)
        token_payload = await _exchange_code_for_tokens(code, verifier, redirect_uri)
    except Exception as exc:
        yield _handled_error_event(
            exc,
            site="auth.openai.browser_login",
            message=f"OpenAI browser login failed: {exc}",
        )
        return

    async for event in _finish_chatgpt_login(config, token_payload):
        yield event


async def login_openai_headless(config: Config) -> AsyncIterator[OAuthEvent]:
    if (event := _default_config_error("Login", config)) is not None:
        yield event
        return

    try:
        device_code = await _request_device_code()
    except Exception as exc:
        yield _handled_error_event(
            exc,
            site="auth.openai.device_start",
            message=f"Failed to start OpenAI device login: {exc}",
        )
        return

    yield OAuthEvent(
        "verification_url",
        f"Open {OPENAI_DEVICE_VERIFICATION_URL} and enter code {device_code.user_code}.",
        data={
            "verification_url": OPENAI_DEVICE_VERIFICATION_URL,
            "user_code": device_code.user_code,
        },
    )
    yield OAuthEvent("waiting", "Waiting for OpenAI device authorization...")

    try:
        code_payload = await _poll_device_code(device_code)
        token_payload = await _exchange_code_for_tokens(
            code_payload["authorization_code"],
            code_payload["code_verifier"],
            OPENAI_DEVICE_REDIRECT_URI,
        )
    except Exception as exc:
        yield _handled_error_event(
            exc,
            site="auth.openai.device_poll",
            message=f"OpenAI device login failed: {exc}",
        )
        return

    async for event in _finish_chatgpt_login(config, token_payload):
        yield event


async def login_openai_api_key(
    config: Config, api_key: str | None = None
) -> AsyncIterator[OAuthEvent]:
    if (event := _default_config_error("Login", config)) is not None:
        yield event
        return
    if not api_key:
        yield OAuthEvent("error", "OpenAI API key is required.")
        return

    from pythinker_code.auth.platforms import get_platform_by_id

    platform = get_platform_by_id(OPENAI_API_PLATFORM_ID)
    if platform is None:
        yield OAuthEvent("error", "OpenAI API platform is unavailable.")
        return

    try:
        models = await list_models(platform, api_key)
    except aiohttp.ClientResponseError as exc:
        if exc.status == 401:
            yield OAuthEvent("error", "Invalid OpenAI API key; the key was not saved.")
            return
        if exc.status == 403:
            # Distinct from 401: the key authenticated but lacks permission —
            # restricted scope (no Models read) or an unsupported region.
            yield OAuthEvent(
                "error",
                "OpenAI rejected the key (HTTP 403: insufficient permissions or "
                "unsupported region); the key was not saved. If this is a "
                "restricted key, grant it the Models read permission and retry.",
            )
            return
        models = list(OPENAI_API_FALLBACK_MODELS)
    except Exception:
        models = list(OPENAI_API_FALLBACK_MODELS)

    if not models:
        yield OAuthEvent("error", "No OpenAI models are available for this API key.")
        return

    selected_model, thinking = _select_default_openai_model(models)
    _apply_openai_config(
        config,
        platform_id=OPENAI_API_PLATFORM_ID,
        provider_type="openai_responses",
        base_url=OPENAI_API_BASE_URL,
        api_key=SecretStr(api_key),
        oauth_ref=None,
        models=models,
        selected_model=selected_model,
        thinking=thinking,
    )
    save_config(config)
    yield OAuthEvent("success", f"OpenAI API key configured with model {selected_model.id}.")
