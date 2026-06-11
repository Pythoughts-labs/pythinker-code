"""Tests for the UpdateGoal tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from pythinker_code.session_state import GoalState, load_session_state
from pythinker_code.soul.agent import Runtime
from pythinker_code.tools.goal import Params, UpdateGoal


@pytest.fixture
def update_goal_tool(runtime: Runtime) -> UpdateGoal:
    return UpdateGoal(runtime)


def _set_active_goal(runtime: Runtime, objective: str = "ship the exporter") -> None:
    runtime.session.state.goal = GoalState(objective=objective, status="active")


class TestUpdateGoal:
    async def test_marks_goal_complete(self, update_goal_tool: UpdateGoal, runtime: Runtime):
        _set_active_goal(runtime)

        result = await update_goal_tool(
            Params(status="complete", summary="all tests pass; exporter verified end-to-end")
        )

        assert not result.is_error
        assert "complete" in result.output
        goal = runtime.session.state.goal
        assert goal is not None and goal.status == "complete"

    async def test_marks_goal_blocked(self, update_goal_tool: UpdateGoal, runtime: Runtime):
        _set_active_goal(runtime)

        result = await update_goal_tool(
            Params(status="blocked", summary="needs production credentials only the user has")
        )

        assert not result.is_error
        assert "blocked" in result.output
        goal = runtime.session.state.goal
        assert goal is not None and goal.status == "blocked"

    async def test_persists_status_to_disk(self, update_goal_tool: UpdateGoal, runtime: Runtime):
        _set_active_goal(runtime)

        await update_goal_tool(Params(status="complete", summary="done with evidence"))

        reloaded = load_session_state(Path(str(runtime.session.dir)))
        assert reloaded.goal is not None and reloaded.goal.status == "complete"

    async def test_errors_without_goal(self, update_goal_tool: UpdateGoal, runtime: Runtime):
        runtime.session.state.goal = None

        result = await update_goal_tool(Params(status="complete", summary="done"))

        assert result.is_error
        assert "No active goal" in result.output

    async def test_errors_on_non_active_goal(self, update_goal_tool: UpdateGoal, runtime: Runtime):
        runtime.session.state.goal = GoalState(objective="x", status="paused")

        result = await update_goal_tool(Params(status="complete", summary="done"))

        assert result.is_error

    async def test_errors_for_subagent(self, runtime: Runtime):
        subagent_runtime = runtime.copy_for_subagent(
            agent_id="test-goal-sub",
            subagent_type="coder",
        )
        _set_active_goal(runtime)
        tool = UpdateGoal(subagent_runtime)

        result = await tool(Params(status="complete", summary="done"))

        assert result.is_error
        assert "root" in result.output
