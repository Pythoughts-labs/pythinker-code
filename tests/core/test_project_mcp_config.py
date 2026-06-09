"""mcpext-2(c): project-scoped .pythinker/mcp.json discovery layered over global."""

from __future__ import annotations

from pathlib import Path

import pytest

from pythinker_code.cli import _find_project_mcp_config_file, _load_mcp_configs_from_cli_inputs


def test_finds_project_mcp_config_at_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".pythinker").mkdir()
    cfg = tmp_path / ".pythinker" / "mcp.json"
    cfg.write_text('{"mcpServers": {}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    found = _find_project_mcp_config_file()
    assert found is not None
    assert found.samefile(cfg)


def test_finds_project_mcp_config_from_subdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".pythinker").mkdir()
    cfg = tmp_path / ".pythinker" / "mcp.json"
    cfg.write_text('{"mcpServers": {}}', encoding="utf-8")
    sub = tmp_path / "packages" / "app"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)

    found = _find_project_mcp_config_file()
    assert found is not None
    assert found.samefile(cfg)


def test_no_project_mcp_config_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()  # repo root with no .pythinker/mcp.json
    monkeypatch.chdir(tmp_path)
    assert _find_project_mcp_config_file() is None


def test_project_config_layered_over_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Isolate the global config to an empty share dir so only the project file loads.
    share = tmp_path / "share"
    share.mkdir()
    monkeypatch.setenv("PYTHINKER_SHARE_DIR", str(share))

    (tmp_path / ".git").mkdir()
    (tmp_path / ".pythinker").mkdir()
    (tmp_path / ".pythinker" / "mcp.json").write_text(
        '{"mcpServers": {"proj": {"command": "x", "args": []}}}', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    configs = _load_mcp_configs_from_cli_inputs(None, None)
    servers = {name for c in configs for name in c.get("mcpServers", {})}
    assert "proj" in servers
