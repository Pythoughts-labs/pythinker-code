from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

import aiohttp
import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from pydantic import SecretStr
from yarl import URL

from pythinker_code.auth import OPENAI_API_PLATFORM_ID, OPENAI_CHATGPT_PLATFORM_ID
from pythinker_code.auth.browser_login_page import (
    browser_login_favicon_data_uri,
    browser_login_logo_data_uri,
)
from pythinker_code.auth.oauth import OAuthError, OAuthToken, load_tokens, save_tokens
from pythinker_code.auth.openai import (
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
    PkceCodes,
    _apply_openai_config,
    _build_authorize_url,
    _callback_html,
    _exchange_id_token_for_api_key,
    _handle_browser_callback,
    _select_default_openai_model,
    _token_from_openai_response,
    _wait_for_browser_code,
    discover_chatgpt_models,
    login_openai_api_key,
    login_openai_browser,
)
from pythinker_code.auth.platforms import (
    ModelInfo,
    managed_model_key,
    managed_provider_key,
    refresh_managed_models,
)
from pythinker_code.config import Config, LLMModel, LLMProvider, OAuthRef


def _model(model_id: str, *, reasoning: bool = False, image: bool = False) -> ModelInfo:
    return ModelInfo(
        id=model_id,
        context_length=128000,
        supports_reasoning=reasoning,
        supports_image_in=image,
        supports_video_in=False,
        display_name=None,
    )


def _jwt_with_chatgpt_account(account_id: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode("utf-8").rstrip("=")
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"https://api.openai.com/auth": {"chatgpt_account_id": account_id}}).encode(
                "utf-8"
            )
        )
        .decode("utf-8")
        .rstrip("=")
    )
    return f"{header}.{payload}.signature"


def _request_info(url: str) -> aiohttp.RequestInfo:
    return aiohttp.RequestInfo(
        url=URL(url),
        method="GET",
        headers=CIMultiDictProxy(CIMultiDict()),
        real_url=URL(url),
    )


def test_openai_auth_constants_match_codex_compatible_values():
    assert OPENAI_AUTH_ISSUER == "https://auth.openai.com"
    assert OPENAI_CLIENT_ID == "app_EMoamEEZ73f0CkXaXp7hrann"
    assert OPENAI_BROWSER_PORT == 1455
    assert OPENAI_BROWSER_FALLBACK_PORT == 1457
    assert OPENAI_BROWSER_REDIRECT_PATH == "/auth/callback"
    assert OPENAI_DEVICE_REDIRECT_URI == "https://auth.openai.com/deviceauth/callback"
    assert OPENAI_DEVICE_VERIFICATION_URL == "https://auth.openai.com/codex/device"
    assert OPENAI_CHATGPT_OAUTH_KEY == "oauth/openai-chatgpt"


def test_openai_callback_html_uses_pythinker_branding():
    page = _callback_html(ok=True, message=None)
    logo_data_uri = browser_login_logo_data_uri()
    favicon_data_uri = browser_login_favicon_data_uri()

    logo_svg = base64.b64decode(logo_data_uri.split(",", 1)[1]).decode("utf-8")
    favicon_bytes = base64.b64decode(favicon_data_uri.split(",", 1)[1])

    assert "<title>Pythinker logged in</title>" in page
    assert "You&#x27;re logged in to Pythinker" in page
    assert "OpenAI login complete" not in page
    assert 'viewBox="0 0 411 512.455"' in logo_svg
    assert favicon_bytes.startswith(b"\x00\x00\x01\x00")
    assert f'<link rel="icon" type="image/x-icon" href="{favicon_data_uri}">' in page
    assert f'<img class="logo" src="{logo_data_uri}" alt="Pythinker logo">' in page


def test_committed_brand_assets_match_web_public_source():
    """Committed login-brand assets must stay byte-identical to their canonical source.

    ``web/static/`` is a build output: ``scripts/build_web.py`` ``rmtree``s it and
    repopulates from the vite build (whose brand files come from ``web/public/brand``).
    We force-commit ``icon.svg`` + ``favicon.ico`` only so the test job — which does
    not run the web build — still has the files the OAuth callback reads. This guard
    fails loudly if the canonical source changes without the committed copies being
    re-synced (otherwise the branding tests above would validate a stale fixture).
    """
    from pythinker_code.auth.browser_login_page import (
        _PYTHINKER_FAVICON_PATH,
        _PYTHINKER_LOGO_PATH,
    )

    public_brand = Path(__file__).resolve().parents[2] / "web" / "public" / "brand"
    for committed, name in (
        (_PYTHINKER_LOGO_PATH, "icon.svg"),
        (_PYTHINKER_FAVICON_PATH, "favicon.ico"),
    ):
        source = public_brand / name
        assert source.exists(), f"canonical brand source missing: {source}"
        assert committed.read_bytes() == source.read_bytes(), (
            f"{committed} drifted from canonical source {source}; re-sync the committed "
            "copy (e.g. `cp` from web/public/brand or rerun the web build) so the "
            "login-branding tests match what actually ships."
        )


def test_browser_login_asset_missing_degrades_gracefully(tmp_path):
    """A missing brand asset must not break the OAuth callback page.

    The data-uri helper should log and return an empty source rather than raising,
    so login still completes if a build ever ships without the cosmetic assets.
    """
    from pythinker_code.auth.browser_login_page import browser_login_asset_data_uri

    missing = tmp_path / "does-not-exist.svg"
    assert browser_login_asset_data_uri(missing, "image/svg+xml") == ""


def test_openai_callback_html_escapes_error_message():
    page = _callback_html(ok=False, message='<script>alert("x")</script>')

    assert "<title>Pythinker login failed</title>" in page
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in page
    assert '<script>alert("x")</script>' not in page


def test_build_authorize_url_uses_codex_parameters():
    url = _build_authorize_url(
        redirect_uri="http://localhost:1455/auth/callback",
        pkce=PkceCodes(code_verifier="verifier", code_challenge="challenge"),
        state="state-123",
    )

    assert url.startswith("https://auth.openai.com/oauth/authorize?")
    assert "client_id=app_EMoamEEZ73f0CkXaXp7hrann" in url
    assert "code_challenge=challenge" in url
    assert "codex_cli_simplified_flow=true" in url
    assert "originator=codex_cli_rs" in url

    params = parse_qs(urlsplit(url).query)
    assert params["scope"] == [
        "openid profile email offline_access api.connectors.read api.connectors.invoke"
    ]
    assert params["id_token_add_organizations"] == ["true"]


def test_build_authorize_url_forces_account_reauth():
    """`/login` must force the OpenAI login screen instead of silently reusing the
    browser's existing ChatGPT session, so users can switch accounts."""
    url = _build_authorize_url(
        redirect_uri="http://localhost:1455/auth/callback",
        pkce=PkceCodes(code_verifier="verifier", code_challenge="challenge"),
        state="state-123",
    )

    params = parse_qs(urlsplit(url).query)
    assert params["prompt"] == ["login"]


@pytest.mark.asyncio
async def test_exchange_id_token_for_api_key_uses_codex_requested_token(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def json(self, content_type=None):
            return {"access_token": "openai-api-key-token"}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def post(self, url, *, data):
            captured["url"] = url
            captured["data"] = data
            return FakeResponse()

    monkeypatch.setattr("pythinker_code.auth.openai.oauth_client.new_client_session", FakeSession)

    token = await _exchange_id_token_for_api_key("id-token")

    assert token == "openai-api-key-token"
    assert captured["url"] == "https://auth.openai.com/oauth/token"
    assert captured["data"]["requested_token"] == "openai-api-key"
    assert "requested_token_type" not in captured["data"]


def test_token_from_openai_response_extracts_chatgpt_account_id_from_access_token():
    token = _token_from_openai_response(
        {
            "access_token": _jwt_with_chatgpt_account("acc_access"),
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "openid profile email offline_access",
        }
    )

    assert token.account_id == "acc_access"


# Generous deadline for the localhost callback round-trip. The happy path completes in
# milliseconds; a tight 2s deadline only flakes under CPU contention (a busy CI or a
# large shuffled run), where event-loop scheduling delays push the round-trip past 2s.
# A large bound still catches a genuine hang without racing load.
_BROWSER_CALLBACK_TEST_TIMEOUT = 15.0


@pytest.mark.asyncio
async def test_wait_for_browser_code_accepts_localhost_callback(monkeypatch):
    monkeypatch.setattr(
        "pythinker_code.auth.openai.browser_flow._generate_pkce",
        lambda: PkceCodes(code_verifier="verifier", code_challenge="challenge"),
    )
    monkeypatch.setattr(
        "pythinker_code.auth.openai.browser_flow._generate_state", lambda: "state-123"
    )

    task = asyncio.create_task(_wait_for_browser_code(open_browser=False))
    writer = None
    actual_port = None
    try:
        for port in (OPENAI_BROWSER_PORT, OPENAI_BROWSER_FALLBACK_PORT):
            deadline = asyncio.get_running_loop().time() + _BROWSER_CALLBACK_TEST_TIMEOUT
            while asyncio.get_running_loop().time() < deadline:
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                    actual_port = port
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            if writer is not None:
                break

        assert writer is not None
        assert actual_port is not None
        writer.write(
            b"GET /auth/callback?code=auth-code&state=state-123 HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )
        await writer.drain()

        result = await asyncio.wait_for(task, timeout=_BROWSER_CALLBACK_TEST_TIMEOUT)
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    assert result == (
        "auth-code",
        "verifier",
        f"http://localhost:{actual_port}/auth/callback",
    )


@pytest.mark.asyncio
async def test_wait_for_browser_code_cleans_up_idle_callback_tasks(monkeypatch):
    monkeypatch.setattr(
        "pythinker_code.auth.openai.browser_flow._generate_pkce",
        lambda: PkceCodes(code_verifier="verifier", code_challenge="challenge"),
    )
    monkeypatch.setattr(
        "pythinker_code.auth.openai.browser_flow._generate_state", lambda: "state-123"
    )

    task = asyncio.create_task(_wait_for_browser_code(open_browser=False))
    writer = None
    try:
        for port in (OPENAI_BROWSER_PORT, OPENAI_BROWSER_FALLBACK_PORT):
            deadline = asyncio.get_running_loop().time() + _BROWSER_CALLBACK_TEST_TIMEOUT
            while asyncio.get_running_loop().time() < deadline:
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            if writer is not None:
                break

        assert writer is not None
        await asyncio.sleep(0)
        task.cancel()
        # Poll until the cancellation has unwound (server closed, callback tasks
        # cancelled) instead of a fixed sleep that races CPU load.
        deadline = asyncio.get_running_loop().time() + _BROWSER_CALLBACK_TEST_TIMEOUT
        while not task.done() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        assert task.done()

        pending_callbacks = [
            pending
            for pending in asyncio.all_tasks()
            if pending is not asyncio.current_task()
            and getattr(pending.get_coro(), "__name__", None) == "_browser_callback_task"
            and not pending.done()
        ]
        assert pending_callbacks == []
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()
        await asyncio.gather(task, return_exceptions=True)


def test_select_default_openai_model_prefers_codex_model():
    models = [_model("gpt-5.2"), _model("gpt-5.1-codex", reasoning=True), _model("gpt-4.1")]

    selected, thinking = _select_default_openai_model(models)

    assert selected.id == "gpt-5.1-codex"
    assert thinking is True


def test_select_default_openai_model_prefers_gpt55_when_available():
    models = [_model("gpt-5.3-codex", reasoning=True), _model("gpt-5.5", reasoning=True)]

    selected, thinking = _select_default_openai_model(models)

    assert selected.id == "gpt-5.5"
    assert thinking is True


def test_select_default_openai_model_rejects_empty_model_list():
    with pytest.raises(OAuthError, match="No OpenAI models available"):
        _select_default_openai_model([])


def test_select_default_openai_model_falls_back_to_gpt5_then_gpt_then_first():
    selected, thinking = _select_default_openai_model([_model("o3"), _model("gpt-5.2")])
    assert selected.id == "gpt-5.2"
    assert thinking is False

    selected, thinking = _select_default_openai_model([_model("o3"), _model("gpt-4.1")])
    assert selected.id == "gpt-4.1"
    assert thinking is False

    selected, thinking = _select_default_openai_model([_model("o3")])
    assert selected.id == "o3"
    assert thinking is False


def test_apply_openai_api_key_config_sets_managed_openai_default():
    config = Config(is_from_default_location=True)
    models = [_model("gpt-5.2", reasoning=True), _model("gpt-4.1")]

    _apply_openai_config(
        config,
        platform_id=OPENAI_API_PLATFORM_ID,
        provider_type="openai_responses",
        base_url=OPENAI_API_BASE_URL,
        api_key=SecretStr("sk-test"),
        oauth_ref=None,
        models=models,
        selected_model=models[0],
        thinking=True,
    )

    provider_key = managed_provider_key(OPENAI_API_PLATFORM_ID)
    assert config.providers[provider_key].type == "openai_responses"
    assert config.providers[provider_key].base_url == "https://api.openai.com/v1"
    assert config.providers[provider_key].api_key.get_secret_value() == "sk-test"
    assert config.providers[provider_key].oauth is None
    assert config.default_model == managed_model_key(OPENAI_API_PLATFORM_ID, "gpt-5.2")
    assert config.default_thinking is True


def test_apply_openai_chatgpt_config_stores_oauth_ref_not_token_in_config():
    config = Config(is_from_default_location=True)
    models = [_model("gpt-5.1-codex", reasoning=True)]
    oauth_ref = OAuthRef(storage="file", key=OPENAI_CHATGPT_OAUTH_KEY)

    _apply_openai_config(
        config,
        platform_id=OPENAI_CHATGPT_PLATFORM_ID,
        provider_type="openai_codex",
        base_url=OPENAI_CHATGPT_BASE_URL,
        api_key=SecretStr(""),
        oauth_ref=oauth_ref,
        models=models,
        selected_model=models[0],
        thinking=True,
    )

    provider_key = managed_provider_key(OPENAI_CHATGPT_PLATFORM_ID)
    assert config.providers[provider_key].type == "openai_codex"
    assert config.providers[provider_key].base_url == "https://chatgpt.com/backend-api/codex"
    assert config.providers[provider_key].api_key.get_secret_value() == ""
    assert config.providers[provider_key].oauth == oauth_ref
    assert config.default_model == managed_model_key(OPENAI_CHATGPT_PLATFORM_ID, "gpt-5.1-codex")


@pytest.mark.asyncio
async def test_login_openai_api_key_saves_config_on_model_discovery(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_list_models(platform, api_key):
        assert platform.id == OPENAI_API_PLATFORM_ID
        assert api_key == "sk-test"
        return [_model("gpt-5.2", reasoning=True)]

    monkeypatch.setattr("pythinker_code.auth.openai.login.list_models", fake_list_models)

    events = [event async for event in login_openai_api_key(config, api_key="sk-test")]

    assert events[-1].type == "success"
    provider = config.providers[managed_provider_key(OPENAI_API_PLATFORM_ID)]
    assert provider.type == "openai_responses"
    assert provider.api_key.get_secret_value() == "sk-test"
    assert config.default_model == managed_model_key(OPENAI_API_PLATFORM_ID, "gpt-5.2")
    assert (tmp_path / "config.toml").exists()


@pytest.mark.asyncio
async def test_login_openai_api_key_does_not_save_on_401(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_list_models(platform, api_key):
        request_info = _request_info("https://api.openai.com/v1/models")
        raise aiohttp.ClientResponseError(request_info, (), status=401, message="Unauthorized")

    monkeypatch.setattr("pythinker_code.auth.openai.login.list_models", fake_list_models)

    events = [event async for event in login_openai_api_key(config, api_key="sk-bad")]
    assert events[-1].type == "error"
    assert "Invalid OpenAI API key" in events[-1].message
    assert config.providers == {}
    assert config.models == {}


@pytest.mark.asyncio
async def test_login_openai_api_key_does_not_save_on_403(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_list_models(platform, api_key):
        request_info = _request_info("https://api.openai.com/v1/models")
        raise aiohttp.ClientResponseError(request_info, (), status=403, message="Forbidden")

    monkeypatch.setattr("pythinker_code.auth.openai.login.list_models", fake_list_models)

    events = [event async for event in login_openai_api_key(config, api_key="sk-bad")]
    assert events[-1].type == "error"
    # 403 is permission/region, not an invalid key — the message must not
    # mislabel it, but the key still must not be saved.
    assert "HTTP 403" in events[-1].message
    assert "was not saved" in events[-1].message
    assert config.providers == {}
    assert config.models == {}


@pytest.mark.asyncio
async def test_discover_chatgpt_models_reraises_401(monkeypatch):
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def get(self, url, *, headers, raise_for_status):
            assert url == OPENAI_CHATGPT_MODELS_URL
            assert headers["Authorization"] == "Bearer bad-token"
            request_info = _request_info(url)
            raise aiohttp.ClientResponseError(request_info, (), status=401, message="Unauthorized")

    monkeypatch.setattr("pythinker_code.auth.openai.models.new_client_session", FakeSession)

    with pytest.raises(aiohttp.ClientResponseError) as exc_info:
        await discover_chatgpt_models("bad-token")
    assert exc_info.value.status == 401


@pytest.mark.asyncio
async def test_discover_chatgpt_models_uses_account_scoped_codex_catalog(monkeypatch):
    captured = {}
    payload = {
        "models": [
            {
                "slug": "gpt-5.3-codex",
                "display_name": "GPT-5.3 Codex",
                "context_window": 272_000,
                "priority": 20,
                "supported_in_api": False,
            },
            {
                "slug": "hidden-model",
                "visibility": "hidden",
                "context_window": 272_000,
                "priority": 1,
            },
            {
                "slug": "gpt-5.3-codex-spark",
                "name": "GPT-5.3 Codex Spark",
                "context_window": 128_000,
                "priority": 10,
                "supported_in_api": False,
            },
        ]
    }

    class FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def json(self, content_type=None):
            return payload

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def get(self, url, *, headers, raise_for_status):
            captured["url"] = url
            captured["headers"] = headers
            captured["raise_for_status"] = raise_for_status
            return FakeResponse()

    monkeypatch.setattr("pythinker_code.auth.openai.models.new_client_session", FakeSession)

    models = await discover_chatgpt_models("access-token", account_id="acc_123")

    assert captured["url"] == OPENAI_CHATGPT_MODELS_URL
    assert captured["headers"]["Authorization"] == "Bearer access-token"
    assert captured["headers"]["ChatGPT-Account-ID"] == "acc_123"
    assert captured["headers"]["originator"] == "codex_cli_rs"
    assert captured["raise_for_status"] is True
    assert [model.id for model in models] == ["gpt-5.3-codex-spark", "gpt-5.3-codex"]
    assert models[0].context_length == 128_000
    assert models[0].supports_image_in is False
    assert models[1].display_name == "GPT-5.3 Codex"


@pytest.mark.asyncio
async def test_discover_chatgpt_models_uses_custom_base_url(monkeypatch):
    captured = {}
    payload = {"models": [{"slug": "gpt-5.3-codex", "supported_in_api": False}]}

    class FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def json(self, content_type=None):
            return payload

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def get(self, url, *, headers, raise_for_status):
            captured["url"] = url
            return FakeResponse()

    monkeypatch.setattr("pythinker_code.auth.openai.models.new_client_session", FakeSession)

    models = await discover_chatgpt_models(
        "access-token",
        base_url="https://proxy.example/backend-api/codex/",
    )

    assert captured["url"] == "https://proxy.example/backend-api/codex/models?client_version=1.0.0"
    assert [model.id for model in models] == ["gpt-5.3-codex"]


@pytest.mark.asyncio
async def test_discover_chatgpt_models_does_not_fallback_when_catalog_unavailable(monkeypatch):
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def get(self, *args, **kwargs):
            raise RuntimeError("models endpoint unavailable")

    monkeypatch.setattr("pythinker_code.auth.openai.models.new_client_session", FakeSession)

    with pytest.raises(RuntimeError, match="models endpoint unavailable"):
        await discover_chatgpt_models("access-token")


@pytest.mark.asyncio
async def test_login_openai_api_key_falls_back_to_public_models_on_non_auth_failure(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_list_models(platform, api_key):
        request_info = _request_info("https://api.openai.com/v1/models")
        raise aiohttp.ClientResponseError(
            request_info,
            (),
            status=500,
            message="Server error",
        )

    monkeypatch.setattr("pythinker_code.auth.openai.login.list_models", fake_list_models)

    events = [event async for event in login_openai_api_key(config, api_key="sk-test")]

    assert events[-1].type == "success"
    assert config.default_model == managed_model_key(OPENAI_API_PLATFORM_ID, "gpt-5.5")
    assert managed_model_key(OPENAI_API_PLATFORM_ID, "gpt-5-codex") in config.models


@pytest.mark.asyncio
async def test_refresh_managed_models_replaces_stale_chatgpt_codex_model_with_live_catalog(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    provider_key = managed_provider_key(OPENAI_CHATGPT_PLATFORM_ID)
    stale_model_key = managed_model_key(OPENAI_CHATGPT_PLATFORM_ID, "gpt-5.1-codex")
    config = Config(is_from_default_location=True)
    chatgpt_base_url = "https://proxy.example/backend-api/codex"
    config.providers[provider_key] = LLMProvider(
        type="openai_codex",
        base_url=chatgpt_base_url,
        api_key=SecretStr("access-token"),
        oauth=OAuthRef(storage="file", key=OPENAI_CHATGPT_OAUTH_KEY),
    )
    config.models[stale_model_key] = LLMModel(
        provider=provider_key,
        model="gpt-5.1-codex",
        max_context_size=1050000,
        capabilities={"thinking"},
    )
    config.default_model = stale_model_key

    async def fake_discover_chatgpt_models(api_key, *, account_id=None, base_url=None):
        assert api_key == "access-token"
        assert account_id is None
        assert base_url == chatgpt_base_url
        return [_model("gpt-5.5", reasoning=True)]

    # refresh_managed_models lazily imports from the package, so patch the package attribute.
    monkeypatch.setattr(
        "pythinker_code.auth.openai.discover_chatgpt_models", fake_discover_chatgpt_models
    )

    changed = await refresh_managed_models(config)

    assert changed is True
    assert config.default_model == managed_model_key(OPENAI_CHATGPT_PLATFORM_ID, "gpt-5.5")
    assert stale_model_key not in config.models
    assert managed_model_key(OPENAI_CHATGPT_PLATFORM_ID, "gpt-5.5") in config.models


@pytest.mark.asyncio
async def test_login_openai_headless_stores_chatgpt_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_request_device_code():
        from pythinker_code.auth.openai import DeviceCode

        return DeviceCode(device_auth_id="dev-1", user_code="ABCD-1234", interval=1)

    async def fake_poll_device_code(device_code):
        assert device_code.device_auth_id == "dev-1"
        return {
            "authorization_code": "auth-code",
            "code_verifier": "verifier",
        }

    async def fake_exchange_code_for_tokens(code, verifier, redirect_uri):
        assert code == "auth-code"
        assert verifier == "verifier"
        assert redirect_uri == "https://auth.openai.com/deviceauth/callback"
        return {
            "access_token": "access-token",
            "id_token": _jwt_with_chatgpt_account("acc_headless"),
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "openid profile email offline_access",
        }

    async def fake_exchange_id_token_for_api_key(id_token):
        assert id_token == _jwt_with_chatgpt_account("acc_headless")
        return ""

    async def fake_discover_chatgpt_models(api_key, *, account_id=None):
        assert api_key == "access-token"
        assert account_id == "acc_headless"
        return [_model("gpt-5.1-codex", reasoning=True)]

    monkeypatch.setattr(
        "pythinker_code.auth.openai.login._request_device_code", fake_request_device_code
    )
    monkeypatch.setattr("pythinker_code.auth.openai.login._poll_device_code", fake_poll_device_code)
    monkeypatch.setattr(
        "pythinker_code.auth.openai.login._exchange_code_for_tokens", fake_exchange_code_for_tokens
    )
    monkeypatch.setattr(
        "pythinker_code.auth.openai.login._exchange_id_token_for_api_key",
        fake_exchange_id_token_for_api_key,
    )
    monkeypatch.setattr(
        "pythinker_code.auth.openai.login.discover_chatgpt_models",
        fake_discover_chatgpt_models,
    )

    from pythinker_code.auth.openai import login_openai_headless

    events = [event async for event in login_openai_headless(config)]

    assert [event.type for event in events] == ["verification_url", "waiting", "success"]
    token = load_tokens(OAuthRef(storage="file", key=OPENAI_CHATGPT_OAUTH_KEY))
    assert token is not None
    assert token.access_token == "access-token"
    assert token.account_id == "acc_headless"
    provider = config.providers[managed_provider_key(OPENAI_CHATGPT_PLATFORM_ID)]
    assert provider.type == "openai_codex"
    assert provider.oauth == OAuthRef(storage="file", key=OPENAI_CHATGPT_OAUTH_KEY)
    Config.model_validate(config.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_login_openai_browser_finishes_with_callback_code(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_wait_for_browser_code(open_browser):
        assert open_browser is False
        return "auth-code", "verifier", "http://localhost:1455/auth/callback"

    async def fake_exchange_code_for_tokens(code, verifier, redirect_uri):
        assert code == "auth-code"
        assert verifier == "verifier"
        assert redirect_uri.startswith("http://localhost:")
        return {
            "access_token": "access-token",
            "id_token": _jwt_with_chatgpt_account("acc_browser"),
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "openid profile email offline_access",
        }

    async def fake_exchange_id_token_for_api_key(id_token):
        assert id_token == _jwt_with_chatgpt_account("acc_browser")
        return ""

    async def fake_discover_chatgpt_models(api_key, *, account_id=None):
        assert account_id == "acc_browser"
        return [_model("gpt-5.1-codex", reasoning=True)]

    monkeypatch.setattr(
        "pythinker_code.auth.openai.login._wait_for_browser_code", fake_wait_for_browser_code
    )
    monkeypatch.setattr(
        "pythinker_code.auth.openai.login._exchange_code_for_tokens", fake_exchange_code_for_tokens
    )
    monkeypatch.setattr(
        "pythinker_code.auth.openai.login._exchange_id_token_for_api_key",
        fake_exchange_id_token_for_api_key,
    )
    monkeypatch.setattr(
        "pythinker_code.auth.openai.login.discover_chatgpt_models", fake_discover_chatgpt_models
    )

    events = [event async for event in login_openai_browser(config, open_browser=False)]

    assert events[0].type == "verification_url"
    assert events[-1].type == "success"
    assert config.default_model == managed_model_key(OPENAI_CHATGPT_PLATFORM_ID, "gpt-5.1-codex")
    # The success message names the account so a switch is verifiable.
    assert "acc_brow" in events[-1].message


def _patch_browser_login_returning_account(monkeypatch, account_id: str) -> None:
    async def fake_wait_for_browser_code(open_browser):
        return "auth-code", "verifier", "http://localhost:1455/auth/callback"

    async def fake_exchange_code_for_tokens(code, verifier, redirect_uri):
        return {
            "access_token": "access-token",
            "id_token": _jwt_with_chatgpt_account(account_id),
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "openid profile email offline_access",
        }

    async def fake_exchange_id_token_for_api_key(id_token):
        return ""

    async def fake_discover_chatgpt_models(api_key, *, account_id=None):
        return [_model("gpt-5.1-codex", reasoning=True)]

    monkeypatch.setattr(
        "pythinker_code.auth.openai.login._wait_for_browser_code", fake_wait_for_browser_code
    )
    monkeypatch.setattr(
        "pythinker_code.auth.openai.login._exchange_code_for_tokens", fake_exchange_code_for_tokens
    )
    monkeypatch.setattr(
        "pythinker_code.auth.openai.login._exchange_id_token_for_api_key",
        fake_exchange_id_token_for_api_key,
    )
    monkeypatch.setattr(
        "pythinker_code.auth.openai.login.discover_chatgpt_models", fake_discover_chatgpt_models
    )


@pytest.mark.asyncio
async def test_login_warns_when_same_chatgpt_account_is_reused(monkeypatch, tmp_path):
    """If a re-login lands on the same account (e.g. OpenAI ignored prompt=login or
    the user re-picked it), warn the user instead of silently 'succeeding'."""
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)
    save_tokens(
        OAuthRef(storage="file", key=OPENAI_CHATGPT_OAUTH_KEY),
        OAuthToken(
            access_token="old-access",
            refresh_token="old-refresh",
            expires_at=0.0,
            scope="openid",
            token_type="Bearer",
            account_id="acc_same",
        ),
    )
    _patch_browser_login_returning_account(monkeypatch, "acc_same")

    events = [event async for event in login_openai_browser(config, open_browser=False)]

    assert events[-1].type == "success"
    warnings = [e for e in events if e.type == "info" and "same ChatGPT account" in e.message]
    assert warnings, "expected a same-account warning"
    assert "incognito" in warnings[0].message


@pytest.mark.asyncio
async def test_login_does_not_warn_when_account_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)
    save_tokens(
        OAuthRef(storage="file", key=OPENAI_CHATGPT_OAUTH_KEY),
        OAuthToken(
            access_token="old-access",
            refresh_token="old-refresh",
            expires_at=0.0,
            scope="openid",
            token_type="Bearer",
            account_id="acc_old",
        ),
    )
    _patch_browser_login_returning_account(monkeypatch, "acc_new")

    events = [event async for event in login_openai_browser(config, open_browser=False)]

    assert events[-1].type == "success"
    assert not [e for e in events if e.type == "info" and "same ChatGPT account" in e.message]
    # New account's token overwrote the old one on disk.
    token = load_tokens(OAuthRef(storage="file", key=OPENAI_CHATGPT_OAUTH_KEY))
    assert token is not None
    assert token.account_id == "acc_new"


class _FakeWriter:
    """Minimal asyncio.StreamWriter stand-in that captures written bytes."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._closed = False

    def write(self, data: bytes) -> None:
        self._buf.extend(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        pass

    @property
    def captured(self) -> bytes:
        return bytes(self._buf)


def _make_reader(raw: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(raw)
    reader.feed_eof()
    return reader


@pytest.mark.asyncio
async def test_handle_browser_callback_ignores_non_callback_probe():
    # --- probe request (favicon.ico): should 404 and return (None, None) ---
    probe_reader = _make_reader(b"GET /favicon.ico HTTP/1.1\r\n\r\n")
    probe_writer = _FakeWriter()
    code, error = await _handle_browser_callback(
        probe_reader, cast("asyncio.StreamWriter", probe_writer), state="s"
    )

    assert (code, error) == (None, None), (
        "Stray probe must return (None, None) so the shared future is not resolved"
    )
    assert probe_writer.captured.startswith(b"HTTP/1.1 404"), (
        f"Expected 404 response for probe; got: {probe_writer.captured[:80]!r}"
    )

    # --- sibling assertion: real callback path with missing code still errors ---
    callback_reader = _make_reader(b"GET /auth/callback?state=s HTTP/1.1\r\n\r\n")
    callback_writer = _FakeWriter()
    code2, error2 = await _handle_browser_callback(
        callback_reader, cast("asyncio.StreamWriter", callback_writer), state="s"
    )

    assert code2 is None, "No authorization code should be extracted"
    assert error2 is not None, (
        "A real /auth/callback request without a code must still produce an error"
    )
