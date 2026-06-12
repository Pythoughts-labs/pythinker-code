"""Per-server MCP tool allow/deny filtering (mcp.json enabledTools/disabledTools).

Noisy servers flood the model tool list with every tool they expose;
filtering scopes them at list time (never registered) and re-checks at
call time as defense in depth for shared tool maps.
"""

from __future__ import annotations

from typing import Any, cast

import mcp.types
import pytest
from fastmcp.mcp_config import MCPConfig

from pythinker_code.soul.toolset import (
    MCPServerInfo,
    MCPTool,
    McpToolFilter,
    PythinkerToolset,
)


class _ListingClient:
    def __init__(self, tool_names: list[str], *, fail_on_call: bool = False) -> None:
        self._tool_names = tool_names
        self.calls: list[str] = []
        self._fail_on_call = fail_on_call

    async def __aenter__(self) -> _ListingClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def list_tools(self) -> list[mcp.types.Tool]:
        return [mcp.types.Tool(name=name, inputSchema={}) for name in self._tool_names]

    async def list_resources(self) -> list[object]:
        return []

    async def list_prompts(self) -> list[object]:
        return []

    async def call_tool(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("call_tool must not be reached for a filtered tool")


class TestFilterSemantics:
    def test_no_filter_allows_everything(self) -> None:
        assert McpToolFilter().allows("anything") is True

    def test_enabled_list_is_exclusive(self) -> None:
        flt = McpToolFilter(enabled=frozenset({"a"}))
        assert flt.allows("a") is True
        assert flt.allows("b") is False

    def test_disabled_blocks(self) -> None:
        flt = McpToolFilter(deny=frozenset({"b"}))
        assert flt.allows("a") is True
        assert flt.allows("b") is False

    def test_deny_wins_over_enabled(self) -> None:
        flt = McpToolFilter(enabled=frozenset({"a"}), deny=frozenset({"a"}))
        assert flt.allows("a") is False

    def test_from_server_config_reads_extras(self) -> None:
        config = MCPConfig.model_validate(
            {
                "mcpServers": {
                    "x": {
                        "command": "echo",
                        "args": [],
                        "enabledTools": ["a", "b"],
                        "disabledTools": ["b"],
                    }
                }
            }
        )

        flt = McpToolFilter.from_server_config(config.mcpServers["x"])

        assert flt.allows("a") is True
        assert flt.allows("b") is False
        assert flt.allows("c") is False

    def test_from_server_config_defaults_permissive(self) -> None:
        config = MCPConfig.model_validate({"mcpServers": {"x": {"command": "echo", "args": []}}})

        assert McpToolFilter.from_server_config(config.mcpServers["x"]).allows("any") is True


class TestListTimeFiltering:
    @pytest.mark.asyncio
    async def test_disallowed_tools_never_register(self, runtime) -> None:
        toolset = PythinkerToolset()
        toolset._mcp_servers["srv"] = MCPServerInfo(
            status="pending",
            client=cast(Any, _ListingClient(["read_db", "drop_db"])),
            tools=[],
            resources=[],
            prompts=[],
            tool_filter=McpToolFilter(enabled=frozenset({"read_db"})),
        )

        await toolset.load_mcp_tools([], runtime, in_background=False)

        assert "read_db" in toolset._tool_dict
        assert "drop_db" not in toolset._tool_dict
        assert "mcp__srv__drop_db" not in runtime.mcp_tools


class TestCallTimeGate:
    @pytest.mark.asyncio
    async def test_denied_tool_errors_without_reaching_server(self, runtime) -> None:
        tool = MCPTool(
            "srv",
            mcp.types.Tool(name="drop_db", inputSchema={}),
            cast(Any, _ListingClient([], fail_on_call=True)),
            runtime=runtime,
            tool_filter=McpToolFilter(deny=frozenset({"drop_db"})),
        )

        result = await tool.call({})

        assert result.is_error
        assert "disabled" in (result.message or "").lower()
