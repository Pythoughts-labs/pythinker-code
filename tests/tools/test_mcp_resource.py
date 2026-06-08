"""mcpext-1: read-only MCP resource & prompt tools."""

from __future__ import annotations

from typing import Any

from pythinker_code.soul.toolset import MCPServerInfo, PythinkerToolset
from pythinker_code.tools.mcp_resource import ListMcpResources, ReadMcpResource


class _Resource:
    def __init__(self, uri: str, name: str = "", description: str = "", mime: str = "") -> None:
        self.uri = uri
        self.name = name
        self.description = description
        self.mimeType = mime


class _Prompt:
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description


class _TextContent:
    def __init__(self, text: str) -> None:
        self.text = text
        self.mimeType = "text/plain"
        self.uri = "res://x"


class _FakeClient:
    def __init__(
        self,
        contents: list[Any] | None = None,
        raise_on_read: bool = False,
        raise_on_enter: bool = False,
    ) -> None:
        self._contents = contents or []
        self._raise = raise_on_read
        self._raise_on_enter = raise_on_enter

    async def __aenter__(self) -> _FakeClient:
        if self._raise_on_enter:
            raise RuntimeError("server not connected")
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def read_resource(self, uri: str) -> list[Any]:
        if self._raise:
            raise RuntimeError("boom")
        return self._contents


def _toolset_with_server(name: str, **kw: Any) -> PythinkerToolset:
    ts = PythinkerToolset()
    ts._mcp_servers[name] = MCPServerInfo(
        status="connected",
        client=kw.get("client", _FakeClient()),
        tools=[],
        resources=kw.get("resources", []),
        prompts=kw.get("prompts", []),
    )
    return ts


async def test_list_resources_and_prompts() -> None:
    ts = _toolset_with_server(
        "db",
        resources=[_Resource("res://schema", "schema", "the schema", "text/plain")],
        prompts=[_Prompt("summarize", "summarize a table")],
    )
    result = await ListMcpResources(ts)(ListMcpResources.params(server=None))

    assert not result.is_error
    assert isinstance(result.output, str)
    assert "server: db" in result.output
    assert "res://schema" in result.output
    assert "the schema" in result.output
    assert "prompt: summarize" in result.output


async def test_list_no_servers_reports_none() -> None:
    ts = PythinkerToolset()
    result = await ListMcpResources(ts)(ListMcpResources.params(server=None))
    assert not result.is_error
    assert isinstance(result.output, str)
    assert "No MCP servers" in result.output


async def test_list_unknown_server_errors() -> None:
    ts = _toolset_with_server("db")
    result = await ListMcpResources(ts)(ListMcpResources.params(server="nope"))
    assert result.is_error
    assert result.brief == "Unknown MCP server"


async def test_read_resource_returns_untrusted_text() -> None:
    ts = _toolset_with_server("db", client=_FakeClient(contents=[_TextContent("hello schema")]))
    result = await ReadMcpResource(ts)(ReadMcpResource.params(server="db", uri="res://schema"))

    assert not result.is_error
    assert isinstance(result.output, str)
    assert "hello schema" in result.output
    assert "untrusted_data" in result.output  # external content is wrapped


async def test_read_resource_unknown_server_errors() -> None:
    ts = _toolset_with_server("db")
    result = await ReadMcpResource(ts)(ReadMcpResource.params(server="nope", uri="x"))
    assert result.is_error
    assert result.brief == "Unknown MCP server"


async def test_read_resource_surfaces_read_failure() -> None:
    ts = _toolset_with_server("db", client=_FakeClient(raise_on_read=True))
    result = await ReadMcpResource(ts)(ReadMcpResource.params(server="db", uri="x"))
    assert result.is_error
    assert result.brief == "Resource read failed"


async def test_read_resource_from_unconnectable_server_errors() -> None:
    # A server that fails to (re)connect at read time surfaces a clean error
    # rather than crashing — covers the failed/unauthorized-server edge case.
    ts = _toolset_with_server("db", client=_FakeClient(raise_on_enter=True))
    result = await ReadMcpResource(ts)(ReadMcpResource.params(server="db", uri="x"))
    assert result.is_error
    assert result.brief == "Resource read failed"
