"""Tests for the customizable status line: config model, segment resolver,
and the external status command runner."""

from __future__ import annotations

import asyncio
import sys

import pytest
from pydantic import ValidationError

from pythinker_code.config import Config, StatusLineConfig, TUIConfig
from pythinker_code.ui.shell.statusline import (
    DEFAULT_STATUSLINE_SEGMENTS,
    StatusLineCommandRunner,
    resolve_segments,
)

# ---------------------------------------------------------------------------
# StatusLineConfig model
# ---------------------------------------------------------------------------


def test_config_has_statusline_section_with_defaults():
    cfg = Config()
    sl = cfg.tui.statusline
    assert isinstance(sl, StatusLineConfig)
    assert sl.enabled is True
    assert sl.segments == list(DEFAULT_STATUSLINE_SEGMENTS)
    assert sl.command is None
    assert sl.command_timeout_ms == 1000


def test_statusline_unknown_segment_ids_are_dropped():
    sl = StatusLineConfig(segments=["cwd", "bogus-from-the-future", "model"])
    assert sl.segments == ["cwd", "model"]


def test_statusline_duplicate_segment_ids_are_deduped_keeping_first():
    sl = StatusLineConfig(segments=["model", "cwd", "model"])
    assert sl.segments == ["model", "cwd"]


def test_statusline_timeout_must_be_positive():
    with pytest.raises(ValidationError):
        StatusLineConfig(command_timeout_ms=0)


def test_statusline_round_trips_through_dump():
    sl = StatusLineConfig(segments=["model", "git"], command="echo hi")
    cfg = Config(tui=TUIConfig(statusline=sl))
    raw = cfg.model_dump(mode="json")
    restored = Config.model_validate(raw)
    assert restored.tui.statusline.segments == ["model", "git"]
    assert restored.tui.statusline.command == "echo hi"


# ---------------------------------------------------------------------------
# resolve_segments
# ---------------------------------------------------------------------------


def test_resolve_segments_default_layout():
    layout = resolve_segments(StatusLineConfig())
    assert layout.line1 == ["cwd", "git", "flags"]
    assert layout.line2_right == ["context", "tokens", "model"]
    assert layout.show_command is False


def test_resolve_segments_disabled_master_switch_keeps_everything():
    # enabled=False means "render the stock footer"; resolver reports defaults.
    layout = resolve_segments(StatusLineConfig(enabled=False, segments=["model"]))
    assert layout.line1 == ["cwd", "git", "flags"]
    assert layout.line2_right == ["context", "tokens", "model"]
    assert layout.show_command is False


def test_resolve_segments_respects_order_and_omissions():
    layout = resolve_segments(StatusLineConfig(segments=["git", "cwd", "model"]))
    assert layout.line1 == ["git", "cwd"]
    assert layout.line2_right == ["model"]


def test_resolve_segments_command_segment_requires_configured_command():
    no_cmd = resolve_segments(StatusLineConfig(segments=["cwd", "command"]))
    assert no_cmd.show_command is False
    with_cmd = resolve_segments(StatusLineConfig(segments=["cwd", "command"], command="echo hi"))
    assert with_cmd.show_command is True


def test_resolve_segments_empty_list_renders_nothing_optional():
    layout = resolve_segments(StatusLineConfig(segments=[]))
    assert layout.line1 == []
    assert layout.line2_right == []
    assert layout.show_command is False


# ---------------------------------------------------------------------------
# StatusLineCommandRunner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_command_runner_caches_first_stdout_line():
    runner = StatusLineCommandRunner(
        command=f"{sys.executable} -c \"print('line-one'); print('line-two')\"",
        timeout_ms=5000,
    )
    await runner.refresh_once()
    assert runner.current_line == "line-one"


@pytest.mark.asyncio
async def test_command_runner_timeout_fails_closed():
    runner = StatusLineCommandRunner(
        command=f'{sys.executable} -c "import time; time.sleep(10)"',
        timeout_ms=100,
    )
    await runner.refresh_once()
    assert runner.current_line == ""


@pytest.mark.asyncio
async def test_command_runner_nonzero_exit_fails_closed():
    runner = StatusLineCommandRunner(
        command=f'{sys.executable} -c "raise SystemExit(3)"',
        timeout_ms=5000,
    )
    await runner.refresh_once()
    assert runner.current_line == ""


@pytest.mark.asyncio
async def test_command_runner_invalid_command_fails_closed():
    runner = StatusLineCommandRunner(command="definitely-not-a-real-binary-xyz", timeout_ms=1000)
    await runner.refresh_once()
    assert runner.current_line == ""


@pytest.mark.asyncio
async def test_command_runner_output_is_capped():
    runner = StatusLineCommandRunner(
        command=f"{sys.executable} -c \"print('x' * 1000)\"",
        timeout_ms=5000,
    )
    await runner.refresh_once()
    assert 0 < len(runner.current_line) <= 200


@pytest.mark.asyncio
async def test_command_runner_lifecycle_start_stop():
    runner = StatusLineCommandRunner(
        command=f"{sys.executable} -c \"print('tick')\"",
        timeout_ms=5000,
        interval_s=0.05,
    )
    runner.start()
    try:
        for _ in range(100):
            if runner.current_line == "tick":
                break
            await asyncio.sleep(0.02)
        assert runner.current_line == "tick"
    finally:
        await runner.stop()
    assert runner.is_running is False


# ---------------------------------------------------------------------------
# Footer render integration
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402

from pythinker_code.soul import StatusSnapshot  # noqa: E402
from pythinker_code.ui.shell import prompt as shell_prompt  # noqa: E402
from pythinker_code.ui.shell.prompt import CustomPromptSession, PromptMode  # noqa: E402


def _make_session(statusline: StatusLineConfig | None = None) -> Any:
    session = object.__new__(CustomPromptSession)
    session._mode = PromptMode.AGENT
    session._model_name = "fast-model"
    session._model_capabilities = set()
    session._thinking = False
    session._status_provider = lambda: StatusSnapshot(context_usage=0.0)
    session._background_task_count_provider = None
    session._tips = []
    session._tip_rotation_index = 0
    session._last_tip_rotate_time = float("inf")
    if statusline is not None:
        session._statusline_layout = resolve_segments(statusline)
    return session


def _render_card(session: Any, monkeypatch: pytest.MonkeyPatch, width: int = 120) -> str:
    class _DummyOutput:
        @staticmethod
        def get_size() -> Any:
            return SimpleNamespace(columns=width)

    monkeypatch.setenv("PYTHINKER_TUI_STYLE", "card")
    monkeypatch.setattr(
        shell_prompt, "get_app_or_none", lambda: SimpleNamespace(output=_DummyOutput())
    )
    monkeypatch.setattr(shell_prompt, "_get_git_branch", lambda: "main")
    monkeypatch.setattr(shell_prompt, "_get_git_status", lambda: (False, 0, 0))
    monkeypatch.setattr(shell_prompt, "_shorten_cwd", lambda _: "~/proj")
    monkeypatch.setattr("pythinker_code.extensions.footer_statuses", lambda: {})
    fragments = session._render_bottom_toolbar()
    return "".join(fragment[1] for fragment in fragments)


def test_card_footer_default_layout_shows_all_segments(monkeypatch: pytest.MonkeyPatch):
    plain = _render_card(_make_session(StatusLineConfig()), monkeypatch)
    assert "~/proj" in plain
    assert "main" in plain
    assert "context: 0.0%" in plain
    assert "fast-model" in plain


def test_card_footer_segments_can_be_hidden(monkeypatch: pytest.MonkeyPatch):
    plain = _render_card(
        _make_session(StatusLineConfig(segments=["context", "model"])), monkeypatch
    )
    assert "~/proj" not in plain
    assert "main" not in plain
    assert "context: 0.0%" in plain
    assert "fast-model" in plain


def test_card_footer_disabled_customization_matches_default(monkeypatch: pytest.MonkeyPatch):
    stock = _render_card(_make_session(None), monkeypatch)
    disabled = _render_card(
        _make_session(StatusLineConfig(enabled=False, segments=["model"])), monkeypatch
    )
    assert disabled == stock


def test_card_footer_shows_external_command_line(monkeypatch: pytest.MonkeyPatch):
    cfg = StatusLineConfig(
        segments=["cwd", "git", "flags", "context", "tokens", "model", "command"],
        command="echo hi",
    )
    session = _make_session(cfg)
    runner = StatusLineCommandRunner(command="echo hi", timeout_ms=1000)
    runner.current_line = "build: green"
    session._statusline_runner = runner
    plain = _render_card(session, monkeypatch)
    assert "build: green" in plain
