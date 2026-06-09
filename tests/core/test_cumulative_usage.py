"""subagent-2: the soul accumulates per-step LLM token usage across its whole life.

This is the wiring test for the cumulative-usage accumulator that ForegroundSubagentRunner
reports back to the orchestrating parent — proving the soul sums each step's usage, not
just that the pure helper sums two records.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Self

import pytest
from pydantic import BaseModel
from pythinker_core.chat_provider import StreamedMessagePart, ThinkingEffort, TokenUsage
from pythinker_core.message import Message, TextPart, ToolCall
from pythinker_core.tooling import CallableTool2, ToolOk, ToolReturnValue
from pythinker_core.tooling.simple import SimpleToolset

from pythinker_code.llm import LLM
from pythinker_code.soul import run_soul
from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.utils.aioqueue import QueueShutDown
from pythinker_code.wire import Wire


class _UsageMessage:
    """A streamed message that reports a fixed TokenUsage."""

    def __init__(self, parts: Sequence[StreamedMessagePart], usage: TokenUsage) -> None:
        self._parts = list(parts)
        self._usage = usage
        self._iter = self._to_stream()

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> StreamedMessagePart:
        return await self._iter.__anext__()

    async def _to_stream(self) -> AsyncIterator[StreamedMessagePart]:
        for part in self._parts:
            yield part

    @property
    def id(self) -> str | None:
        return "usage-msg"

    @property
    def usage(self) -> TokenUsage | None:
        return self._usage


class _PerStepUsageProvider:
    """Step 0 emits a tool call, step 1 emits final text; each reports `usage`."""

    name = "per-step-usage"

    def __init__(self, usage: TokenUsage) -> None:
        self._usage = usage
        self.generate_attempts = 0

    @property
    def model_name(self) -> str:
        return "per-step-usage"

    @property
    def thinking_effort(self) -> ThinkingEffort | None:
        return None

    async def generate(
        self, system_prompt: str, tools: Sequence[object], history: Sequence[Message]
    ) -> _UsageMessage:
        index = self.generate_attempts
        self.generate_attempts += 1
        if index == 0:
            return _UsageMessage(
                [ToolCall(id="c0", function=ToolCall.FunctionBody(name="Ok", arguments="{}"))],
                self._usage,
            )
        return _UsageMessage([TextPart(text="done")], self._usage)

    def with_thinking(self, effort: ThinkingEffort) -> Self:
        return self


class _NoParams(BaseModel):
    pass


class _OkTool(CallableTool2[_NoParams]):
    name: str = "Ok"
    description: str = "Always succeeds."
    params: type[_NoParams] = _NoParams

    async def __call__(self, params: _NoParams) -> ToolReturnValue:
        return ToolOk(output="ok", message="ok")


async def _drain_ui_messages(wire: Wire) -> None:
    wire_ui = wire.ui_side(merge=True)
    while True:
        try:
            await wire_ui.receive()
        except QueueShutDown:
            return


@pytest.mark.asyncio
async def test_soul_accumulates_usage_across_steps(runtime: Runtime, tmp_path: Path) -> None:
    usage = TokenUsage(input_other=10, output=5, input_cache_read=2, input_cache_creation=1)
    provider = _PerStepUsageProvider(usage)
    llm = LLM(chat_provider=provider, max_context_size=100_000, capabilities=set())
    runtime = dataclasses.replace(runtime, llm=llm)
    agent = Agent(
        name="Usage Test Agent",
        system_prompt="Usage test prompt.",
        toolset=SimpleToolset([_OkTool()]),
        runtime=runtime,
    )
    soul = PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))

    await run_soul(soul, "go", _drain_ui_messages, asyncio.Event())

    # Two LLM calls (tool step + final text), each reporting `usage`.
    assert provider.generate_attempts == 2
    assert soul.cumulative_usage.output == 10  # 5 + 5
    assert soul.cumulative_usage.input_other == 20  # 10 + 10
    assert soul.cumulative_usage.input_cache_read == 4
    assert soul.cumulative_usage.input_cache_creation == 2
