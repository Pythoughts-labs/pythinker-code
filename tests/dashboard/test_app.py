from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pythinker_code.dashboard.api import system as dashboard_system_api
from pythinker_code.dashboard.app import create_app, loopback_browser_host
from pythinker_code.metadata import Metadata, WorkDirMeta, save_metadata


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("0.0.0.0", "localhost"),
        ("::", "localhost"),
        ("127.0.0.1", "127.0.0.1"),
        ("192.168.1.5", "192.168.1.5"),
    ],
)
def test_loopback_browser_host_maps_wildcard_to_localhost(host: str, expected: str) -> None:
    # Wildcard bind addresses are not valid browser origins, so they must fall
    # back to localhost (which is the only loopback entry in allowed_origins).
    assert loopback_browser_host(host) == expected


def test_dashboard_sessions_include_session_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))

    work_dir = tmp_path / "project"
    work_dir.mkdir()
    metadata = Metadata(work_dirs=[WorkDirMeta(path=str(work_dir))])
    save_metadata(metadata)

    session_dir = metadata.work_dirs[0].sessions_dir / "session123"
    session_dir.mkdir(parents=True)
    (session_dir / "context.jsonl").write_text("{}\n", encoding="utf-8")

    with TestClient(create_app()) as client:
        response = client.get("/api/dashboard/sessions")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["session_id"] == "session123"
    assert payload[0]["session_dir"] == str(session_dir)
    assert payload[0]["work_dir"] == str(work_dir)


def test_dashboard_app_mounts_open_in_route() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/open-in",
            json={"app": "finder", "path": "/definitely/missing/path"},
        )

    assert response.status_code == 400


def test_dashboard_capabilities_report_open_in_support(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_system_api.sys, "platform", "linux")

    with TestClient(create_app()) as client:
        response = client.get("/api/dashboard/capabilities")

    assert response.status_code == 200
    assert response.json() == {"open_in_supported": False}


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_dashboard_import_rejects_zip_slip_entries(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    payload = _zip_bytes({"wire.jsonl": "{}\n", "../evil.txt": "owned"})

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/dashboard/sessions/import",
            files={"file": ("session.zip", payload, "application/zip")},
        )

    assert response.status_code == 400
    assert "unsafe path" in response.json()["detail"]
    assert not (tmp_path / "evil.txt").exists()


def test_dashboard_import_rejects_dot_member(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    payload = _zip_bytes({"wire.jsonl": "{}\n", ".": ""})

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/dashboard/sessions/import",
            files={"file": ("session.zip", payload, "application/zip")},
        )

    imported_root = tmp_path / "imported_sessions"
    assert response.status_code == 400
    assert "unsafe path" in response.json()["detail"]
    assert not imported_root.exists() or list(imported_root.iterdir()) == []


def test_dashboard_import_accepts_safe_zip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(tmp_path))
    payload = _zip_bytes({"session/wire.jsonl": "{}\n"})

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/dashboard/sessions/import",
            files={"file": ("session.zip", payload, "application/zip")},
        )

    assert response.status_code == 200
    imported = tmp_path / "imported_sessions" / response.json()["session_id"]
    assert (imported / "wire.jsonl").read_text(encoding="utf-8") == "{}\n"
