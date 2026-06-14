"""MCP per-server startup timeout and actionable failure diagnostics.

A hung connect used to leave a server in 'connecting' forever — and the
agent loop awaits MCP loading, so it blocked every turn. Connects are now
bounded by mcp.client.startup_timeout_ms, and failures carry one short
actionable line surfaced by /mcp instead of a bare 'failed'.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from pythinker_code.exception import MCPRuntimeError
from pythinker_code.soul.toolset import (
    MCPServerInfo,
    PythinkerToolset,
    _classify_mcp_connect_error,
)


def _hanging_client() -> Any:
    return cast(Any, _HangingClient())


class _HangingClient:
    async def __aenter__(self) -> _HangingClient:
        await asyncio.sleep(60)
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class TestStartupTimeout:
    @pytest.mark.asyncio
    async def test_hung_connect_fails_with_actionable_error(self, runtime) -> None:
        runtime.config.mcp.client.startup_timeout_ms = 100
        toolset = PythinkerToolset()
        toolset._mcp_servers["slow"] = MCPServerInfo(
            status="pending", client=_hanging_client(), tools=[], resources=[], prompts=[]
        )

        with pytest.raises(MCPRuntimeError):
            await toolset.load_mcp_tools([], runtime, in_background=False)

        info = toolset._mcp_servers["slow"]
        assert info.status == "failed"
        assert info.error is not None
        assert "timed out" in info.error
        assert "startup_timeout_ms" in info.error


class TestErrorClassification:
    def test_timeout_points_at_the_config_knob(self) -> None:
        message = _classify_mcp_connect_error(TimeoutError(), "db")
        assert "timed out" in message
        assert "startup_timeout_ms" in message

    def test_unauthorized_points_at_auth_command(self) -> None:
        message = _classify_mcp_connect_error(Exception("HTTP 401 Unauthorized"), "db")
        assert "pythinker mcp auth db" in message

    def test_missing_command_named(self) -> None:
        error = FileNotFoundError(2, "No such file or directory")
        error.filename = "npxx"
        message = _classify_mcp_connect_error(error, "db")
        assert "command not found" in message
        assert "npxx" in message

    def test_connection_refused(self) -> None:
        message = _classify_mcp_connect_error(ConnectionRefusedError("refused"), "db")
        assert "running" in message

    def test_generic_error_is_first_line_only(self) -> None:
        message = _classify_mcp_connect_error(Exception("first line\nsecond line"), "db")
        assert message == "first line"


class TestLoadingHonestSnapshot:
    """mcp_status_snapshot must distinguish 'still starting' from 'no MCP configured' so the
    required-MCP spawn gate (which treats a None snapshot as settled-absent) cannot reject a
    subagent during the brief window before the deferred startup populates the servers."""

    def test_deferred_load_reports_loading_not_none(self) -> None:
        toolset = PythinkerToolset()
        # Configured-but-not-started: a deferred load is queued, _mcp_servers still empty.
        toolset._deferred_mcp_load = ([], cast(Any, None))
        snapshot = toolset.mcp_status_snapshot()
        assert snapshot is not None
        assert snapshot.loading is True
        assert snapshot.total == 0

    def test_no_mcp_configured_reports_none(self) -> None:
        # Settled 'no MCP': nothing configured and nothing pending -> None (the state where the
        # gate correctly reports a required server as genuinely unavailable).
        assert PythinkerToolset().mcp_status_snapshot() is None


class TestDiagnosticsSurface:
    def test_snapshot_carries_error(self) -> None:
        toolset = PythinkerToolset()
        toolset._mcp_servers["db"] = MCPServerInfo(
            status="failed",
            client=_hanging_client(),
            tools=[],
            resources=[],
            prompts=[],
            error="connection refused — is the server running?",
        )

        snapshot = toolset.mcp_status_snapshot()

        assert snapshot is not None
        assert snapshot.servers[0].error == "connection refused — is the server running?"

    def test_failed_server_render_includes_error(self) -> None:
        from pythinker_code.ui.shell.mcp_status import _server_inventory_lines
        from pythinker_code.wire.types import MCPServerSnapshot

        lines = _server_inventory_lines(
            MCPServerSnapshot(name="db", status="failed", error="startup timed out")
        )

        joined = " ".join(str(line) for line in lines)
        assert "startup timed out" in joined
