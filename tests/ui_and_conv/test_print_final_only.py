"""Tests for final-message-only print mode output."""

from __future__ import annotations

import importlib
import json
import sys

from rich.console import Console

from pythinker_code.ui.print.visualize import FinalOnlyJsonPrinter, FinalOnlyTextPrinter
from pythinker_code.wire.types import StepBegin, TextPart, ThinkPart

print_visualize = importlib.import_module("pythinker_code.ui.print.visualize")


def test_final_only_text_printer_outputs_final_text(capsys):
    printer = FinalOnlyTextPrinter()
    printer.feed(StepBegin(n=1))
    printer.feed(TextPart(text="first"))
    printer.feed(StepBegin(n=2))
    printer.feed(TextPart(text="final"))
    printer.feed(TextPart(text=" msg"))
    printer.flush()

    assert capsys.readouterr().out.strip() == "final msg"


def test_final_only_text_printer_plain_prose_is_byte_identical(capsys):
    """Non-report output must be unchanged — same verbatim text, no framing."""
    printer = FinalOnlyTextPrinter()
    printer.feed(TextPart(text="just a plain answer"))
    printer.flush()
    assert capsys.readouterr().out == "just a plain answer\n"


def test_final_only_text_printer_terminal_wraps_plain_prose(capsys, monkeypatch):
    """Interactive final-text output should wrap before the terminal hard-clips it."""

    def narrow_console() -> Console:
        return Console(width=40, file=sys.stdout, color_system=None, legacy_windows=False)

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(print_visualize, "Console", narrow_console)

    print_visualize._print_final_text(
        "This is **bold** terminal prose that should wrap on word boundaries instead of "
        "overflowing beyond the shell viewport."
    )

    out = capsys.readouterr().out
    lines = [line.rstrip() for line in out.splitlines()]
    assert all(len(line) <= 40 for line in lines)
    assert "**" not in out
    assert lines == [
        "This is bold terminal prose that should",
        "wrap on word boundaries instead of",
        "overflowing beyond the shell viewport.",
    ]


def test_final_only_text_printer_renders_report_block(capsys):
    """A ` ```report ` block in the final text renders as a clean report, not raw JSON."""
    printer = FinalOnlyTextPrinter()
    printer.feed(
        TextPart(
            text=(
                "Summary line.\n\n"
                "```report\n"
                '{"title": "Audit Results", '
                '"findings": [{"title": "SQL injection", "severity": "high", '
                '"location": "db.py:42"}]}\n'
                "```\n"
            )
        )
    )
    printer.flush()

    out = capsys.readouterr().out
    assert "Summary line." in out
    assert "Audit Results" in out
    assert "1 high" in out
    assert "SQL injection" in out
    assert "db.py:42" in out
    assert '"severity"' not in out  # rendered, not raw JSON


def test_final_only_json_printer_outputs_final_message(capsys):
    printer = FinalOnlyJsonPrinter()
    printer.feed(StepBegin(n=1))
    printer.feed(TextPart(text="first"))
    printer.feed(StepBegin(n=2))
    printer.feed(ThinkPart(think="secret"))
    printer.feed(TextPart(text="final"))
    printer.flush()

    output = capsys.readouterr().out.strip()
    message = json.loads(output)
    assert message["role"] == "assistant"
    assert message["content"] == "final"
