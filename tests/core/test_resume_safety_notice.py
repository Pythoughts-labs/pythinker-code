"""Resume safety notice (Hypothesis B3b).

When a resumed session is running unsupervised (yolo and/or auto), the welcome banner
must surface a warning so the state is never silently restored from disk.
"""

from __future__ import annotations

from pythinker_code.app import _resumed_unsupervised_notice


def test_no_notice_for_fresh_session() -> None:
    assert _resumed_unsupervised_notice(resumed=False, yolo=True, auto=True) is None


def test_no_notice_when_not_unsupervised() -> None:
    assert _resumed_unsupervised_notice(resumed=True, yolo=False, auto=False) is None


def test_notice_names_active_modes_on_resume() -> None:
    # The mode label is the prefix before " active —"; assert on that to avoid colliding
    # with "auto-approved" / "/auto" later in the message.
    yolo_only = _resumed_unsupervised_notice(resumed=True, yolo=True, auto=False)
    assert yolo_only is not None and yolo_only.startswith("YOLO active")

    auto_only = _resumed_unsupervised_notice(resumed=True, yolo=False, auto=True)
    assert auto_only is not None and auto_only.startswith("auto active")

    both = _resumed_unsupervised_notice(resumed=True, yolo=True, auto=True)
    assert both is not None and both.startswith("YOLO + auto active")
