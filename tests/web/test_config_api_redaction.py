from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pythinker_code.config import Config
from pythinker_code.web.api import config as config_api
from pythinker_code.web.api.config import (
    UpdateConfigTomlRequest,
    _redact_api_keys,
    update_config_toml,
)


def test_redact_replaces_api_key_value():
    toml = 'api_key = "sk-ant-api-1234567890abcdef"\n'
    result = _redact_api_keys(toml)
    assert "sk-ant-api-1234567890abcdef" not in result
    assert 'api_key = "***"' in result


def test_redact_leaves_other_fields_unchanged():
    toml = 'base_url = "https://api.example.com"\nname = "gpt-4"\n'
    assert _redact_api_keys(toml) == toml


def test_redact_handles_empty_string():
    assert _redact_api_keys("") == ""


def test_redact_handles_no_api_keys():
    toml = '[model]\nname = "claude"\n'
    assert _redact_api_keys(toml) == toml


# ---------------------------------------------------------------------------
# WS5 — base_url validation on config.toml writes
# ---------------------------------------------------------------------------

_INITIAL_TOML = """\
default_model = "m1"

[providers.myprovider]
type = "openai_legacy"
base_url = "https://safe.example.com"
api_key = "sk-test"

[models.m1]
model = "gpt-4"
provider = "myprovider"
max_context_size = 128000
"""

_HTTP_REQUEST = cast(
    Any,
    SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(restrict_sensitive_apis=False))),
)


@pytest.fixture()
def patched_config(monkeypatch, tmp_path: Path):
    """Redirect config file I/O and load_config to an isolated temp file."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(_INITIAL_TOML, encoding="utf-8")

    # Redirect get_config_file so the PUT writes to tmp_path
    monkeypatch.setattr(config_api, "get_config_file", lambda: config_file)

    # Redirect load_config so validation reads the same temp config
    from pythinker_code.config import load_config_from_string

    def fake_load_config(*_args: object, **_kwargs: object) -> Config:
        return load_config_from_string(config_file.read_text(encoding="utf-8"))

    monkeypatch.setattr(config_api, "load_config", fake_load_config)

    return config_file


async def test_update_config_toml_rejects_insecure_base_url(patched_config: Path) -> None:
    """PUT /api/config/toml with http:// provider base_url must return 400."""
    from fastapi import HTTPException

    evil_toml = """\
default_model = "m1"

[providers.myprovider]
type = "openai_legacy"
base_url = "http://evil.example.com"
api_key = "sk-test"

[models.m1]
model = "gpt-4"
provider = "myprovider"
max_context_size = 128000
"""
    with pytest.raises(HTTPException) as exc_info:
        await update_config_toml(
            UpdateConfigTomlRequest(content=evil_toml),
            _HTTP_REQUEST,
        )

    assert exc_info.value.status_code == 400
    assert "https" in exc_info.value.detail.lower()

    # Config file must be unchanged (no write occurred)
    assert patched_config.read_text(encoding="utf-8") == _INITIAL_TOML

    # Companion: https:// base_url succeeds
    safe_toml = """\
default_model = "m1"

[providers.myprovider]
type = "openai_legacy"
base_url = "https://new-safe.example.com"
api_key = "sk-test"

[models.m1]
model = "gpt-4"
provider = "myprovider"
max_context_size = 128000
"""
    result = await update_config_toml(
        UpdateConfigTomlRequest(content=safe_toml),
        _HTTP_REQUEST,
    )
    assert result.success is True
