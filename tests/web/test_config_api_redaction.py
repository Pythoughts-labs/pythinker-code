from pythinker_code.web.api.config import _redact_api_keys


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
