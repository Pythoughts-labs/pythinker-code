"""Unit tests for ACPServer.initialize — terminal auth method."""

from __future__ import annotations

import acp.schema
import pytest

from pythinker_code.acp.server import ACPServer

pytestmark = pytest.mark.asyncio


async def test_initialize_advertises_terminal_auth_method():
    """initialize() advertises a single ``terminal`` auth method.

    ACP 0.10 removed the per-method ``command`` field: for security the client
    invokes the agent binary it already spawned directly (it never runs an
    agent-supplied command), passing only the extra ``args``/``env``. So the
    agent only needs to advertise the login ``args`` — not how it was launched.
    """
    server = ACPServer()

    resp = await server.initialize(protocol_version=1)

    assert resp.protocol_version == 1
    assert resp.auth_methods is not None
    assert len(resp.auth_methods) == 1

    auth_method = resp.auth_methods[0]
    assert isinstance(auth_method, acp.schema.TerminalAuthMethod)
    assert auth_method.id == "login"
    assert auth_method.type == "terminal"
    assert auth_method.args == ["login"]
    assert auth_method.env == {}


async def test_close_session_drops_session_from_registry():
    """ACP 0.10 session/close removes the session from the in-memory registry."""
    server = ACPServer()
    server.sessions["sess-1"] = ("placeholder",)  # type: ignore[assignment]

    result = await server.close_session("sess-1")

    assert result is None
    assert "sess-1" not in server.sessions
    # Closing an unknown session is a no-op (must not raise).
    assert await server.close_session("missing") is None
