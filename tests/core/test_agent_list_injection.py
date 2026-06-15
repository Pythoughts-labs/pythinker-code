from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from pythinker_code.soul.agent import Runtime
from pythinker_code.soul.dynamic_injections.agent_list import (
    AgentListInjectionProvider,
    format_agent_line,
)
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.subagents.models import AgentTypeDefinition, ToolPolicy


def _type(
    name: str,
    when: str = "",
    tools: tuple[str, ...] = (),
    default_model: str | None = None,
) -> AgentTypeDefinition:
    policy = ToolPolicy(mode="inherit") if not tools else ToolPolicy(mode="allowlist", tools=tools)
    return AgentTypeDefinition(
        name=name,
        description=f"{name} agent",
        agent_file=Path("/tmp/agent.yaml"),
        when_to_use=when,
        default_model=default_model,
        tool_policy=policy,
    )


def test_format_agent_line_allowlist_only() -> None:
    line = format_agent_line(_type("explore", "recon", ("ReadFile", "Glob", "Grep")))
    assert "`explore`" in line
    assert "recon" in line
    assert "Tools: ReadFile, Glob, Grep" in line


def test_format_agent_line_no_restrictions() -> None:
    line = format_agent_line(_type("general", "default"))
    assert "Tools: All tools" in line


def test_provider_is_self_filtering_root_only() -> None:
    assert AgentListInjectionProvider() is not None


@pytest.mark.asyncio
async def test_provider_only_emits_for_root(runtime: Runtime) -> None:
    prov = AgentListInjectionProvider()
    root_soul = cast(PythinkerSoul, SimpleNamespace(is_subagent=False, runtime=runtime))
    root_injections = await prov.get_injections([], root_soul)
    assert len(root_injections) == 1
    assert root_injections[0].type == "agent_list"
    assert "mocker" in root_injections[0].content

    sub_runtime = runtime.copy_for_subagent(agent_id="sub-1", subagent_type="coder")
    sub_soul = cast(PythinkerSoul, SimpleNamespace(is_subagent=True, runtime=sub_runtime))
    assert await prov.get_injections([], sub_soul) == []
