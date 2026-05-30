# tests/ui_and_conv/test_md_contract_helpers.py
"""Smoke test for the shared Markdown/report contract helpers."""

from __future__ import annotations

from rich.text import Text

from tests.ui_and_conv._md_contract_helpers import (
    THEMES,
    WIDTHS,
    render_ansi,
    render_plain,
    render_twice_identical,
)


def test_helpers_capture_and_compare():
    assert "hello" in render_plain(Text("hello"), width=40)
    # truecolor capture keeps SGR codes; a red fg emits the 31-family sequence.
    assert "\x1b[" in render_ansi(Text("hi", style="red"), width=40)
    assert render_twice_identical(lambda: Text("stable")) is True
    assert WIDTHS and THEMES  # parametrization sources are non-empty
