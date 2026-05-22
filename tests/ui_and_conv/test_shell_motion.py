from __future__ import annotations

from rich.console import Console

from pythinker_code.ui.shell.motion import ActivitySnapshot, activity_status_line, spinner_frame_at


def _plain(renderable) -> str:
    console = Console(record=True, width=100, color_system=None)
    console.print(renderable)
    return console.export_text()


def test_spinner_frame_changes_with_time():
    assert spinner_frame_at(0.0) != spinner_frame_at(0.2)


def test_reduced_motion_uses_static_glyph():
    assert spinner_frame_at(0.2, reduced_motion=True) == "●"


def test_activity_status_line_contains_label_elapsed_tokens_and_interrupt_hint():
    line = activity_status_line(
        ActivitySnapshot(label="Thinking", elapsed_s=12.0, tokens=2400, token_rate=42)
    )
    output = _plain(line)
    assert "Thinking" in output
    assert "12s" in output
    assert "2.4k tokens" in output
    assert "42 tok/s" in output
    assert "esc to interrupt" in output


def test_activity_status_line_hides_secondary_parts_at_narrow_width():
    line = activity_status_line(
        ActivitySnapshot(label="Thinking", elapsed_s=12.0, tokens=2400, token_rate=42),
        width=24,
    )
    output = _plain(line)
    assert "Thinking" in output
    assert "42 tok/s" not in output
