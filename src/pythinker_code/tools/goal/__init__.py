from pathlib import Path
from typing import Literal, override

from pydantic import BaseModel, Field
from pythinker_core.tooling import CallableTool2, ToolReturnValue

from pythinker_code.session_state import GoalState
from pythinker_code.soul.agent import Runtime
from pythinker_code.tools.utils import load_desc


class Params(BaseModel):
    status: Literal["complete", "blocked"] = Field(
        description=(
            "'complete' only after the completion audit proves every requirement "
            "with current evidence; 'blocked' only when the strict blocked audit "
            "is satisfied."
        )
    )
    summary: str = Field(
        min_length=1,
        description=(
            "For 'complete': the per-requirement evidence. For 'blocked': the "
            "specific blocking condition and what would unblock it."
        ),
    )


class UpdateGoal(CallableTool2[Params]):
    name: str = "UpdateGoal"
    description: str = load_desc(Path(__file__).parent / "update_goal.md")
    params: type[Params] = Params

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        if self._runtime.role != "root":
            return ToolReturnValue(
                is_error=True,
                output="Only the root agent can update the thread goal.",
                message="",
                display=[],
            )
        goal = self._runtime.session.state.goal
        if goal is None or goal.status != "active":
            return ToolReturnValue(
                is_error=True,
                output="No active goal. The user sets one with /goal <objective>.",
                message="",
                display=[],
            )
        self._runtime.session.state.goal = GoalState(objective=goal.objective, status=params.status)
        self._runtime.session.save_state()
        if params.status == "complete":
            next_step = "/goal clear to dismiss it, or /goal resume to keep working on it"
        else:
            next_step = "/goal resume to retry once unblocked, or /goal clear to drop it"
        return ToolReturnValue(
            is_error=False,
            output=f"Goal marked {params.status}: {params.summary}\nThe user can run {next_step}.",
            message=f"Goal marked {params.status}",
            display=[],
        )
