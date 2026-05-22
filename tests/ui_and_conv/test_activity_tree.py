from __future__ import annotations

from rich.console import Console

from pythinker_code.ui.shell.visualize._activity_tree import ActivityRow, render_activity_tree


def _plain(renderable, *, width: int = 80) -> str:
    console = Console(record=True, width=width, color_system=None)
    console.print(renderable)
    return console.export_text()


def test_activity_tree_renders_compact_rows():
    output = _plain(
        render_activity_tree(
            [
                ActivityRow(label="explore", detail="Read _live_view.py", state="running"),
                ActivityRow(label="review", detail="Finished audit", state="completed"),
            ],
            width=80,
        )
    )
    assert "explore" in output
    assert "Read _live_view.py" in output
    assert "review" in output


def test_activity_tree_truncates_long_detail():
    output = _plain(
        render_activity_tree(
            [ActivityRow(label="explore", detail="x" * 120, state="running")],
            width=40,
        ),
        width=40,
    )
    assert all(len(row) <= 41 for row in output.splitlines() if row)
