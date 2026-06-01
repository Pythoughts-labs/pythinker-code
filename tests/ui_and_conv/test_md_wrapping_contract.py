"""Markdown wrapping contracts for clean TUI margins."""

from __future__ import annotations

from pythinker_code.ui.shell.components.markdown import PythinkerMarkdown
from tests.ui_and_conv._md_contract_helpers import render_plain


def _lines(rendered: str) -> list[str]:
    return [line.rstrip() for line in rendered.splitlines()]


def test_markdown_paragraph_wraps_on_word_boundaries() -> None:
    rendered = render_plain(
        PythinkerMarkdown(
            "The user requested a deep code scan for vulnerabilities in direct "
            "dependencies. Preparing the deep code scan."
        ),
        width=24,
    )

    assert _lines(rendered) == [
        "The user requested a",
        "deep code scan for",
        "vulnerabilities in",
        "direct dependencies.",
        "Preparing the deep code",
        "scan.",
    ]


def test_ordered_list_wrap_uses_hanging_indent_without_dropping_text() -> None:
    rendered = render_plain(
        PythinkerMarkdown("1. alpha beta gamma delta epsilon"),
        width=24,
    )

    assert _lines(rendered) == [
        "1. alpha beta gamma",
        "   delta epsilon",
    ]


def test_nested_list_wrap_keeps_continuation_under_item_text() -> None:
    rendered = render_plain(
        PythinkerMarkdown("- parent\n  - alpha beta gamma delta epsilon"),
        width=24,
    )

    assert _lines(rendered) == [
        "• parent",
        "  • alpha beta gamma",
        "    delta epsilon",
    ]
