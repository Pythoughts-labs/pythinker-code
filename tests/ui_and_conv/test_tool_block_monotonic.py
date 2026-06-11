"""Monotonic state-transition guards for _ToolCallBlock.

A tool-call row moves pending -> running -> terminal exactly once. Late or
duplicated wire events (ToolExecutionStarted after ToolResult, a replayed
ToolResult) must not restyle a finished row or let a failed row become
successful — a retry is a new tool call with its own id and row.
"""

from __future__ import annotations

from pythinker_core.tooling import ToolError, ToolOk

from pythinker_code.ui.shell.visualize._blocks import _ToolCallBlock
from pythinker_code.wire.types import ToolCall


def _block(name: str = "Shell") -> _ToolCallBlock:
    return _ToolCallBlock(
        ToolCall(
            id="call-1",
            function=ToolCall.FunctionBody(name=name, arguments='{"command": "ls"}'),
        )
    )


def test_failed_row_cannot_become_successful() -> None:
    block = _block()
    block.finish(ToolError(message="boom", brief="Failed"))
    assert block.finished
    assert block._result is not None and block._result.is_error

    block.finish(ToolOk(output="all good"))

    assert block._result.is_error, "replayed success result must not overwrite failure"


def test_first_terminal_result_wins() -> None:
    block = _block()
    block.finish(ToolOk(output="first"))
    block.finish(ToolError(message="late failure", brief="Failed"))

    assert block._result is not None and not block._result.is_error


def test_late_execution_started_after_finish_is_ignored() -> None:
    block = _block()
    block.finish(ToolOk(output="done"))
    rendered_before = block._renderable

    block.mark_execution_started()

    assert not block._execution_started
    assert block._renderable is rendered_before, "finished row must not be recomposed"


def test_late_output_part_after_finish_is_ignored() -> None:
    block = _block()
    block.finish(ToolOk(output="done"))

    block.append_output_part("stray chunk")

    assert block._streamed_output_parts == []
