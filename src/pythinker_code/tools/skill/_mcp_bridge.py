from __future__ import annotations

from collections.abc import Mapping

from pythinker_code.skill import normalize_skill_name


def skill_lookup_keys(skill_name: str) -> tuple[str, ...]:
    """Return normalized lookup keys, including plugin-style suffixes."""
    raw = skill_name.strip()
    if not raw:
        return ()
    keys: list[str] = [raw]
    if ":" in raw:
        suffix = raw.rsplit(":", 1)[-1].strip()
        if suffix and suffix not in keys:
            keys.append(suffix)
        prefix = raw.split(":", 1)[0].strip()
        if prefix and prefix not in keys:
            keys.append(prefix)
    return tuple(normalize_skill_name(key) for key in keys)


def _index_mcp_servers(mcp_tools: Mapping[str, object]) -> dict[str, list[str]]:
    servers: dict[str, list[str]] = {}
    for key in mcp_tools:
        if not key.startswith("mcp__"):
            continue
        parts = key.split("__", 2)
        if len(parts) != 3:
            continue
        _, server, tool = parts
        servers.setdefault(server, []).append(tool)
    return {server: sorted(tools) for server, tools in servers.items()}


def find_mcp_server_for_skill_name(
    skill_name: str,
    mcp_tools: Mapping[str, object],
) -> tuple[str, list[str]] | None:
    """Match a skill name (or plugin alias) to a connected MCP server."""
    servers = _index_mcp_servers(mcp_tools)
    if not servers:
        return None

    candidates: list[str] = []
    raw = skill_name.strip()
    if raw:
        candidates.append(raw)
    if ":" in raw:
        suffix = raw.rsplit(":", 1)[-1].strip()
        if suffix:
            candidates.append(suffix)
        prefix = raw.split(":", 1)[0].strip()
        if prefix:
            candidates.append(prefix)

    seen: set[str] = set()
    for candidate in candidates:
        norm = normalize_skill_name(candidate)
        if norm in seen:
            continue
        seen.add(norm)
        for server, tools in servers.items():
            if normalize_skill_name(server) == norm:
                return server, tools
    return None


def mcp_skill_bridge_content(server: str, tools: list[str]) -> str:
    """Instructions when a name maps to MCP tools but no filesystem skill exists."""
    tool_lines = "\n".join(f"- `mcp__{server}__{tool}`" for tool in tools)
    return f"""# MCP skill bridge: {server}

**Do not call ReadSkill again for `{server}`.** This name is served by a connected
MCP server, not a filesystem SKILL.md.

## Connected MCP tools
{tool_lines}

## How to use
1. Invoke the MCP tools above directly — they are already registered in your toolset.
2. Read each tool's description to choose the right entry point for the user's request.
3. If a tool is missing, check `/mcp` — the server may still be connecting or need
   auth (`pythinker mcp auth {server}`).

User-added MCP servers work the same way: configure them in `mcp.json`, then call
`mcp__<server>__<tool>` by name.
"""
