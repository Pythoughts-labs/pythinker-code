"""Tests for wire protocol plan mode support."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from pythinker_code.soul.toolset import PythinkerToolset
from pythinker_code.tools.plan import ExitPlanMode
from pythinker_code.tools.plan.enter import EnterPlanMode
from pythinker_code.wire.jsonrpc import ClientCapabilities


class TestClientCapabilities:
    def test_defaults_to_false(self) -> None:
        caps = ClientCapabilities()
        assert caps.supports_plan_mode is False

    def test_parses_true(self) -> None:
        caps = ClientCapabilities(supports_plan_mode=True)
        assert caps.supports_plan_mode is True


class TestSyncPlanModeToolVisibility:
    def _make_toolset_with_plan_tools(self) -> PythinkerToolset:
        ts = PythinkerToolset()
        ts.add(ExitPlanMode())
        ts.add(EnterPlanMode())
        return ts

    def _make_server(self, supports_plan_mode: bool):
        """Create a minimal WireServer-like object with _sync_plan_mode_tool_visibility."""
        from pythinker_code.wire.server import WireServer

        # We need to construct WireServer with minimal mocking
        soul = MagicMock()
        soul.agent = MagicMock()
        soul.agent.runtime = MagicMock()
        soul.agent.runtime.labor_market.builtin_types = {}

        server = WireServer.__new__(WireServer)
        server._soul = soul
        server._client_supports_plan_mode = supports_plan_mode
        return server

    def test_hides_tools_when_unsupported(self) -> None:
        ts = self._make_toolset_with_plan_tools()
        server = self._make_server(supports_plan_mode=False)

        server._sync_plan_mode_tool_visibility(ts)

        # Tools should be hidden
        tool_names = {t.name for t in ts.tools}
        assert "ExitPlanMode" not in tool_names
        assert "EnterPlanMode" not in tool_names

    def test_tools_visible_when_supported(self) -> None:
        ts = self._make_toolset_with_plan_tools()
        server = self._make_server(supports_plan_mode=True)

        server._sync_plan_mode_tool_visibility(ts)

        tool_names = {t.name for t in ts.tools}
        assert "ExitPlanMode" in tool_names
        assert "EnterPlanMode" in tool_names

    def test_unhide_after_hide(self) -> None:
        ts = self._make_toolset_with_plan_tools()
        server = self._make_server(supports_plan_mode=False)

        # First hide
        server._sync_plan_mode_tool_visibility(ts)
        assert "ExitPlanMode" not in {t.name for t in ts.tools}

        # Then unhide
        server._client_supports_plan_mode = True
        server._sync_plan_mode_tool_visibility(ts)
        assert "ExitPlanMode" in {t.name for t in ts.tools}
        assert "EnterPlanMode" in {t.name for t in ts.tools}


async def test_handle_set_plan_mode_returns_invalid_state_when_streaming() -> None:
    """_handle_set_plan_mode must return INVALID_STATE when a turn is in progress.

    Mirrors the guard already present in _handle_replay and _handle_initialize.
    """
    from pythinker_code.soul.pythinkersoul import PythinkerSoul
    from pythinker_code.wire.jsonrpc import (
        ErrorCodes,
        JSONRPCErrorResponse,
        JSONRPCSetPlanModeMessage,
    )
    from pythinker_code.wire.server import WireServer

    server = WireServer.__new__(WireServer)
    # _soul must be a PythinkerSoul to pass the isinstance guard
    server._soul = MagicMock(spec=PythinkerSoul)
    # Simulate an active turn: _cancel_event is not None → _is_streaming is True
    server._cancel_event = asyncio.Event()

    msg = JSONRPCSetPlanModeMessage(id="req-1", params={"enabled": True})  # type: ignore[arg-type]
    result = await server._handle_set_plan_mode(msg)

    assert isinstance(result, JSONRPCErrorResponse)
    assert result.error.code == ErrorCodes.INVALID_STATE
    assert "in progress" in result.error.message
