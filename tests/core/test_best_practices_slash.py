"""Tests for /best-practices slash command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pythinker_core.message import TextPart as CoreTextPart
from pythinker_core.tooling.empty import EmptyToolset

import pythinker_code.prompts as prompts
from pythinker_code.soul.agent import Agent, Runtime
from pythinker_code.soul.context import Context
from pythinker_code.soul.pythinkersoul import PythinkerSoul
from pythinker_code.soul.slash import best_practices
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


async def _run(soul: PythinkerSoul, args: str) -> None:
    result = best_practices(soul, args)
    if result is not None:
        await result


def _context_texts(soul: PythinkerSoul) -> list[str]:
    return [
        part.text
        for msg in soul.context.history
        for part in msg.content
        if isinstance(part, CoreTextPart)
    ]


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[TextPart]:
    captured: list[TextPart] = []
    monkeypatch.setattr("pythinker_code.soul.slash.wire_send", lambda msg: captured.append(msg))
    return captured


def test_best_practices_prompt_asset_loads() -> None:
    assert "Engineering best practices" in prompts.BEST_PRACTICES
    # Core sections distilled from the Codex CLI prompts.
    for heading in (
        "## Code changes",
        "## Working in a dirty worktree",
        "## Testing",
        "## Plan and todo hygiene",
        "## Progress updates",
        "## Debugging",
        "## Final answers",
    ):
        assert heading in prompts.BEST_PRACTICES
    # Wording pins for the load-bearing Codex guidance.
    assert "do not add tests to codebases with no tests" in prompts.BEST_PRACTICES
    assert "exactly one item in_progress at a time" in prompts.BEST_PRACTICES
    assert "NEVER revert existing changes you did not make" in prompts.BEST_PRACTICES


class TestBestPracticesSlashCommand:
    async def test_injects_guidance_into_context(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run(soul, "")

        texts = _context_texts(soul)
        assert any("Engineering best practices" in t for t in texts)
        assert any("## Debugging" in t for t in texts)

    async def test_does_not_start_a_turn(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run(soul, "")

        turn_mock = soul._turn
        assert isinstance(turn_mock, AsyncMock)
        turn_mock.assert_not_awaited()

    async def test_confirms_to_user(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run(soul, "")

        assert any("Best practices injected" in s.text for s in sent)

    async def test_section_filter_injects_only_matching_section(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run(soul, "testing")

        texts = _context_texts(soul)
        injected = next(t for t in texts if "## Testing" in t)
        assert "## Debugging" not in injected
        assert "Engineering best practices" in injected  # preamble retained

    async def test_unknown_section_shows_available_sections(
        self, runtime: Runtime, tmp_path: Path, sent: list[TextPart]
    ) -> None:
        soul = _make_soul(runtime, tmp_path)

        await _run(soul, "nonexistent-topic")

        assert any("Unknown section" in s.text for s in sent)
        assert _context_texts(soul) == []

    async def test_command_and_alias_registered(self, runtime: Runtime, tmp_path: Path) -> None:
        soul = _make_soul(runtime, tmp_path)
        names = {cmd.name for cmd in soul.available_slash_commands}
        assert "best-practices" in names
        cmd = soul_slash_registry.find_command("bp")
        assert cmd is not None and cmd.name == "best-practices"
