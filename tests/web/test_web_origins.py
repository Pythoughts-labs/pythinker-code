"""Regression tests for allowed-origin population in local mode.

The local-mode web server enforces the origin check whenever token auth is
enabled. If no allowed origins are populated, every request carrying an
``Origin`` header is rejected — which breaks all WebSocket connections (they
always send ``Origin``) with a 403 handshake failure.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from pythinker_code.web.app import (
    ENV_ALLOWED_ORIGINS,
    ENV_ENFORCE_ORIGIN,
    ENV_SESSION_TOKEN,
    run_web_server,
)
from pythinker_code.web.auth import is_origin_allowed, normalize_allowed_origins

_ENV_KEYS = (
    ENV_ALLOWED_ORIGINS,
    ENV_ENFORCE_ORIGIN,
    ENV_SESSION_TOKEN,
    "PYTHINKER_WEB_RESTRICT_SENSITIVE_APIS",
    "PYTHINKER_WEB_LAN_ONLY",
)


@pytest.fixture
def restore_web_env() -> Iterator[None]:
    """Snapshot and restore env keys that run_web_server mutates."""
    saved = {key: os.environ.get(key) for key in _ENV_KEYS}
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_local_mode_populates_allowed_origins(
    restore_web_env: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured_port: dict[str, int] = {}

    def fake_uvicorn_run(*args: object, **kwargs: object) -> None:
        captured_port["port"] = int(kwargs["port"])  # type: ignore[arg-type]

    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)

    run_web_server(host="127.0.0.1", open_browser=False)
    capsys.readouterr()

    port = captured_port["port"]
    assert os.environ[ENV_ENFORCE_ORIGIN] == "1"

    origins = normalize_allowed_origins(os.environ.get(ENV_ALLOWED_ORIGINS))
    assert f"http://localhost:{port}" in origins
    assert f"http://127.0.0.1:{port}" in origins
    # No duplicates from the explicit-host branch.
    assert len(origins) == len(set(origins))

    # The browser's same-origin WebSocket handshake must pass the check.
    assert is_origin_allowed(f"http://127.0.0.1:{port}", origins)
    assert is_origin_allowed(f"http://localhost:{port}", origins)


def test_empty_allowlist_rejects_all_origins() -> None:
    """Documents why auto-population is required: [] means reject everything."""
    assert not is_origin_allowed("http://127.0.0.1:5494", [])
