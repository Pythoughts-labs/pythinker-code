# pyright: reportPrivateUsage=false
"""OpenAI auth package: login flows, OAuth client, browser callback, and model discovery."""

from __future__ import annotations

from pythinker_code.auth.openai.browser_flow import (
    _build_authorize_url,
    _callback_html,
    _handle_browser_callback,
    _wait_for_browser_code,
)
from pythinker_code.auth.openai.catalog import (
    OPENAI_API_FALLBACK_MODELS,
    OPENAI_CHATGPT_FALLBACK_MODELS,
)
from pythinker_code.auth.openai.config_apply import _apply_openai_config, logout_openai
from pythinker_code.auth.openai.constants import (
    OPENAI_API_BASE_URL,
    OPENAI_AUTH_ISSUER,
    OPENAI_BROWSER_FALLBACK_PORT,
    OPENAI_BROWSER_PORT,
    OPENAI_BROWSER_REDIRECT_PATH,
    OPENAI_CHATGPT_BASE_URL,
    OPENAI_CHATGPT_MODELS_URL,
    OPENAI_CHATGPT_OAUTH_KEY,
    OPENAI_CLIENT_ID,
    OPENAI_DEVICE_REDIRECT_URI,
    OPENAI_DEVICE_VERIFICATION_URL,
)
from pythinker_code.auth.openai.login import (
    login_openai_api_key,
    login_openai_browser,
    login_openai_headless,
)
from pythinker_code.auth.openai.models import (
    _select_default_openai_model,
    build_chatgpt_codex_headers,
    discover_chatgpt_models,
)
from pythinker_code.auth.openai.oauth_client import (
    DeviceCode,
    PkceCodes,
    _exchange_code_for_tokens,
    _exchange_id_token_for_api_key,
    _generate_pkce,
    _generate_state,
    _poll_device_code,
    _request_device_code,
    _token_from_openai_response,
    refresh_openai_chatgpt_token,
)

__all__ = [
    "OPENAI_API_BASE_URL",
    "OPENAI_API_FALLBACK_MODELS",
    "OPENAI_AUTH_ISSUER",
    "OPENAI_BROWSER_FALLBACK_PORT",
    "OPENAI_BROWSER_PORT",
    "OPENAI_BROWSER_REDIRECT_PATH",
    "OPENAI_CHATGPT_BASE_URL",
    "OPENAI_CHATGPT_FALLBACK_MODELS",
    "OPENAI_CHATGPT_MODELS_URL",
    "OPENAI_CHATGPT_OAUTH_KEY",
    "OPENAI_CLIENT_ID",
    "OPENAI_DEVICE_REDIRECT_URI",
    "OPENAI_DEVICE_VERIFICATION_URL",
    "DeviceCode",
    "PkceCodes",
    "_apply_openai_config",
    "_build_authorize_url",
    "_callback_html",
    "_exchange_code_for_tokens",
    "_exchange_id_token_for_api_key",
    "_generate_pkce",
    "_generate_state",
    "_handle_browser_callback",
    "_poll_device_code",
    "_request_device_code",
    "_select_default_openai_model",
    "_token_from_openai_response",
    "_wait_for_browser_code",
    "build_chatgpt_codex_headers",
    "discover_chatgpt_models",
    "login_openai_api_key",
    "login_openai_browser",
    "login_openai_headless",
    "logout_openai",
    "refresh_openai_chatgpt_token",
]
