from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pythinker_core.message import Message, TextPart

from pythinker_code.notifications import is_notification_message
from pythinker_code.soul.dynamic_injection import DynamicInjection, DynamicInjectionProvider

if TYPE_CHECKING:
    from pythinker_code.soul.pythinkersoul import PythinkerSoul

_INLINE_COMMANDS_TYPE = "inline_commands"

# A slash token preceded by whitespace (or start) and not followed by another
# path segment: `/best-practices` and `/skill:name` match; `tests/clear` and
# `/clear/cache` do not. Known-command filtering removes the remaining
# path-like false positives (`/tmp`, `/usr`).
_TOKEN_RE = re.compile(r"(?<!\S)/([A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*)(?!/)")

_SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)

_REMINDER_TEMPLATE = (
    "The user's message references slash commands inline: {refs}. Inline references do "
    "NOT execute — a slash command runs only as its own message starting with '/'. Do "
    "not silently ignore them; treat each reference as part of the request: for "
    "/skill:<name>, load that skill with ReadSkill and apply its instructions; for "
    "guidance-injecting commands (e.g. /best-practices), apply the closest equivalent "
    "guidance yourself and tell the user how to run the real command; otherwise tell "
    "the user the command did not run and how to invoke it."
)


class InlineCommandReminderProvider(DynamicInjectionProvider):
    """Flags inline ``/command`` references the shell could not execute.

    Slash commands only run when the user's message starts with ``/``; a
    command or ``/skill:<name>`` referenced mid-message reaches the model as
    plain text and has historically been silently dropped. This provider
    inspects the latest user message once and reminds the model to handle
    each reference deliberately. Root-only: subagent prompts come from the
    parent, not from a shell input that could have executed commands.
    """

    def __init__(self) -> None:
        self._processed: set[str] = set()

    async def get_injections(
        self,
        history: Sequence[Message],
        soul: PythinkerSoul,
    ) -> list[DynamicInjection]:
        if soul.is_subagent or not history:
            return []
        last = history[-1]
        if last.role != "user" or is_notification_message(last):
            return []
        raw = "\n".join(part.text for part in last.content if isinstance(part, TextPart))
        text = _SYSTEM_REMINDER_RE.sub("", raw).strip()
        if not text:
            return []
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in self._processed:
            return []
        self._processed.add(digest)

        # Slash dispatch strips the original text before checking the leading
        # "/", so judge "did the shell already run this?" on the raw message,
        # not on the reminder-stripped scan text.
        leading_command_ran = raw.strip().startswith("/")
        known = _known_command_names(soul)
        refs: list[str] = []
        for match in _TOKEN_RE.finditer(text):
            if match.start() == 0 and leading_command_ran:
                # The leading command was already handled (or rejected) by the
                # shell's normal slash parsing; only mid-message refs matter.
                continue
            name = match.group(1)
            folded = name.casefold()
            if folded in known or folded.startswith("skill:"):
                token = f"/{name}"
                if token not in refs:
                    refs.append(token)
        if not refs:
            return []
        return [
            DynamicInjection(
                type=_INLINE_COMMANDS_TYPE,
                content=_REMINDER_TEMPLATE.format(refs=", ".join(refs)),
            )
        ]

    async def on_context_compacted(self) -> None:
        # Compaction rebuilds history; message identities are stale.
        self._processed.clear()


def _known_command_names(soul: PythinkerSoul) -> set[str]:
    names: set[str] = set()
    for cmd in soul.available_slash_commands:
        names.add(cmd.name.casefold())
        names.update(alias.casefold() for alias in cmd.aliases)
    return names
