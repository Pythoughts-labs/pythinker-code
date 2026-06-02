"""Tests for Approval's yolo / auto orthogonal state model."""

from __future__ import annotations

import json

from pythinker_code.soul.approval import Approval, ApprovalState, deliberation_scope
from pythinker_code.wire.types import ToolCall


def _shell_call(cmd: str) -> ToolCall:
    return ToolCall(
        id="call-1",
        function=ToolCall.FunctionBody(name="Shell", arguments=json.dumps({"command": cmd})),
    )


def test_tool_destructive_reason_gates_background_shell() -> None:
    from pythinker_code.soul.permission import tool_destructive_reason

    # Background shell is the same "Shell" tool (run_in_background=true); a destructive
    # background command must still be classified as destructive.
    reason = tool_destructive_reason(
        "Shell", {"command": "rm -rf build", "run_in_background": True}
    )
    assert reason is not None


def test_tool_destructive_reason_ignores_unregistered_tool() -> None:
    from pythinker_code.soul.permission import tool_destructive_reason

    assert (
        tool_destructive_reason("WriteFile", {"path": "x", "content": "y", "mode": "overwrite"})
        is None
    )


def test_deliberation_scope_sets_and_restores_contextvar() -> None:
    from pythinker_code.soul.approval import (
        DeliberationScope,
        _current_deliberation_scope,
        deliberation_scope,
    )

    assert _current_deliberation_scope.get() is None
    with deliberation_scope("root", 3):
        assert _current_deliberation_scope.get() == DeliberationScope("root", 3)
    assert _current_deliberation_scope.get() is None


def test_yolo_only() -> None:
    approval = Approval(yolo=True)
    assert approval.is_yolo() is True
    assert approval.is_yolo_flag() is True
    assert approval.is_auto_approve() is True
    assert approval.is_auto() is False


def test_auto_only() -> None:
    state = ApprovalState(yolo=False, auto=True)
    approval = Approval(state=state)
    assert approval.is_auto_approve() is True
    assert approval.is_yolo() is False
    assert approval.is_yolo_flag() is False  # explicit flag only
    assert approval.is_auto() is True
    assert approval.is_auto_flag() is True


def test_yolo_and_auto() -> None:
    state = ApprovalState(yolo=True, auto=True)
    approval = Approval(state=state)
    assert approval.is_yolo() is True
    assert approval.is_auto_approve() is True
    assert approval.is_auto() is True


def test_neither_flag_set() -> None:
    approval = Approval(yolo=False)
    assert approval.is_yolo() is False
    assert approval.is_auto_approve() is False
    assert approval.is_auto() is False


def test_runtime_auto_only() -> None:
    state = ApprovalState(yolo=False, auto=False, runtime_auto=True)
    approval = Approval(state=state)
    assert approval.is_auto_approve() is True
    assert approval.is_yolo() is False
    assert approval.is_auto() is True
    assert approval.is_auto_flag() is False
    assert approval.is_runtime_auto() is True


def test_set_runtime_auto_does_not_trigger_on_change() -> None:
    fired: list[bool] = []
    state = ApprovalState(on_change=lambda: fired.append(True))
    approval = Approval(state=state)
    approval.set_runtime_auto(True)
    assert approval.is_auto() is True
    assert approval.is_auto_flag() is False
    assert fired == []


def test_set_yolo_does_not_touch_auto() -> None:
    state = ApprovalState(yolo=False, auto=True)
    approval = Approval(state=state)
    approval.set_yolo(True)
    assert approval.is_auto() is True
    assert approval.is_yolo() is True
    assert approval.is_auto_approve() is True
    approval.set_yolo(False)
    # Auto keeps auto-approve on even after the explicit yolo flag is cleared.
    assert approval.is_auto() is True
    assert approval.is_yolo() is False
    assert approval.is_auto_approve() is True


def test_shared_state_preserves_auto() -> None:
    state = ApprovalState(yolo=False, auto=True, runtime_auto=True)
    parent = Approval(state=state)
    child = parent.share()
    assert child.is_auto() is True
    assert child.is_yolo() is False
    assert child.is_auto_approve() is True
    assert child.is_runtime_auto() is True


def test_set_auto_toggles_with_on_change() -> None:
    """set_auto persists session auto and triggers on_change."""
    fired: list[bool] = []
    state = ApprovalState(yolo=False, auto=False, on_change=lambda: fired.append(True))
    approval = Approval(state=state)
    approval.set_auto(True)
    assert approval.is_auto() is True
    assert approval.is_auto_flag() is True
    assert fired == [True]
    approval.set_auto(False)
    assert approval.is_auto() is False
    assert approval.is_auto_flag() is False
    assert fired == [True, True]


def test_set_auto_false_clears_runtime_auto() -> None:
    state = ApprovalState(yolo=False, auto=False, runtime_auto=True)
    approval = Approval(state=state)
    assert approval.is_auto() is True
    approval.set_auto(False)
    assert approval.is_auto() is False
    assert approval.is_runtime_auto() is False


def test_destructive_action_deliberates_once_then_proceeds_under_auto() -> None:
    """auto + auto_deliberate: a destructive command deliberates the first time, the
    re-issue in a LATER generation runs once, and a fresh issue later deliberates again."""
    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    with deliberation_scope("root", 1):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
    with deliberation_scope("root", 2):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is None
    with deliberation_scope("root", 3):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None


def test_same_generation_duplicate_destructive_calls_both_bounce() -> None:
    # Property (a): two byte-identical destructive calls in ONE generation both deliberate.
    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    with deliberation_scope("root", 1):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None


def test_subagent_identical_call_does_not_consume_main_one_shot() -> None:
    # Property (c): a subagent's identical call must not ride on the main agent's bounce.
    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    with deliberation_scope("root", 1):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
    with deliberation_scope("sub-1", 1):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None


def test_older_generation_duplicate_destructive_call_still_bounces() -> None:
    # Defensive guard: only a strictly later generation can consume a prior bounce.
    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    with deliberation_scope("root", 2):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None
    with deliberation_scope("root", 1):
        assert approval.deliberation_gate(_shell_call("rm -rf build")) is not None


def test_deliberation_gate_conditions() -> None:
    """The gate fires only when the feature is on, we would otherwise auto-approve
    (auto OR yolo), and the command is destructive."""
    rm = _shell_call("rm -rf x")
    safe = _shell_call("ls -la")

    # feature off -> never deliberates (full back-compat)
    off = Approval(state=ApprovalState(auto=True, auto_deliberate=False))
    assert off.deliberation_gate(rm) is None

    # human present (not auto, not yolo) -> normal interactive approval shows the rm -rf;
    # no self-deliberation needed
    human = Approval(state=ApprovalState(auto=False, auto_deliberate=True))
    assert human.deliberation_gate(rm) is None

    # yolo + auto_deliberate -> gates AHEAD of the yolo bypass
    yolo = Approval(state=ApprovalState(yolo=True, auto_deliberate=True))
    assert yolo.deliberation_gate(rm) is not None

    # non-destructive in auto + auto_deliberate -> proceeds untouched
    benign = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    assert benign.deliberation_gate(safe) is None


async def test_request_bounces_destructive_then_approves_retry() -> None:
    """End-to-end through request(): a destructive command in auto + auto_deliberate is
    bounced once with deliberation feedback that does NOT masquerade as a user rejection,
    then the identical retry auto-approves."""
    from tests.conftest import tool_call_context

    approval = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    with tool_call_context("Shell", arguments={"command": "rm -rf build"}):
        with deliberation_scope("root", 1):
            first = await approval.request("Shell", "run command", "Run command `rm -rf build`")
        assert not first, "destructive action is bounced for deliberation"
        assert first.deliberation is True
        assert "irreversible" in first.feedback
        assert "rejected by the user" not in first.rejection_error().message

        with deliberation_scope("root", 2):
            second = await approval.request("Shell", "run command", "Run command `rm -rf build`")
        assert second, "one-shot consumed in a later generation: the deliberated retry runs"


def test_approval_state_honors_auto_deliberate_flag() -> None:
    on = Approval(state=ApprovalState(auto=True, auto_deliberate=True))
    assert on.deliberation_gate(_shell_call("rm -rf build")) is not None
    off = Approval(state=ApprovalState(auto=True, auto_deliberate=False))
    assert off.deliberation_gate(_shell_call("rm -rf build")) is None
