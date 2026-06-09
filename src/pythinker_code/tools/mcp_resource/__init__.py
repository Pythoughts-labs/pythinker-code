"""Read-only MCP resource & prompt tools (mcpext-1).

Pythinker connects to MCP servers but previously only exposed their *tools*. A
server that also publishes resources (readable URIs) or prompt templates was
half-integrated. These two read-only tools let the model enumerate and read those
resources from already-connected servers. They never mutate, so they are safe
under every permission profile.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pythinker_core.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue

from pythinker_code.soul.toolset import PythinkerToolset
from pythinker_code.tools.utils import ToolResultBuilder, load_desc


class ListParams(BaseModel):
    server: str | None = Field(
        default=None,
        description="Limit to one connected MCP server by name. Omit to list all servers.",
    )


class ListMcpResources(CallableTool2[ListParams]):
    name: str = "ListMcpResources"
    params: type[ListParams] = ListParams

    def __init__(self, toolset: PythinkerToolset) -> None:
        super().__init__(description=load_desc(Path(__file__).parent / "list_description.md"))
        self._toolset = toolset

    async def __call__(self, params: ListParams) -> ToolReturnValue:
        servers = self._toolset.mcp_servers
        if params.server is not None:
            info = servers.get(params.server)
            if info is None:
                available = ", ".join(sorted(servers)) or "(none connected)"
                return ToolError(
                    message=f"Unknown MCP server: {params.server}. Connected servers: {available}",
                    brief="Unknown MCP server",
                )
            selected = [(params.server, info)]
        else:
            selected = sorted(servers.items())

        if not selected:
            return ToolOk(output="No MCP servers are connected.", message="No MCP servers.")

        lines: list[str] = []
        for name, info in selected:
            lines.append(f"server: {name} (status: {info.status})")
            for resource in info.resources:
                mime = f" [{resource.mimeType}]" if getattr(resource, "mimeType", None) else ""
                title = getattr(resource, "name", None) or ""
                lines.append(f"  resource: {resource.uri}  {title}{mime}".rstrip())
                desc = getattr(resource, "description", None)
                if desc:
                    lines.append(f"    {desc}")
            for prompt in info.prompts:
                desc = getattr(prompt, "description", None)
                lines.append(f"  prompt: {prompt.name}  {desc or ''}".rstrip())
            if not info.resources and not info.prompts:
                lines.append("  (no resources or prompts published)")
        return ToolOk(output="\n".join(lines), message="Listed MCP resources and prompts.")


class ReadParams(BaseModel):
    server: str = Field(description="The connected MCP server to read from.")
    uri: str = Field(description="The resource URI to read (from ListMcpResources).")


class ReadMcpResource(CallableTool2[ReadParams]):
    name: str = "ReadMcpResource"
    params: type[ReadParams] = ReadParams

    def __init__(self, toolset: PythinkerToolset) -> None:
        super().__init__(description=load_desc(Path(__file__).parent / "read_description.md"))
        self._toolset = toolset

    async def __call__(self, params: ReadParams) -> ToolReturnValue:
        info = self._toolset.mcp_servers.get(params.server)
        if info is None:
            available = ", ".join(sorted(self._toolset.mcp_servers)) or "(none connected)"
            return ToolError(
                message=f"Unknown MCP server: {params.server}. Connected servers: {available}",
                brief="Unknown MCP server",
            )

        try:
            async with info.client as client:
                contents = await client.read_resource(params.uri)
        except Exception as exc:
            return ToolError(
                message=f"Failed to read {params.uri} from {params.server}: {exc}",
                brief="Resource read failed",
            )

        builder = ToolResultBuilder()
        wrote = False
        for content in contents:
            text = getattr(content, "text", None)
            if text is not None:
                builder.write(text)
                wrote = True
            else:
                blob: Any = getattr(content, "blob", None)
                mime = getattr(content, "mimeType", None) or "application/octet-stream"
                size = f"{len(blob)} bytes" if isinstance(blob, (bytes, str)) else "size unknown"
                builder.write(f"[binary content omitted: {mime}, {size}]\n")
                wrote = True
        if not wrote:
            builder.write("(resource returned no content)")
        # Resource content is external, untrusted data — wrap it so the model
        # treats it as data, never instructions.
        builder.mark_untrusted()
        return builder.ok(f"Read resource {params.uri} from {params.server}.")
