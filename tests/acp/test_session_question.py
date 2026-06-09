"""uxsteer-3(a): ACP signals QuestionNotSupported instead of a false empty answer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import acp
import pytest

from pythinker_code.acp.session import ACPSession
from pythinker_code.wire.types import (
    ProgressNote,
    QuestionItem,
    QuestionNotSupported,
    QuestionOption,
    QuestionRequest,
    Suggestion,
    TextPart,
    TurnBegin,
    TurnEnd,
)


class _FakeConn:
    def __init__(self) -> None:
        self.updates: list[tuple[str, Any]] = []

    async def session_update(self, session_id: str, update: object) -> None:
        self.updates.append((session_id, update))


class _QuestionCLI:
    def __init__(self, question: QuestionRequest) -> None:
        self._question = question

    async def run(self, _user_input: object, _cancel_event: object) -> AsyncIterator[object]:
        yield TurnBegin(user_input=[TextPart(text="hi")])
        yield self._question
        yield TurnEnd()


def _question() -> QuestionRequest:
    return QuestionRequest(
        id="q1",
        tool_call_id="c1",
        questions=[
            QuestionItem(
                question="Pick one",
                options=[QuestionOption(label="A"), QuestionOption(label="B")],
            )
        ],
    )


@pytest.mark.asyncio
async def test_acp_question_request_signals_not_supported() -> None:
    conn = _FakeConn()
    question = _question()
    session = ACPSession("s1", _QuestionCLI(question), conn)  # type: ignore[arg-type]

    await session.prompt([acp.text_block("hi")])

    # The model gets an accurate "ask in text, do not retry" signal — not a
    # misleading empty (resolve({})) "user dismissed" answer.
    assert question.resolved
    with pytest.raises(QuestionNotSupported):
        await question.wait()


class _TransparencyCLI:
    async def run(self, _user_input: object, _cancel_event: object) -> AsyncIterator[object]:
        yield TurnBegin(user_input=[TextPart(text="hi")])
        yield ProgressNote(title="Migrated auth", body="next: update tests")
        yield Suggestion(label="Review my changes", prefill="/review")
        yield TurnEnd()


@pytest.mark.asyncio
async def test_acp_renders_progress_and_suggestion_as_text() -> None:
    # uxsteer-1/2: progress checkpoints and suggestions surface in ACP, not just shell.
    conn = _FakeConn()
    session = ACPSession("s1", _TransparencyCLI(), conn)  # type: ignore[arg-type]

    await session.prompt([acp.text_block("hi")])

    texts = [getattr(u[1].content, "text", "") for u in conn.updates]
    assert any("[Progress] Migrated auth" in t for t in texts)
    assert any("[Suggestion] Review my changes" in t for t in texts)
