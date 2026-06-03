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
