from __future__ import annotations

import aiohttp
import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from pydantic import SecretStr
from yarl import URL

from pythinker_code.config import Config


def _request_info(url: str) -> aiohttp.RequestInfo:
    return aiohttp.RequestInfo(
        url=URL(url),
        method="GET",
        headers=CIMultiDictProxy(CIMultiDict()),
        real_url=URL(url),
    )


def test_kimi_catalog_defaults_to_k27_code():
    from pythinker_code.auth.kimi import KIMI_DEFAULT_MODEL_ALIAS, KIMI_MODELS

    assert KIMI_DEFAULT_MODEL_ALIAS == "kimi/kimi-k2.7-code"
    aliases = {m.alias: m.model_id for m in KIMI_MODELS}
    assert aliases == {"kimi/kimi-k2.7-code": "kimi-k2.7-code"}
    assert all(m.provider_key == "managed:kimi" for m in KIMI_MODELS)
    k27 = next(m for m in KIMI_MODELS if m.alias == "kimi/kimi-k2.7-code")
    assert k27.max_context_size == 262_144


def test_kimi_env_key_falls_back_to_moonshot(monkeypatch):
    from pythinker_code.auth.kimi import get_kimi_api_key_from_env

    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    assert get_kimi_api_key_from_env() is None

    monkeypatch.setenv("MOONSHOT_API_KEY", "  ms-key  ")
    assert get_kimi_api_key_from_env() == "ms-key"

    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    assert get_kimi_api_key_from_env() == "kimi-key"


def test_apply_kimi_config_uses_anthropic_endpoint_and_default():
    from pythinker_code.auth.kimi import (
        KIMI_BASE_URL,
        KIMI_DEFAULT_MODEL_ALIAS,
        KIMI_PROVIDER_KEY,
        _apply_kimi_config,
    )

    config = Config(is_from_default_location=True)
    _apply_kimi_config(config, SecretStr("ms-test"))

    assert set(config.providers) == {KIMI_PROVIDER_KEY}
    provider = config.providers[KIMI_PROVIDER_KEY]
    assert provider.type == "anthropic"
    assert provider.base_url == KIMI_BASE_URL == "https://api.moonshot.ai/anthropic"
    assert provider.api_key.get_secret_value() == "ms-test"
    assert config.models["kimi/kimi-k2.7-code"].model == "kimi-k2.7-code"
    assert config.models["kimi/kimi-k2.7-code"].max_context_size == 262_144
    assert config.default_model == KIMI_DEFAULT_MODEL_ALIAS


@pytest.mark.parametrize(
    "payload, expected",
    [
        (None, None),
        ({}, None),
        ({"data": "nope"}, None),
        ({"data": [{"id": "unknown-model"}]}, set()),
        ({"data": [{"id": "kimi-k2.7-code"}]}, {"kimi/kimi-k2.7-code"}),
    ],
)
def test_parse_discovered_kimi_models(payload, expected):
    from pythinker_code.auth.kimi import _parse_discovered_models

    result = _parse_discovered_models(payload)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert {m.alias for m in result} == expected


def test_parse_discovered_kimi_uses_context_length_when_positive():
    from pythinker_code.auth.kimi import _parse_discovered_models

    result = _parse_discovered_models(
        {"data": [{"id": "kimi-k2.7-code", "context_length": 512_000}]}
    )
    assert result is not None
    assert result[0].max_context_size == 512_000


@pytest.mark.asyncio
async def test_login_kimi_saves_static_models_when_discovery_fails(monkeypatch, tmp_path):
    from pythinker_code.auth.kimi import login_kimi_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_discover(api_key: str):
        raise aiohttp.ClientConnectionError("models unavailable")

    monkeypatch.setattr("pythinker_code.auth.kimi._discover_kimi_models", fake_discover)

    events = [event async for event in login_kimi_api_key(config, "ms-test")]

    assert [e.type for e in events] == ["info", "success"]
    assert config.default_model == "kimi/kimi-k2.7-code"
    assert (tmp_path / "config.toml").exists()


@pytest.mark.asyncio
async def test_login_kimi_rejects_401(monkeypatch, tmp_path):
    from pythinker_code.auth.kimi import login_kimi_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_discover(api_key: str):
        raise aiohttp.ClientResponseError(
            _request_info("https://api.moonshot.ai/anthropic/v1/models"),
            (),
            status=401,
            message="Unauthorized",
        )

    monkeypatch.setattr("pythinker_code.auth.kimi._discover_kimi_models", fake_discover)

    events = [event async for event in login_kimi_api_key(config, "bad-key")]

    assert events[-1].type == "error"
    assert "Invalid Kimi API key" in events[-1].message
    assert config.providers == {}
    assert config.models == {}


@pytest.mark.asyncio
async def test_login_kimi_requires_key():
    from pythinker_code.auth.kimi import login_kimi_api_key

    config = Config(is_from_default_location=True)
    events = [event async for event in login_kimi_api_key(config, "")]

    assert events[-1].type == "error"
    assert events[-1].message == "Kimi API key is required."


@pytest.mark.asyncio
async def test_logout_kimi_removes_only_kimi(monkeypatch, tmp_path):
    from pythinker_code.auth.kimi import KIMI_PROVIDER_KEY, _apply_kimi_config, logout_kimi
    from pythinker_code.config import LLMModel, LLMProvider

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)
    config.providers["managed:openai"] = LLMProvider(
        type="openai_responses",
        base_url="https://api.openai.com/v1",
        api_key=SecretStr("sk-test"),
    )
    config.models["openai/gpt-5.2"] = LLMModel(
        provider="managed:openai", model="gpt-5.2", max_context_size=400_000
    )
    _apply_kimi_config(config, SecretStr("ms-test"))

    events = [event async for event in logout_kimi(config)]

    assert events[-1].type == "success"
    assert KIMI_PROVIDER_KEY not in config.providers
    assert "kimi/kimi-k2.7-code" not in config.models
    assert "managed:openai" in config.providers
    assert config.default_model == "openai/gpt-5.2"
