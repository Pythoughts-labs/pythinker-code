from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pythinker_code.soul.dynamic_injection import DynamicInjection, DynamicInjectionProvider
from pythinker_code.subagents.models import AgentTypeDefinition

if TYPE_CHECKING:
    from pythinker_core.message import Message

    from pythinker_code.soul.pythinkersoul import PythinkerSoul


def format_agent_line(agent: AgentTypeDefinition) -> str:
    policy = agent.tool_policy
    if policy.mode == "allowlist" and policy.tools:
        names: list[str] = []
        for path in policy.tools:
            segment = path.split(":")[-1]
            if segment not in names:
                names.append(segment)
        tools_desc = ", ".join(names) if names else "(none)"
    elif policy.mode == "allowlist":
        tools_desc = "(none)"
    else:
        tools_desc = "All tools"
    suffix = f" — {agent.when_to_use.strip()}" if agent.when_to_use else ""
    return f"- `{agent.name}`: {agent.description} (Tools: {tools_desc}){suffix}"


class AgentListInjectionProvider(DynamicInjectionProvider):
    """Emit the built-in agent list as a dynamic injection for root sessions only."""

    async def get_injections(
        self,
        history: Sequence[Message],
        soul: PythinkerSoul,
    ) -> list[DynamicInjection]:
        _ = history
        if soul.is_subagent:
            return []
        types = list(soul.runtime.labor_market.builtin_types.values())
        if not types:
            return []
        items = "\n".join(
            format_agent_line(agent_type)
            for agent_type in sorted(types, key=lambda agent_type: agent_type.name)
        )
        body = (
            "Available agent types (this list is regenerated when subagent specs change):\n" + items
        )
        return [DynamicInjection(type="agent_list", content=body)]
