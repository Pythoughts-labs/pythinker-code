from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import time as dt_time

from pythinker_core.message import Message
from pythinker_host.path import HostPath

from pythinker_code.session import Session
from pythinker_code.tools.display import DiffDisplayBlock
from pythinker_code.utils.string import shorten
from pythinker_code.wire.types import TextPart, ToolCall, ToolResult, TurnBegin


@dataclass(frozen=True, slots=True)
class RecapRange:
    label: str
    start_ts: float
    end_ts: float


def _list_str() -> list[str]:
    return []


def _counter_str() -> Counter[str]:
    return Counter()


def _set_str() -> set[str]:
    return set()


@dataclass(slots=True)
class SessionRecapItem:
    title: str
    session_id: str
    start_ts: float = 0.0
    end_ts: float = 0.0
    turn_count: int = 0
    first_user_message: str = ""
    last_user_message: str = ""
    assistant_snippets: list[str] = field(default_factory=_list_str)
    tool_counts: Counter[str] = field(default_factory=_counter_str)
    files_modified: list[str] = field(default_factory=_list_str)
    _files_modified_seen: set[str] = field(default_factory=_set_str)

    def add_modified_file(self, path: str) -> None:
        if not path or path in self._files_modified_seen:
            return
        self._files_modified_seen.add(path)
        self.files_modified.append(path)

    @property
    def duration_minutes(self) -> int:
        if not self.start_ts or not self.end_ts:
            return 0
        return max(0, round((self.end_ts - self.start_ts) / 60))


def parse_recap_range(args: str, *, now: datetime | None = None) -> RecapRange:
    now = now or datetime.now().astimezone()
    raw = args.strip().lower() or "today"

    def start_of_day(value: datetime) -> datetime:
        return datetime.combine(value.date(), dt_time.min, tzinfo=value.tzinfo)

    def end_of_day(value: datetime) -> datetime:
        return datetime.combine(value.date(), dt_time.max, tzinfo=value.tzinfo)

    if raw == "today":
        start = start_of_day(now)
        end = now
        label = "today"
    elif raw == "yesterday":
        day = now - timedelta(days=1)
        start = start_of_day(day)
        end = end_of_day(day)
        label = "yesterday"
    elif raw in {"week", "7d", "past 7 days"}:
        start = start_of_day(now - timedelta(days=7))
        end = now
        label = "past 7 days"
    else:
        try:
            day = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=now.tzinfo)
        except ValueError:
            raise ValueError(
                "Unknown recap period. Use: today, yesterday, week, or YYYY-MM-DD."
            ) from None
        start = start_of_day(day)
        end = end_of_day(day)
        label = raw

    return RecapRange(label=label, start_ts=start.timestamp(), end_ts=end.timestamp())


async def build_pythinker_recap(work_dir: HostPath, args: str = "") -> str:
    recap_range = parse_recap_range(args)
    sessions = await Session.list(work_dir)
    items: list[SessionRecapItem] = []
    for session in sessions:
        item = await summarize_session_for_recap(session, recap_range)
        if item is not None:
            items.append(item)
    items.sort(key=lambda item: item.start_ts)
    return format_recap(items, recap_range)


async def summarize_session_for_recap(
    session: Session, recap_range: RecapRange
) -> SessionRecapItem | None:
    item = SessionRecapItem(title=session.title or "Untitled", session_id=session.id)

    async for record in session.wire_file.iter_records():
        if record.timestamp < recap_range.start_ts or record.timestamp > recap_range.end_ts:
            continue
        msg = record.to_wire_message()
        if item.start_ts == 0.0:
            item.start_ts = record.timestamp
        item.end_ts = record.timestamp

        if isinstance(msg, TurnBegin):
            text = (
                msg.user_input
                if isinstance(msg.user_input, str)
                else Message(role="user", content=msg.user_input).extract_text(" ")
            ).strip()
            if text:
                item.turn_count += 1
                if not item.first_user_message:
                    item.first_user_message = text
                item.last_user_message = text
            continue

        if isinstance(msg, TextPart):
            text = " ".join(msg.text.split())
            if text:
                item.assistant_snippets.append(text)
            continue

        if isinstance(msg, ToolCall):
            item.tool_counts[msg.function.name] += 1
            continue

        if isinstance(msg, ToolResult):
            for block in getattr(msg.return_value, "display", []) or []:
                if isinstance(block, DiffDisplayBlock):
                    item.add_modified_file(block.path)

    if item.turn_count == 0:
        return None
    return item


def format_recap(items: list[SessionRecapItem], recap_range: RecapRange) -> str:
    title = f"**Recap — {recap_range.label}**"
    if not items:
        return f"{title}\n\nNo Pythinker sessions found for this period."

    total_minutes = sum(item.duration_minutes for item in items)
    total_turns = sum(item.turn_count for item in items)
    lines = [title, "", "**What you worked on:**"]
    for item in items:
        duration = _format_duration(item.duration_minutes)
        tools = _format_tool_counts(item.tool_counts)
        first = shorten(item.first_user_message, width=150)
        line = f"- **{item.title}** ({duration}, {item.turn_count} turns) — {first}"
        if tools:
            line += f" Tools: {tools}."
        if item.files_modified:
            shown = ", ".join(shorten(path, width=48) for path in item.files_modified[:4])
            hidden = len(item.files_modified) - 4
            line += f" Modified: {shown}{f', +{hidden} more' if hidden > 0 else ''}."
        lines.append(line)

    lines.extend(["", "**Summary:**"])
    lines.append(
        f"- {len(items)} session{'s' if len(items) != 1 else ''}, "
        f"{total_turns} turn{'s' if total_turns != 1 else ''}, "
        f"{_format_duration(total_minutes)} of visible Pythinker activity."
    )
    last_thread = _last_substantive_thread(items)
    if last_thread:
        lines.extend(["", "**A thread worth remembering:**", last_thread])
    return "\n".join(lines)


def build_turn_recap_line(
    *, request: str, assistant_text: str = "", step_count: int | None = None
) -> str | None:
    source = _first_sentence(assistant_text) or request.strip()
    if not source:
        return None
    summary = shorten(" ".join(source.split()), width=180)
    if step_count is not None and step_count > 0:
        summary += f" ({step_count} step{'s' if step_count != 1 else ''})"
    return f"※ recap: {summary} (disable recaps in /settings)"


def _last_substantive_thread(items: list[SessionRecapItem]) -> str:
    for item in reversed(items):
        if item.last_user_message:
            return shorten(item.last_user_message, width=220)
    return ""


def _first_sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    for sep in (". ", "! ", "? "):
        idx = cleaned.find(sep)
        if idx >= 40:
            return cleaned[: idx + 1]
    return cleaned


def _format_duration(minutes: int) -> str:
    if minutes < 1:
        return "<1 min"
    if minutes < 60:
        return f"~{minutes} min"
    hours, mins = divmod(minutes, 60)
    if mins == 0:
        return f"~{hours} hr"
    return f"~{hours} hr {mins} min"


def _format_tool_counts(counts: Counter[str]) -> str:
    if not counts:
        return ""
    parts: list[str] = []
    for name, count in counts.most_common(4):
        label = _tool_label(name)
        parts.append(f"{label} ×{count}" if count > 1 else label)
    hidden = len(counts) - len(parts)
    if hidden > 0:
        parts.append(f"+{hidden} more")
    return ", ".join(parts)


def _tool_label(name: str) -> str:
    return {
        "ReadFile": "Read",
        "WriteFile": "Write",
        "StrReplaceFile": "Edit",
        "Grep": "Search",
        "Glob": "Find",
        "Shell": "Bash",
        "Agent": "Agent",
    }.get(name, name)
