from __future__ import annotations

from typing import cast

import aiohttp
import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from pydantic import SecretStr
from yarl import URL

from pythinker_code.config import Config, LLMModel, LLMProvider


def test_alibaba_model_catalog_contains_current_models():
    from pythinker_code.auth.alibaba import ALIBABA_MODELS

    aliases = {model.alias for model in ALIBABA_MODELS}
    assert aliases == {
        "alibaba/qwen3.7-max",
        "alibaba/qwen3.7-plus",
        "alibaba/qwen3.6-plus",
        "alibaba/qwen3.6-flash",
        "alibaba/qwen3-coder-plus",
        "alibaba/qwen3-coder-flash",
        "alibaba/deepseek-v4-pro",
        "alibaba/deepseek-v4-flash",
        "alibaba/deepseek-v3.2",
        "alibaba/kimi-k2.6",
        "alibaba/glm-5.1",
    }

    api_ids = {m.alias: m.model_id for m in ALIBABA_MODELS}
    assert api_ids == {
        "alibaba/qwen3.7-max": "qwen3.7-max",
        "alibaba/qwen3.7-plus": "qwen3.7-plus",
        "alibaba/qwen3.6-plus": "qwen3.6-plus",
        "alibaba/qwen3.6-flash": "qwen3.6-flash",
        "alibaba/qwen3-coder-plus": "qwen3-coder-plus",
        "alibaba/qwen3-coder-flash": "qwen3-coder-flash",
        "alibaba/deepseek-v4-pro": "deepseek-v4-pro",
        "alibaba/deepseek-v4-flash": "deepseek-v4-flash",
        "alibaba/deepseek-v3.2": "deepseek-v3.2",
        "alibaba/kimi-k2.6": "kimi-k2.6",
        "alibaba/glm-5.1": "glm-5.1",
    }

    assert all(m.provider_key == "managed:alibaba" for m in ALIBABA_MODELS)

    by_alias = {m.alias: m for m in ALIBABA_MODELS}
    assert by_alias["alibaba/qwen3.7-max"].capabilities == frozenset({"thinking", "image_in"})
    assert by_alias["alibaba/qwen3.7-max"].max_context_size == 1_000_000
    assert by_alias["alibaba/qwen3.7-plus"].capabilities == frozenset({"thinking", "image_in"})
    assert by_alias["alibaba/qwen3.7-plus"].max_context_size == 1_000_000
    assert by_alias["alibaba/qwen3.6-plus"].capabilities == frozenset({"thinking", "image_in"})
    assert by_alias["alibaba/qwen3.6-plus"].max_context_size == 1_000_000
    assert by_alias["alibaba/qwen3.6-flash"].capabilities == frozenset({"thinking", "image_in"})
    assert by_alias["alibaba/qwen3-coder-plus"].capabilities == frozenset({"thinking"})
    assert by_alias["alibaba/qwen3-coder-plus"].max_context_size == 1_000_000
    assert by_alias["alibaba/qwen3-coder-flash"].capabilities == frozenset({"thinking"})
    assert by_alias["alibaba/qwen3-coder-flash"].max_context_size == 1_000_000
    assert by_alias["alibaba/deepseek-v4-pro"].capabilities == frozenset({"thinking"})
    assert by_alias["alibaba/deepseek-v4-flash"].capabilities == frozenset({"thinking"})
    assert by_alias["alibaba/deepseek-v3.2"].capabilities == frozenset({"thinking"})
    assert by_alias["alibaba/deepseek-v3.2"].max_context_size == 128_000
    assert by_alias["alibaba/kimi-k2.6"].capabilities == frozenset({"thinking", "image_in"})
    assert by_alias["alibaba/glm-5.1"].capabilities == frozenset({"always_thinking"})


def test_alibaba_env_key_prefers_dashscope_api_key(monkeypatch):
    from pythinker_code.auth.alibaba import get_alibaba_api_key_from_env

    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("ALIBABA_API_KEY", raising=False)
    assert get_alibaba_api_key_from_env() is None

    monkeypatch.setenv("DASHSCOPE_API_KEY", "  sk-dashscope  ")
    assert get_alibaba_api_key_from_env() == "sk-dashscope"

    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    monkeypatch.setenv("ALIBABA_API_KEY", "sk-alibaba")
    assert get_alibaba_api_key_from_env() == "sk-alibaba"

    monkeypatch.delenv("ALIBABA_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    assert get_alibaba_api_key_from_env() is None


def test_alibaba_base_url_env_normalizes_workspace_endpoints(monkeypatch):
    from pythinker_code.auth.alibaba import ALIBABA_BASE_URL, get_alibaba_base_url_from_env

    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("ALIBABA_BASE_URL", raising=False)
    assert get_alibaba_base_url_from_env() == ALIBABA_BASE_URL

    monkeypatch.setenv(
        "DASHSCOPE_BASE_URL",
        "ws-example.ap-southeast-1.maas.aliyuncs.com",
    )
    assert (
        get_alibaba_base_url_from_env()
        == "https://ws-example.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    )

    monkeypatch.setenv(
        "DASHSCOPE_BASE_URL",
        "https://ws-example.ap-southeast-1.maas.aliyuncs.com/api/v1",
    )
    assert (
        get_alibaba_base_url_from_env()
        == "https://ws-example.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    )


def test_apply_alibaba_config_writes_provider_and_default():
    from pythinker_code.auth.alibaba import (
        ALIBABA_BASE_URL,
        ALIBABA_PROVIDER_KEY,
        _apply_alibaba_config,
    )

    config = Config(is_from_default_location=True)
    _apply_alibaba_config(config, SecretStr("sk-test"))

    assert set(config.providers) == {ALIBABA_PROVIDER_KEY}
    provider = config.providers[ALIBABA_PROVIDER_KEY]
    assert provider.type == "openai_legacy"
    assert provider.base_url == ALIBABA_BASE_URL
    assert provider.api_key.get_secret_value() == "sk-test"

    assert "alibaba/qwen3.6-plus" in config.models
    assert config.models["alibaba/qwen3.6-plus"].provider == ALIBABA_PROVIDER_KEY
    assert config.models["alibaba/qwen3.6-plus"].model == "qwen3.6-plus"
    assert config.models["alibaba/qwen3.7-max"].capabilities == frozenset({"thinking", "image_in"})
    assert config.models["alibaba/qwen3.6-plus"].capabilities == frozenset({"thinking", "image_in"})
    assert config.models["alibaba/qwen3.6-flash"].capabilities == frozenset(
        {"thinking", "image_in"}
    )
    assert config.models["alibaba/deepseek-v4-pro"].capabilities == frozenset({"thinking"})
    assert config.models["alibaba/kimi-k2.6"].capabilities == frozenset({"thinking", "image_in"})
    assert config.models["alibaba/glm-5.1"].capabilities == frozenset({"always_thinking"})
    assert "alibaba/minimax-m2.5" not in config.models
    assert config.default_model == "alibaba/qwen3.6-plus"
    assert config.default_thinking is True
    assert config.default_thinking_effort == "high"


def test_apply_alibaba_config_empty_catalog_preserves_non_alibaba_default():
    from pythinker_code.auth.alibaba import _apply_alibaba_config

    config = Config(is_from_default_location=True)
    config.providers["managed:openai"] = LLMProvider(
        type="openai_responses",
        base_url="https://api.openai.com/v1",
        api_key=SecretStr("sk-test"),
    )
    config.models["openai/gpt-5.2"] = LLMModel(
        provider="managed:openai",
        model="gpt-5.2",
        max_context_size=400_000,
    )
    config.default_model = "openai/gpt-5.2"

    _apply_alibaba_config(config, SecretStr("sk-test"), models=())

    assert config.default_model == "openai/gpt-5.2"
    assert "openai/gpt-5.2" in config.models
    assert not any(k.startswith("alibaba/") for k in config.models)


def test_alibaba_oauth_selector_status_uses_provider_key():
    from pythinker_code.auth.alibaba import ALIBABA_PROVIDER_KEY
    from pythinker_code.ui.shell import oauth

    login_entries = {entry.id: entry for entry in oauth._SELECTOR_PROVIDER_ENTRIES}
    logout_entries = {entry.id: entry for entry in oauth._LOGOUT_PROVIDER_ENTRIES}
    assert login_entries["alibaba"].name == "Alibaba (DashScope)"
    assert logout_entries["alibaba"].name == "Alibaba (DashScope)"

    config = Config(is_from_default_location=True)
    assert oauth._get_provider_status(config, "alibaba").source == "unconfigured"
    config.providers[ALIBABA_PROVIDER_KEY] = LLMProvider(
        type="openai_legacy",
        base_url="https://dashscope-us.aliyuncs.com/compatible-mode/v1",
        api_key=SecretStr("sk-test"),
    )
    assert oauth._get_provider_status(config, "alibaba").source == "configured"


def _request_info(url: str) -> aiohttp.RequestInfo:
    return aiohttp.RequestInfo(
        url=URL(url),
        method="GET",
        headers=CIMultiDictProxy(CIMultiDict()),
        real_url=URL(url),
    )


class _FakeAiohttpResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    async def __aenter__(self) -> _FakeAiohttpResponse:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def json(self, *, content_type: str | None = None) -> object:
        return self._payload


@pytest.mark.asyncio
async def test_discover_alibaba_models_uses_provided_base_url(monkeypatch):
    from pythinker_code.auth.alibaba import _discover_alibaba_models

    seen_urls: list[str] = []

    async def fake_request(*args: object, **kwargs: object) -> object:
        seen_urls.append(str(args[2]))
        return _FakeAiohttpResponse({"data": []})

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)

    await _discover_alibaba_models("sk-test", "https://custom.example.com/compatible-mode/v1")
    assert len(seen_urls) == 1
    assert "custom.example.com" in seen_urls[0]


@pytest.mark.asyncio
async def test_login_alibaba_saves_static_models_when_discovery_fails(monkeypatch, tmp_path):
    from pythinker_code.auth.alibaba import login_alibaba_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_request(*args: object, **kwargs: object) -> object:
        raise aiohttp.ClientConnectionError("models unavailable")

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)

    events = [event async for event in login_alibaba_api_key(config, "sk-test")]

    assert [event.type for event in events] == ["info", "success"]
    assert "sk-test" not in "\n".join(event.json for event in events)
    assert config.default_model == "alibaba/qwen3.6-plus"
    assert "alibaba/qwen3.7-max" in config.models
    assert "alibaba/qwen3.6-plus" in config.models
    assert (tmp_path / "config.toml").exists()


@pytest.mark.asyncio
async def test_login_alibaba_falls_back_on_non_auth_response_error(monkeypatch, tmp_path):
    from pythinker_code.auth.alibaba import login_alibaba_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_request(*args: object, **kwargs: object) -> object:
        raise aiohttp.ClientResponseError(
            _request_info("https://dashscope-us.aliyuncs.com/compatible-mode/v1/models"),
            (),
            status=503,
            message="Service Unavailable",
        )

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)

    events = [event async for event in login_alibaba_api_key(config, "sk-test")]

    assert [event.type for event in events] == ["info", "success"]
    assert config.default_model == "alibaba/qwen3.6-plus"


@pytest.mark.asyncio
async def test_login_alibaba_rejects_401(monkeypatch, tmp_path):
    from pythinker_code.auth.alibaba import login_alibaba_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_request(*args: object, **kwargs: object) -> object:
        raise aiohttp.ClientResponseError(
            _request_info("https://dashscope-us.aliyuncs.com/compatible-mode/v1/models"),
            (),
            status=401,
            message="Unauthorized",
        )

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)

    events = [event async for event in login_alibaba_api_key(config, "bad-key")]

    assert events[-1].type == "error"
    assert "Alibaba" in events[-1].message
    assert "API key" in events[-1].message
    assert config.providers == {}
    assert config.models == {}


@pytest.mark.asyncio
async def test_login_alibaba_china_key_auto_detected(monkeypatch, tmp_path):
    """A China-region key that fails on US but succeeds on China is auto-configured."""
    from pythinker_code.auth.alibaba import ALIBABA_CHINA_BASE_URL, login_alibaba_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("ALIBABA_BASE_URL", raising=False)
    config = Config(is_from_default_location=True)

    async def fake_request(*args: object, **kwargs: object) -> object:
        url = str(args[2])
        if "dashscope-us" in url:
            raise aiohttp.ClientResponseError(
                _request_info(url), (), status=401, message="Unauthorized"
            )
        return _FakeAiohttpResponse({"data": [{"id": "qwen3.6-plus", "context_length": 1_000_000}]})

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)

    events = [event async for event in login_alibaba_api_key(config, "sk-china-key")]

    types = [e.type for e in events]
    assert types == ["info", "success"], types
    assert "China" in events[0].message
    provider = next(iter(config.providers.values()))
    assert provider.base_url == ALIBABA_CHINA_BASE_URL
    assert config.models["alibaba/qwen3.6-plus"].max_context_size == 1_000_000
    assert (tmp_path / "config.toml").exists()


@pytest.mark.asyncio
async def test_login_alibaba_china_probe_network_error_configures_china(monkeypatch, tmp_path):
    """When US returns 401 and China is unreachable, we still configure for China."""
    from pythinker_code.auth.alibaba import ALIBABA_CHINA_BASE_URL, login_alibaba_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("ALIBABA_BASE_URL", raising=False)
    config = Config(is_from_default_location=True)

    async def fake_request(*args: object, **kwargs: object) -> object:
        url = str(args[2])
        if "dashscope-us" in url:
            raise aiohttp.ClientResponseError(
                _request_info(url), (), status=401, message="Unauthorized"
            )
        raise aiohttp.ClientConnectionError("China unreachable")

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)

    events = [event async for event in login_alibaba_api_key(config, "sk-china-key")]

    types = [e.type for e in events]
    assert types == ["info", "success"], types
    assert "China" in events[0].message
    provider = next(iter(config.providers.values()))
    assert provider.base_url == ALIBABA_CHINA_BASE_URL
    assert "alibaba/qwen3.6-plus" in config.models
    assert (tmp_path / "config.toml").exists()


@pytest.mark.asyncio
async def test_login_alibaba_primary_already_china_401_fails(monkeypatch, tmp_path):
    """When DASHSCOPE_BASE_URL is already China and it returns 401, fail without probing again."""
    from pythinker_code.auth.alibaba import ALIBABA_CHINA_BASE_URL, login_alibaba_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    monkeypatch.setenv("DASHSCOPE_BASE_URL", ALIBABA_CHINA_BASE_URL)
    config = Config(is_from_default_location=True)

    call_count = 0

    async def fake_request(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        url = str(args[2])
        raise aiohttp.ClientResponseError(
            _request_info(url), (), status=401, message="Unauthorized"
        )

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)

    events = [event async for event in login_alibaba_api_key(config, "bad-key")]

    assert events[-1].type == "error"
    assert "Alibaba" in events[-1].message
    assert call_count == 1, "should not probe a second endpoint when primary is already China"
    assert config.providers == {}


@pytest.mark.asyncio
async def test_login_alibaba_workspace_key_gives_targeted_error(monkeypatch, tmp_path):
    """sk-ws- workspace keys get a targeted error with DASHSCOPE_BASE_URL guidance."""
    from pythinker_code.auth.alibaba import login_alibaba_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("ALIBABA_BASE_URL", raising=False)
    config = Config(is_from_default_location=True)

    call_count = 0

    async def fake_request(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        url = str(args[2])
        raise aiohttp.ClientResponseError(
            _request_info(url), (), status=401, message="Unauthorized"
        )

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)

    events = [
        event
        async for event in login_alibaba_api_key(
            config, "sk-ws-H.HXDYIP.c9u4.abcdefghijklmnopqrstuvwxyz"
        )
    ]

    assert events[-1].type == "error"
    assert "sk-ws-" in events[-1].message
    assert "DASHSCOPE_BASE_URL" in events[-1].message
    assert call_count == 1, "should not probe China for workspace keys"
    assert config.providers == {}


@pytest.mark.asyncio
async def test_login_alibaba_workspace_key_with_correct_base_url_succeeds(monkeypatch, tmp_path):
    """sk-ws- key succeeds when DASHSCOPE_BASE_URL is set to the workspace endpoint."""
    from pythinker_code.auth.alibaba import login_alibaba_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DASHSCOPE_BASE_URL",
        "ws-kopy0du82ky7144q.ap-southeast-1.maas.aliyuncs.com",
    )
    config = Config(is_from_default_location=True)

    async def fake_request(*args: object, **kwargs: object) -> object:
        return _FakeAiohttpResponse({"data": [{"id": "qwen3.6-plus"}]})

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)

    events = [
        event
        async for event in login_alibaba_api_key(
            config, "sk-ws-H.HXDYIP.c9u4.abcdefghijklmnopqrstuvwxyz"
        )
    ]

    assert events[-1].type == "success"
    provider = next(iter(config.providers.values()))
    assert "ws-kopy0du82ky7144q" in provider.base_url
    assert (tmp_path / "config.toml").exists()


@pytest.mark.asyncio
async def test_login_alibaba_uses_discovered_context_length(monkeypatch, tmp_path):
    from pythinker_code.auth.alibaba import login_alibaba_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_request(*args: object, **kwargs: object) -> object:
        headers = cast("dict[str, object]", kwargs.get("headers", {}))
        assert headers.get("Authorization") == "Bearer sk-test"
        return _FakeAiohttpResponse({"data": [{"id": "qwen3.7-max", "context_length": 512_000}]})

    monkeypatch.setattr(aiohttp.ClientSession, "_request", fake_request)

    events = [event async for event in login_alibaba_api_key(config, "sk-test")]

    assert events[-1].type == "success"
    assert config.models["alibaba/qwen3.7-max"].max_context_size == 512_000
    assert config.models["alibaba/qwen3.7-max"].capabilities == frozenset({"thinking", "image_in"})


@pytest.mark.asyncio
async def test_login_alibaba_requires_key(monkeypatch, tmp_path):
    from pythinker_code.auth.alibaba import login_alibaba_api_key

    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("ALIBABA_API_KEY", raising=False)
    config = Config(is_from_default_location=True)

    events = [event async for event in login_alibaba_api_key(config, "")]

    assert events[-1].type == "error"
    assert "Alibaba" in events[-1].message
    assert "API key" in events[-1].message


@pytest.mark.parametrize(
    ("payload", "expected_aliases"),
    [
        (None, set()),
        ({}, set()),
        ({"data": "not a list"}, set()),
        ({"data": [{"context_length": 1000}]}, set()),
        ({"data": [{"id": "unknown-model-xyz"}]}, set()),
        ({"data": [{"id": "qwen3.7-max"}]}, {"alibaba/qwen3.7-max"}),
        ({"data": [{"id": "deepseek-v3.2"}]}, {"alibaba/deepseek-v3.2"}),
    ],
)
def test_parse_discovered_alibaba_models_handles_malformed_payloads(payload, expected_aliases):
    from pythinker_code.auth.alibaba import _parse_discovered_models

    result = _parse_discovered_models(payload)
    assert {m.alias for m in result} == expected_aliases


def test_parse_discovered_alibaba_models_overrides_context_length_only_for_positive_int():
    from pythinker_code.auth.alibaba import _parse_discovered_models

    payload = {
        "data": [
            {"id": "qwen3.7-max", "context_length": "bogus"},
            {"id": "qwen3.6-plus", "context_length": -5},
            {"id": "deepseek-v3.2", "context_length": 512_000},
        ]
    }
    result = _parse_discovered_models(payload)
    by_id = {m.model_id: m for m in result}
    assert by_id["qwen3.7-max"].max_context_size == 1_000_000
    assert by_id["qwen3.6-plus"].max_context_size == 1_000_000
    assert by_id["deepseek-v3.2"].max_context_size == 512_000


def test_parse_discovered_alibaba_models_preserves_capabilities():
    from pythinker_code.auth.alibaba import _parse_discovered_models

    payload = {
        "data": [
            {"id": "qwen3.6-plus", "context_length": 900_000},
            {"id": "deepseek-v3.2"},
        ]
    }
    result = _parse_discovered_models(payload)
    by_id = {m.model_id: m for m in result}
    assert by_id["qwen3.6-plus"].capabilities == frozenset({"thinking", "image_in"})
    assert by_id["deepseek-v3.2"].capabilities == frozenset({"thinking"})


@pytest.mark.asyncio
async def test_logout_alibaba_removes_only_alibaba(monkeypatch, tmp_path):
    from pythinker_code.auth.alibaba import (
        ALIBABA_PROVIDER_KEY,
        _apply_alibaba_config,
        logout_alibaba,
    )

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)
    config.providers["managed:openai"] = LLMProvider(
        type="openai_responses",
        base_url="https://api.openai.com/v1",
        api_key=SecretStr("sk-test"),
    )
    config.models["openai/gpt-5.2"] = LLMModel(
        provider="managed:openai",
        model="gpt-5.2",
        max_context_size=400_000,
    )
    _apply_alibaba_config(config, SecretStr("sk-test"))

    events = [event async for event in logout_alibaba(config)]

    assert events[-1].type == "success"
    assert ALIBABA_PROVIDER_KEY not in config.providers
    assert not any(k.startswith("alibaba/") for k in config.models)
    assert "managed:openai" in config.providers
    assert "openai/gpt-5.2" in config.models
    assert config.default_model == "openai/gpt-5.2"


@pytest.mark.asyncio
async def test_logout_alibaba_rejects_non_default_config_location():
    from pythinker_code.auth.alibaba import logout_alibaba

    config = Config(is_from_default_location=False)

    events = [event async for event in logout_alibaba(config)]

    assert events[-1].type == "error"
    assert "default config file" in events[-1].message
    assert config.providers == {}
    assert config.models == {}
