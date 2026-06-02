from __future__ import annotations

import json
from pathlib import Path

import pytest

from pythinker_code.cli import _load_mcp_configs_from_cli_inputs


def test_load_mcp_configs_rechecks_default_file_between_reloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reload must see MCP servers added after process startup."""
    default_mcp_file = tmp_path / "mcp" / "global.json"
    monkeypatch.setattr(
        "pythinker_code.cli.mcp.get_global_mcp_config_file", lambda: default_mcp_file
    )

    assert not default_mcp_file.exists()
    assert _load_mcp_configs_from_cli_inputs(None, None) == []

    default_mcp_file.parent.mkdir(parents=True, exist_ok=True)
    expected = {
        "mcpServers": {"context7": {"url": "https://mcp.example.test", "transport": "http"}}
    }
    default_mcp_file.write_text(json.dumps(expected), encoding="utf-8")

    assert _load_mcp_configs_from_cli_inputs(None, None) == [expected]
