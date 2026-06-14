from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pythinker_core.chat_provider import ThinkingEffort

type ToolPolicyMode = Literal["inherit", "allowlist"]
type SubagentStatus = Literal[
    "idle",
    "running_foreground",
    "running_background",
    "completed",
    "failed",
    "killed",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolPolicy:
    mode: ToolPolicyMode
    tools: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentTypeDefinition:
    name: str
    description: str
    agent_file: Path
    when_to_use: str = ""
    default_model: str | None = None
    tool_policy: ToolPolicy = field(default_factory=lambda: ToolPolicy(mode="inherit"))
    supports_background: bool = True
    required_mcp_servers: tuple[str, ...] = ()
    """MCP server names this agent type needs. Spawning it is gated when these servers
    are configured-and-absent (after MCP loading settles), so a turn is not wasted on an
    agent that cannot reach its required tools."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentLaunchSpec:
    agent_id: str
    subagent_type: str
    model_override: str | None
    effective_model: str | None
    thinking: bool | None = None
    thinking_effort: ThinkingEffort | None = None
    variant: str | None = None
    parent_agent_id: str | None = None
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentInstanceRecord:
    agent_id: str
    subagent_type: str
    status: SubagentStatus
    description: str
    created_at: float
    updated_at: float
    last_task_id: str | None
    launch_spec: AgentLaunchSpec
