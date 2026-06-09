from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from pythinker_code.wire.types import DisplayBlock

type ApprovalResponseKind = Literal["approve", "approve_for_session", "reject"]
type ApprovalSourceKind = Literal["foreground_turn", "background_agent"]
type ApprovalStatus = Literal["pending", "resolved", "cancelled"]
type ApprovalRuntimeEventKind = Literal["request_created", "request_resolved"]


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovalSource:
    kind: ApprovalSourceKind
    id: str
    agent_id: str | None = None
    subagent_type: str | None = None


@dataclass(slots=True, kw_only=True)
class ApprovalRequestRecord:
    id: str
    tool_call_id: str
    sender: str
    action: str
    description: str
    display: list[DisplayBlock]
    source: ApprovalSource
    created_at: float = field(default_factory=time.time)
    status: ApprovalStatus = "pending"
    resolved_at: float | None = None
    response: ApprovalResponseKind | None = None
    feedback: str = ""
    # Whether this request may be cleared by a *sibling's* approval drain.
    # Bound from the real tool call at request time (not reconstructed from the
    # display blocks): an irreversible/config-surface call is never
    # session-approvable, so a concurrent benign sibling that merely shares the
    # coarse signature can never resolve it (permgate-1b/3, OWASP: bind approval
    # to the exact action, fail closed). Defaults to ``False`` so any request
    # created without an explicit decision is excluded from drains.
    session_approvable: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovalRuntimeEvent:
    kind: ApprovalRuntimeEventKind
    request: ApprovalRequestRecord
