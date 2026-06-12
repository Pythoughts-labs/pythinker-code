"""Headless channel discipline: stdout is a data channel, stderr is for humans.

In stream-json mode every stdout line must parse as JSON — plain-text
failure diagnostics corrupt the stream for machine parsers. Diagnostics
route to stderr in every mode, and stream-json additionally emits one
structured error record (a Notification with category="run",
type="error") so parsers observe the terminal failure and its exit code.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pythinker_core.chat_provider import APIConnectionError, APIStatusError, ChatProviderError

from pythinker_code.cli import ExitCode, OutputFormat
from pythinker_code.soul import LLMNotSet, MaxStepsReached, RunCancelled
from pythinker_code.ui.print import Print


def _make_print(tmp_path: Path, output_format: OutputFormat) -> Print:
    from unittest.mock import AsyncMock

    soul = AsyncMock()
    soul.runtime = None
    return Print(
        soul=soul,
        input_format="text",
        output_format=output_format,
        context_file=tmp_path / "context.json",
    )


def _run_failing(p: Print, monkeypatch: pytest.MonkeyPatch, exception: BaseException) -> int:
    async def _raise(*args: object, **kwargs: object) -> object:
        raise exception

    monkeypatch.setattr("pythinker_code.ui.print.run_soul", _raise)
    return asyncio.run(p.run(command="do something"))


def _parsed_stdout_lines(out: str) -> list[dict]:
    lines = [line for line in out.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def _error_events(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("category") == "run" and r.get("type") == "error"]


FAILURES = [
    pytest.param(LLMNotSet(), id="llm-not-set"),
    pytest.param(ChatProviderError("provider exploded"), id="provider-error"),
    pytest.param(RunCancelled(), id="cancelled"),
    pytest.param(MaxStepsReached(10), id="max-steps"),
]


class TestStreamJsonChannelDiscipline:
    @pytest.mark.parametrize("exception", FAILURES)
    def test_every_stdout_line_parses_as_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, exception
    ) -> None:
        p = _make_print(tmp_path, "stream-json")

        _run_failing(p, monkeypatch, exception)

        records = _parsed_stdout_lines(capsys.readouterr().out)
        assert _error_events(records), "expected a structured error record on stdout"

    @pytest.mark.parametrize("exception", FAILURES)
    def test_diagnostic_text_reaches_stderr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, exception
    ) -> None:
        p = _make_print(tmp_path, "stream-json")

        _run_failing(p, monkeypatch, exception)

        assert capsys.readouterr().err.strip()

    def test_error_event_carries_exit_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        p = _make_print(tmp_path, "stream-json")

        code = _run_failing(p, monkeypatch, APIStatusError(401, "no auth"))

        events = _error_events(_parsed_stdout_lines(capsys.readouterr().out))
        assert events[0]["payload"]["exit_code"] == int(code) == int(ExitCode.FAILURE)

    def test_retryable_error_event_exit_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        p = _make_print(tmp_path, "stream-json")

        code = _run_failing(p, monkeypatch, APIConnectionError("connection refused"))

        events = _error_events(_parsed_stdout_lines(capsys.readouterr().out))
        assert events[0]["payload"]["exit_code"] == int(code) == int(ExitCode.RETRYABLE)

    def test_unknown_error_emits_event_then_reraises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        p = _make_print(tmp_path, "stream-json")

        with pytest.raises(RuntimeError):
            _run_failing(p, monkeypatch, RuntimeError("boom"))

        records = _parsed_stdout_lines(capsys.readouterr().out)
        assert _error_events(records)


class TestTextModeChannelDiscipline:
    def test_diagnostic_goes_to_stderr_not_stdout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        p = _make_print(tmp_path, "text")

        _run_failing(p, monkeypatch, LLMNotSet())

        captured = capsys.readouterr()
        assert str(LLMNotSet()) not in captured.out
        assert captured.err.strip()
