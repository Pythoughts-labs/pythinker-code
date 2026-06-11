from __future__ import annotations

import platform

import pytest
from pythinker_core.tooling import CallableTool, ToolOk, ToolReturnValue

from pythinker_code.agentspec import DEFAULT_AGENT_FILE
from pythinker_code.soul.agent import load_agent
from pythinker_code.soul.toolset import ToolType
from pythinker_code.subagents.builder import SubagentBuilder
from pythinker_code.subagents.models import AgentLaunchSpec, AgentTypeDefinition, ToolPolicy


class _FakeMCPTool(CallableTool):
    async def __call__(self) -> ToolReturnValue:
        return ToolOk(output="fake")


def _fake_mcp_tool(name: str) -> ToolType:
    return _FakeMCPTool(
        name=name,
        description="fake mcp tool",
        parameters={"type": "object", "properties": {}},
    )


@pytest.mark.skipif(platform.system() == "Windows", reason="Skipping test on Windows")
async def test_builder_builds_coder_with_write_tools(runtime):
    await load_agent(DEFAULT_AGENT_FILE, runtime, mcp_configs=[])

    builder = SubagentBuilder(runtime)
    coder = await builder.build_builtin_instance(
        agent_id="acoder",
        type_def=runtime.labor_market.require_builtin_type("coder"),
        launch_spec=AgentLaunchSpec(
            agent_id="acoder",
            subagent_type="coder",
            model_override=None,
            effective_model=None,
        ),
    )

    tool_names = [tool.name for tool in coder.toolset.tools]
    assert "Shell" in tool_names
    assert "WriteFile" in tool_names
    assert "StrReplaceFile" in tool_names
    assert "Agent" not in tool_names
    assert "AskUserQuestion" not in tool_names
    assert "SetTodoList" in tool_names


@pytest.mark.skipif(platform.system() == "Windows", reason="Skipping test on Windows")
async def test_builder_builds_explore_read_only_with_shell(runtime):
    await load_agent(DEFAULT_AGENT_FILE, runtime, mcp_configs=[])

    builder = SubagentBuilder(runtime)
    explore = await builder.build_builtin_instance(
        agent_id="aexplore",
        type_def=runtime.labor_market.require_builtin_type("explore"),
        launch_spec=AgentLaunchSpec(
            agent_id="aexplore",
            subagent_type="explore",
            model_override=None,
            effective_model=None,
        ),
    )

    tool_names = [tool.name for tool in explore.toolset.tools]
    assert "Shell" in tool_names
    assert "ReadFile" in tool_names
    assert "Grep" in tool_names
    assert "SetTodoList" in tool_names
    assert "WriteFile" not in tool_names
    assert "StrReplaceFile" not in tool_names
    assert "Agent" not in tool_names


@pytest.mark.skipif(platform.system() == "Windows", reason="Skipping test on Windows")
async def test_builder_builds_plan_without_shell_or_write_tools(runtime):
    await load_agent(DEFAULT_AGENT_FILE, runtime, mcp_configs=[])

    builder = SubagentBuilder(runtime)
    plan = await builder.build_builtin_instance(
        agent_id="aplan",
        type_def=runtime.labor_market.require_builtin_type("plan"),
        launch_spec=AgentLaunchSpec(
            agent_id="aplan",
            subagent_type="plan",
            model_override=None,
            effective_model=None,
        ),
    )

    tool_names = [tool.name for tool in plan.toolset.tools]
    assert "ReadFile" in tool_names
    assert "Glob" in tool_names
    assert "SearchWeb" in tool_names
    assert "SetTodoList" in tool_names
    assert "Shell" not in tool_names
    assert "WriteFile" not in tool_names
    assert "StrReplaceFile" not in tool_names
    assert "Agent" not in tool_names


@pytest.mark.skipif(platform.system() == "Windows", reason="Skipping test on Windows")
async def test_builder_builds_project_markdown_agent(runtime):
    agent_path = runtime.session.work_dir / ".claude" / "agents" / "local-reviewer.md"
    await agent_path.parent.mkdir(parents=True, exist_ok=True)
    await agent_path.write_text(
        "---\n"
        "name: local-reviewer\n"
        "description: Local reviewer\n"
        'tools: ["Read", "Grep"]\n'
        "---\n"
        "You are the local markdown reviewer.",
        encoding="utf-8",
    )
    await load_agent(DEFAULT_AGENT_FILE, runtime, mcp_configs=[])

    builder = SubagentBuilder(runtime)
    reviewer = await builder.build_builtin_instance(
        agent_id="amarkdown",
        type_def=runtime.labor_market.require_builtin_type("local-reviewer"),
        launch_spec=AgentLaunchSpec(
            agent_id="amarkdown",
            subagent_type="local-reviewer",
            model_override=None,
            effective_model=None,
        ),
    )

    assert "You are the local markdown reviewer." in reviewer.system_prompt
    assert "description: Local reviewer" not in reviewer.system_prompt
    tool_names = [tool.name for tool in reviewer.toolset.tools]
    assert tool_names == ["ReadFile", "Grep"]


@pytest.mark.skipif(platform.system() == "Windows", reason="Skipping test on Windows")
async def test_builder_model_priority_prefers_override_then_type_default_then_inherit(
    runtime, monkeypatch
):
    captured_aliases: list[str | None] = []
    captured_thinking: list[bool | None] = []

    def fake_clone_llm_with_model_alias(
        llm, config, model_alias, *, session_id, oauth, thinking=None, thinking_effort=None
    ):
        captured_aliases.append(model_alias)
        captured_thinking.append(thinking)
        return llm

    monkeypatch.setattr(
        "pythinker_code.subagents.builder.clone_llm_with_model_alias",
        fake_clone_llm_with_model_alias,
    )

    builder = SubagentBuilder(runtime)
    type_def = AgentTypeDefinition(
        name="explore",
        description="Fast codebase exploration.",
        agent_file=DEFAULT_AGENT_FILE.parent / "explore.yaml",
        default_model="type-default",
        tool_policy=ToolPolicy(mode="allowlist", tools=()),
    )

    await builder.build_builtin_instance(
        agent_id="aoverride",
        type_def=type_def,
        launch_spec=AgentLaunchSpec(
            agent_id="aoverride",
            subagent_type="explore",
            model_override="tool-override",
            effective_model="type-default",
            thinking=False,
        ),
    )
    await builder.build_builtin_instance(
        agent_id="atype-default",
        type_def=type_def,
        launch_spec=AgentLaunchSpec(
            agent_id="atype-default",
            subagent_type="explore",
            model_override=None,
            effective_model="type-default",
        ),
    )
    await builder.build_builtin_instance(
        agent_id="ainherit",
        type_def=AgentTypeDefinition(
            name="plan",
            description="Planning agent.",
            agent_file=DEFAULT_AGENT_FILE.parent / "plan.yaml",
            default_model=None,
            tool_policy=ToolPolicy(mode="allowlist", tools=()),
        ),
        launch_spec=AgentLaunchSpec(
            agent_id="ainherit",
            subagent_type="plan",
            model_override=None,
            effective_model=None,
        ),
    )

    assert captured_aliases == ["tool-override", "type-default", None]
    assert captured_thinking == [False, None, None]


@pytest.mark.skipif(platform.system() == "Windows", reason="Skipping test on Windows")
async def test_builder_attaches_shared_mcp_tools_from_allowlist(runtime):
    runtime.mcp_tools.update(
        {
            "mcp__context7__resolve-library-id": _fake_mcp_tool("resolve-library-id"),
            "mcp__context7__query-docs": _fake_mcp_tool("query-docs"),
            "mcp__tavily__tavily_search": _fake_mcp_tool("tavily_search"),
            "mcp__tavily__tavily_crawl": _fake_mcp_tool("tavily_crawl"),
        }
    )
    await load_agent(DEFAULT_AGENT_FILE, runtime, mcp_configs=[])

    builder = SubagentBuilder(runtime)
    coder = await builder.build_builtin_instance(
        agent_id="acoder-mcp",
        type_def=runtime.labor_market.require_builtin_type("coder"),
        launch_spec=AgentLaunchSpec(
            agent_id="acoder-mcp",
            subagent_type="coder",
            model_override=None,
            effective_model=None,
        ),
    )
    coder_tools = [tool.name for tool in coder.toolset.tools]
    assert "resolve-library-id" in coder_tools
    assert "query-docs" in coder_tools
    assert "tavily_search" not in coder_tools

    judge = await builder.build_builtin_instance(
        agent_id="ajudge-mcp",
        type_def=runtime.labor_market.require_builtin_type("judge"),
        launch_spec=AgentLaunchSpec(
            agent_id="ajudge-mcp",
            subagent_type="judge",
            model_override=None,
            effective_model=None,
        ),
    )
    judge_tools = [tool.name for tool in judge.toolset.tools]
    assert "tavily_search" in judge_tools
    assert "query-docs" in judge_tools
    assert "tavily_crawl" not in judge_tools


@pytest.mark.skipif(platform.system() == "Windows", reason="Skipping test on Windows")
async def test_builder_skips_unconnected_mcp_allowlist_entries(runtime):
    await load_agent(DEFAULT_AGENT_FILE, runtime, mcp_configs=[])

    builder = SubagentBuilder(runtime)
    coder = await builder.build_builtin_instance(
        agent_id="acoder-nomcp",
        type_def=runtime.labor_market.require_builtin_type("coder"),
        launch_spec=AgentLaunchSpec(
            agent_id="acoder-nomcp",
            subagent_type="coder",
            model_override=None,
            effective_model=None,
        ),
    )
    tool_names = [tool.name for tool in coder.toolset.tools]
    assert "query-docs" not in tool_names
    assert "mcp__context7__query-docs" not in tool_names
    assert "WriteFile" in tool_names
