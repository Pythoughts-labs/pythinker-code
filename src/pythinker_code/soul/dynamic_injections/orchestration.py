from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pythinker_core.message import Message, TextPart

from pythinker_code.notifications import is_notification_message
from pythinker_code.soul.dynamic_injection import DynamicInjection, DynamicInjectionProvider
from pythinker_code.soul.message import is_system_reminder_message

if TYPE_CHECKING:
    from pythinker_code.soul.pythinkersoul import PythinkerSoul

_TURN_INTERVAL = 5
_INJECTION_TYPE = "orchestration"
_REMINDER_MARKER = "Orchestration reminder:"
_SUBSTANTIAL_TERMS = (
    "implement",
    "enhance",
    "refactor",
    "fix",
    "debug",
    "review",
    "audit",
    "orchestration",
    "system prompt",
    "runtime",
    "multiple",
    "test",
    "tests",
    "plan",
)
# Word-boundary matching: bare substring checks misfire on words like
# "prefix" (fix), "explanation" (plan), or "protest" (test).
_SUBSTANTIAL_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in _SUBSTANTIAL_TERMS) + r")\b",
    re.IGNORECASE,
)
_PATHISH_RE = re.compile(r"(?:^|\s)(?:[\w.-]+/)+[\w.-]+")


class OrchestrationInjectionProvider(DynamicInjectionProvider):
    """Inject sparse orchestration guidance for substantial root tasks.

    Stateless by design: throttling is derived from history (the literal
    reminder marker), so it survives restarts and re-arms naturally when
    compaction collapses a prior reminder into the summary.
    """

    async def get_injections(
        self,
        history: Sequence[Message],
        soul: PythinkerSoul,
    ) -> list[DynamicInjection]:
        if _stronger_mode_active(soul):
            return []

        task_text = _latest_real_user_text(history)
        if not task_text or not _looks_substantial(task_text):
            return []

        if not _should_inject(history):
            return []

        return [DynamicInjection(type=_INJECTION_TYPE, content=_reminder())]


def _stronger_mode_active(soul: PythinkerSoul) -> bool:
    """Defer to modes that carry their own work-shaping guidance.

    Plan mode, auto mode, /goal continuations, and subagent overlays each
    inject stronger task framing already; stacking this reminder on top
    would dilute them.
    """
    if soul.is_subagent or soul.plan_mode or soul.is_auto:
        return True
    goal = soul.runtime.session.state.goal
    return goal is not None and goal.status == "active"


def _latest_real_user_text(history: Sequence[Message]) -> str | None:
    for message in reversed(history):
        if message.role != "user":
            continue
        if is_notification_message(message) or is_system_reminder_message(message):
            continue
        text = message.extract_text(" ").strip()
        if text:
            return text
    return None


def _looks_substantial(text: str) -> bool:
    if _SUBSTANTIAL_RE.search(text):
        return True
    return len(_PATHISH_RE.findall(text)) >= 2


def _should_inject(history: Sequence[Message]) -> bool:
    turns_since_last = 0
    for message in reversed(history):
        if message.role == "user" and _is_orchestration_reminder(message):
            return turns_since_last >= _TURN_INTERVAL
        if message.role == "assistant":
            turns_since_last += 1
    return True


def _is_orchestration_reminder(message: Message) -> bool:
    if message.role != "user":
        return False
    for part in message.content:
        if isinstance(part, TextPart) and _REMINDER_MARKER in part.text:
            return True
    return False


def _reminder() -> str:
    return (
        "Orchestration reminder: choose the lightest effective work shape. "
        "Use direct tools for known-path or one-file work. Use SetTodoList after "
        "the approach is clear for substantial multi-step work. Use foreground "
        "RunAgents when independent investigation, review, or verification can run "
        "in parallel and your next step is synthesis; use background agents only "
        "when you can make other progress while they run. Keep progress updates "
        "short and verify with concrete commands before claiming completion."
    )
