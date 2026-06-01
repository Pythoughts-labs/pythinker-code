from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Literal

from pythinker_core.utils.typing import JsonType

from pythinker_code.approval_runtime import (
    ApprovalCancelledError,
    ApprovalRuntime,
    ApprovalSource,
    get_current_approval_source_or_none,
)
from pythinker_code.soul.toolset import (
    emit_current_tool_execution_started,
    get_current_tool_call_or_none,
)
from pythinker_code.tools.utils import ToolRejectedError
from pythinker_code.utils.logging import logger
from pythinker_code.wire.types import DisplayBlock, ToolCall

type Response = Literal["approve", "approve_for_session", "reject"]

_DELIBERATION_FEEDBACK = (
    "No user is present and this action is irreversible ({reason}). Before re-issuing: "
    "enumerate the realistic alternatives, weigh them against the current task, and commit "
    "to the best one. If this exact action is still right, re-issue it and it will run."
)


class ApprovalResult:
    """Result of an approval request. Behaves as bool for backward compatibility."""

    __slots__ = ("approved", "feedback", "deliberation")

    def __init__(self, approved: bool, feedback: str = "", deliberation: bool = False):
        self.approved = approved
        self.feedback = feedback
        self.deliberation = deliberation
        """True when the bounce is an auto-mode deliberation prompt, not a user rejection."""

    def __bool__(self) -> bool:
        return self.approved

    def rejection_error(self) -> ToolRejectedError:
        if self.deliberation and self.feedback:
            # Auto-mode deliberation: no user is present, so do not frame it as a
            # user rejection — the feedback itself is the instruction to deliberate.
            return ToolRejectedError(
                message=self.feedback,
                brief="Deliberate before retrying",
                has_feedback=True,
            )
        if self.feedback:
            return ToolRejectedError(
                message=(f"The tool call is rejected by the user. User feedback: {self.feedback}"),
                brief=f"Rejected: {self.feedback}",
                has_feedback=True,
            )
        source = get_current_approval_source_or_none()
        is_subagent = source is not None and source.agent_id is not None
        if is_subagent:
            return ToolRejectedError(
                message=(
                    "The tool call is rejected by the user. "
                    "Try a different approach to complete your task, or explain the "
                    "limitation in your summary if no alternative is available. "
                    "Do not retry the same tool call, and do not attempt to bypass "
                    "this restriction through indirect means."
                ),
            )
        return ToolRejectedError()


class ApprovalState:
    def __init__(
        self,
        yolo: bool = False,
        auto: bool = False,
        runtime_auto: bool = False,
        safe_mode: bool = False,
        auto_deliberate: bool = False,
        auto_approve_actions: set[str] | None = None,
        on_change: Callable[[], None] | None = None,
    ):
        self.yolo = yolo
        self.auto = auto
        """Persisted session flag. True when no user is present (auto mode).

        Implies auto-approve and is restored with the session.
        """
        self.runtime_auto = runtime_auto
        """Invocation-only auto flag, e.g. ``--auto`` or ``--print``. Not persisted."""
        self.safe_mode = safe_mode
        """When true, all auto-approval paths are suppressed."""
        self.auto_deliberate = auto_deliberate
        """When true, destructive auto-approved actions must deliberate once first.

        Set from ``ask_user_question_policy == "auto_deliberate"``. Gates *ahead*
        of yolo/auto: an irreversible action (``rm -rf``, ``git push --force``, ...)
        is bounced back once for the agent to weigh alternatives before it runs.
        """
        self.auto_approve_actions: set[str] = auto_approve_actions or set()
        """Set of action names that should automatically be approved."""
        self.approved_orchestration_fingerprints: set[str] = set()
        """RunAgents orchestration shapes approved for this in-memory session."""
        self.deliberated_fingerprints: set[str] = set()
        """Destructive (tool, command) shapes already bounced once; the re-issue runs."""
        self._on_change = on_change

    def notify_change(self) -> None:
        if self._on_change is not None:
            self._on_change()


class Approval:
    def __init__(
        self,
        yolo: bool = False,
        *,
        state: ApprovalState | None = None,
        runtime: ApprovalRuntime | None = None,
    ):
        self._state = state or ApprovalState(yolo=yolo)
        self._runtime = runtime or ApprovalRuntime()

    def share(self) -> Approval:
        """Create a new approval queue that shares approval state."""
        return Approval(state=self._state, runtime=self._runtime)

    def set_runtime(self, runtime: ApprovalRuntime) -> None:
        self._runtime = runtime

    @property
    def runtime(self) -> ApprovalRuntime:
        return self._runtime

    def set_yolo(self, yolo: bool) -> None:
        self._state.yolo = yolo
        self._state.notify_change()

    def set_auto(self, auto: bool) -> None:
        """Toggle persisted auto (unattended, no user present) mode.

        Turning it off also clears any invocation-only auto overlay so an
        interactive session started with ``--auto`` can return to interactive
        behavior via ``/auto``.
        """
        self._state.auto = auto
        if not auto:
            self._state.runtime_auto = False
        self._state.notify_change()

    def set_runtime_auto(self, auto: bool) -> None:
        """Toggle invocation-only auto mode without persisting it."""
        self._state.runtime_auto = auto

    def set_safe_mode(self, safe_mode: bool) -> None:
        self._state.safe_mode = safe_mode
        self._state.notify_change()

    def is_auto_approve(self) -> bool:
        """True when tool calls should be auto-approved.

        Yolo is a deliberate, explicit opt-in to auto-approve everything, so it
        overrides the workspace safe-mode guardrail. Auto mode (no user present)
        does not — it stays gated behind safe mode for untrusted workspaces.
        """
        if self._state.yolo:
            return True
        if self._state.safe_mode:
            return False
        return self.is_auto()

    def is_yolo(self) -> bool:
        """True only when the user explicitly opted into yolo."""
        return self._state.yolo

    def is_yolo_flag(self) -> bool:
        """True only when the user explicitly opted into yolo (not via auto)."""
        return self.is_yolo()

    def is_auto(self) -> bool:
        """True when no user is present (auto mode)."""
        return self._state.auto or self._state.runtime_auto

    def is_auto_flag(self) -> bool:
        """True only when persisted auto mode is active."""
        return self._state.auto

    def is_runtime_auto(self) -> bool:
        """True only when auto mode came from this invocation."""
        return self._state.runtime_auto

    def is_orchestration_approved(self, fingerprint: str) -> bool:
        return fingerprint in self._state.approved_orchestration_fingerprints

    def approve_orchestration(self, fingerprint: str) -> None:
        self._state.approved_orchestration_fingerprints.add(fingerprint)

    @staticmethod
    def _shell_command(tool_call: ToolCall) -> str | None:
        """Extract the Shell command string from a tool call, else ``None``."""
        if tool_call.function.name != "Shell":
            return None
        try:
            args: JsonType = json.loads(tool_call.function.arguments or "{}")
        except (ValueError, TypeError):
            return None
        if not isinstance(args, dict):
            return None
        command = args.get("command")
        return command if isinstance(command, str) else None

    def deliberation_gate(self, tool_call: ToolCall) -> str | None:
        """Reason a destructive auto-approved action must deliberate once, else ``None``.

        Fires only when ``auto_deliberate`` is on, the action would otherwise be
        auto-approved (auto *or* yolo — so it gates ahead of the yolo bypass), and the
        command is destructive (Unit 1's classifier). One-shot: the first occurrence is
        bounced for the agent to weigh alternatives; the identical re-issue is let through
        once, so a deliberated ``rm -rf`` runs without being permanently whitelisted.
        """
        if not self._state.auto_deliberate:
            return None
        if not self.is_auto_approve():
            return None
        command = self._shell_command(tool_call)
        if command is None:
            return None
        from pythinker_code.soul.permission import shell_destructive_reason

        reason = shell_destructive_reason(command)
        if reason is None:
            return None
        fingerprint = f"{tool_call.function.name}::{command}"
        if fingerprint in self._state.deliberated_fingerprints:
            self._state.deliberated_fingerprints.discard(fingerprint)  # consume one-shot
            return None
        self._state.deliberated_fingerprints.add(fingerprint)
        return reason

    async def request(
        self,
        sender: str,
        action: str,
        description: str,
        display: list[DisplayBlock] | None = None,
    ) -> ApprovalResult:
        """
        Request approval for the given action. Intended to be called by tools.

        Args:
            sender (str): The name of the sender.
            action (str): The action to request approval for.
                This is used to identify the action for auto-approval.
            description (str): The description of the action. This is used to display to the user.

        Returns:
            ApprovalResult: Result with ``approved`` flag and optional ``feedback``.
                Behaves as ``bool`` via ``__bool__``, so ``if not result:`` works.

        Raises:
            RuntimeError: If the approval is requested from outside a tool call.
        """
        tool_call = get_current_tool_call_or_none()
        if tool_call is None:
            raise RuntimeError("Approval must be requested from a tool call.")

        logger.debug(
            "{tool_name} ({tool_call_id}) requesting approval: {action} {description}",
            tool_name=tool_call.function.name,
            tool_call_id=tool_call.id,
            action=action,
            description=description,
        )
        # Gate ahead of the auto/yolo auto-approve: an irreversible action under
        # auto_deliberate is bounced once so the agent weighs alternatives first.
        if (reason := self.deliberation_gate(tool_call)) is not None:
            from pythinker_code.telemetry import track

            track(
                "tool_deliberation",
                tool_name=tool_call.function.name,
                approval_mode="auto" if self.is_auto() else "yolo",
            )
            return ApprovalResult(
                approved=False,
                feedback=_DELIBERATION_FEEDBACK.format(reason=reason),
                deliberation=True,
            )
        if self.is_auto_approve():
            from pythinker_code.telemetry import track

            track(
                "tool_approved",
                tool_name=tool_call.function.name,
                approval_mode="auto" if self.is_auto() else "yolo",
            )
            emit_current_tool_execution_started()
            return ApprovalResult(approved=True)

        if action in self._state.auto_approve_actions:
            from pythinker_code.telemetry import track

            track(
                "tool_approved",
                tool_name=tool_call.function.name,
                approval_mode="auto_session",
            )
            emit_current_tool_execution_started()
            return ApprovalResult(approved=True)

        request_id = str(uuid.uuid4())
        display_blocks = display or []
        source = get_current_approval_source_or_none() or ApprovalSource(
            kind="foreground_turn",
            id=tool_call.id,
        )
        self._runtime.create_request(
            request_id=request_id,
            tool_call_id=tool_call.id,
            sender=sender,
            action=action,
            description=description,
            display=display_blocks,
            source=source,
        )
        try:
            response, feedback = await self._runtime.wait_for_response(request_id)
        except ApprovalCancelledError:
            from pythinker_code.telemetry import track

            track(
                "tool_rejected",
                tool_name=tool_call.function.name,
                approval_mode="cancelled",
            )
            record = self._runtime.get_request(request_id)
            return ApprovalResult(approved=False, feedback=record.feedback if record else "")
        from pythinker_code.telemetry import track

        match response:
            case "approve":
                track(
                    "tool_approved",
                    tool_name=tool_call.function.name,
                    approval_mode="manual",
                )
                emit_current_tool_execution_started()
                return ApprovalResult(approved=True)
            case "approve_for_session":
                track(
                    "tool_approved",
                    tool_name=tool_call.function.name,
                    approval_mode="manual",
                )
                self._state.auto_approve_actions.add(action)
                self._state.notify_change()
                for pending in self._runtime.list_pending():
                    if pending.action == action:
                        self._runtime.resolve(pending.id, "approve")
                emit_current_tool_execution_started()
                return ApprovalResult(approved=True)
            case "reject":
                track(
                    "tool_rejected",
                    tool_name=tool_call.function.name,
                    approval_mode="manual",
                )
                return ApprovalResult(approved=False, feedback=feedback)
            case _:
                track(
                    "tool_rejected",
                    tool_name=tool_call.function.name,
                    approval_mode="manual",
                )
                return ApprovalResult(approved=False)
