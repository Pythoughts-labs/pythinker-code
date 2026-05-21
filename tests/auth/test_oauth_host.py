import pytest


def test_oauth_host_rejects_http_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PYTHINKER_CODE_OAUTH_HOST", "http://evil.example.com")
    monkeypatch.delenv("PYTHINKER_OAUTH_HOST", raising=False)
    from pythinker_code.auth import oauth

    with pytest.raises(ValueError, match="HTTPS"):
        oauth._oauth_host()


def test_oauth_host_accepts_https_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PYTHINKER_CODE_OAUTH_HOST", "https://custom.example.com")
    monkeypatch.delenv("PYTHINKER_OAUTH_HOST", raising=False)
    from pythinker_code.auth import oauth

    assert oauth._oauth_host() == "https://custom.example.com"


def test_oauth_host_uses_default_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PYTHINKER_CODE_OAUTH_HOST", raising=False)
    monkeypatch.delenv("PYTHINKER_OAUTH_HOST", raising=False)
    from pythinker_code.auth import oauth

    host = oauth._oauth_host()
    assert host.startswith("https://")
