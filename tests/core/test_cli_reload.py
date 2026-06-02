from __future__ import annotations

import json

from pythinker_code.cli import _load_mcp_configs_from_cli_inputs
from pythinker_code.cli.mcp import get_global_mcp_config_file


def test_load_mcp_configs_rechecks_default_file_between_reloads() -> None:
    """Reload must see MCP servers added after process startup."""
    default_mcp_file = get_global_mcp_config_file()
    assert not default_mcp_file.exists()
    assert _load_mcp_configs_from_cli_inputs(None, None) == []

    default_mcp_file.parent.mkdir(parents=True, exist_ok=True)
    expected = {
        "mcpServers": {"context7": {"url": "https://mcp.example.test", "transport": "http"}}
    }
    default_mcp_file.write_text(json.dumps(expected), encoding="utf-8")

    assert _load_mcp_configs_from_cli_inputs(None, None) == [expected]
