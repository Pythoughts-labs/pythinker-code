"""Unit tests for MCP skill bridge helpers."""

from __future__ import annotations

from pythinker_code.tools.skill._mcp_bridge import (
    find_mcp_server_for_skill_name,
    skill_lookup_keys,
)


def test_skill_lookup_keys_includes_plugin_suffix() -> None:
    assert skill_lookup_keys("designer-skill:designer-skill") == (
        "designer-skill:designer-skill",
        "designer-skill",
    )


def test_find_mcp_server_for_skill_name_matches_server() -> None:
    mcp_tools = {
        "mcp__designer-skill__get_design_system": object(),
        "mcp__designer-skill__anti_slop_checklist": object(),
    }

    match = find_mcp_server_for_skill_name("designer-skill", mcp_tools)

    assert match is not None
    server, tools = match
    assert server == "designer-skill"
    assert tools == ["anti_slop_checklist", "get_design_system"]
