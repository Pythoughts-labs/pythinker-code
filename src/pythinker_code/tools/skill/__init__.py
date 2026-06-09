from pathlib import Path
from typing import override

from pydantic import BaseModel, Field
from pythinker_core.tooling import CallableTool2, ToolError, ToolReturnValue

from pythinker_code.skill import (
    normalize_skill_name,
    read_skill_text_with_local_specialization,
)
from pythinker_code.soul.agent import Runtime
from pythinker_code.tools.utils import load_desc

NAME = "ReadSkill"


class Params(BaseModel):
    skill_name: str = Field(description="Name of the skill to read, for example review-pr")


class ReadSkillTool(CallableTool2[Params]):
    name: str = NAME
    params: type[Params] = Params

    def __init__(self, runtime: Runtime):
        super().__init__(description=load_desc(Path(__file__).parent / "description.md"))
        self._runtime = runtime

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        skill_name = params.skill_name.strip()
        if not skill_name:
            return ToolError(message="Skill name is required.", brief="Missing skill name")

        skill = self._runtime.skills.get(normalize_skill_name(skill_name))
        if skill is None:
            available = ", ".join(sorted(s.name for s in self._runtime.skills.values())) or "(none)"
            return ToolError(
                message=f"Skill not found: {skill_name}. Available skills: {available}",
                brief="Skill not found",
            )

        content = await read_skill_text_with_local_specialization(skill, self._runtime.skills)
        if content is None:
            return ToolError(
                message=f"Failed to read skill: {skill.name}", brief="Skill read failed"
            )

        return ToolReturnValue(
            is_error=False,
            output=f"skill: {skill.name}\npath: {skill.skill_md_file}\n\n{content}",
            message=f"Read skill {skill.name}.",
            display=[],
        )


ReadSkill = ReadSkillTool
