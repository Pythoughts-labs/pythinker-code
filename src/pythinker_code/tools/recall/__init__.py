"""Cross-session Recall tool (memory-1 / ctxmgmt-3).

Distilled JOURNAL recaps lose the load-bearing detail — exact commands, file paths,
why a fix was chosen — that an agent often needs to repeat or extend prior work.
Recall gives the model a designed, sanitized, workspace-scoped affordance to (1)
search prior sessions by keyword and (2) read a chosen session's transcript on
demand, instead of a brittle raw-file shell hatch.

Read-only and scoped to the current workspace's sessions. Transcript text is both
sanitized (secrets / injection-pattern blocks redacted via memory/sanitize) and
wrapped as untrusted data, since a prior transcript is untrusted historical input.
"""

import asyncio
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pythinker_core.message import Message
from pythinker_core.tooling import CallableTool2, ToolError, ToolOk, ToolReturnValue

from pythinker_code.memory.sanitize import sanitize_candidate_block
from pythinker_code.session import Session
from pythinker_code.soul.agent import Runtime
from pythinker_code.tools.utils import ToolResultBuilder, load_desc

NAME = "Recall"
_MAX_SEARCH_RESULTS = 10
_READ_BUDGET_CHARS = 16_000


class Params(BaseModel):
    mode: Literal["search", "read"] = Field(
        description="'search' to find prior sessions by keyword; 'read' to read one's transcript."
    )
    query: str | None = Field(
        default=None,
        description="Keywords to match against prior session titles (mode=search). "
        "Omit to list recent sessions.",
    )
    session_id: str | None = Field(
        default=None,
        description="The session_id to read, from a prior Recall search (mode=read).",
    )


def _rank_sessions(
    sessions: list[Session], *, query: str, current_id: str, limit: int
) -> list[Session]:
    """Rank prior sessions by title keyword overlap then recency (pure)."""
    terms = query.lower().split()
    scored: list[tuple[int, float, Session]] = []
    for session in sessions:
        if session.id == current_id:
            continue
        title = (session.state.custom_title or session.title or "").strip()
        score = sum(1 for term in terms if term in title.lower())
        if terms and score == 0:
            continue
        scored.append((score, session.updated_at, session))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [session for _score, _ts, session in scored[:limit]]


def _render_transcript(context_file: Path, budget: int) -> str:
    """Render a session's message log into a budgeted, sanitized transcript.

    Internal (``_``-prefixed) roles are skipped. Each message's text is sanitized;
    a block that trips the secret/injection scanner becomes ``[redacted]`` rather
    than leaking or silently vanishing. Stops once the char budget is reached.
    """
    try:
        raw = context_file.read_text(encoding="utf-8")
    except OSError:
        return ""
    out: list[str] = []
    used = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = Message.model_validate_json(line)
        except Exception:
            continue
        role = msg.role
        if role.startswith("_"):
            continue
        text = msg.extract_text(" ").strip()
        tool_names = [call.function.name for call in (msg.tool_calls or [])]
        segment = text
        if tool_names:
            segment = f"{segment} [tool calls: {', '.join(tool_names)}]".strip()
        if not segment:
            continue
        clean = sanitize_candidate_block(segment)
        entry = f"[{role}] {clean if clean is not None else '[redacted]'}"
        if used + len(entry) + 1 > budget:
            out.append("… (transcript truncated to fit the recall budget)")
            break
        out.append(entry)
        used += len(entry) + 1
    return "\n".join(out)


class Recall(CallableTool2[Params]):
    name: str = NAME
    params: type[Params] = Params

    def __init__(self, runtime: Runtime):
        super().__init__(description=load_desc(Path(__file__).parent / "description.md"))
        self._runtime = runtime

    async def __call__(self, params: Params) -> ToolReturnValue:
        if params.mode == "search":
            return await self._search((params.query or "").strip())
        if not params.session_id:
            return ToolError(
                message='mode="read" requires session_id (from a Recall search).',
                brief="Missing session_id",
            )
        return await self._read(params.session_id.strip())

    async def _search(self, query: str) -> ToolReturnValue:
        work_dir = self._runtime.session.work_dir
        try:
            sessions = await Session.list(work_dir)
        except Exception as exc:
            return ToolError(message=f"Failed to list prior sessions: {exc}", brief="Recall failed")

        top = _rank_sessions(
            sessions,
            query=query,
            current_id=self._runtime.session.id,
            limit=_MAX_SEARCH_RESULTS,
        )
        if not top:
            return ToolOk(
                output="No matching prior sessions in this workspace.",
                message="No matches.",
            )
        lines = ["Prior sessions in this workspace (most relevant first):", ""]
        for session in top:
            title = session.state.custom_title or session.title or "(untitled)"
            lines.append(f"- session_id: {session.id}")
            lines.append(f"  title: {title}")
        lines.append("")
        lines.append('Read one with Recall(mode="read", session_id="...").')
        return ToolOk(output="\n".join(lines), message=f"Found {len(top)} prior session(s).")

    async def _read(self, session_id: str) -> ToolReturnValue:
        if session_id == self._runtime.session.id:
            return ToolError(message="Cannot recall the current session.", brief="Current session")
        work_dir = self._runtime.session.work_dir
        try:
            session = await Session.find(work_dir, session_id)
        except Exception as exc:
            return ToolError(message=f"Failed to open session: {exc}", brief="Recall failed")
        if session is None:
            return ToolError(
                message=(
                    f"No session {session_id} in this workspace. "
                    'Use Recall(mode="search") to find valid session_ids.'
                ),
                brief="Unknown session",
            )

        rendered = await asyncio.to_thread(
            _render_transcript, session.context_file, _READ_BUDGET_CHARS
        )
        if not rendered:
            return ToolOk(
                output="(this prior session has no readable transcript)",
                message="Empty transcript.",
            )
        builder = ToolResultBuilder()
        builder.write(rendered)
        builder.mark_untrusted()
        return builder.ok(f"Recalled transcript of prior session {session_id}.")
