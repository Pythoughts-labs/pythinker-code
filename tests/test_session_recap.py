from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from pythinker_code.session_recap import (
    SessionRecapItem,
    build_turn_recap_line,
    format_recap,
    parse_recap_range,
)


def test_parse_recap_range_defaults_to_today() -> None:
    now = datetime(2026, 6, 1, 15, 30, tzinfo=ZoneInfo("UTC"))

    recap_range = parse_recap_range("", now=now)

    assert recap_range.label == "today"
    assert recap_range.start_ts == datetime(2026, 6, 1, tzinfo=ZoneInfo("UTC")).timestamp()
    assert recap_range.end_ts == now.timestamp()


def test_format_recap_includes_tools_and_modified_files() -> None:
    item = SessionRecapItem(title="prompt rendering", session_id="s1")
    item.start_ts = 100.0
    item.end_ts = 430.0
    item.turn_count = 2
    item.first_user_message = "make shell output match the transcript example"
    item.last_user_message = "add recaps too"
    item.tool_counts.update({"ReadFile": 2, "WriteFile": 1})
    item.add_modified_file("src/pythinker_code/ui/shell/visualize/_live_view.py")

    output = format_recap(
        [item],
        parse_recap_range("today", now=datetime(2026, 6, 1, 15, 30, tzinfo=ZoneInfo("UTC"))),
    )

    assert "**Recap — today**" in output
    assert "Read ×2" in output
    assert "Write" in output
    assert "src/pythinker_code/ui/shell/visualize/_live_vie" in output
    assert "add recaps too" in output


def test_build_turn_recap_line_uses_assistant_text() -> None:
    line = build_turn_recap_line(
        request="implement recaps",
        assistant_text="Implemented a /recap command and a shell recap banner. Extra detail.",
        step_count=3,
    )

    assert line == (
        "※ recap: Implemented a /recap command and a shell recap banner. (3 steps) "
        "(disable recaps in /settings)"
    )
