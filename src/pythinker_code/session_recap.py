from __future__ import annotations

import re
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
    if _is_light_day(items, total_minutes, total_turns):
        return _format_light_recap(title, items[0], total_minutes, total_turns)
    lines = [title, "", "**What you worked on:**"]
    for item in items:
        duration = _format_duration(item.duration_minutes)
        tools = _format_tool_counts(item.tool_counts)
        outcome = shorten(_session_outcome(item), width=150)
        line = f"- **{item.title}** ({duration}, {item.turn_count} turns) — {outcome}"
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


_LIGHT_DAY_MAX_MINUTES = 30
_LIGHT_DAY_MAX_TURNS = 4


def _is_light_day(items: list[SessionRecapItem], total_minutes: int, total_turns: int) -> bool:
    """A single short session that changed nothing reads as a light day."""
    return (
        len(items) == 1
        and total_turns < _LIGHT_DAY_MAX_TURNS
        and total_minutes < _LIGHT_DAY_MAX_MINUTES
        and not any(item.files_modified for item in items)
    )


def _format_light_recap(title: str, item: SessionRecapItem, minutes: int, turns: int) -> str:
    lines = [
        title,
        "",
        (
            f"Light day — one session, {turns} turn{'s' if turns != 1 else ''}, "
            f"{_format_duration(minutes)}."
        ),
    ]
    summary = _session_outcome(item)
    if summary:
        lines.extend(["", shorten(summary, width=220)])
    return "\n".join(lines)


def build_turn_recap_line(
    *,
    request: str,
    assistant_text: str = "",
    step_count: int | None = None,
    files_changed: int = 0,
) -> str | None:
    assistant_source = _recap_source_text(assistant_text)
    request_source = _recap_source_text(request)
    source = (
        _outcome_summary(assistant_source, require_action=True)
        or _outcome_sentence(request_source)
        or request_source
    )
    if not source:
        return None
    summary = shorten(source, width=220)
    deltas: list[str] = []
    if files_changed > 0:
        deltas.append(f"{files_changed} file{'s' if files_changed != 1 else ''} changed")
    if step_count is not None and step_count > 0:
        deltas.append(f"{step_count} step{'s' if step_count != 1 else ''}")
    suffix = f" · {' · '.join(deltas)}" if deltas else ""
    return f"※ recap: {summary}{suffix} (disable recaps in /config)"


def _last_substantive_thread(items: list[SessionRecapItem]) -> str:
    for item in reversed(items):
        if item.last_user_message:
            return shorten(item.last_user_message, width=220)
    return ""


_MIN_RECAP_SENTENCE_CHARS = 16
_FENCE_START_RE = re.compile(r"^ {0,3}(```+|~~~+)")
_TABLE_DELIMITER_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_MARKDOWN_RULE_RE = re.compile(r"^\s{0,3}(?:[-*_]\s*){3,}$")
_ATX_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+.+?\s*#*\s*$")
_ACTION_OUTCOME_RE = re.compile(
    r"\b(implemented|fixed|updated|added|removed|renamed|released|published|created|"
    r"opened|pushed|committed|merged|verified|validated|ran|completed|finished|"
    r"generated|adjusted|resolved|repaired|improved|changed|patched|hardened|rendered|wired|made|"
    r"aligned|preserved|stripped|switched|migrated|refactored|restored|documented|"
    r"configured|enabled|disabled)\b",
    re.IGNORECASE,
)
_STATUS_OUTCOME_RE = re.compile(
    r"^(no\s+|all\s+|nothing\s+|everything\s+|tests?\s+passed\b|there\s+(?:is|are)\s+no\s+)",
    re.IGNORECASE,
)
_MARKDOWN_INLINE_PREFIX_RE = re.compile(r"^\s*(?:[-*_]{3,}\s+)?#{1,6}\s+")
_OPTION_HEADING_RE = re.compile(
    r"^\s*(?:[-*_]{3,}\s+)?(?:#{1,6}\s+)?(?:option|variant|concept|direction)\s+\d+\s*:",
    re.IGNORECASE,
)
_PARENTHETICAL_RE = re.compile(r"\([^)]*\)")
_SYSTEM_REMINDER_BLOCK_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)


def _recap_source_text(text: str) -> str:
    """Return one-line recap input with bulky structured blocks removed."""
    without_reminders = _SYSTEM_REMINDER_BLOCK_RE.sub("", text)
    without_fences = _strip_fenced_blocks(without_reminders)
    without_tables = _strip_markdown_tables(without_fences)
    without_structure = _strip_markdown_structure(without_tables)
    without_ticks = without_structure.replace("`", "")
    return " ".join(without_ticks.split())


def _strip_fenced_blocks(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        match = _FENCE_START_RE.match(line)
        if in_fence:
            if stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            continue
        if match is not None:
            in_fence = True
            fence_marker = match.group(1)[0] * len(match.group(1))
            continue
        lines.append(line)
    return "\n".join(lines)


def _is_table_delimiter(line: str) -> bool:
    return _TABLE_DELIMITER_RE.match(line) is not None


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _strip_markdown_tables(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if _is_table_row(line) and _is_table_delimiter(next_line):
            index += 2
            while index < len(lines) and _is_table_row(lines[index]):
                index += 1
            continue
        kept.append(line)
        index += 1
    return "\n".join(kept)


def _strip_markdown_structure(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if _MARKDOWN_RULE_RE.match(stripped) or _ATX_HEADING_RE.match(stripped):
            continue
        lines.append(line)
    return "\n".join(lines)


def _first_sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    for sep in (". ", "! ", "? "):
        idx = cleaned.find(sep)
        if idx >= _MIN_RECAP_SENTENCE_CHARS:
            return cleaned[: idx + 1]
    return cleaned


# A turn's text opens with intent and ends with a summary. These openers mark
# intent/offer sentences that describe what *will* happen, not what was done.
_SKIP_SENTENCE_PREFIXES = (
    "i'll",
    "i will",
    "let me",
    "let's",
    "now i'll",
    "now let",
    "i'm going to",
    "i am going to",
    "i'm going",
    "to start",
    "starting by",
    "first, i",
    "next, i",
    "want me",
    "let me know",
    "shall i",
    "should i",
    "do you want",
    "would you like",
)
# A single token longer than this is almost always a path/URL/hash, not prose.
_MAX_RECAP_TOKEN_CHARS = 30
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _iter_sentences(text: str) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    return [part for part in _SENTENCE_SPLIT_RE.split(cleaned) if part.strip()]


def _is_outcome_sentence(sentence: str) -> bool:
    """True when the sentence reads like a result rather than intent or noise."""
    candidate = sentence.strip()
    if len(candidate) < _MIN_RECAP_SENTENCE_CHARS:
        return False
    if candidate.endswith("?"):
        return False
    # Models emit a typographic apostrophe (U+2019); normalize so intent
    # openers like "I'll" / "I’ll" are skipped identically.
    lowered = candidate.lower().replace("’", "'")
    if lowered.startswith(_SKIP_SENTENCE_PREFIXES):
        return False
    if _MARKDOWN_INLINE_PREFIX_RE.match(candidate) or _OPTION_HEADING_RE.match(candidate):
        return False
    return not any(len(token) > _MAX_RECAP_TOKEN_CHARS for token in candidate.split())


def _is_action_outcome_sentence(sentence: str) -> bool:
    prose = _PARENTHETICAL_RE.sub(" ", sentence)
    return _ACTION_OUTCOME_RE.search(prose) is not None


def _is_status_outcome_sentence(sentence: str) -> bool:
    return _STATUS_OUTCOME_RE.match(sentence.strip()) is not None


def _outcome_summary(text: str, *, require_action: bool = False) -> str:
    sentences = _iter_sentences(text)
    outcomes = [
        (index, sentence)
        for index, sentence in enumerate(sentences)
        if _is_outcome_sentence(sentence)
    ]
    if not outcomes:
        return "" if require_action else _first_sentence(text)
    if not require_action:
        return outcomes[-1][1]

    action_outcomes = [item for item in outcomes if _is_action_outcome_sentence(item[1])]
    if not action_outcomes:
        return ""

    start_index, first = action_outcomes[-1]
    selected = [first]
    for sentence in sentences[start_index + 1 :]:
        if len(selected) >= 2:
            break
        if not _is_outcome_sentence(sentence):
            break
        if _is_action_outcome_sentence(sentence) or _is_status_outcome_sentence(sentence):
            selected.append(sentence)
            continue
        break
    return " ".join(selected)


def _outcome_sentence(text: str) -> str:
    """Return the closing outcome sentence, skipping intent/offer/noise lines.

    Falls back to the first sentence when nothing reads like an outcome, so a
    terse or interrupted turn still produces a line.
    """
    return _outcome_summary(text)


def _session_outcome(item: SessionRecapItem) -> str:
    """What the session accomplished — its closing summary, not the first ask."""
    combined = " ".join(item.assistant_snippets[-3:])
    sentence = _outcome_sentence(combined)
    if sentence and _is_outcome_sentence(sentence):
        return sentence
    return item.first_user_message


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
