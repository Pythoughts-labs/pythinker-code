"""Blind-first advisor for auto-mode AskUserQuestion deliberation (Entry A).

A single tool-less LLM call that ranks the model's own enumerated options
WITHOUT seeing which one the model favors. Modeled on ``soul/btw.py``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

import pythinker_core
from pythinker_core.message import Message, TextPart
from pythinker_core.tooling.empty import EmptyToolset

from pythinker_code.utils.logging import logger

if TYPE_CHECKING:
    from pythinker_core.chat_provider import StreamedMessagePart

    from pythinker_code.soul.pythinkersoul import PythinkerSoul
    from pythinker_code.wire.types import QuestionItem

_RECOMMENDED_RE = re.compile(r"\s*\(\s*recommended\s*\)\s*$", re.IGNORECASE)

_ADVISOR_SYSTEM_PROMPT = (
    "You are an independent decision advisor for an autonomous coding agent that has "
    "no human available. You are shown a decision and its candidate options, but NOT "
    "which option the agent prefers. Rank the options from best to worst for the stated "
    "task, each with a one-line rationale grounded in the trade-offs. Be decisive and "
    "concise. You are advising, not deciding — the agent makes the final call."
)


def _strip_recommended(label: str) -> str:
    return _RECOMMENDED_RE.sub("", label).strip()


def _format_questions_for_advisor(questions: Sequence[QuestionItem]) -> str:
    blocks: list[str] = []
    for qi, q in enumerate(questions, 1):
        lines = [f"Decision {qi}: {q.question}"]
        for oi, opt in enumerate(q.options, 1):
            label = _strip_recommended(opt.label)
            desc = f" — {opt.description}" if opt.description else ""
            lines.append(f"  {oi}. {label}{desc}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


async def blind_advisor_verdict(
    soul: PythinkerSoul,
    questions: Sequence[QuestionItem],
) -> str | None:
    """Return the advisor's ranked verdict, or ``None`` if unavailable.

    Never raises: any failure (no LLM, provider error) returns ``None`` so the
    caller falls back to a plain self-decision prompt rather than blocking.
    """
    runtime = soul._runtime  # pyright: ignore[reportPrivateUsage]
    if runtime.llm is None:
        return None
    try:
        chat_provider = runtime.llm.chat_provider
        prompt = (
            "Independently rank the options for the following decision(s). "
            "You do not know which option is favored.\n\n"
            f"{_format_questions_for_advisor(questions)}"
        )
        history = [Message(role="user", content=prompt)]
        chunks: list[str] = []

        def _on_part(part: StreamedMessagePart) -> None:
            if isinstance(part, TextPart) and part.text:
                chunks.append(part.text)

        await pythinker_core.step(
            chat_provider,
            _ADVISOR_SYSTEM_PROMPT,
            EmptyToolset(),
            history,
            on_message_part=_on_part,
        )
        verdict = "".join(chunks).strip()
        return verdict or None
    except Exception as exc:  # noqa: BLE001 — advisor is best-effort, never blocks
        from pythinker_code.telemetry.errors import report_handled_error

        report_handled_error(exc, site="soul.deliberation.advisor")
        logger.warning("Blind advisor failed: {error}", error=exc)
        return None
