from __future__ import annotations

from rich.console import Console

from pythinker_code.ui.shell.visualize._transcript import render_transcript_row


def _plain(renderable, *, width: int = 80) -> str:
    console = Console(record=True, width=width, color_system=None)
    console.print(renderable)
    return console.export_text()


def test_user_row_contains_role_and_content():
    output = _plain(render_transcript_row("user", "scan this codebase"))
    assert "You" in output
    assert "scan this codebase" in output


def test_tool_row_contains_label_target_and_status():
    output = _plain(render_transcript_row("tool", "Read src/app.py", status="completed"))
    assert "Read src/app.py" in output
    assert "✓" in output
