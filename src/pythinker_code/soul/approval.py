from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from pythinker_core.utils.typing import JsonType

from pythinker_code.approval_runtime import (
    ApprovalCancelledError,
    ApprovalRequestRecord,
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
_EDIT_OUTSIDE_ACTION = "edit file outside of working directory"
_SAFE_MODE_UNATTENDED_FEEDBACK = (
    "Approval is required for this action, but this run is in auto/non-interactive mode "
    "and safe mode prevents auto-approval. The action was denied instead of waiting "
    "indefinitely for a user who is not present. Trust the workspace first or rerun with "
    "explicit yolo/--yes after verifying the action is safe."
)
_OUTSIDE_WORKSPACE_UNATTENDED_FEEDBACK = (
    "Outside-workspace file changes require explicit approval. Auto mode does not "
    "auto-approve them, even in a trusted workspace, because they cross the workspace "
    "trust boundary. Rerun interactively, or use explicit yolo/--yes only after verifying "
    "the exact path and change are safe."
)


@dataclass(frozen=True)
class DeliberationScope:
    """Execution context + LLM generation a deliberation decision is scoped to.

    ``context_id`` separates the main agent from each subagent (approval state is shared
    via ``Approval.share()``); ``generation`` is the step number within that context.
    """

    context_id: str
    generation: int


_current_deliberation_scope: ContextVar[DeliberationScope | None] = ContextVar(
    "deliberation_scope", default=None
)


@contextmanager
def deliberation_scope(context_id: str, generation: int) -> Generator[None, None, None]:
    """Bind the active deliberation scope for the duration of one step's tool execution."""
    token = _current_deliberation_scope.set(DeliberationScope(context_id, generation))
    try:
        yield
    finally:
        _current_deliberation_scope.reset(token)


class ApprovalResult:
    """Result of an approval request. Behaves as bool for backward compatibility."""

    __slots__ = ("approved", "feedback", "deliberation", "user_rejection")

    def __init__(
        self,
        approved: bool,
        feedback: str = "",
        deliberation: bool = False,
        user_rejection: bool = True,
    ):
        self.approved = approved
        self.feedback = feedback
        self.deliberation = deliberation
        """True when the bounce is an auto-mode deliberation prompt, not a user rejection."""
        self.user_rejection = user_rejection
        """True when the denial came from a user-backed approval response."""

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
            if not self.user_rejection:
                return ToolRejectedError(
                    message=self.feedback,
                    brief="Approval unavailable",
                    has_feedback=True,
                )
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

        Wired in ``Runtime.create`` from the destructive deliberation config flag
        and the legacy ``ask_user_question_policy == "auto_deliberate"`` mode. Gates
        *ahead* of yolo/auto: an irreversible action (``rm -rf``, ``git push --force``,
        ...) is bounced back once for the agent to weigh alternatives before it runs.
        """
        self.auto_approve_actions: set[str] = auto_approve_actions or set()
        """Set of action names that should automatically be approved."""
        self.approved_orchestration_fingerprints: set[str] = set()
        """RunAgents orchestration shapes approved for this in-memory session."""
        self.deliberated_fingerprints: dict[str, int] = {}
        """Maps a context-namespaced destructive fingerprint to the generation it was last
        bounced at; a re-issue in a later generation of the same context consumes it once."""
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

    def _unattended_denial_feedback(self, action: str) -> str | None:
        """Fail closed when an unattended run would otherwise wait for approval forever."""
        if not self.is_auto() or self._state.yolo:
            return None
        if str(action) == _EDIT_OUTSIDE_ACTION:
            return _OUTSIDE_WORKSPACE_UNATTENDED_FEEDBACK
        if self._state.safe_mode and action not in self._state.auto_approve_actions:
            return _SAFE_MODE_UNATTENDED_FEEDBACK
        return None

    def is_orchestration_approved(self, fingerprint: str) -> bool:
        return fingerprint in self._state.approved_orchestration_fingerprints

    def approve_orchestration(self, fingerprint: str) -> None:
        self._state.approved_orchestration_fingerprints.add(fingerprint)

    @staticmethod
    def _tool_arguments(tool_call: ToolCall) -> dict[str, JsonType] | None:
        """Parse a tool call's JSON arguments into a dict, else ``None``."""
        try:
            args: JsonType = json.loads(tool_call.function.arguments or "{}")
        except (ValueError, TypeError):
            return None
        return args if isinstance(args, dict) else None

    def _approval_key(self, tool_call: ToolCall, action: str) -> str:
        """Session-approval key, narrowed below the coarse ``action`` where possible.

        For Shell, fold a normalized command signature into the key so "approve for
        session" is scoped per command family — approving ``git status`` does not also
        whitelist ``git push`` or ``rm``. Other tools keep the bare ``action`` key.
        """
        if tool_call.function.name == "Shell":
            args = self._tool_arguments(tool_call)
            command = (args or {}).get("command")
            if isinstance(command, str) and command:
                from pythinker_code.soul.permission import shell_command_signature

                return f"{action}::{shell_command_signature(command)}"
        return action

    def _pending_approval_key(self, pending: ApprovalRequestRecord) -> str:
        """Reconstruct the session-approval key for a pending request from its display.

        Mirrors ``_approval_key`` so the approve-for-session drain only clears pending
        siblings with the SAME key, never a different (e.g. destructive) command that
        merely shares the coarse action string.
        """
        if pending.sender == "Shell":
            for block in pending.display:
                command = getattr(block, "command", None)
                if isinstance(command, str) and command:
                    from pythinker_code.soul.permission import shell_command_signature

                    return f"{pending.action}::{shell_command_signature(command)}"
        return pending.action

    def _is_destructive_call(self, tool_call: ToolCall) -> bool:
        """Whether this call is irreversible/destructive per the central classifier."""
        arguments = self._tool_arguments(tool_call)
        if arguments is None:
            return False
        from pythinker_code.soul.permission import tool_destructive_reason

        return tool_destructive_reason(tool_call.function.name, arguments) is not None

    @staticmethod
    def _deliberation_fingerprint(
        context_id: str, tool_name: str, arguments: dict[str, JsonType]
    ) -> str:
        """Context-namespaced identity for a destructive call (context + name + sorted args)."""
        encoded = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        return f"{context_id}::{tool_name}::{encoded}"

    def deliberation_gate(self, tool_call: ToolCall) -> str | None:
        """Reason a destructive auto-approved action must deliberate once, else ``None``.

        Fires when the action would otherwise be auto-approved (auto *or* yolo — so it
        gates ahead of the yolo bypass), it is destructive, and either no user is present
        (``is_auto`` — no human to veto, so deliberation is mandatory) or ``auto_deliberate``
        is on (which extends deliberation to the interactive-yolo case). Destructiveness is
        classified by the tool-agnostic classifier in ``permission``
        (today only ``Shell``; other destructive tools register their classifier there).
        One-shot, scoped to (execution context, generation): the first sighting and any
        same-generation duplicate are bounced; only a re-issue in a later generation of the
        same context is let through once, so a deliberated ``rm -rf`` runs without being
        permanently whitelisted, while two identical calls in one model response both
        deliberate and a subagent cannot consume the main agent's one-shot.
        """
        # The destructive backstop must hold whenever an irreversible action would be
        # auto-approved with NO user present (``is_auto``): there is no human to veto it,
        # so the model must deliberate once first. The ``auto_deliberate`` config flag
        # only EXTENDS this to the interactive-yolo case (a user IS present but approvals
        # are skipped), where the human would otherwise see the action at approval time.
        if not (self._state.auto_deliberate or self.is_auto()):
            return None
        if not self.is_auto_approve():
            return None
        arguments = self._tool_arguments(tool_call)
        if arguments is None:
            return None
        from pythinker_code.soul.permission import tool_destructive_reason

        reason = tool_destructive_reason(tool_call.function.name, arguments)
        if reason is None:
            return None
        scope = _current_deliberation_scope.get()
        if scope is None:
            # Defensive fallback. The production path (PythinkerSoul._step) always binds a
            # scope around step + tool-result collection, and the only caller of this gate
            # (Approval.request, via a tool future created inside that scope) inherits it.
            # Reaching here means a destructive call was gated with no turn-boundary signal,
            # so we cannot distinguish a same-response duplicate from a deliberated re-issue.
            # Fail CLOSED: keep bouncing rather than auto-approving a destructive action we
            # cannot prove was deliberated. Surface it loudly — it indicates a wiring bug.
            logger.warning(
                "deliberation_gate reached without a deliberation scope for {tool_name}; "
                "bouncing fail-closed (no turn boundary to authorize a retry)",
                tool_name=tool_call.function.name,
            )
            return reason
        fingerprint = self._deliberation_fingerprint(
            scope.context_id, tool_call.function.name, arguments
        )
        # One-shot keyed by (execution context, generation): the first sighting and any
        # same-generation duplicate are bounced; only a re-issue in a strictly LATER
        # generation of the same context is let through once. The context_id prefix prevents
        # a subagent's identical call from consuming the main agent's one-shot (state is
        # shared via Approval.share()).
        prior_generation = self._state.deliberated_fingerprints.get(fingerprint)
        if prior_generation is not None:
            if prior_generation < scope.generation:
                del self._state.deliberated_fingerprints[fingerprint]
                return None
            return reason
        self._state.deliberated_fingerprints[fingerprint] = scope.generation
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
        if (feedback := self._unattended_denial_feedback(action)) is not None:
            from pythinker_code.telemetry import track

            track(
                "tool_rejected",
                tool_name=tool_call.function.name,
                approval_mode="auto_unavailable",
            )
            return ApprovalResult(approved=False, feedback=feedback, user_rejection=False)

        if self.is_auto_approve():
            from pythinker_code.telemetry import track

            track(
                "tool_approved",
                tool_name=tool_call.function.name,
                approval_mode="auto" if self.is_auto() else "yolo",
            )
            emit_current_tool_execution_started()
            return ApprovalResult(approved=True)

        # Session approval is keyed per command/path (permgate-1a), and never covers
        # a destructive/irreversible call: a coarse "approve for session" on a benign
        # command must not silently carry a later `rm -rf`/`git push --force`
        # (permgate-1b). Destructive calls fall through to a fresh prompt.
        approval_key = self._approval_key(tool_call, action)
        if approval_key in self._state.auto_approve_actions and not self._is_destructive_call(
            tool_call
        ):
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
                # permgate-3: when several concurrent subagents issue a byte-identical
                # action, one approval should clear them all instead of re-prompting once
                # per sibling (which pressures the user toward blanket approval). Drain only
                # pending requests with the SAME fine-grained identity (per-command key AND
                # description), and never for a destructive call — each irreversible action
                # is approved individually. This does NOT touch auto_approve_actions, so it
                # is one-time coverage of concurrent duplicates, not a standing session rule.
                if not self._is_destructive_call(tool_call):
                    for pending in self._runtime.list_pending():
                        if (
                            pending.id != request_id
                            and pending.description == description
                            and self._pending_approval_key(pending) == approval_key
                        ):
                            self._runtime.resolve(pending.id, "approve")
                emit_current_tool_execution_started()
                return ApprovalResult(approved=True)
            case "approve_for_session":
                track(
                    "tool_approved",
                    tool_name=tool_call.function.name,
                    approval_mode="manual",
                )
                # A destructive call is never recorded as session-approved — it must
                # re-prompt every time — so "approve for session" on one degrades to a
                # one-time approve (permgate-1b). Otherwise record the per-command key
                # and drain only pending siblings with that SAME key, so approving
                # `git status` for the session cannot silently clear a queued `rm -rf`.
                if not self._is_destructive_call(tool_call):
                    self._state.auto_approve_actions.add(approval_key)
                    self._state.notify_change()
                    for pending in self._runtime.list_pending():
                        if self._pending_approval_key(pending) == approval_key:
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
