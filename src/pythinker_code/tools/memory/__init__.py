from pathlib import Path
from typing import Literal, override

from pydantic import BaseModel, Field
from pythinker_core.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue

from pythinker_code.project_memory import ProjectMemoryStore
from pythinker_code.soul.agent import Runtime
from pythinker_code.tools.memory.routing_guard import routing_signals
from pythinker_code.tools.utils import load_desc
from pythinker_code.utils.logging import logger

# Appended (never substituted) to a successful add/replace whose content looks
# like it governs behavior defined in a project file. The tool is blind to
# conversation context, so it can only nudge — enforcement lives in memory.md
# guidance and the model's own awareness of the correction it just received.
_ROUTING_ADVISORY = (
    "\n\nNote: this looks like it may set a rule that lives in a project file "
    "(a protocol, spec, or config you read). If so, edit that file directly — "
    "memory does not change files you follow, so the change would be silently "
    "lost. Memory is only for durable facts with no authoritative home."
)


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
                message += (
                    "\n\nProject memory for this repo is full — nothing was lost, and your "
                    "task can continue. To free space: ask me to merge or drop stale entries, "
                    "run /memory to see what's stored, or edit MEMORY.md / USER.md directly. "
                    "Memory is for durable facts only, so occasional pruning is expected."
                )
            brief = "memory: full" if result.full else "memory: rejected"
            return ToolError(message=message, brief=brief)
        rearm = getattr(self._runtime, "rearm_injection", None)
        if rearm is not None:
            rearm("project_memory")
        message = result.message
        if params.action in ("add", "replace"):
            signals = routing_signals(params.content or "")
            if signals:
                logger.bind(
                    event="memory_guard_advisory",
                    action=params.action,
                    target=params.target,
                    signals=signals,
                ).debug(
                    "memory write tripped routing advisory: {preview}",
                    preview=(params.content or "")[:60],
                )
                message += _ROUTING_ADVISORY
        return ToolOk(output=message, message=message, brief=params.action)
