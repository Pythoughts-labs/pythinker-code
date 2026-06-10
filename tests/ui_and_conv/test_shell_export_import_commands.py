from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pythinker_core.message import Message
from rich.console import Console

from pythinker_code.session import Session
from pythinker_code.ui.shell import export_import as shell_export_import
from pythinker_code.wire.types import TextPart, TurnBegin, TurnEnd


def _make_shell_app(work_dir: Path) -> Mock:
    from pythinker_code.soul.pythinkersoul import PythinkerSoul

    soul = Mock(spec=PythinkerSoul)
    soul.runtime.session.work_dir = work_dir
    soul.runtime.session.id = "curr-session-id"
    soul.context.history = []
    soul.context.token_count = 123
    soul.context.append_message = AsyncMock()
    soul.context.update_token_count = AsyncMock()
    soul.wire_file.append_message = AsyncMock()

    app = Mock()
    app.soul = soul
    return app


async def test_export_writes_markdown_file(tmp_path: Path) -> None:
    app = _make_shell_app(tmp_path)
    app.soul.context.history = [
        Message(role="user", content=[TextPart(text="Hello")]),
        Message(role="assistant", content=[TextPart(text="Hi!")]),
    ]

    output = tmp_path / "session.md"
    await shell_export_import.export(app, str(output))  # type: ignore[reportGeneralTypeIssues]

    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "# Pythinker Session Export" in content
    assert "session_id: curr-session-id" in content
    assert "Hello" in content
    assert "Hi!" in content


async def test_export_escapes_bracketed_output_path(tmp_path: Path, monkeypatch) -> None:
    app = _make_shell_app(tmp_path)
    app.soul.context.history = [Message(role="user", content=[TextPart(text="Hello")])]
    output_dir = tmp_path / "[proj]"
    output_dir.mkdir()
    output = output_dir / "session.md"

    printed = StringIO()
    monkeypatch.setattr(
        shell_export_import,
        "console",
        Console(file=printed, force_terminal=False, color_system=None),
    )

    await shell_export_import.export(app, str(output))  # type: ignore[reportGeneralTypeIssues]

    assert "[proj]" in printed.getvalue()


async def test_import_from_file_appends_message_and_wire_markers(tmp_path: Path) -> None:
    app = _make_shell_app(tmp_path)
    source_file = tmp_path / "source.md"
    source_file.write_text("previous conversation context", encoding="utf-8")

    await shell_export_import.import_context(app, str(source_file))  # type: ignore[reportGeneralTypeIssues]

    assert app.soul.context.append_message.await_count == 1
    imported_message = app.soul.context.append_message.await_args.args[0]
    assert imported_message.role == "user"

    imported_text = next(
        p.text
        for p in imported_message.content
        if isinstance(p, TextPart) and "<imported_context" in p.text
    )
    assert "source=\"file 'source.md'\"" in imported_text
    assert "previous conversation context" in imported_text

    wire_calls = app.soul.wire_file.append_message.await_args_list
    assert len(wire_calls) == 2
    assert isinstance(wire_calls[0].args[0], TurnBegin)
    assert wire_calls[0].args[0].user_input == "[Imported context from file 'source.md']"
    assert isinstance(wire_calls[1].args[0], TurnEnd)


async def test_import_from_session_appends_message_and_wire_markers(
    tmp_path: Path, monkeypatch
) -> None:
    app = _make_shell_app(tmp_path)

    source_context_file = tmp_path / "source_context.jsonl"
    source_message = Message(
        role="user",
        content=[TextPart(text="Question from old session")],
    )
    source_context_file.write_text(
        source_message.model_dump_json(exclude_none=True) + "\n",
        encoding="utf-8",
    )

    async def fake_find(_work_dir: Path, _target: str) -> SimpleNamespace:
        return SimpleNamespace(context_file=source_context_file)

    monkeypatch.setattr(Session, "find", fake_find)

    await shell_export_import.import_context(app, "old-session-id")  # type: ignore[reportGeneralTypeIssues]

    assert app.soul.context.append_message.await_count == 1
    imported_message = app.soul.context.append_message.await_args.args[0]
    imported_text = next(
        p.text
        for p in imported_message.content
        if isinstance(p, TextPart) and "<imported_context" in p.text
    )
    assert "source=\"session 'old-session-id'\"" in imported_text
    assert "[USER]" in imported_text
    assert "Question from old session" in imported_text

    wire_calls = app.soul.wire_file.append_message.await_args_list
    assert len(wire_calls) == 2
    assert isinstance(wire_calls[0].args[0], TurnBegin)
    assert wire_calls[0].args[0].user_input == "[Imported context from session 'old-session-id']"
    assert isinstance(wire_calls[1].args[0], TurnEnd)


async def test_import_directory_path_prints_clear_error(tmp_path: Path, monkeypatch) -> None:
    app = _make_shell_app(tmp_path)
    target_dir = tmp_path / "context-dir"
    target_dir.mkdir()

    print_mock = Mock()
    monkeypatch.setattr(shell_export_import.console, "print", print_mock)

    await shell_export_import.import_context(app, str(target_dir))  # type: ignore[reportGeneralTypeIssues]

    assert print_mock.called
    rendered = " ".join(str(arg) for args in print_mock.call_args_list for arg in args.args)
    assert "directory" in rendered.lower()
    assert "provide a file" in rendered.lower()
    assert app.soul.context.append_message.await_count == 0


def test_restore_rejects_path_traversal_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The /restore handler must reject traversal args before calling restore_file_restore_point."""
    import pythinker_code.file_restore as file_restore_mod
    from pythinker_code.soul.pythinkersoul import PythinkerSoul
    from pythinker_code.ui.shell import slash as shell_slash
    from pythinker_code.ui.shell.slash import registry as shell_slash_registry

    # A sentinel outside the session dir — must remain untouched
    secret = tmp_path / "secret.json"
    secret.write_text('{"secret": true}', encoding="utf-8")

    # Build a mock shell whose soul passes the PythinkerSoul isinstance check
    mock_soul = Mock(spec=PythinkerSoul)
    mock_soul.runtime.session = Mock()
    shell = Mock()
    shell.soul = mock_soul

    # No valid restore points exist — so any supplied arg is not a member
    monkeypatch.setattr(file_restore_mod, "list_file_restore_points", lambda _session, **kw: [])

    # restore_file_restore_point must NOT be invoked on the traversal path
    def _should_not_be_called(*args, **kwargs):
        pytest.fail("restore_file_restore_point was called with a traversal id")

    monkeypatch.setattr(file_restore_mod, "restore_file_restore_point", _should_not_be_called)

    # Capture console output
    print_mock = Mock()
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    cmd = shell_slash_registry.find_command("restore")
    assert cmd is not None
    cmd.func(shell, "../../secret")

    # The sentinel file must be untouched
    assert secret.exists()
    assert secret.read_text(encoding="utf-8") == '{"secret": true}'

    # The handler must have printed "Restore point not found"
    rendered = " ".join(str(arg) for args in print_mock.call_args_list for arg in args.args)
    assert "Restore point not found" in rendered


def test_restore_surfaces_value_error_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A *valid* restore id whose stored path escapes the workspace must surface a clean
    'Failed to restore' message (file_restore raises ValueError), not crash uncaught."""
    import pythinker_code.file_restore as file_restore_mod
    from pythinker_code.soul.pythinkersoul import PythinkerSoul
    from pythinker_code.ui.shell import slash as shell_slash
    from pythinker_code.ui.shell.slash import registry as shell_slash_registry

    mock_soul = Mock(spec=PythinkerSoul)
    mock_soul.runtime.session = Mock()
    shell = Mock()
    shell.soul = mock_soul

    # A valid restore point so the membership guard passes and we reach the restore call.
    point = Mock()
    point.id = "a1b2c3d4"
    monkeypatch.setattr(
        file_restore_mod, "list_file_restore_points", lambda _session, **kw: [point]
    )

    def _raise_value_error(*args, **kwargs):
        raise ValueError("Restore target outside workspace")

    monkeypatch.setattr(file_restore_mod, "restore_file_restore_point", _raise_value_error)

    print_mock = Mock()
    monkeypatch.setattr(shell_slash.console, "print", print_mock)

    cmd = shell_slash_registry.find_command("restore")
    assert cmd is not None
    cmd.func(shell, "a1b2c3d4")  # must NOT raise

    rendered = " ".join(str(arg) for args in print_mock.call_args_list for arg in args.args)
    assert "Failed to restore" in rendered
