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


def test_z_ai_model_catalog_contains_six_models():
    from pythinker_code.auth.z_ai import ZAI_MODELS

    aliases = {model.alias for model in ZAI_MODELS}
    assert aliases == {
        "z-ai/glm-5.2",
        "z-ai/glm-5.1",
        "z-ai/glm-5",
        "z-ai/glm-5-turbo",
        "z-ai/glm-4.7",
        "z-ai/glm-4.5-air",
    }

    api_ids = {m.alias: m.model_id for m in ZAI_MODELS}
    assert api_ids == {
        # The "[1m]" suffix is rejected by z.ai's Anthropic endpoint; the plain
        # id is what actually serves GLM-5.2 there.
        "z-ai/glm-5.2": "glm-5.2",
        "z-ai/glm-5.1": "glm-5.1",
        "z-ai/glm-5": "glm-5",
        "z-ai/glm-5-turbo": "glm-5-turbo",
        "z-ai/glm-4.7": "glm-4.7",
        "z-ai/glm-4.5-air": "glm-4.5-air",
    }

    assert all(m.provider_key == "managed:z-ai" for m in ZAI_MODELS)


def test_z_ai_glm52_is_default_with_plain_id_and_1m_context():
    from pythinker_code.auth.z_ai import ZAI_DEFAULT_MODEL_ALIAS, ZAI_MODELS

    assert ZAI_DEFAULT_MODEL_ALIAS == "z-ai/glm-5.2"
    glm52 = next(m for m in ZAI_MODELS if m.alias == "z-ai/glm-5.2")
    # Plain id (the "[1m]" suffix is rejected by the endpoint) but the plain id
    # already carries the full 1M window (verified empirically).
    assert glm52.model_id == "glm-5.2"
    assert glm52.max_context_size == 1_000_000


@pytest.mark.asyncio
async def test_login_z_ai_pins_glm52_when_discovery_omits_it(monkeypatch, tmp_path):
    """z.ai's /models listing does not include glm-5.2, but the model is usable.
    Pinning must keep it in the catalog and as the default after a successful
    discovery that returned other models."""
    from pythinker_code.auth.z_ai import ZaiModel, login_z_ai_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_discover(api_key: str):
        return (
            ZaiModel("glm-5.1", "glm-5.1", "GLM-5.1", max_context_size=204_800),
            ZaiModel("glm-4.6", "glm-4.6", "GLM-4.6"),
        )

    monkeypatch.setattr("pythinker_code.auth.z_ai._discover_z_ai_models", fake_discover)

    events = [event async for event in login_z_ai_api_key(config, "zai-test")]
    assert events[-1].type == "success"
    assert config.models["z-ai/glm-5.2"].model == "glm-5.2"
    assert config.default_model == "z-ai/glm-5.2"


def test_apply_z_ai_models_no_duplicate_when_api_lists_glm52():
    """If z.ai later returns glm-5.2 from /models, the discovered entry wins and
    the pin is dropped: glm-5.2 appears exactly once with the API definition."""
    from pythinker_code.auth.z_ai import (
        ZAI_PROVIDER_KEY,
        ZaiModel,
        _apply_z_ai_config,
        apply_z_ai_models,
    )

    config = Config(is_from_default_location=True)
    _apply_z_ai_config(config, SecretStr("zai-test"))

    apply_z_ai_models(
        config,
        (ZaiModel("glm-5.2", "glm-5.2", "GLM-5.2", max_context_size=400_000),),
    )

    glm52 = [a for a, m in config.models.items() if a == "z-ai/glm-5.2"]
    assert glm52 == ["z-ai/glm-5.2"]  # exactly one, no duplicate
    # The API-provided context window wins over the curated pin.
    assert config.models["z-ai/glm-5.2"].max_context_size == 400_000
    assert config.models["z-ai/glm-5.2"].provider == ZAI_PROVIDER_KEY


def test_z_ai_glm51_has_200k_context():
    from pythinker_code.auth.z_ai import ZAI_MODELS

    glm51 = next(m for m in ZAI_MODELS if m.model_id == "glm-5.1")
    assert glm51.max_context_size == 204_800


def test_z_ai_glm45air_has_96k_context():
    from pythinker_code.auth.z_ai import ZAI_MODELS

    air = next(m for m in ZAI_MODELS if m.model_id == "glm-4.5-air")
    assert air.max_context_size == 98_304


def test_z_ai_env_key_uses_zai_api_key(monkeypatch):
    from pythinker_code.auth.z_ai import get_z_ai_api_key_from_env

    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    assert get_z_ai_api_key_from_env() is None

    monkeypatch.setenv("ZAI_API_KEY", "  zai-key  ")
    assert get_z_ai_api_key_from_env() == "zai-key"

    monkeypatch.setenv("ZAI_API_KEY", "")
    assert get_z_ai_api_key_from_env() is None


@pytest.mark.parametrize(
    "payload, expected_aliases",
    [
        # Structurally invalid → None (no prune should happen)
        (None, None),
        ({}, None),
        ({"data": "not a list"}, None),
        # Valid structure, no matching models → empty tuple
        ({"data": [{"context_length": 1000}]}, set()),
        ({"data": [{"id": "unknown-model-xyz"}]}, set()),
        # Valid structure with known models
        ({"data": [{"id": "glm-5.1"}]}, {"z-ai/glm-5.1"}),
        ({"data": [{"id": "glm-5-turbo"}]}, {"z-ai/glm-5-turbo"}),
        (
            {"data": [{"id": "glm-4.7"}, {"id": "glm-4.5-air"}]},
            {"z-ai/glm-4.7", "z-ai/glm-4.5-air"},
        ),
    ],
)
def test_parse_discovered_z_ai_models_handles_payloads(payload, expected_aliases):
    from pythinker_code.auth.z_ai import _parse_discovered_models

    result = _parse_discovered_models(payload)
    if expected_aliases is None:
        assert result is None
    else:
        assert result is not None
        assert {m.alias for m in result} == expected_aliases


def test_parse_discovered_z_ai_models_uses_context_length_when_positive():
    from pythinker_code.auth.z_ai import _parse_discovered_models

    payload = {
        "data": [
            {"id": "glm-5.1", "context_length": 400_000},
            {"id": "glm-4.5-air", "context_length": -5},
            {"id": "glm-4.7", "context_length": "bogus"},
        ]
    }
    result = _parse_discovered_models(payload)
    assert result is not None
    by_id = {m.model_id: m for m in result}
    assert by_id["glm-5.1"].max_context_size == 400_000
    assert by_id["glm-4.5-air"].max_context_size == 98_304  # fallback to hardcoded
    assert by_id["glm-4.7"].max_context_size == 131_072  # fallback to hardcoded


def test_parse_discovered_z_ai_models_accepts_unknown_glm_future_models():
    from pythinker_code.auth.z_ai import _parse_discovered_models

    payload = {"data": [{"id": "glm-6.0", "context_length": 512_000}]}
    result = _parse_discovered_models(payload)
    assert result is not None
    assert len(result) == 1
    assert result[0].model_id == "glm-6.0"
    assert result[0].alias_suffix == "glm-6.0"
    assert result[0].max_context_size == 512_000


def test_parse_discovered_z_ai_models_deduplicates():
    from pythinker_code.auth.z_ai import _parse_discovered_models

    payload = {"data": [{"id": "glm-5.1"}, {"id": "glm-5.1"}]}
    result = _parse_discovered_models(payload)
    assert result is not None
    assert len(result) == 1


def test_apply_z_ai_config_writes_provider_and_default():
    from pythinker_code.auth.z_ai import (
        ZAI_BASE_URL,
        ZAI_DEFAULT_MODEL_ALIAS,
        ZAI_PROVIDER_KEY,
        _apply_z_ai_config,
    )

    config = Config(is_from_default_location=True)
    _apply_z_ai_config(config, SecretStr("zai-test"))

    assert set(config.providers) == {ZAI_PROVIDER_KEY}
    provider = config.providers[ZAI_PROVIDER_KEY]
    assert provider.type == "anthropic"
    assert provider.base_url == ZAI_BASE_URL
    assert provider.api_key.get_secret_value() == "zai-test"
    assert config.models["z-ai/glm-5.1"].provider == ZAI_PROVIDER_KEY
    assert config.models["z-ai/glm-5.1"].model == "glm-5.1"
    assert config.models["z-ai/glm-5.1"].max_context_size == 204_800
    assert config.default_model == ZAI_DEFAULT_MODEL_ALIAS


def test_apply_z_ai_config_replaces_existing_z_ai_models():
    from pythinker_code.auth.z_ai import (
        ZAI_PROVIDER_KEY,
        ZaiModel,
        _apply_z_ai_config,
    )

    config = Config(is_from_default_location=True)
    _apply_z_ai_config(config, SecretStr("zai-test"))

    new_models = (ZaiModel("glm-5.1", "glm-5.1", "GLM-5.1 New", max_context_size=300_000),)
    _apply_z_ai_config(config, SecretStr("zai-test-2"), models=new_models)

    z_ai_aliases = {a for a, m in config.models.items() if m.provider == ZAI_PROVIDER_KEY}
    # The replaced catalog plus the always-pinned GLM-5.2 default.
    assert z_ai_aliases == {"z-ai/glm-5.2", "z-ai/glm-5.1"}
    assert config.models["z-ai/glm-5.1"].max_context_size == 300_000


@pytest.mark.asyncio
async def test_login_z_ai_saves_static_models_when_discovery_fails(monkeypatch, tmp_path):
    from pythinker_code.auth.z_ai import login_z_ai_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_discover(api_key: str):
        assert api_key == "zai-test"
        raise aiohttp.ClientConnectionError("models unavailable")

    monkeypatch.setattr("pythinker_code.auth.z_ai._discover_z_ai_models", fake_discover)

    events = [event async for event in login_z_ai_api_key(config, "zai-test")]

    assert [e.type for e in events] == ["info", "success"]
    assert config.default_model == "z-ai/glm-5.2"
    assert "z-ai/glm-5-turbo" in config.models
    assert (tmp_path / "config.toml").exists()


@pytest.mark.asyncio
async def test_login_z_ai_falls_back_on_non_auth_response_error(monkeypatch, tmp_path):
    from pythinker_code.auth.z_ai import login_z_ai_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_discover(api_key: str):
        raise aiohttp.ClientResponseError(
            _request_info("https://api.z.ai/api/anthropic/v1/models"),
            (),
            status=503,
            message="Service Unavailable",
        )

    monkeypatch.setattr("pythinker_code.auth.z_ai._discover_z_ai_models", fake_discover)

    events = [event async for event in login_z_ai_api_key(config, "zai-test")]

    assert [e.type for e in events] == ["info", "success"]
    assert config.default_model == "z-ai/glm-5.2"


@pytest.mark.asyncio
async def test_login_z_ai_rejects_401(monkeypatch, tmp_path):
    from pythinker_code.auth.z_ai import login_z_ai_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_discover(api_key: str):
        raise aiohttp.ClientResponseError(
            _request_info("https://api.z.ai/api/anthropic/v1/models"),
            (),
            status=401,
            message="Unauthorized",
        )

    monkeypatch.setattr("pythinker_code.auth.z_ai._discover_z_ai_models", fake_discover)

    events = [event async for event in login_z_ai_api_key(config, "bad-key")]

    assert events[-1].type == "error"
    assert "Invalid Z AI API key" in events[-1].message
    assert config.providers == {}
    assert config.models == {}


@pytest.mark.asyncio
async def test_login_z_ai_uses_discovered_context_length(monkeypatch, tmp_path):
    from pythinker_code.auth.z_ai import ZaiModel, login_z_ai_api_key

    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    config = Config(is_from_default_location=True)

    async def fake_discover(api_key: str):
        return (ZaiModel("glm-5.1", "glm-5.1", "GLM-5.1", max_context_size=512_000),)

    monkeypatch.setattr("pythinker_code.auth.z_ai._discover_z_ai_models", fake_discover)

    events = [event async for event in login_z_ai_api_key(config, "zai-test")]

    assert events[-1].type == "success"
    assert config.models["z-ai/glm-5.1"].max_context_size == 512_000


@pytest.mark.asyncio
async def test_login_z_ai_requires_key(tmp_path):
    from pythinker_code.auth.z_ai import login_z_ai_api_key

    config = Config(is_from_default_location=True)

    events = [event async for event in login_z_ai_api_key(config, "")]

    assert events[-1].type == "error"
    assert events[-1].message == "Z AI API key is required."


@pytest.mark.asyncio
async def test_logout_z_ai_removes_only_z_ai(monkeypatch, tmp_path):
    from pythinker_code.auth.z_ai import (
        ZAI_PROVIDER_KEY,
        _apply_z_ai_config,
        logout_z_ai,
    )
    from pythinker_code.config import LLMModel, LLMProvider

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
    _apply_z_ai_config(config, SecretStr("zai-test"))

    events = [event async for event in logout_z_ai(config)]

    assert events[-1].type == "success"
    assert ZAI_PROVIDER_KEY not in config.providers
    assert "z-ai/glm-5.1" not in config.models
    assert "managed:openai" in config.providers
    assert "openai/gpt-5.2" in config.models
    assert config.default_model == "openai/gpt-5.2"


@pytest.mark.asyncio
async def test_logout_z_ai_rejects_non_default_config_location():
    from pythinker_code.auth.z_ai import logout_z_ai

    config = Config(is_from_default_location=False)

    events = [event async for event in logout_z_ai(config)]

    assert events[-1].type == "error"
    assert "default config file" in events[-1].message
    assert config.providers == {}


def test_apply_z_ai_models_prunes_stale_models_and_preserves_user_default():
    from pythinker_code.auth.z_ai import (
        ZAI_PROVIDER_KEY,
        ZaiModel,
        _apply_z_ai_config,
        apply_z_ai_models,
    )

    config = Config(is_from_default_location=True)
    _apply_z_ai_config(config, SecretStr("zai-test"))
    config.default_model = "z-ai/glm-5.1"

    discovered = (
        ZaiModel("glm-5.1", "glm-5.1", "GLM-5.1", max_context_size=400_000),
        ZaiModel("glm-6.0", "glm-6.0", "GLM-6.0", max_context_size=512_000),
    )

    changed = apply_z_ai_models(config, discovered)

    assert changed is True
    z_ai_aliases = {a for a, m in config.models.items() if m.provider == ZAI_PROVIDER_KEY}
    # GLM-5.2 is always pinned even when discovery omits it.
    assert z_ai_aliases == {"z-ai/glm-5.2", "z-ai/glm-5.1", "z-ai/glm-6.0"}
    assert config.models["z-ai/glm-5.1"].max_context_size == 400_000
    assert config.default_model == "z-ai/glm-5.1"


def test_apply_z_ai_models_reassigns_default_when_it_disappears():
    from pythinker_code.auth.z_ai import (
        ZaiModel,
        _apply_z_ai_config,
        apply_z_ai_models,
    )

    config = Config(is_from_default_location=True)
    _apply_z_ai_config(
        config,
        SecretStr("zai-test"),
        models=(ZaiModel("glm-5.1", "glm-5.1", "GLM-5.1"),),
    )
    config.default_model = "z-ai/glm-5.1"

    changed = apply_z_ai_models(
        config,
        (ZaiModel("glm-5-turbo", "glm-5-turbo", "GLM-5-Turbo"),),
    )

    assert changed is True
    assert "z-ai/glm-5.1" not in config.models
    assert "z-ai/glm-5-turbo" in config.models
    # The disappeared default falls back to the first alias, which is the always
    # pinned GLM-5.2.
    assert config.default_model == "z-ai/glm-5.2"


def test_apply_z_ai_models_returns_false_for_noop():
    from pythinker_code.auth.z_ai import (
        ZAI_MODELS,
        _apply_z_ai_config,
        apply_z_ai_models,
    )

    config = Config(is_from_default_location=True)
    _apply_z_ai_config(config, SecretStr("zai-test"))

    assert apply_z_ai_models(config, ZAI_MODELS) is False


def test_apply_z_ai_config_defaults_thinking_off():
    """Z.ai is wired to its Anthropic-compatible endpoint, which (verified
    empirically 2026-06-03 against glm-5.1) defaults thinking OFF and honors
    `thinking: {"type": "disabled"}`. The login default of effort="off"
    therefore matches the endpoint's native behavior. If the provider type or
    base_url ever moves to the OpenAI-compatible endpoint (which defaults
    thinking ON for GLM-5.x), these defaults must be re-evaluated.
    """
    from pythinker_code.auth.z_ai import _apply_z_ai_config

    config = Config(is_from_default_location=True)
    assert config.default_thinking_effort is None
    _apply_z_ai_config(config, SecretStr("zai-test"))

    assert config.providers["managed:z-ai"].type == "anthropic"
    assert config.default_thinking is False  # unchanged from Config default
    assert config.default_thinking_effort == "off"


def test_apply_z_ai_config_preserves_legacy_thinking_true():
    """Users with legacy default_thinking=True must not be silently downgraded."""
    from pythinker_code.auth.z_ai import _apply_z_ai_config

    config = Config(is_from_default_location=True)
    config.default_thinking = True
    # effort unset — the legacy path
    assert config.default_thinking_effort is None
    _apply_z_ai_config(config, SecretStr("zai-test"))

    assert config.default_thinking is True
    assert config.default_thinking_effort is None


def test_apply_z_ai_config_preserves_existing_effort_choice():
    from pythinker_code.auth.z_ai import _apply_z_ai_config

    config = Config(is_from_default_location=True)
    config.default_thinking = True
    config.default_thinking_effort = "medium"
    _apply_z_ai_config(config, SecretStr("zai-test"))

    assert config.default_thinking is True
    assert config.default_thinking_effort == "medium"
