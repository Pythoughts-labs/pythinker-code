from __future__ import annotations

import os
import pydoc
import re
import shutil
import sys
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from io import StringIO
from typing import Any

from rich.console import Console, PagerContext, RenderableType
from rich.pager import Pager
from rich.theme import Theme

NEUTRAL_MARKDOWN_THEME = Theme(
    {
        "markdown.paragraph": "none",
        "markdown.block_quote": "none",
        "markdown.hr": "none",
        "markdown.list": "none",
        "markdown.item": "none",
        "markdown.item.bullet": "none",
        "markdown.item.number": "none",
        "markdown.link": "none",
        "markdown.link_url": "none",
        "markdown.h1": "none",
        "markdown.h1.border": "none",
        "markdown.h2": "none",
        "markdown.h3": "none",
        "markdown.h4": "none",
        "markdown.h5": "none",
        "markdown.h6": "none",
        "markdown.h7": "none",
        "markdown.em": "none",
        "markdown.emph": "none",
        "markdown.strong": "none",
        "markdown.s": "none",
        "markdown.code": "none",
        "markdown.code_block": "none",
        "status.spinner": "none",
    },
    inherit=True,
)

_NEUTRAL_MARKDOWN_THEME = NEUTRAL_MARKDOWN_THEME


class _BuiltinPager:
    """In-process ANSI pager built on prompt_toolkit.

    Used where no capable external pager exists (Windows without ``PAGER``:
    pydoc falls back to ``more.com``, which prints raw escape sequences and
    has no status line). Renders the already-styled rich output in a
    full-screen scrollable view with an ASCII-only footer, and erases itself
    on exit like the other interactive views.
    """

    def __init__(self, content: str) -> None:
        self._lines = content.splitlines()
        self._offset = 0

    def _page_height(self, rows: int) -> int:
        return max(1, rows - 1)  # one row reserved for the footer

    def _scroll(self, delta: int, rows: int) -> None:
        max_offset = max(0, len(self._lines) - self._page_height(rows))
        self._offset = min(max_offset, max(0, self._offset + delta))

    def _body(self):
        from prompt_toolkit.application import get_app
        from prompt_toolkit.formatted_text import ANSI

        height = self._page_height(get_app().output.get_size().rows)
        return ANSI("\n".join(self._lines[self._offset : self._offset + height]))

    def _footer(self) -> str:
        from prompt_toolkit.application import get_app

        total = max(1, len(self._lines))
        height = self._page_height(get_app().output.get_size().rows)
        last = min(len(self._lines), self._offset + height)
        pct = last * 100 // total
        return f" line {self._offset + 1}/{total} {pct}% (arrows scroll, space/b page, q quit) "

    def run(self) -> None:
        from prompt_toolkit.application import Application
        from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
        from prompt_toolkit.layout import HSplit, Layout, Window
        from prompt_toolkit.layout.controls import FormattedTextControl

        kb = KeyBindings()

        @kb.add("q")
        @kb.add("escape")
        @kb.add("c-c")
        def _quit(event: KeyPressEvent) -> None:
            event.app.exit()

        def _move(event: KeyPressEvent, delta_lines: int, *, pages: bool = False) -> None:
            rows = event.app.output.get_size().rows
            delta = delta_lines * self._page_height(rows) if pages else delta_lines
            self._scroll(delta, rows)
            event.app.invalidate()

        @kb.add("up")
        @kb.add("k")
        def _up(event: KeyPressEvent) -> None:
            _move(event, -1)

        @kb.add("down")
        @kb.add("j")
        @kb.add("enter")
        def _down(event: KeyPressEvent) -> None:
            _move(event, 1)

        @kb.add("pageup")
        @kb.add("b")
        def _page_up(event: KeyPressEvent) -> None:
            _move(event, -1, pages=True)

        @kb.add("pagedown")
        @kb.add("space")
        @kb.add("f")
        def _page_down(event: KeyPressEvent) -> None:
            _move(event, 1, pages=True)

        @kb.add("home")
        @kb.add("g")
        def _home(event: KeyPressEvent) -> None:
            self._offset = 0
            event.app.invalidate()

        @kb.add("end")
        @kb.add("G")
        def _end(event: KeyPressEvent) -> None:
            rows = event.app.output.get_size().rows
            self._offset = max(0, len(self._lines) - self._page_height(rows))
            event.app.invalidate()

        _ = (_quit, _up, _down, _page_up, _page_down, _home, _end)

        app: Application[None] = Application(
            layout=Layout(
                HSplit(
                    [
                        Window(FormattedTextControl(self._body, focusable=False)),
                        Window(
                            FormattedTextControl(self._footer),
                            height=1,
                            style="reverse",
                        ),
                    ]
                )
            ),
            key_bindings=kb,
            full_screen=True,
            erase_when_done=True,
            mouse_support=False,
        )
        # in_thread keeps this sync call safe when an asyncio loop is running
        # (slash commands execute inside the shell's event loop).
        app.run(in_thread=True)


class _PythinkerPager(Pager):
    """Pager that ignores MANPAGER to avoid garbled output.

    ``pydoc.getpager()`` reads ``MANPAGER`` before ``PAGER``.  When the user
    sets ``MANPAGER`` to a man-specific pipeline (e.g.
    ``sh -c 'col -bx | bat -l man -p'``), that pipeline mangles the ANSI
    rich-text we emit.  This pager strips ``MANPAGER`` from the subprocess
    environment so only ``PAGER`` (or the default ``less``) is used.

    On Windows with no ``PAGER`` configured, pydoc's fallback is ``more.com``,
    which mangles ANSI styles and offers no quit/status line — so we page
    in-process with :class:`_BuiltinPager` instead.
    """

    def _use_builtin(self) -> bool:
        return (
            sys.platform == "win32"
            and not os.environ.get("PAGER")
            and sys.stdout is not None
            and sys.stdout.isatty()
        )

    def show(self, content: str) -> None:
        if self._use_builtin():
            # Short content fits on screen: print it straight through.
            if len(content.splitlines()) < shutil.get_terminal_size().lines:
                sys.stdout.write(content)
                sys.stdout.write("\n")
                return
            _BuiltinPager(content).run()
            return
        saved = os.environ.pop("MANPAGER", None)
        try:
            pydoc.pager(content)
        finally:
            if saved is not None:
                os.environ["MANPAGER"] = saved


# Per-async-context print redirect. ``asyncio.create_task`` snapshots the
# context, so setting this inside a slash-command task captures that task's
# prints across awaits without touching concurrent printers.
_print_redirect: ContextVar[Console | None] = ContextVar(
    "pythinker_console_print_redirect", default=None
)


class _PythinkerConsole(Console):
    """Console subclass that defaults to :class:`_PythinkerPager`."""

    def print(self, *args: Any, **kwargs: Any) -> None:
        target = _print_redirect.get()
        if target is not None:
            target.print(*args, **kwargs)
            return
        super().print(*args, **kwargs)

    def pager(
        self,
        pager: Pager | None = None,
        styles: bool = False,
        links: bool = False,
    ) -> PagerContext:
        if pager is None:
            pager = _PythinkerPager()
        return super().pager(pager=pager, styles=styles, links=links)


console = _PythinkerConsole(highlight=False, theme=NEUTRAL_MARKDOWN_THEME)


def clear_terminal_screen() -> None:
    """Fully clear the terminal: visible screen, cursor home, and scrollback.

    ``console.clear()`` handles the visible screen (ED2 + home) through
    rich's platform-aware output. The extra ``ESC[3J`` wipes scrollback —
    honored by Terminal.app, iTerm2, Windows Terminal, and modern conhost;
    terminals that don't support it simply ignore the sequence.
    """
    if not console.is_terminal:
        return
    console.clear()
    console.file.write("\x1b[3J")
    console.file.flush()


@contextmanager
def redirect_console_prints(*, columns: int) -> Generator[StringIO]:
    """Capture ``console.print`` output from the current async context as ANSI.

    Yields the buffer the redirected prints render into. Only printers in the
    same context (e.g. one slash-command task) are captured; everything else
    keeps writing to the terminal.
    """
    buf = StringIO()
    target = Console(
        file=buf,
        force_terminal=True,
        width=max(20, columns),
        theme=NEUTRAL_MARKDOWN_THEME,
        highlight=False,
    )
    token = _print_redirect.set(target)
    try:
        yield buf
    finally:
        _print_redirect.reset(token)


def current_console_width(active_console: Console | None = None, *, default: int = 78) -> int:
    """Return the current terminal width without relying on cached ``Console.width``.

    Rich's ``Console.width`` can be stale across live refreshes after terminal
    resizes. ``Console.size.width`` re-queries the console options and keeps
    activity/status lines width-adaptive.
    """
    target = active_console or console
    try:
        return max(1, target.size.width)
    except Exception:
        return default


# Matches OSC 8 hyperlink open/close markers emitted by Rich's Style(link=...).
# Format: ESC ] 8 ; <params> ; <uri> ST   where ST is ESC \ or BEL (\x07).
# prompt_toolkit's ANSI parser does not understand OSC 8 and renders the raw
# escape bytes as visible garbage (e.g. "8;id=391551;https://…").  We wrap each
# marker in \001…\002 so prompt_toolkit treats it as a ZeroWidthEscape and
# passes it through to the terminal via write_raw, preserving clickable links.
_OSC8_RE = re.compile(r"\x1b\]8;[^\x07\x1b]*(?:\x1b\\|\x07)")


def _wrap_osc8_as_zero_width(m: re.Match[str]) -> str:
    """Wrap an OSC 8 marker in \\001…\\002 for prompt_toolkit ZeroWidthEscape."""
    return f"\x01{m.group(0)}\x02"


def render_to_ansi(renderable: RenderableType, *, columns: int) -> str:
    """Render a Rich renderable to an ANSI string for prompt_toolkit integration."""
    from io import StringIO

    width = max(20, columns)
    buf = StringIO()
    temp = Console(
        file=buf,
        force_terminal=True,
        width=width,
        theme=NEUTRAL_MARKDOWN_THEME,
        highlight=False,
    )
    temp.print(renderable, end="")
    result = buf.getvalue()
    return _OSC8_RE.sub(_wrap_osc8_as_zero_width, result)
