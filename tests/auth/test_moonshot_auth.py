from __future__ import annotations

from pydantic import SecretStr

from pythinker_code.config import Config


def test_moonshot_defaults_to_k27_code():
    from pythinker_code.auth.moonshot import MOONSHOT_DEFAULT_MODEL_ALIAS, MOONSHOT_MODELS

    assert MOONSHOT_DEFAULT_MODEL_ALIAS == "moonshot/kimi-k2.7-code"
    aliases = {m.alias for m in MOONSHOT_MODELS}
    assert "moonshot/kimi-k2.7-code" in aliases
    # Existing models remain available.
    assert "moonshot/kimi-k2.6" in aliases


def test_apply_moonshot_config_sets_k27_default():
    from pythinker_code.auth.moonshot import MOONSHOT_PROVIDER_KEY, _apply_moonshot_config

    config = Config(is_from_default_location=True)
    _apply_moonshot_config(config, SecretStr("ms-test"))

    assert config.providers[MOONSHOT_PROVIDER_KEY].type == "openai_legacy"
    assert config.models["moonshot/kimi-k2.7-code"].model == "kimi-k2.7-code"
    assert config.default_model == "moonshot/kimi-k2.7-code"
