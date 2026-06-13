from pathlib import Path
from typing import Literal, override

from pydantic import BaseModel, Field
from pythinker_core.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue

from pythinker_code.project_memory import ProjectMemoryStore
from pythinker_code.soul.agent import Runtime
from pythinker_code.tools.memory.routing_guard import routing_signals
from pythinker_code.tools.utils import load_desc
from pythinker_code.utils.logging import logger


class Params(BaseModel):
    action: Literal["add", "replace", "remove", "list"] = Field(description="The memory operation.")
    target: Literal["memory", "user"] = Field(description="Which store to write.")
    content: str | None = Field(default=None, description="Entry text for add/replace.")
    old_text: str | None = Field(
        default=None, description="Unique substring identifying the entry to replace/remove."
    )
    index: int | None = Field(
        default=None,
        description="0-based index of the entry to replace/remove (from `list`). "
        "Deterministic alternative to old_text — prefer it when a substring match is uncertain.",
    )


class Memory(CallableTool2[Params]):
    name: str = "Memory"
    description: str = load_desc(Path(__file__).parent / "memory.md", {})
    params: type[Params] = Params

    def __init__(self, runtime: Runtime) -> None:
        super().__init__()
        self._runtime = runtime
        self._store = ProjectMemoryStore(runtime.work_dir)

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        if self._runtime.role != "root":
            return ToolError(
                message="Memory is only available to the root agent.", brief="memory: subagent"
            )
        if params.action in ("add", "replace") and not (params.content or "").strip():
            return ToolError(
                message="content is required for add/replace.", brief="memory: no content"
            )
        if (
            params.action in ("replace", "remove")
            and not (params.old_text or "").strip()
            and params.index is None
        ):
            return ToolError(
                message="old_text or index is required for replace/remove.",
                brief="memory: no locator",
            )

        if params.action == "list":
            output = await self._store.status(params.target)
            return ToolOk(output=output, message=output, brief="list")

        # Confirm-before-remember: a write whose content looks like a rule or a
        # file-governed setting (routing signals) is gated behind the user, so the
        # agent can't silently fill memory with corrections that belong in a project
        # file. Plain durable facts (no signals) skip the gate and write directly.
        if params.action in ("add", "replace"):
            declined = await self._confirm_flagged_write(params.target, params.content or "")
            if declined is not None:
                return declined

        if params.action == "add":
            result = await self._store.add(params.target, params.content or "")
        elif params.action == "replace":
            result = await self._store.replace(
                params.target, params.old_text or "", params.content or "", index=params.index
            )
        else:
            result = await self._store.remove(
                params.target, params.old_text or "", index=params.index
            )

        if not result.ok:
            message = result.message
            if result.full:
                # Educate the human reading the tool card: what happened, that nothing
                # was lost, and the real ways to fix it. Kept short and command-accurate.
                store_label = "Project memory" if params.target == "memory" else "User memory"
                message += (
                    f"\n\n{store_label} for this repo is full — nothing was lost, and your "
                    "task can continue. To free space: ask me to merge or drop stale entries, "
                    "run /memory to see what's stored, or edit MEMORY.md / USER.md directly. "
                    "Memory is for durable facts only, so occasional pruning is expected."
                )
            brief = "memory: full" if result.full else "memory: rejected"
            return ToolError(message=message, brief=brief)
        rearm = getattr(self._runtime, "rearm_injection", None)
        if rearm is not None:
            rearm("project_memory")
        return ToolOk(output=result.message, message=result.message, brief=params.action)

    async def _confirm_flagged_write(
        self, target: Literal["memory", "user"], content: str
    ) -> ToolReturnValue | None:
        """Gate a routing-flagged add/replace behind user confirmation.

        Returns ``None`` when the write may proceed — either the content has no
        routing signals (a plain durable fact) or the user approved. Returns a
        non-error result describing what to do instead when the write is declined:
        by the user (edit the governing file) or because no user is available to
        confirm (skipped). Yolo/auto-approve and "allow for session" are handled by
        the shared approval flow, so a confirmed store stops nagging for the session.
        """
        signals = routing_signals(content)
        if not signals:
            return None
        logger.bind(event="memory_guard_gate", target=target, signals=signals).debug(
            "memory write flagged for confirmation: {preview}", preview=content[:60]
        )

        store_label = "project" if target == "memory" else "user"
        why = (
            "It names a project file"
            if "file_ref" in signals
            else "It reads like a rule or a value/limit"
        )
        preview = content if len(content) <= 200 else content[:200] + "…"
        description = (
            f"Save this to {store_label} memory?\n\n{preview}\n\n"
            f"{why}, which usually belongs in an authoritative project file. Memory does "
            "not change files you follow, so a rule stored here is silently lost — edit "
            "that file instead. Approve only if this is a durable fact with no file home."
        )
        decision = await self._runtime.approval.request(self.name, "save to memory", description)
        if decision:
            return None  # approved → caller performs the write
        if decision.user_rejection:
            message = (
                "Not saved to memory — you declined. This looks like it belongs in a "
                "project file; edit that file directly so the change actually takes effect."
            )
            if decision.feedback:
                message += f"\n\nYour note: {decision.feedback}"
        else:
            message = (
                "Not saved to memory: this write was flagged for confirmation but no user "
                "is available to approve it. Skipped — continue the task, and if this fact "
                "governs behavior, edit the relevant project file instead."
            )
        return ToolOk(output=message, message=message, brief="memory: not saved")
