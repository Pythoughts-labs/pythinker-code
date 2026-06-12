"""Same-step tool-call concurrency policy.

When a provider emits parallel tool calls, mutating tools (WriteFile +
Shell from one assistant message) used to execute concurrently with no
race protection. Policy: parallel-safe tools overlap freely; everything
else (including unflagged plugin/MCP tools — safe default) runs
exclusively, keeping same-step mutation ordering deterministic.
"""

from __future__ import annotations

import asyncio

from pythinker_core.tooling import ToolReturnValue

from pythinker_code.hooks.engine import HookEngine
from pythinker_code.soul.toolset import PythinkerToolset
from pythinker_code.wire.types import ToolCall


class _RecordingTool:
    base = None

    def __init__(
        self, name: str, events: list[tuple[str, str]], *, parallel: bool, delay: float = 0.05
    ) -> None:
        self.name = name
        self._events = events
        self._delay = delay
        if parallel:
            self.supports_parallel = True

    async def call(self, arguments: object) -> ToolReturnValue:
        self._events.append(("enter", self.name))
        await asyncio.sleep(self._delay)
        self._events.append(("exit", self.name))
        return ToolReturnValue(is_error=False, output="ok", message="ok", display=[])


def _toolset(*tools: _RecordingTool) -> PythinkerToolset:
    toolset = PythinkerToolset()
    toolset._hook_engine = HookEngine([], cwd="/tmp")
    for tool in tools:
        toolset._tool_dict[tool.name] = tool  # type: ignore[assignment]
    return toolset


async def _dispatch(toolset: PythinkerToolset, *names: str) -> None:
    tasks = []
    for index, name in enumerate(names):
        result = toolset.handle(
            ToolCall(id=f"tc_{index}", function=ToolCall.FunctionBody(name=name, arguments="{}"))
        )
        assert isinstance(result, asyncio.Task)
        tasks.append(result)
    await asyncio.gather(*tasks)


class TestSameStepConcurrencyPolicy:
    async def test_mutating_tools_serialize_in_dispatch_order(self) -> None:
        events: list[tuple[str, str]] = []
        toolset = _toolset(
            _RecordingTool("WriteA", events, parallel=False),
            _RecordingTool("WriteB", events, parallel=False),
        )

        await _dispatch(toolset, "WriteA", "WriteB")

        assert events == [
            ("enter", "WriteA"),
            ("exit", "WriteA"),
            ("enter", "WriteB"),
            ("exit", "WriteB"),
        ]

    async def test_parallel_safe_tools_overlap(self) -> None:
        events: list[tuple[str, str]] = []
        toolset = _toolset(
            _RecordingTool("ReadA", events, parallel=True),
            _RecordingTool("ReadB", events, parallel=True),
        )

        await _dispatch(toolset, "ReadA", "ReadB")

        assert {events[0][0], events[1][0]} == {"enter"}, events

    async def test_reader_waits_for_earlier_writer(self) -> None:
        events: list[tuple[str, str]] = []
        toolset = _toolset(
            _RecordingTool("Write", events, parallel=False),
            _RecordingTool("Read", events, parallel=True),
        )

        await _dispatch(toolset, "Write", "Read")

        assert events.index(("exit", "Write")) < events.index(("enter", "Read"))

    async def test_writer_waits_for_inflight_readers(self) -> None:
        events: list[tuple[str, str]] = []
        toolset = _toolset(
            _RecordingTool("Read", events, parallel=True),
            _RecordingTool("Write", events, parallel=False),
        )

        await _dispatch(toolset, "Read", "Write")

        assert events.index(("exit", "Read")) < events.index(("enter", "Write"))


class TestParallelSafeFlags:
    def test_read_only_builtins_are_parallel_safe(self) -> None:
        from pythinker_code.tools.file.glob import Glob
        from pythinker_code.tools.file.grep_local import Grep, SmartSearch
        from pythinker_code.tools.file.read import ReadFile
        from pythinker_code.tools.mcp_resource import ListMcpResources, ReadMcpResource
        from pythinker_code.tools.think import Think

        for tool_cls in (
            Glob,
            Grep,
            SmartSearch,
            ReadFile,
            ListMcpResources,
            ReadMcpResource,
            Think,
        ):
            assert getattr(tool_cls, "supports_parallel", False), tool_cls.__name__

    def test_mutating_builtins_stay_exclusive(self) -> None:
        from pythinker_code.tools.file.replace import StrReplaceFile
        from pythinker_code.tools.file.write import WriteFile
        from pythinker_code.tools.shell import Shell

        for tool_cls in (WriteFile, StrReplaceFile, Shell):
            assert not getattr(tool_cls, "supports_parallel", False), tool_cls.__name__
