from __future__ import annotations

from collections import Counter
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from zoneinfo import ZoneInfo

import pytest

if TYPE_CHECKING:
    from pythinker_code.session import Session

from pythinker_code.session_recap import (
    SessionRecapItem,
    _first_sentence,
    _format_duration,
    _format_tool_counts,
    _last_substantive_thread,
    _outcome_sentence,
    _tool_label,
    build_turn_recap_line,
    format_recap,
    parse_recap_range,
    summarize_session_for_recap,
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
        "※ recap: Implemented a /recap command and a shell recap banner. · 3 steps "
        "(disable recaps in /settings)"
    )


def test_build_turn_recap_line_strips_report_blocks() -> None:
    line = build_turn_recap_line(
        request="run deep scan",
        assistant_text=(
            "Deep scan completed. Full report saved here:\n"
            "  `.pythinker/reports/deep-code-scan-pr-auto-mode-deliberation-clean.md`\n"
            "```report\n"
            '{"title": "Deep Code Scan Results", "findings": []}\n'
            "```\n"
        ),
        step_count=28,
    )

    assert line == ("※ recap: Deep scan completed. · 28 steps (disable recaps in /settings)")


def test_build_turn_recap_line_prefers_closing_summary_over_opening_intent() -> None:
    # The opening sentence is pure intent; the recap should surface the outcome.
    line = build_turn_recap_line(
        request="run a deep scan",
        assistant_text=(
            "I'll start by gathering the current state of the repository before "
            "kicking off a fresh deep scan. "
            "I read every existing report and traced the imports. "
            "Generated three fresh report files and refreshed the scan index."
        ),
        step_count=67,
        files_changed=4,
    )

    assert line == (
        "※ recap: Generated three fresh report files and refreshed the scan index. "
        "· 4 files changed · 67 steps (disable recaps in /settings)"
    )


def test_build_turn_recap_line_skips_trailing_question() -> None:
    line = build_turn_recap_line(
        request="refactor auth",
        assistant_text=(
            "Refactored the auth module and added regression tests. "
            "Want me to also update the docs?"
        ),
        step_count=5,
    )

    assert line == (
        "※ recap: Refactored the auth module and added regression tests. · 5 steps "
        "(disable recaps in /settings)"
    )


def test_build_turn_recap_line_singular_deltas() -> None:
    line = build_turn_recap_line(
        request="tweak",
        assistant_text="Adjusted the spinner interval to feel calmer on slow terminals.",
        step_count=1,
        files_changed=1,
    )

    assert line == (
        "※ recap: Adjusted the spinner interval to feel calmer on slow terminals. "
        "· 1 file changed · 1 step (disable recaps in /settings)"
    )


def test_outcome_sentence_picks_last_substantive_declarative() -> None:
    # Skips intent opener and a path-dominated trailing line.
    text = (
        "Let me trace the failure first. "
        "Patched the off-by-one in the cursor math and added a guard. "
        "See logs/very-long-trace-file-name-that-exceeds-the-token-limit.txt"
    )
    assert _outcome_sentence(text) == (
        "Patched the off-by-one in the cursor math and added a guard."
    )


def test_outcome_sentence_skips_curly_apostrophe_intent() -> None:
    # Models emit a typographic apostrophe; the trailing intent must still skip.
    text = (
        "Patched the cursor math and added a regression guard. "
        "Now I’ll run the full suite to confirm."
    )
    assert _outcome_sentence(text) == "Patched the cursor math and added a regression guard."


_UTC = ZoneInfo("UTC")
_NOW = datetime(2026, 6, 1, 15, 30, tzinfo=_UTC)


def test_parse_recap_range_yesterday() -> None:
    rng = parse_recap_range("yesterday", now=_NOW)
    assert rng.label == "yesterday"
    assert rng.start_ts == datetime(2026, 5, 31, tzinfo=_UTC).timestamp()
    assert rng.end_ts == datetime(2026, 5, 31, 23, 59, 59, 999999, tzinfo=_UTC).timestamp()


@pytest.mark.parametrize("arg", ["week", "7d", "past 7 days"])
def test_parse_recap_range_week_aliases(arg: str) -> None:
    rng = parse_recap_range(arg, now=_NOW)
    assert rng.label == "past 7 days"
    assert rng.start_ts == datetime(2026, 5, 25, tzinfo=_UTC).timestamp()
    assert rng.end_ts == _NOW.timestamp()


def test_parse_recap_range_explicit_date() -> None:
    rng = parse_recap_range("2026-05-20", now=_NOW)
    assert rng.label == "2026-05-20"
    assert rng.start_ts == datetime(2026, 5, 20, tzinfo=_UTC).timestamp()


def test_parse_recap_range_invalid_raises() -> None:
    with pytest.raises(ValueError, match="Unknown recap period"):
        parse_recap_range("last decade", now=_NOW)


def test_add_modified_file_ignores_empty_and_duplicates() -> None:
    item = SessionRecapItem(title="t", session_id="s")
    item.add_modified_file("")
    item.add_modified_file("a.py")
    item.add_modified_file("a.py")
    item.add_modified_file("b.py")
    assert item.files_modified == ["a.py", "b.py"]


def test_duration_minutes_zero_when_timestamps_missing() -> None:
    assert SessionRecapItem(title="t", session_id="s").duration_minutes == 0
    item = SessionRecapItem(title="t", session_id="s")
    item.start_ts, item.end_ts = 100.0, 280.0
    assert item.duration_minutes == 3  # round(180 / 60)


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(0, "<1 min"), (1, "~1 min"), (59, "~59 min"), (60, "~1 hr"), (90, "~1 hr 30 min")],
)
def test_format_duration_boundaries(minutes: int, expected: str) -> None:
    assert _format_duration(minutes) == expected


def test_format_tool_counts_caps_at_four_with_more() -> None:
    counts = Counter({"ReadFile": 5, "WriteFile": 3, "Grep": 2, "Glob": 2, "Shell": 1, "Agent": 1})
    rendered = _format_tool_counts(counts)
    assert "Read ×5" in rendered
    assert "+2 more" in rendered
    assert _format_tool_counts(Counter()) == ""


def test_tool_label_known_and_passthrough() -> None:
    assert _tool_label("WriteFile") == "Write"
    assert _tool_label("CustomTool") == "CustomTool"


def test_first_sentence_boundaries() -> None:
    # Very short separators are ignored; the whole string is kept.
    assert _first_sentence("Too short. Then more text here") == "Too short. Then more text here"
    assert _first_sentence("Deep scan completed. Full report saved here") == "Deep scan completed."
    # No punctuation -> whole (collapsed) string.
    assert _first_sentence("a plain line with no terminator at all") == (
        "a plain line with no terminator at all"
    )
    # '? ' boundary past index 40 splits the first sentence.
    long_q = "I spent a while wondering what the right approach was? Then I moved on."
    assert _first_sentence(long_q) == "I spent a while wondering what the right approach was?"
    assert _first_sentence("   ") == ""


def test_last_substantive_thread_empty() -> None:
    assert _last_substantive_thread([]) == ""


def test_format_recap_empty_items() -> None:
    out = format_recap([], parse_recap_range("today", now=_NOW))
    assert "No Pythinker sessions found" in out


def test_format_recap_leads_bullet_with_outcome_not_first_message() -> None:
    item = SessionRecapItem(title="renderer work", session_id="s1")
    item.start_ts, item.end_ts = 100.0, 100.0 + 90 * 60  # 90 min -> not a light day
    item.turn_count = 6
    item.first_user_message = "the table rendering looks wrong"
    item.last_user_message = "thanks"
    item.assistant_snippets = [
        "Let me look at the renderer.",
        "Repaired the markdown table pipeline and added a contract test.",
    ]

    out = format_recap([item], parse_recap_range("today", now=_NOW))

    assert "Repaired the markdown table pipeline and added a contract test." in out
    assert "the table rendering looks wrong" not in out


def test_format_recap_light_day_is_reported_plainly() -> None:
    item = SessionRecapItem(title="quick planning", session_id="s1")
    item.start_ts, item.end_ts = 100.0, 100.0 + 11 * 60  # ~11 min
    item.turn_count = 2
    item.first_user_message = "let's sketch the content automation system"
    item.assistant_snippets = ["Outlined the pipeline stages and open questions."]

    out = format_recap([item], parse_recap_range("today", now=_NOW))

    assert "Light day" in out
    assert "1 session" in out or "one session" in out
    assert "2 turns" in out
    # Light days skip the heavy bulleted structure.
    assert "**What you worked on:**" not in out


def test_build_turn_recap_line_falls_back_to_request_and_handles_empty() -> None:
    assert build_turn_recap_line(request="fix the bug", assistant_text="") == (
        "※ recap: fix the bug (disable recaps in /settings)"
    )
    assert build_turn_recap_line(request="", assistant_text="") is None


def _record(timestamp: float, message: object) -> SimpleNamespace:
    return SimpleNamespace(timestamp=timestamp, to_wire_message=lambda: message)


@pytest.mark.asyncio
async def test_summarize_session_collects_turns_tools_and_files() -> None:
    from pythinker_core.message import ToolCall as CoreToolCall
    from pythinker_core.tooling import ToolReturnValue

    from pythinker_code.tools.display import DiffDisplayBlock
    from pythinker_code.wire.types import TextPart, ToolCall, ToolResult, TurnBegin

    rng = parse_recap_range("today", now=_NOW)
    in_range = rng.start_ts + 10.0
    records = [
        _record(rng.start_ts - 100.0, TurnBegin(user_input="out of range, skipped")),
        _record(in_range, TurnBegin(user_input="first ask")),
        _record(in_range + 1, TextPart(text="working on it")),
        _record(
            in_range + 2,
            ToolCall(id="1", function=CoreToolCall.FunctionBody(name="WriteFile", arguments="{}")),
        ),
        _record(
            in_range + 3,
            ToolResult(
                tool_call_id="1",
                return_value=ToolReturnValue(
                    is_error=False,
                    output="ok",
                    message="ok",
                    display=[
                        DiffDisplayBlock(
                            path="a.py", old_text="", new_text="x", old_start=1, new_start=1
                        )
                    ],
                ),
            ),
        ),
        _record(in_range + 4, TurnBegin(user_input="second ask")),
    ]

    async def _iter_records():
        for record in records:
            yield record

    session = SimpleNamespace(
        title="My session",
        id="sess-1",
        wire_file=SimpleNamespace(iter_records=_iter_records),
    )

    item = await summarize_session_for_recap(cast("Session", session), rng)
    assert item is not None
    assert item.turn_count == 2  # out-of-range TurnBegin skipped
    assert item.first_user_message == "first ask"
    assert item.last_user_message == "second ask"
    assert item.assistant_snippets == ["working on it"]
    assert item.tool_counts["WriteFile"] == 1
    assert item.files_modified == ["a.py"]


@pytest.mark.asyncio
async def test_summarize_session_returns_none_without_turns() -> None:
    rng = parse_recap_range("today", now=_NOW)

    async def _iter_records():
        from pythinker_code.wire.types import TextPart

        yield _record(rng.start_ts + 5.0, TextPart(text="no turn began"))

    session = SimpleNamespace(
        title="t", id="s", wire_file=SimpleNamespace(iter_records=_iter_records)
    )
    assert await summarize_session_for_recap(cast("Session", session), rng) is None
