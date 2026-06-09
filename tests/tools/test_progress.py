"""Progress tool (uxsteer-1).

The ProgressNote transparency channel is plumbed end-to-end (wire type + shell
renderer) but had zero producers, so the model could never post a mid-task
checkpoint. The Progress tool is that producer: it emits a ProgressNote and
returns a no-op result.
"""

from __future__ import annotations

from unittest.mock import patch

from pythinker_code.tools.progress import Params, Progress
from pythinker_code.wire.types import ProgressNote


async def test_progress_emits_note_and_returns_noop() -> None:
    captured: list[object] = []
    with patch("pythinker_code.tools.progress.wire_send", side_effect=captured.append):
        result = await Progress()(Params(title="Migrated auth", body="next: update tests"))

    assert not result.is_error
    assert len(captured) == 1
    note = captured[0]
    assert isinstance(note, ProgressNote)
    assert note.title == "Migrated auth"
    assert note.body == "next: update tests"


async def test_progress_body_is_optional() -> None:
    captured: list[object] = []
    with patch("pythinker_code.tools.progress.wire_send", side_effect=captured.append):
        result = await Progress()(Params(title="Completed step 1"))

    assert not result.is_error
    assert len(captured) == 1
    note = captured[0]
    assert isinstance(note, ProgressNote)
    assert note.title == "Completed step 1"
    assert note.body == ""
