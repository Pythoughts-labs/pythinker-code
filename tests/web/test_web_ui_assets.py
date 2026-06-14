"""When the bundled frontend is missing, "/" must explain why, not 404.

Regression guard for the native installers that froze without building the
gitignored web/dashboard bundles: the served app answered ``GET /?token=...`` with a
bare 404 (see windows-installer.yml / linux-installer.yml web build steps).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient


def test_web_root_explains_missing_assets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import pythinker_code.web.app as web_app

    monkeypatch.setattr(web_app, "STATIC_DIR", tmp_path)
    app = web_app.create_app(session_token="test-token")
    client = TestClient(app)
    client.cookies.set("session_token", "test-token")

    resp = client.get("/")

    assert resp.status_code == 503
    assert "make build-web" in resp.text
    assert "pythinker_code/web/static/index.html" in resp.text


def test_dashboard_root_explains_missing_assets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import pythinker_code.dashboard.app as dashboard_app

    monkeypatch.setattr(dashboard_app, "STATIC_DIR", tmp_path)
    with TestClient(dashboard_app.create_app()) as client:
        resp = client.get("/")

    assert resp.status_code == 503
    assert "make build-dashboard" in resp.text
