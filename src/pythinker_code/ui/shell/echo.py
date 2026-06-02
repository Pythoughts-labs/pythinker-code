from __future__ import annotations

from pythinker_core.message import Message
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.measure import Measurement
from rich.text import Text

from pythinker_code.ui.shell.components.markdown import PythinkerMarkdown
from pythinker_code.ui.shell.prompt import PROMPT_SYMBOL_AGENT_INPUT
from pythinker_code.ui.shell.spacing import BLANK_ROW
from pythinker_code.utils.message import message_stringify
from pythinker_code.utils.rich.columns import BulletColumns


class UserEcho:
    """Transcript-shaped user input with aligned wrapped continuation rows."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.plain = f"{PROMPT_SYMBOL_AGENT_INPUT} {text}"
        self._body = BulletColumns(
            PythinkerMarkdown(text), bullet=Text(PROMPT_SYMBOL_AGENT_INPUT), padding=1
        )

    def __rich_measure__(self, console: Console, options: ConsoleOptions) -> Measurement:
        return Measurement.get(console, options, self._body)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield from console.render(Group(BLANK_ROW, self._body), options)


def render_user_echo(message: Message) -> RenderableType:
    """Render a user message as transcript output.

    User input stays transcript-shaped in both styles: the submitted buffer
    is echoed back with the same prompt marker shown in the live input row.
    """
    text = message_stringify(message)
    return UserEcho(text)


def render_user_echo_text(text: str) -> RenderableType:
    """Render submitted local prompt text in the transcript."""
    return UserEcho(text)
