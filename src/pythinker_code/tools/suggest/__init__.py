from pathlib import Path
from typing import override

from pydantic import BaseModel, Field
from pythinker_core.tooling import CallableTool2, ToolOk, ToolReturnValue

from pythinker_code.soul import wire_send
from pythinker_code.tools.utils import load_desc
from pythinker_code.wire.types import Suggestion


class Params(BaseModel):
    label: str = Field(
        description="The suggested next action, e.g. 'Review my changes with /review'."
    )
    prefill: str = Field(
        default="",
        description="Optional text or slash-command to prefill the user's input if they "
        "accept, e.g. '/review'.",
    )
    category: str = Field(
        default="",
        description="Optional category for grouping, e.g. 'review'.",
    )


class Suggest(CallableTool2[Params]):
    """Post a non-blocking, optional next-action suggestion (does not pause the turn)."""

    name: str = "Suggest"
    description: str = load_desc(Path(__file__).parent / "description.md")
    params: type[Params] = Params

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        wire_send(Suggestion(label=params.label, prefill=params.prefill, category=params.category))
        return ToolOk(output="", message="Suggestion posted")
