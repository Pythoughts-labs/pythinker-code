"""Spawn-time context fork: child inherits a filtered parent transcript.

New children start blank and rely on the orchestrator hand-writing context
packets. fork_context seeds the child with the conversational spine — user
requests and assistant text — and drops tool traffic (whose call/result
pairing would dangle out of context), thinking, and injected wrappers.
"""

from __future__ import annotations

import pytest
from pythinker_core.message import Message, ToolCall

from pythinker_code.soul.context import Context
from pythinker_code.subagents.core import filter_history_for_fork, seed_forked_history
from pythinker_code.wire.types import TextPart, ThinkPart


def _user(text: str) -> Message:
    return Message(role="user", content=[TextPart(text=text)])


def _assistant(text: str) -> Message:
    return Message(role="assistant", content=[TextPart(text=text)])


def _tool_call(call_id: str) -> ToolCall:
    return ToolCall.model_validate(
        {"type": "function", "id": call_id, "function": {"name": "Shell", "arguments": "{}"}}
    )


class TestFilterHistoryForFork:
    def test_keeps_conversational_spine_in_order(self) -> None:
        history = [_user("do the thing"), _assistant("done, summary follows")]

        forked = filter_history_for_fork(history)

        assert [(m.role, m.extract_text(" ")) for m in forked] == [
            ("user", "do the thing"),
            ("assistant", "done, summary follows"),
        ]

    def test_drops_tool_messages_and_strips_tool_calls(self) -> None:
        assistant = Message(
            role="assistant",
            content=[TextPart(text="running a check")],
            tool_calls=[_tool_call("c1")],
        )
        history = [
            _user("task"),
            assistant,
            Message(role="tool", content=[TextPart(text="raw output")], tool_call_id="c1"),
        ]

        forked = filter_history_for_fork(history)

        assert [m.role for m in forked] == ["user", "assistant"]
        assert forked[1].tool_calls is None
        assert "raw output" not in " ".join(m.extract_text(" ") for m in forked)

    def test_drops_thinking_parts(self) -> None:
        history = [
            Message(
                role="assistant",
                content=[ThinkPart(think="private reasoning"), TextPart(text="the answer")],
            )
        ]

        forked = filter_history_for_fork(history)

        assert forked[0].extract_text(" ") == "the answer"

    def test_drops_reminders_notifications_and_checkpoints(self) -> None:
        history = [
            _user("<system-reminder>\ninjected guidance\n</system-reminder>"),
            _user(
                '<notification id="n1" category="task" type="complete" '
                'source_kind="background_task" source_id="t1">done</notification>'
            ),
            _user("CHECKPOINT 3"),
            _user("real request"),
        ]

        forked = filter_history_for_fork(history)

        assert [m.extract_text(" ") for m in forked] == ["real request"]

    def test_drops_empty_assistant_messages(self) -> None:
        history = [
            Message(role="assistant", content=[], tool_calls=[_tool_call("c1")]),
        ]

        assert filter_history_for_fork(history) == []


class TestSeedForkedHistory:
    @pytest.mark.asyncio
    async def test_seeds_new_child_and_persists(self, tmp_path) -> None:
        context = Context(file_backend=tmp_path / "child.jsonl")
        forked = [_user("inherited request"), _assistant("inherited summary")]

        await seed_forked_history(context, forked, resumed=False)

        assert [m.role for m in context.history] == ["user", "assistant"]
        reloaded = Context(file_backend=tmp_path / "child.jsonl")
        assert await reloaded.restore()
        assert reloaded.history[0].extract_text(" ") == "inherited request"

    @pytest.mark.asyncio
    async def test_noop_on_resume(self, tmp_path) -> None:
        context = Context(file_backend=tmp_path / "child.jsonl")

        await seed_forked_history(context, [_user("x")], resumed=True)

        assert list(context.history) == []

    @pytest.mark.asyncio
    async def test_noop_when_child_already_has_history(self, tmp_path) -> None:
        context = Context(file_backend=tmp_path / "child.jsonl")
        await context.append_message(_user("existing"))

        await seed_forked_history(context, [_user("forked")], resumed=False)

        assert len(context.history) == 1

    @pytest.mark.asyncio
    async def test_noop_without_fork_history(self, tmp_path) -> None:
        context = Context(file_backend=tmp_path / "child.jsonl")

        await seed_forked_history(context, None, resumed=False)

        assert list(context.history) == []
