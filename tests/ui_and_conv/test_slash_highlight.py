"""Tests for inline slash-command highlighting in the input area."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import StyleAndTextTuples

from pythinker_code.ui.shell.prompt import (
    SlashCommandHighlightLexer,
    _command_name_set,
)
from pythinker_code.utils.slashcmd import SlashCommand


def _noop(app: object, args: str) -> None:
    pass


def _make_command(
    name: str, *, aliases: Iterable[str] = ()
) -> SlashCommand[Callable[[object, str], None]]:
    return SlashCommand(
        name=name,
        description=f"{name} command",
        func=_noop,
        aliases=list(aliases),
    )


_KNOWN = _command_name_set(
    [
        _make_command("clear"),
        _make_command("statusline", aliases=["sl"]),
        _make_command("skill:best-practices"),
    ]
)


def _lex_line(text: str, lineno: int = 0) -> StyleAndTextTuples:
    lexer = SlashCommandHighlightLexer(lambda: _KNOWN)
    return list(lexer.lex_document(Document(text))(lineno))


def _highlighted(fragments: StyleAndTextTuples) -> list[str]:
    return [frag[1] for frag in fragments if frag[0] == "class:slash-command"]


def test_known_command_highlighted_mid_text():
    fragments = _lex_line("we need commands like /clear here")
    assert _highlighted(fragments) == ["/clear"]
    assert "".join(frag[1] for frag in fragments) == "we need commands like /clear here"


def test_known_command_highlighted_at_start():
    assert _highlighted(_lex_line("/clear")) == ["/clear"]


def test_unknown_command_not_highlighted():
    assert _highlighted(_lex_line("run deep review /best now")) == []


def test_partial_name_not_highlighted():
    assert _highlighted(_lex_line("/clea")) == []


def test_alias_and_namespaced_command_highlighted():
    fragments = _lex_line("/sl then /skill:best-practices")
    assert _highlighted(fragments) == ["/sl", "/skill:best-practices"]


def test_case_insensitive_match():
    assert _highlighted(_lex_line("try /CLEAR now")) == ["/CLEAR"]


def test_path_like_token_not_highlighted():
    assert _highlighted(_lex_line("see src/clear and /clear/subdir")) == []


def test_multiline_highlights_each_line():
    text = "first /clear line\nsecond /statusline line"
    assert _highlighted(_lex_line(text, lineno=0)) == ["/clear"]
    assert _highlighted(_lex_line(text, lineno=1)) == ["/statusline"]


def test_out_of_range_line_returns_empty():
    assert _lex_line("/clear", lineno=5) == []


def test_trailing_punctuation_keeps_highlight():
    assert _highlighted(_lex_line("use /clear, then continue")) == ["/clear"]
