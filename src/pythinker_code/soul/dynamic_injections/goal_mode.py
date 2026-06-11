from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pythinker_core.message import Message, TextPart

import pythinker_code.prompts as prompts
from pythinker_code.soul.dynamic_injection import DynamicInjection, DynamicInjectionProvider

if TYPE_CHECKING:
    from pythinker_code.soul.pythinkersoul import PythinkerSoul

# Inject a reminder every N assistant turns.
_TURN_INTERVAL = 5
# Every N-th reminder is the full version; others are sparse.
_FULL_EVERY_N = 5


class GoalModeInjectionProvider(DynamicInjectionProvider):
    """Periodically re-injects the goal continuation prompt while /goal is active.

    Throttling is inferred from history: scan backwards to the last
    reminder for the *current* objective and count assistant messages in
    between. Reminders for a replaced objective do not throttle the new
    one, so a goal change is announced on the very next LLM step.

    Root-only: the thread goal belongs to the user's session; subagents
    receive their own task prompts and must not inherit it.
    """

    def __init__(self) -> None:
        self._inject_count: int = 0

    async def get_injections(
        self,
        history: Sequence[Message],
        soul: PythinkerSoul,
    ) -> list[DynamicInjection]:
        goal = soul.runtime.session.state.goal
        if goal is None or not goal.objective:
            self._inject_count = 0
            return []
        if soul.is_subagent or goal.status != "active":
            return []

        # Scan history backwards to find the last reminder for this objective.
        turns_since_last = 0
        found_previous = False
        for msg in reversed(history):
            if msg.role == "user" and _has_goal_reminder(msg, goal.objective):
                found_previous = True
                break
            if msg.role == "assistant":
                turns_since_last += 1

        # First reminder for this objective (newly set or replaced) -> full version.
        if not found_previous:
            self._inject_count = 1
            return [DynamicInjection(type="goal_mode", content=_full_reminder(goal.objective))]

        # Not enough turns since last reminder -> skip.
        if turns_since_last < _TURN_INTERVAL:
            return []

        # Inject.
        self._inject_count += 1
        is_full = self._inject_count % _FULL_EVERY_N == 1
        content = _full_reminder(goal.objective) if is_full else _sparse_reminder(goal.objective)
        return [DynamicInjection(type="goal_mode", content=content)]

    async def on_context_compacted(self) -> None:
        # Compaction drops prior reminders from history; reset so the full
        # continuation prompt re-fires on the next LLM step.
        self._inject_count = 0


def _objective_headline(objective: str) -> str:
    """First non-empty line of the objective, for compact reminders and matching."""
    for line in objective.strip().splitlines():
        if line.strip():
            return line.strip()
    return objective.strip()


def _has_goal_reminder(msg: Message, objective: str) -> bool:
    """Check whether a message contains a goal reminder for the current objective.

    Detects by matching a stable prefix of the reminder texts plus the
    objective headline, so wording changes stay in sync and reminders for a
    replaced objective never suppress the new one.
    """
    markers = (
        _full_reminder(objective).split(".")[0],  # "Continue working toward ..."
        _sparse_reminder(objective).split(".")[0],  # "Goal contract still active ..."
    )
    headline = _objective_headline(objective)
    for part in msg.content:
        if (
            isinstance(part, TextPart)
            and headline in part.text
            and any(marker in part.text for marker in markers)
        ):
            return True
    return False


def _full_reminder(objective: str) -> str:
    return prompts.GOAL_CONTINUATION.format(objective=objective)


def _sparse_reminder(objective: str) -> str:
    return (
        "Goal contract still active (see the earlier goal continuation instructions). "
        f"Objective: {_objective_headline(objective)}. "
        "Make concrete progress toward the requested end state; do not shrink scope "
        "or substitute an easier-to-test solution. Mark completion only via UpdateGoal "
        "after the completion audit proves every requirement with current evidence; "
        "report specific blockers instead of stalling."
    )
