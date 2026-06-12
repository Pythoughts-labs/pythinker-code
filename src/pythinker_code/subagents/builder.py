from __future__ import annotations

from pythinker_host.path import HostPath

from pythinker_code.llm import clone_llm_with_model_alias
from pythinker_code.soul.agent import Agent, Runtime, load_agent
from pythinker_code.subagents.models import AgentLaunchSpec, AgentTypeDefinition


class SubagentBuilder:
    def __init__(self, root_runtime: Runtime):
        self._root_runtime = root_runtime

    async def build_builtin_instance(
        self,
        *,
        agent_id: str,
        type_def: AgentTypeDefinition,
        launch_spec: AgentLaunchSpec,
        work_dir_override: HostPath | None = None,
    ) -> Agent:
        effective_model = self.resolve_effective_model(type_def=type_def, launch_spec=launch_spec)
        llm_override = clone_llm_with_model_alias(
            self._root_runtime.llm,
            self._root_runtime.config,
            effective_model,
            session_id=self._root_runtime.session.id,
            oauth=self._root_runtime.oauth,
            thinking=launch_spec.thinking,
            thinking_effort=launch_spec.thinking_effort,
        )
        work_dir_ls: str | None = None
        work_dir_agents_md: str | None = None
        if work_dir_override is not None:
            from pythinker_code.soul.agent import load_agents_md
            from pythinker_code.utils.path import list_directory

            work_dir_ls, work_dir_agents_md = (
                await list_directory(work_dir_override),
                await load_agents_md(work_dir_override),
            )
        runtime = self._root_runtime.copy_for_subagent(
            agent_id=agent_id,
            subagent_type=type_def.name,
            llm_override=llm_override,
            work_dir_override=work_dir_override,
            work_dir_ls=work_dir_ls,
            work_dir_agents_md=work_dir_agents_md,
        )
        return await load_agent(
            type_def.agent_file,
            runtime,
            mcp_configs=[],
        )

    @staticmethod
    def resolve_effective_model(
        *, type_def: AgentTypeDefinition, launch_spec: AgentLaunchSpec
    ) -> str | None:
        return launch_spec.model_override or launch_spec.effective_model or type_def.default_model
