"""Failure-threshold escalation (obs-eval-5).

When a model gets stuck in a degenerate loop where every tool call fails, the
agent loop should yield to the human after `max_consecutive_failures` consecutive
all-error steps — stopping with a `stuck` turn outcome and a handoff summary —
instead of burning steps until the blunt `max_steps_per_turn` cap.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Self
from unittest.mock import patch

import pytest
from pydantic import BaseModel
from pythinker_core.chat_provider import StreamedMessagePart, ThinkingEffort, TokenUsage
from pythinker_core.message import Message, TextPart, ToolCall
from pythinker_core.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pythinker_core.tooling.simple import SimpleToolset

from pythinker_code.llm import LLM
from pythinker_code.soul import run_soul
from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.utils.aioqueue import QueueShutDown
from pythinker_code.wire import Wire


class _StaticStreamedMessage:
    def __init__(self, parts: Sequence[StreamedMessagePart]) -> None:
        self._iter = self._to_stream(parts)

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> StreamedMessagePart:
        return await self._iter.__anext__()

    async def _to_stream(
        self, parts: Sequence[StreamedMessagePart]
    ) -> AsyncIterator[StreamedMessagePart]:
        for part in parts:
            yield part

    @property
    def id(self) -> str | None:
        return "stuck-loop"

    @property
    def usage(self) -> TokenUsage | None:
        return None


class _ScriptedToolCallProvider:
    """Emits one tool call (or final text) per step from a fixed script.

    Each script entry is a tool name to call, or ``None`` to emit a tool-call-free
    text message (which ends the turn normally).
    """

    name = "scripted-tool-call"

    def __init__(self, script: Sequence[str | None]) -> None:
        self._script = list(script)
        self.generate_attempts = 0

    @property
    def model_name(self) -> str:
        return "scripted-tool-call"

    @property
    def thinking_effort(self) -> ThinkingEffort | None:
        return None

    async def generate(
        self,
        system_prompt: str,
        tools: Sequence[object],
        history: Sequence[Message],
    ) -> _StaticStreamedMessage:
        index = self.generate_attempts
        self.generate_attempts += 1
        entry = self._script[index] if index < len(self._script) else None
        if entry is None:
            return _StaticStreamedMessage([TextPart(text="done")])
        return _StaticStreamedMessage(
            [ToolCall(id=f"c{index}", function=ToolCall.FunctionBody(name=entry, arguments="{}"))]
        )

    def with_thinking(self, effort: ThinkingEffort) -> Self:
        return self


class _NoParams(BaseModel):
    pass


class _BoomTool(CallableTool2[_NoParams]):
    name: str = "Boom"
    description: str = "Always fails."
    params: type[_NoParams] = _NoParams

    async def __call__(self, params: _NoParams) -> ToolReturnValue:
        return ToolError(message="boom", brief="boom")


class _OkTool(CallableTool2[_NoParams]):
    name: str = "Ok"
    description: str = "Always succeeds."
    params: type[_NoParams] = _NoParams

    async def __call__(self, params: _NoParams) -> ToolReturnValue:
        return ToolOk(output="ok", message="ok")


def _make_soul(
    runtime: Runtime, provider: _ScriptedToolCallProvider, tmp_path: Path
) -> tuple[Context, PythinkerSoul]:
    llm = LLM(chat_provider=provider, max_context_size=100_000, capabilities=set())
    runtime = Runtime(
        config=runtime.config,
        llm=llm,
        session=runtime.session,
        builtin_args=runtime.builtin_args,
        denwa_renji=runtime.denwa_renji,
        approval=runtime.approval,
        labor_market=runtime.labor_market,
        environment=runtime.environment,
        notifications=runtime.notifications,
        background_tasks=runtime.background_tasks,
        skills=runtime.skills,
        oauth=runtime.oauth,
        additional_dirs=runtime.additional_dirs,
        skills_dirs=runtime.skills_dirs,
        role=runtime.role,
    )
    agent = Agent(
        name="Stuck Test Agent",
        system_prompt="Stuck test prompt.",
        toolset=SimpleToolset([_BoomTool(), _OkTool()]),
        runtime=runtime,
    )
    context = Context(file_backend=tmp_path / "history.jsonl")
    soul = PythinkerSoul(agent, context=context)
    return context, soul


async def _drain_ui_messages(wire: Wire) -> None:
    wire_ui = wire.ui_side(merge=True)
    while True:
        try:
            await wire_ui.receive()
        except QueueShutDown:
            return


@pytest.mark.asyncio
async def test_consecutive_failures_yield_stuck_outcome(runtime: Runtime, tmp_path: Path) -> None:
    """N consecutive all-error steps stop the turn with `stuck`, not max_steps."""
    runtime.config.loop_control.max_consecutive_failures = 3
    runtime.config.loop_control.max_steps_per_turn = 50
    provider = _ScriptedToolCallProvider(["Boom"] * 10)
    context, soul = _make_soul(runtime, provider, tmp_path)

    with patch("pythinker_code.telemetry.metrics.record_turn") as record_turn:
        await run_soul(soul, "go", _drain_ui_messages, asyncio.Event())

    # Stopped at the failure threshold, well before max_steps_per_turn.
    assert provider.generate_attempts == 3
    assert record_turn.call_args.kwargs["stop_reason"] == "stuck"
    # The final assistant message is a handoff summary mentioning being stuck.
    assert "stuck" in context.history[-1].extract_text(" ").lower()


@pytest.mark.asyncio
async def test_a_successful_step_resets_the_failure_counter(
    runtime: Runtime, tmp_path: Path
) -> None:
    """A productive (non-all-error) step resets the consecutive-failure counter."""
    runtime.config.loop_control.max_consecutive_failures = 3
    runtime.config.loop_control.max_steps_per_turn = 50
    # Boom, Boom, Ok (reset), Boom, Boom, then final text. Max run of failures is
    # 2 < 3, so the turn ends normally rather than `stuck`.
    provider = _ScriptedToolCallProvider(["Boom", "Boom", "Ok", "Boom", "Boom", None])
    context, soul = _make_soul(runtime, provider, tmp_path)

    with patch("pythinker_code.telemetry.metrics.record_turn") as record_turn:
        await run_soul(soul, "go", _drain_ui_messages, asyncio.Event())

    assert provider.generate_attempts == 6
    assert record_turn.call_args.kwargs["stop_reason"] == "no_tool_calls"


def test_stuck_summary_handles_whitespace_only_brief() -> None:
    """A tool error with a whitespace-only brief must not crash the handoff summary.

    ``(brief or message or "error").strip().splitlines()[0]`` raised IndexError when
    brief was non-empty whitespace: it is truthy, ``.strip()`` yields ``""``, and
    ``"".splitlines()`` is ``[]`` — exactly the all-error path this backstop exists for.
    """
    from pythinker_core.tooling import ToolError, ToolResult

    from pythinker_code.soul.pythinkersoul import _stuck_summary_message

    call = ToolCall(id="c0", function=ToolCall.FunctionBody(name="Boom", arguments="{}"))
    result = ToolResult(tool_call_id="c0", return_value=ToolError(message="", brief="   "))

    msg = _stuck_summary_message(3, [call], [result])

    text = msg.extract_text(" ")
    assert "stuck" in text.lower()
    assert "Boom" in text  # tool name still surfaced despite the empty brief


@pytest.mark.asyncio
async def test_max_consecutive_failures_zero_disables_backstop(
    runtime: Runtime, tmp_path: Path
) -> None:
    """A threshold of 0 disables the backstop entirely."""
    runtime.config.loop_control.max_consecutive_failures = 0
    runtime.config.loop_control.max_steps_per_turn = 50
    provider = _ScriptedToolCallProvider(["Boom", "Boom", "Boom", "Boom", None])
    context, soul = _make_soul(runtime, provider, tmp_path)

    with patch("pythinker_code.telemetry.metrics.record_turn") as record_turn:
        await run_soul(soul, "go", _drain_ui_messages, asyncio.Event())

    # Never escalated despite 4 consecutive failures; ran to the final text step.
    assert provider.generate_attempts == 5
    assert record_turn.call_args.kwargs["stop_reason"] == "no_tool_calls"
