from __future__ import annotations

from pythinker_core.message import Message
from rich.console import RenderableType
from rich.text import Text

from pythinker_code.ui.shell.prompt import PROMPT_SYMBOL_AGENT_INPUT
from pythinker_code.utils.message import message_stringify


def render_user_echo(message: Message) -> RenderableType:
    """Render a user message as transcript output.

    User input stays transcript-shaped in both styles: the submitted buffer
    is echoed back with the same prompt marker shown in the live input row.
    """
    text = message_stringify(message)
    return Text(f"{PROMPT_SYMBOL_AGENT_INPUT} {text}")


def render_user_echo_text(text: str) -> RenderableType:
    """Render the local prompt text exactly as the user saw it in the buffer."""
    return Text(f"{PROMPT_SYMBOL_AGENT_INPUT} {text}")
