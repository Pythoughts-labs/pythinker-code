from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from pythinker_core import StepResult
from pythinker_core.message import Message, ToolCall
from pythinker_core.tooling import ToolResult
from pythinker_core.tooling.empty import EmptyToolset

import pythinker_code.soul.pythinkersoul as pythinkersoul_module
from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.approval import Approval
from pythinker_code.soul.context import Context
from pythinker_code.soul.dynamic_injection import DynamicInjection
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.wire.types import StepBegin, StepInterrupted, TextPart, TurnBegin, TurnEnd


@pytest.fixture
def approval() -> Approval:
    """Override global yolo=True fixture; these tests only need wire semantics."""
    return Approval(yolo=False)


def _make_soul(runtime: Runtime, tmp_path: Path) -> PythinkerSoul:
    agent = Agent(
        name="Turn Balance Agent",
        system_prompt="Test prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    return PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))


@pytest.mark.asyncio
async def test_run_emits_turn_end_when_step_interrupts(
    runtime: Runtime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    soul = _make_soul(runtime, tmp_path)
    sent: list[object] = []

    async def fake_checkpoint() -> None:
        return None

    async def fake_step():
        raise RuntimeError("boom")

    monkeypatch.setattr(soul, "_checkpoint", fake_checkpoint)
    monkeypatch.setattr(soul._denwa_renji, "set_n_checkpoints", lambda _n: None)
    monkeypatch.setattr(soul, "_step", fake_step)
    monkeypatch.setattr(pythinkersoul_module, "wire_send", lambda msg: sent.append(msg))

    with pytest.raises(RuntimeError, match="boom"):
        await soul.run("hello")

    assert [msg for msg in sent if isinstance(msg, TurnBegin)] == [TurnBegin(user_input="hello")]
    assert [msg for msg in sent if isinstance(msg, StepBegin)] == [StepBegin(n=1)]
    assert [msg for msg in sent if isinstance(msg, StepInterrupted)] == [StepInterrupted()]
    assert [msg for msg in sent if isinstance(msg, TurnEnd)] == [TurnEnd()]
    assert isinstance(sent[-1], TurnEnd)


@pytest.mark.asyncio
async def test_run_emits_turn_end_on_cancelled_error(
    runtime: Runtime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    soul = _make_soul(runtime, tmp_path)
    sent: list[object] = []

    async def fake_checkpoint() -> None:
        return None

    async def fake_step():
        raise asyncio.CancelledError()

    monkeypatch.setattr(soul, "_checkpoint", fake_checkpoint)
    monkeypatch.setattr(soul._denwa_renji, "set_n_checkpoints", lambda _n: None)
    monkeypatch.setattr(soul, "_step", fake_step)
    monkeypatch.setattr(pythinkersoul_module, "wire_send", lambda msg: sent.append(msg))

    with pytest.raises(asyncio.CancelledError):
        await soul.run("hello")

    assert [msg for msg in sent if isinstance(msg, TurnBegin)] == [TurnBegin(user_input="hello")]
    assert [msg for msg in sent if isinstance(msg, StepBegin)] == [StepBegin(n=1)]
    assert [msg for msg in sent if isinstance(msg, StepInterrupted)] == []
    assert [msg for msg in sent if isinstance(msg, TurnEnd)] == [TurnEnd()]
    assert isinstance(sent[-1], TurnEnd)


@pytest.mark.asyncio
async def test_run_does_not_duplicate_turn_end_for_blocked_prompt(
    runtime: Runtime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    soul = _make_soul(runtime, tmp_path)
    sent: list[object] = []

    async def fake_trigger(*args, **kwargs):
        return [SimpleNamespace(action="block", reason="blocked by hook")]

    monkeypatch.setattr(soul._hook_engine, "trigger", fake_trigger)
    monkeypatch.setattr(pythinkersoul_module, "wire_send", lambda msg: sent.append(msg))

    await soul.run("hello")

    assert sent == [
        TurnBegin(user_input="hello"),
        TextPart(text="blocked by hook"),
        TurnEnd(),
    ]


@pytest.mark.asyncio
async def test_step_persists_assistant_message_when_tool_results_cancelled(
    runtime: Runtime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_step must persist the assistant message and a synthetic tool-result message when
    tool_results() is cancelled mid-await, so the next turn does not see unanswered
    tool calls (which providers reject)."""
    soul = _make_soul(runtime, tmp_path)

    tool_call = ToolCall(
        id="call-cancel-1",
        function=ToolCall.FunctionBody(name="Noop", arguments="{}"),
    )
    pending_future: asyncio.Future[ToolResult] = asyncio.get_event_loop().create_future()

    async def fake_pythinker_core_step(chat_provider, system_prompt, toolset, history, **kwargs):
        return StepResult(
            id="step-cancel-1",
            message=Message(role="assistant", content=[TextPart(text="I'll use a tool.")]),
            usage=None,
            tool_calls=[tool_call],
            _tool_result_futures={"call-cancel-1": pending_future},
        )

    async def fake_collect_injections() -> list[DynamicInjection]:
        return []

    monkeypatch.setattr(soul, "_collect_injections", fake_collect_injections)
    monkeypatch.setattr(pythinkersoul_module.pythinker_core, "step", fake_pythinker_core_step)
    monkeypatch.setattr(pythinkersoul_module, "wire_send", lambda _msg: None)

    # Run _step in a task and cancel it while it is blocked in tool_results()
    step_task = asyncio.create_task(soul._step())
    # Yield enough times for the task to reach `await result.tool_results()` which
    # then blocks on the pending_future.
    for _ in range(10):
        await asyncio.sleep(0)
    step_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await step_task

    # Allow any asyncio.shield()-wrapped grow_context_task to complete.
    for _ in range(10):
        await asyncio.sleep(0)

    history = list(soul.context.history)
    roles = [m.role for m in history]
    assert "assistant" in roles, f"assistant message not persisted; history={history}"
    tool_messages = [m for m in history if m.role == "tool"]
    assert tool_messages, f"no synthetic tool result message persisted; history={history}"
    assert tool_messages[0].tool_call_id == tool_call.id, (
        f"tool message has wrong tool_call_id; "
        f"expected={tool_call.id}, got={tool_messages[0].tool_call_id}"
    )
