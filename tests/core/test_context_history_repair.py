"""Restore-time history invariant repair.

A crash between persisting an assistant tool-call message and its tool
results leaves a dangling call (or an orphaned result) in context.jsonl.
Without repair, every subsequent API call fails with a call/result pairing
error. Repair happens only at the restore boundary — runtime appends are
already pair-shielded — and never rewrites the file, so it must be
idempotent across restores.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pythinker_core.message import Message, ToolCall

from pythinker_code.soul.context import Context
from pythinker_code.wire.types import TextPart


def _tool_call(call_id: str, name: str = "Shell") -> ToolCall:
    return ToolCall.model_validate(
        {"type": "function", "id": call_id, "function": {"name": name, "arguments": "{}"}}
    )


def _user(text: str) -> dict:
    return json.loads(
        Message(role="user", content=[TextPart(text=text)]).model_dump_json(exclude_none=True)
    )


def _assistant_with_calls(*call_ids: str) -> dict:
    message = Message(
        role="assistant",
        content=[TextPart(text="running tools")],
        tool_calls=[_tool_call(cid) for cid in call_ids],
    )
    return json.loads(message.model_dump_json(exclude_none=True))


def _tool_result(call_id: str, text: str = "done") -> dict:
    message = Message(role="tool", content=[TextPart(text=text)], tool_call_id=call_id)
    return json.loads(message.model_dump_json(exclude_none=True))


def _write_lines(path: Path, lines: list[dict]) -> None:
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")


async def _restore(path: Path) -> Context:
    ctx = Context(file_backend=path)
    assert await ctx.restore()
    return ctx


@pytest.mark.asyncio
async def test_intact_history_is_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "context.jsonl"
    _write_lines(
        path,
        [_user("hi"), _assistant_with_calls("call_1"), _tool_result("call_1")],
    )

    ctx = await _restore(path)

    assert [m.role for m in ctx.history] == ["user", "assistant", "tool"]


@pytest.mark.asyncio
async def test_dangling_call_at_end_gets_synthetic_result(tmp_path: Path) -> None:
    path = tmp_path / "context.jsonl"
    _write_lines(path, [_user("hi"), _assistant_with_calls("call_1")])

    ctx = await _restore(path)

    assert [m.role for m in ctx.history] == ["user", "assistant", "tool"]
    synthetic = ctx.history[-1]
    assert synthetic.tool_call_id == "call_1"
    assert "was lost" in synthetic.extract_text(" ")


@pytest.mark.asyncio
async def test_partially_recorded_results_are_completed(tmp_path: Path) -> None:
    path = tmp_path / "context.jsonl"
    _write_lines(
        path,
        [_assistant_with_calls("call_1", "call_2"), _tool_result("call_1")],
    )

    ctx = await _restore(path)

    tool_ids = [m.tool_call_id for m in ctx.history if m.role == "tool"]
    assert tool_ids == ["call_1", "call_2"]


@pytest.mark.asyncio
async def test_dangling_call_followed_by_user_message(tmp_path: Path) -> None:
    path = tmp_path / "context.jsonl"
    _write_lines(path, [_assistant_with_calls("call_1"), _user("next task")])

    ctx = await _restore(path)

    assert [m.role for m in ctx.history] == ["assistant", "tool", "user"]
    assert ctx.history[1].tool_call_id == "call_1"


@pytest.mark.asyncio
async def test_orphaned_tool_result_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / "context.jsonl"
    _write_lines(path, [_user("hi"), _tool_result("call_ghost")])

    ctx = await _restore(path)

    assert [m.role for m in ctx.history] == ["user"]


@pytest.mark.asyncio
async def test_duplicate_tool_result_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / "context.jsonl"
    _write_lines(
        path,
        [
            _assistant_with_calls("call_1"),
            _tool_result("call_1"),
            _tool_result("call_1", text="duplicate"),
        ],
    )

    ctx = await _restore(path)

    tool_messages = [m for m in ctx.history if m.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].extract_text(" ") == "done"


@pytest.mark.asyncio
async def test_repair_is_idempotent_across_restores(tmp_path: Path) -> None:
    path = tmp_path / "context.jsonl"
    _write_lines(path, [_assistant_with_calls("call_1"), _user("next")])
    before = path.read_text(encoding="utf-8")

    first = await _restore(path)
    second = await _restore(path)

    assert path.read_text(encoding="utf-8") == before
    assert [m.role for m in first.history] == [m.role for m in second.history]
    assert [m.tool_call_id for m in first.history] == [m.tool_call_id for m in second.history]


@pytest.mark.asyncio
async def test_revert_to_also_repairs(tmp_path: Path) -> None:
    path = tmp_path / "context.jsonl"
    _write_lines(
        path,
        [
            {"role": "_checkpoint", "id": 0},
            _assistant_with_calls("call_1"),
            {"role": "_checkpoint", "id": 1},
            _user("after"),
        ],
    )

    ctx = await _restore(path)
    await ctx.revert_to(1)

    assert [m.role for m in ctx.history] == ["assistant", "tool"]
    assert ctx.history[-1].tool_call_id == "call_1"
