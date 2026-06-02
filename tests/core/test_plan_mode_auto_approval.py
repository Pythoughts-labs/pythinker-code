"""Plan-mode auto-approval binding (Hypothesis B2).

EnterPlanMode and ExitPlanMode must gate on the SAME predicate (``is_auto`` -- "no user
present"), not on ``is_auto_approve`` (which yolo flips True). Otherwise a yolo-only
session (user present, approvals merely skipped) silently slips *into* plan mode but
still needs a human to *leave* it -- an asymmetric surface that quietly defeats the
plan-review checkpoint. Under genuine auto mode both transitions self-approve because no
human is there to confirm.
"""

from __future__ import annotations

from pathlib import Path

from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.soul.toolset import PythinkerToolset
from pythinker_code.tools.plan import ExitPlanMode
from pythinker_code.tools.plan.enter import EnterPlanMode


def _bound_plan_tools(runtime: Runtime, tmp_path: Path) -> tuple[EnterPlanMode, ExitPlanMode]:
    """Build a soul with the plan tools so PythinkerSoul binds their auto-approve checkers."""
    toolset = PythinkerToolset()
    enter = EnterPlanMode()
    exit_ = ExitPlanMode()
    toolset.add(enter)
    toolset.add(exit_)
    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=toolset,
        runtime=runtime,
    )
    PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))
    return enter, exit_


def test_yolo_only_does_not_auto_confirm_plan_transitions(runtime: Runtime, tmp_path: Path) -> None:
    """Yolo-only (user present): neither entering nor leaving plan mode is auto-confirmed,
    so the human still reviews the plan."""
    runtime.approval.set_yolo(True)  # fixture default is yolo=True; auto stays off
    assert runtime.approval.is_yolo() is True
    assert runtime.approval.is_auto() is False

    enter, exit_ = _bound_plan_tools(runtime, tmp_path)

    assert enter._is_auto_approve is not None
    assert enter._is_auto_approve() is False
    assert exit_._should_auto_approve_exit is not None
    assert exit_._should_auto_approve_exit() is False


def test_unsupervised_auto_self_manages_plan_transitions(runtime: Runtime, tmp_path: Path) -> None:
    """Auto mode (no user present): both transitions self-approve -- there is no human to
    confirm. This must hold regardless of yolo."""
    runtime.approval.set_auto(True)
    assert runtime.approval.is_auto() is True

    enter, exit_ = _bound_plan_tools(runtime, tmp_path)

    assert enter._is_auto_approve is not None
    assert enter._is_auto_approve() is True
    assert exit_._should_auto_approve_exit is not None
    assert exit_._should_auto_approve_exit() is True
