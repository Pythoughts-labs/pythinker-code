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


def test_z_ai_model_catalog_contains_five_models():
    from pythinker_code.auth.z_ai import ZAI_MODELS

    aliases = {model.alias for model in ZAI_MODELS}
    assert aliases == {
        "z-ai/glm-5.1",
        "z-ai/glm-5",
        "z-ai/glm-5-turbo",
        "z-ai/glm-4.7",
        "z-ai/glm-4.5-air",
    }

    api_ids = {m.alias: m.model_id for m in ZAI_MODELS}
    assert api_ids == {
        "z-ai/glm-5.1": "glm-5.1",
        "z-ai/glm-5": "glm-5",
        "z-ai/glm-5-turbo": "glm-5-turbo",
        "z-ai/glm-4.7": "glm-4.7",
        "z-ai/glm-4.5-air": "glm-4.5-air",
    }

    assert all(m.provider_key == "managed:z-ai" for m in ZAI_MODELS)


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
        (None, set()),
        ({}, set()),
        ({"data": "not a list"}, set()),
        ({"data": [{"context_length": 1000}]}, set()),
        ({"data": [{"id": "unknown-model-xyz"}]}, set()),
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
    by_id = {m.model_id: m for m in result}
    assert by_id["glm-5.1"].max_context_size == 400_000
    assert by_id["glm-4.5-air"].max_context_size == 98_304   # fallback to hardcoded
    assert by_id["glm-4.7"].max_context_size == 131_072       # fallback to hardcoded


def test_parse_discovered_z_ai_models_accepts_unknown_glm_future_models():
    from pythinker_code.auth.z_ai import _parse_discovered_models

    payload = {"data": [{"id": "glm-6.0", "context_length": 512_000}]}
    result = _parse_discovered_models(payload)
    assert len(result) == 1
    assert result[0].model_id == "glm-6.0"
    assert result[0].alias_suffix == "glm-6.0"
    assert result[0].max_context_size == 512_000


def test_parse_discovered_z_ai_models_deduplicates():
    from pythinker_code.auth.z_ai import _parse_discovered_models

    payload = {"data": [{"id": "glm-5.1"}, {"id": "glm-5.1"}]}
    result = _parse_discovered_models(payload)
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

    z_ai_aliases = [a for a, m in config.models.items() if m.provider == ZAI_PROVIDER_KEY]
    assert z_ai_aliases == ["z-ai/glm-5.1"]
    assert config.models["z-ai/glm-5.1"].max_context_size == 300_000
