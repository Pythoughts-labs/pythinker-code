from __future__ import annotations

from rich.console import Console
from rich.text import Text

from pythinker_code.ui.shell.visualize._dialog_shell import DialogOption, render_dialog


def _plain(renderable, *, width: int = 80) -> str:
    console = Console(record=True, width=width, color_system=None)
    console.print(renderable)
    return console.export_text()


def test_dialog_renders_title_body_and_options():
    output = _plain(
        render_dialog(
            kind="approval",
            title="Run shell command",
            body=[Text("pytest")],
            options=[
                DialogOption(label="Approve once", selected=True, key="1"),
                DialogOption(label="Reject", selected=False, key="2"),
            ],
        )
    )
    assert "Run shell command" in output
    assert "pytest" in output
    assert "Approve once" in output
    assert "Reject" in output
