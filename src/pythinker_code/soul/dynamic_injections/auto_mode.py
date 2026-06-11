from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pythinker_core.message import Message

from pythinker_code.soul.dynamic_injection import DynamicInjection, DynamicInjectionProvider

if TYPE_CHECKING:
    from pythinker_code.soul.pythinkersoul import PythinkerSoul

_AUTO_INJECTION_TYPE = "auto_mode"

_AUTO_PROMPT_DESTRUCTIVE_DELIBERATE = (
    "You are running in auto mode. No user is present to answer questions or "
    "approve actions.\n"
    "- Do NOT call AskUserQuestion — it will be auto-dismissed with no answer, "
    "wasting a turn. Make your best judgment and proceed.\n"
    "- Tool calls are auto-approved only when the current trust/safe-mode policy "
    "allows. If approval is unavailable, the tool fails closed instead of "
    "waiting forever; choose a safe alternative or explain the required explicit "
    "trust/yolo step.\n"
    "- Irreversible auto-approved actions may be bounced once for deliberation. "
    "Weigh alternatives, then retry only if the exact action is still right.\n"
    "- Outside-workspace file writes are not auto-approved by auto mode.\n"
    "- Proactively run tests and lint to verify your work before finishing — "
    "no user is present to confirm validation steps.\n"
    "- Finish the user's request end-to-end in this run. Do not defer decisions "
    "to a human."
)

_AUTO_PROMPT_DELIBERATE = (
    "You are running in auto mode. No user is present to answer questions or "
    "approve actions.\n"
    "- Tool calls are auto-approved only when the current trust/safe-mode policy "
    "allows. If approval is unavailable, the tool fails closed instead of "
    "waiting forever; choose a safe alternative or explain the required explicit "
    "trust/yolo step.\n"
    "- Irreversible auto-approved actions may be bounced once for deliberation. "
    "Weigh alternatives, then retry only if the exact action is still right.\n"
    "- At a genuine, consequential, hard-to-reverse fork, you MAY call "
    "AskUserQuestion: it triggers an advisor-assisted self-decision (you still "
    "decide). Do NOT ask routine confirmations or progress check-ins — proceed "
    "instantly on trivial, reversible choices.\n"
    "- Outside-workspace file writes are not auto-approved by auto mode.\n"
    "- Proactively run tests and lint to verify your work before finishing — "
    "no user is present to confirm validation steps.\n"
    "- Finish the user's request end-to-end in this run. Do not defer decisions "
    "to a human."
)

AUTO_DISABLED_REMINDER = (
    "Auto mode is now disabled. The user is back at the terminal and CAN answer "
    "AskUserQuestion.\n"
    "- Ignore any earlier auto mode reminders that said no user is present or "
    "that you must not call AskUserQuestion.\n"
    "- AskUserQuestion is available again when a decision genuinely changes "
    "your next action. Do not ask routine confirmations or progress check-ins.\n"
    "- Tool calls are no longer auto-approved by auto mode. They may still be "
    "auto-approved if yolo mode remains active.\n"
    "- Hold off on slow test/lint commands until the user is ready to finalize: "
    "suggest what you want to run next and let the user confirm first. For "
    "test-related tasks (adding tests, fixing tests, reproducing a bug), you "
    "may still run tests proactively."
)


class AutoModeInjectionProvider(DynamicInjectionProvider):
    """Injects auto-mode (no user present) guidance for the model."""

    def __init__(self) -> None:
        self._injected: bool = False

    async def get_injections(
        self,
        history: Sequence[Message],
        soul: PythinkerSoul,
    ) -> list[DynamicInjection]:
        _ = history
        if not soul.is_auto:
            return []

        if self._injected:
            return []
        self._injected = True
        # No user is present, so a destructive auto-approved action is always bounced once
        # for deliberation (see Approval.deliberation_gate) — surface that guidance in
        # every auto prompt. Under the auto_deliberate policy AskUserQuestion additionally
        # self-decides (advisor-assisted) at consequential forks instead of being
        # dismissed, so invite it there.
        if soul.runtime.config.ask_user_question_policy == "auto_deliberate":
            content = _AUTO_PROMPT_DELIBERATE
        else:
            content = _AUTO_PROMPT_DESTRUCTIVE_DELIBERATE
        return [DynamicInjection(type=_AUTO_INJECTION_TYPE, content=content)]

    async def on_context_compacted(self) -> None:
        # Compaction rewrites history; the prior auto-mode reminder may have
        # been summarized away, so let the next auto step restate the
        # constraint.
        self._injected = False

    async def on_auto_changed(self, enabled: bool) -> None:
        # A runtime toggle changes the latest truth about user presence.
        # Re-arm so the next LLM step can inject the current auto guidance.
        _ = enabled
        self._injected = False
