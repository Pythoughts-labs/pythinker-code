from __future__ import annotations

from pythinker_code.soul.approval import Approval, ApprovalState


def test_safe_mode_disables_auto_approval_even_when_yolo_is_on() -> None:
    approval = Approval(state=ApprovalState(yolo=True, safe_mode=True))

    assert approval.is_yolo() is True
    assert approval.is_auto_approve() is False


def test_safe_mode_can_be_toggled_off() -> None:
    approval = Approval(state=ApprovalState(yolo=True, safe_mode=True))

    approval.set_safe_mode(False)

    assert approval.is_auto_approve() is True
