"""Tests for /learn slash command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pythinker_core.tooling.empty import EmptyToolset

import pythinker_code.prompts as prompts
from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.soul.slash import learn
from pythinker_code.soul.slash import registry as soul_slash_registry
from pythinker_code.wire.types import TextPart


def _make_soul(runtime: Runtime, tmp_path: Path) -> PythinkerSoul:
    agent = Agent(
        name="Test Agent",
        system_prompt="Test system prompt.",
        toolset=EmptyToolset(),
        runtime=runtime,
    )
    soul = PythinkerSoul(agent, context=Context(file_backend=tmp_path / "history.jsonl"))
    soul._turn = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return soul


async def _run_learn(soul: PythinkerSoul, args: str) -> None:
    result = learn(soul, args)
    if result is not None:
        await result


def _message_text(message) -> str:
    return "".join(part.text for part in message.content if hasattr(part, "text"))


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[TextPart]:
    captured: list[TextPart] = []
    monkeypatch.setattr("pythinker_code.soul.slash.wire_send", lambda msg: captured.append(msg))
    return captured


def test_learn_prompt_asset_loads() -> None:
    assert "The user ran `/learn`" in prompts.LEARN
    # Wording pins for the load-bearing extraction discipline.
    assert "Extract the PATTERN, not the instance" in prompts.LEARN
    assert "when X, do Y" in prompts.LEARN
    assert "One pattern per lesson" in prompts.LEARN
    assert "an empty result is a valid result" in prompts.LEARN
    # The prompt must route persistence through the Memory tool.
    assert "Memory tool" in prompts.LEARN
    assert "{focus}" in prompts.LEARN


class TestLearnSlashCommand:
    async def test_starts_turn_with_learn_prompt(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run_learn(soul, "")

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)
        turn_mock.assert_awaited_once()
        assert turn_mock.await_args is not None
        text = _message_text(turn_mock.await_args.args[0])
        assert "Extract the PATTERN, not the instance" in text
        assert "review the whole session" in text

    async def test_focus_argument_is_threaded_into_prompt(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run_learn(soul, "the polling mistake")

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)
        assert turn_mock.await_args is not None
        text = _message_text(turn_mock.await_args.args[0])
        assert "Focus especially on: the polling mistake" in text

    async def test_confirms_to_user(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run_learn(soul, "")

        assert any("lessons worth keeping" in s.text for s in sent)

    async def test_command_registered(self, runtime: Runtime, tmp_path: Path) -> None:
        soul = _make_soul(runtime, tmp_path)
        names = {cmd.name for cmd in soul.available_slash_commands}
        assert "learn" in names
        cmd = soul_slash_registry.find_command("learn")
        assert cmd is not None and cmd.name == "learn"
