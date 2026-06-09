from pathlib import Path
from typing import override

from pydantic import BaseModel, Field
from pythinker_core.tooling import CallableTool2, ToolOk, ToolReturnValue

from pythinker_code.soul import wire_send
from pythinker_code.tools.utils import load_desc
from pythinker_code.wire.types import ProgressNote


class Params(BaseModel):
    title: str = Field(
        description="Short, scannable checkpoint title, e.g. 'Migrated auth module'."
    )
    body: str = Field(
        default="",
        description="Optional one-line detail or what's next, e.g. 'next: update tests'.",
    )


class Progress(CallableTool2[Params]):
    name: str = "Progress"
    description: str = load_desc(Path(__file__).parent / "description.md")
    params: type[Params] = Params

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        wire_send(ProgressNote(title=params.title, body=params.body))
        return ToolOk(output="", message="Progress note posted")
