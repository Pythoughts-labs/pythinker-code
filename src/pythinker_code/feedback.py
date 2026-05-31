from __future__ import annotations

import asyncio
import json
import platform
import re
import shlex
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import aiohttp

from pythinker_code.constant import VERSION
from pythinker_code.telemetry.errors import RecentError, recent_errors
from pythinker_code.ui.shell.oauth import current_model_key
from pythinker_code.utils.aiohttp import new_client_session
from pythinker_code.utils.export import is_sensitive_file
from pythinker_code.utils.logging import logger
from pythinker_code.utils.string import shorten
from pythinker_code.wire.types import TextPart, ThinkPart

if TYPE_CHECKING:
    from pythinker_core.message import Message

    from pythinker_code.soul.pythinkersoul import PythinkerSoul

FeedbackType = Literal["bug", "feature", "ux", "wrong", "other"]

FEEDBACK_TYPES: set[str] = {"bug", "feature", "ux", "wrong", "other"}
_TYPE_ALIASES: dict[str, FeedbackType] = {
    "bug": "bug",
    "error": "bug",
    "crash": "bug",
    "feature": "feature",
    "request": "feature",
    "ux": "ux",
    "ui": "ux",
    "wrong": "wrong",
    "incorrect": "wrong",
    "bad": "wrong",
    "other": "other",
    "feedback": "other",
}
_SENSITIVE_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|passwd|authorization)", re.I)
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer|token)\s+)[A-Za-z0-9._~+/=-]{8,}"),
        r"\1<redacted>",
    ),
    (
        re.compile(r"(?i)((?:api[_-]?key|token|secret|password|passwd)\s*[:=]\s*)[^\s'\"]+"),
        r"\1<redacted>",
    ),
    (re.compile(r"\bsk-(?:ant|proj|[A-Za-z0-9])[A-Za-z0-9_-]{16,}\b"), "<redacted-api-key>"),
    (re.compile(r"\bxox(?:a|b|p|r|s)-[A-Za-z0-9-]{10,}\b"), "<redacted-slack-token>"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,45}\b"), "<redacted-google-api-key>"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "<redacted-jwt>",
    ),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"), "<redacted-github-token>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "<redacted-aws-key>"),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.S,
        ),
        "<redacted-private-key>",
    ),
)
_HINT_KEYS = ("path", "file_path", "command", "query", "url", "name", "pattern")
_MAX_MESSAGE_TEXT = 1_500
_MAX_MESSAGES_DEFAULT = 10
_MAX_MESSAGES_WITH_TRANSCRIPT = 80
_MAX_TOOL_CALLS = 40
_MAX_DIFF_CHARS = 60_000
_MAX_COMMAND_OUTPUT = 20_000
_MAX_ISSUE_URL_BODY_CHARS = 5_500
_MAX_ISSUE_URL_CONTENT_CHARS = 2_500


@dataclass(slots=True, frozen=True)
class FeedbackOptions:
    kind: FeedbackType
    message: str
    include_diff: bool = False
    include_transcript: bool = False
    include_tool_details: bool = False
    yes: bool = False

    @property
    def includes_sensitive_context(self) -> bool:
        return self.include_diff or self.include_transcript or self.include_tool_details


@dataclass(slots=True, frozen=True)
class FeedbackSubmission:
    number: int | None = None
    html_url: str | None = None


def parse_feedback_args(args: str) -> FeedbackOptions | str:
    """Parse `/feedback` args into a structured request or an error string."""
    try:
        parts = shlex.split(args)
    except ValueError as exc:
        return f"Invalid /feedback arguments: {exc}"

    kind: FeedbackType = "other"
    include_diff = False
    include_transcript = False
    include_tool_details = False
    yes = False
    message_parts: list[str] = []

    for part in parts:
        if part in {"--include-diff", "--diff"}:
            include_diff = True
        elif part in {"--include-transcript", "--transcript"}:
            include_transcript = True
        elif part in {"--include-tool-details", "--tool-details"}:
            include_tool_details = True
        elif part in {"--yes", "-y"}:
            yes = True
        elif part.startswith("--"):
            return f"Unknown /feedback option: {part}"
        elif not message_parts and kind == "other" and part.lower() in _TYPE_ALIASES:
            kind = _TYPE_ALIASES[part.lower()]
        else:
            message_parts.append(part)

    return FeedbackOptions(
        kind=kind,
        message=" ".join(message_parts).strip(),
        include_diff=include_diff,
        include_transcript=include_transcript,
        include_tool_details=include_tool_details,
        yes=yes,
    )


def redact_text(text: str) -> str:
    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    try:
        home = str(Path.home())
        if home and home != "/":
            redacted = redacted.replace(home, "~")
    except (RuntimeError, OSError):
        logger.debug("Could not resolve home directory for redaction")
    return redacted


def redact_value(value: object, *, key: str = "") -> object:
    if _SENSITIVE_KEY_RE.search(key):
        return "<redacted>"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        values = cast(Mapping[object, object], value)
        return {str(k): redact_value(v, key=str(k)) for k, v in values.items()}
    if isinstance(value, list | tuple):
        values = cast(list[object] | tuple[object, ...], value)
        return [redact_value(v) for v in values]
    return value


def feedback_summary(payload: dict[str, Any]) -> str:
    privacy = cast(dict[str, Any], payload.get("privacy") or {})
    context = cast(dict[str, Any], payload.get("context") or {})
    repo = cast(dict[str, Any], payload.get("repo") or {})
    lines = ["Pythinker will include:"]
    lines.append("✓ session id, version, OS, Python, active model")
    if repo:
        lines.append("✓ git branch/head and diffstat")
    if context.get("recent_errors"):
        lines.append(f"✓ {len(context['recent_errors'])} recent error(s)")
    if context.get("last_messages"):
        lines.append(f"✓ {len(context['last_messages'])} recent visible message(s)")
    if context.get("tool_calls"):
        lines.append(f"✓ {len(context['tool_calls'])} tool call summary item(s)")
    lines.append("✓ best-effort secret/path redaction")
    lines.append("✓ patch diff" if privacy.get("included_diff") else "✗ patch diff")
    lines.append(
        "✓ extended transcript" if privacy.get("included_transcript") else "✗ extended transcript"
    )
    lines.append(
        "✓ tool args/results"
        if privacy.get("included_tool_details")
        else "✗ detailed tool args/results"
    )
    return "\n".join(lines)


async def build_feedback_payload(soul: PythinkerSoul, options: FeedbackOptions) -> dict[str, Any]:
    session = soul.runtime.session
    errors = recent_errors()
    repo = await _collect_git_snapshot(Path(str(session.work_dir)), options)
    context = _collect_context_snapshot(soul, options, errors)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "type": options.kind,
        "content": redact_text(options.message),
        # Compatibility with the existing feedback worker.
        "session_id": session.id,
        "version": VERSION,
        "os": f"{platform.system()} {platform.release()}",
        "model": current_model_key(soul),
        "session": {
            "id": session.id,
            "title": getattr(session, "title", "") or "",
            "role": soul.runtime.role,
        },
        "client": {
            "version": VERSION,
            "os": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "model": current_model_key(soul),
            "agent": soul.name,
        },
        "repo": repo,
        "context": context,
        "privacy": {
            "redacted": True,
            "included_diff": options.include_diff,
            "included_transcript": options.include_transcript,
            "included_tool_details": options.include_tool_details,
        },
    }
    return cast(dict[str, Any], redact_value(payload))


async def submit_feedback_payload(
    feedback_url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> FeedbackSubmission:
    async with (
        new_client_session() as session,
        session.post(
            feedback_url, json=payload, headers=headers, raise_for_status=True
        ) as response,
    ):
        if response.status == 204:
            return FeedbackSubmission()
        try:
            data_any: Any = await response.json(content_type=None)
        except (aiohttp.ContentTypeError, ValueError):
            return FeedbackSubmission()
    if not isinstance(data_any, dict):
        return FeedbackSubmission()
    data = cast(dict[str, object], data_any)
    number = data.get("number")
    html_url = data.get("html_url")
    return FeedbackSubmission(
        number=number if isinstance(number, int) else None,
        html_url=html_url if isinstance(html_url, str) and html_url else None,
    )


def build_feedback_issue_url(
    payload: dict[str, Any], repo: str = "TechMatrix-labs/pythinker-code"
) -> str:
    from urllib.parse import urlencode

    title = build_feedback_title(payload)
    body = build_feedback_issue_body(payload)
    labels = f"feedback,feedback:{payload.get('type') or 'other'}"
    return f"https://github.com/{repo}/issues/new?" + urlencode(
        {"title": title, "body": body, "labels": labels}
    )


def build_feedback_title(payload: dict[str, Any]) -> str:
    kind = str(payload.get("type") or "other")
    message = str(payload.get("content") or "").strip().splitlines()[0:1]
    suffix = f": {shorten(message[0], width=70)}" if message else ""
    return f"[Pythinker CLI] {kind.title()} feedback{suffix}"


def build_feedback_issue_body(payload: dict[str, Any]) -> str:
    """Compact GitHub URL fallback body.

    GitHub's ``issues/new?body=...`` path has practical URL-length limits, so
    this intentionally omits rich transcript/tool/diff context. The structured
    worker/API path receives the full JSON payload instead.
    """
    session = cast(dict[str, Any], payload.get("session") or {})
    client = cast(dict[str, Any], payload.get("client") or {})
    repo = cast(dict[str, Any], payload.get("repo") or {})
    context = cast(dict[str, Any], payload.get("context") or {})
    privacy = cast(dict[str, Any], payload.get("privacy") or {})
    content = str(payload.get("content") or "_(no comment)_")
    lines = [
        "## User submission",
        "",
        _truncate(content, _MAX_ISSUE_URL_CONTENT_CHARS),
        "",
        "## Compact fallback context",
        "",
        f"- Type: {payload.get('type') or 'other'}",
        f"- Session: {session.get('id') or payload.get('session_id') or 'unknown'}",
        f"- Version: {client.get('version') or payload.get('version') or 'unknown'}",
        f"- OS: {client.get('os') or payload.get('os') or 'unknown'}",
        f"- Python: {client.get('python') or 'unknown'}",
        f"- Model: {client.get('model') or payload.get('model') or 'unknown'}",
        f"- Redacted: {privacy.get('redacted', True)}",
    ]
    if repo:
        lines.extend(
            [
                f"- Branch: {repo.get('branch') or 'unknown'}",
                f"- HEAD: {repo.get('head') or 'unknown'}",
                f"- Dirty: {repo.get('dirty', 'unknown')}",
            ]
        )
    if context.get("recent_errors"):
        lines.append(f"- Recent errors: {len(context['recent_errors'])}")
    if context.get("last_messages"):
        lines.append(f"- Recent visible messages omitted: {len(context['last_messages'])}")
    if context.get("tool_calls"):
        lines.append(f"- Tool call summaries omitted: {len(context['tool_calls'])}")
    if repo.get("diff"):
        lines.append("- Patch diff omitted: GitHub fallback URLs are length-limited.")
    lines.extend(
        [
            "",
            "> Full structured context was omitted from this browser fallback because "
            "GitHub issue URLs are length-limited.",
        ]
    )
    return _truncate("\n".join(lines), _MAX_ISSUE_URL_BODY_CHARS)


def build_feedback_body(payload: dict[str, Any]) -> str:
    session = cast(dict[str, Any], payload.get("session") or {})
    client = cast(dict[str, Any], payload.get("client") or {})
    repo = cast(dict[str, Any], payload.get("repo") or {})
    context = cast(dict[str, Any], payload.get("context") or {})
    privacy = cast(dict[str, Any], payload.get("privacy") or {})
    lines = [
        "## User submission",
        "",
        str(payload.get("content") or "_(no comment)_"),
        "",
        "## Context",
        "",
        f"- Type: {payload.get('type') or 'other'}",
        f"- Session: {session.get('id') or payload.get('session_id') or 'unknown'}",
        f"- Version: {client.get('version') or payload.get('version') or 'unknown'}",
        f"- OS: {client.get('os') or payload.get('os') or 'unknown'}",
        f"- Python: {client.get('python') or 'unknown'}",
        f"- Model: {client.get('model') or payload.get('model') or 'unknown'}",
        f"- Redacted: {privacy.get('redacted', True)}",
    ]
    if repo:
        lines.extend(
            [
                "",
                "## Repository",
                "",
                f"- Branch: {repo.get('branch') or 'unknown'}",
                f"- HEAD: {repo.get('head') or 'unknown'}",
                f"- Dirty: {repo.get('dirty', 'unknown')}",
            ]
        )
        if repo.get("diff_stat"):
            lines.extend(["", "```text", str(repo["diff_stat"]), "```"])
        if repo.get("diff"):
            lines.extend(
                [
                    "",
                    "<details><summary>Patch diff</summary>",
                    "",
                    "```diff",
                    str(repo["diff"]),
                    "```",
                    "</details>",
                ]
            )

    if context.get("recent_errors"):
        lines.extend(["", "## Recent errors", ""])
        for error in cast(list[dict[str, Any]], context["recent_errors"]):
            lines.append(
                f"- {error.get('site') or 'unknown'}: {error.get('exc_class') or 'unknown'}"
                f"{f' (tool={error.get("tool")})' if error.get('tool') else ''}"
                f"{f' — {error.get("message")}' if error.get('message') else ''}"
            )

    if context.get("last_messages"):
        lines.extend(["", "## Recent visible messages", ""])
        for message in cast(list[dict[str, Any]], context["last_messages"]):
            lines.append(f"### {message.get('role', 'message')}")
            lines.append("")
            lines.append(str(message.get("text") or ""))
            lines.append("")

    if context.get("tool_calls"):
        lines.extend(["", "## Tool calls", ""])
        for call in cast(list[dict[str, Any]], context["tool_calls"]):
            hint = f" — {call.get('hint')}" if call.get("hint") else ""
            lines.append(f"- {call.get('name') or 'unknown'}{hint}")

    return "\n".join(lines)


async def _collect_git_snapshot(work_dir: Path, options: FeedbackOptions) -> dict[str, Any]:
    async def git(*args: str) -> str:
        return await asyncio.to_thread(_run_git, work_dir, list(args))

    branch = await git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch:
        return {}
    head, status, unstaged_stat, cached_stat = await asyncio.gather(
        git("rev-parse", "--short", "HEAD"),
        git("status", "--short"),
        git("diff", "--stat"),
        git("diff", "--cached", "--stat"),
    )
    diff_stat = "\n".join(part for part in [unstaged_stat, cached_stat] if part.strip())
    snapshot: dict[str, Any] = {
        "branch": branch,
        "head": head,
        "dirty": bool(status.strip()),
        "status_short": status[:_MAX_COMMAND_OUTPUT],
        "diff_stat": diff_stat[:_MAX_COMMAND_OUTPUT],
    }
    if options.include_diff:
        unstaged_diff, cached_diff = await asyncio.gather(
            git("diff", "--no-ext-diff"),
            git("diff", "--cached", "--no-ext-diff"),
        )
        diff = "\n".join(part for part in [unstaged_diff, cached_diff] if part.strip())
        snapshot["diff"] = _truncate(redact_text(diff), _MAX_DIFF_CHARS)
    return snapshot


def _run_git(work_dir: Path, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=work_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return redact_text(proc.stdout.strip())


def _collect_context_snapshot(
    soul: PythinkerSoul,
    options: FeedbackOptions,
    errors: list[RecentError],
) -> dict[str, Any]:
    history = list(soul.context.history)
    message_limit = (
        _MAX_MESSAGES_WITH_TRANSCRIPT if options.include_transcript else _MAX_MESSAGES_DEFAULT
    )
    return {
        "recent_errors": [
            {
                "timestamp": err.timestamp,
                "site": err.site,
                "exc_class": err.exc_class,
                "message": err.message,
                "tool": err.tool,
            }
            for err in errors
        ],
        "last_messages": _collect_recent_messages(history, limit=message_limit),
        "tool_calls": _collect_tool_calls(history, include_details=options.include_tool_details),
        "subagents": _collect_subagents(soul),
    }


def _collect_recent_messages(history: list[Message], *, limit: int) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for message in history:
        if message.role not in {"user", "assistant", "tool"}:
            continue
        text = _message_visible_text(message)
        if not text:
            continue
        messages.append(
            {
                "role": message.role,
                "text": _truncate(redact_text(text), _MAX_MESSAGE_TEXT),
            }
        )
    return messages[-limit:]


def _collect_tool_calls(history: list[Message], *, include_details: bool) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for message in history:
        for tool_call in message.tool_calls or []:
            args_raw = tool_call.function.arguments or "{}"
            record: dict[str, Any] = {
                "id": tool_call.id,
                "name": tool_call.function.name,
                "hint": redact_text(_extract_tool_hint(args_raw)),
            }
            if include_details:
                record["arguments"] = redact_value(_parse_json_or_text(args_raw))
            calls.append(record)
    return calls[-_MAX_TOOL_CALLS:]


def _collect_subagents(soul: PythinkerSoul) -> list[dict[str, Any]]:
    root = soul.runtime.session.subagents_dir
    records: list[dict[str, Any]] = []
    try:
        meta_paths = sorted(root.glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return records
    for path in meta_paths[:10]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        data_dict = cast(dict[str, object], data)
        launch_any = data_dict.get("launch_spec")
        launch = cast(dict[str, object], launch_any) if isinstance(launch_any, dict) else {}
        records.append(
            {
                "agent_id": data_dict.get("agent_id"),
                "type": data_dict.get("subagent_type") or launch.get("subagent_type"),
                "status": data_dict.get("status"),
                "description": data_dict.get("description"),
            }
        )
    return records


def _message_visible_text(message: Message) -> str:
    parts: list[str] = []
    for part in message.content:
        if isinstance(part, ThinkPart):
            continue
        if isinstance(part, TextPart):
            parts.append(part.text)
        else:
            part_type = getattr(part, "type", type(part).__name__)
            parts.append(f"[{part_type}]")
    return "\n".join(p for p in parts if p.strip()).strip()


def _extract_tool_hint(args_raw: str) -> str:
    parsed = _parse_json_or_text(args_raw)
    if not isinstance(parsed, dict):
        return ""
    parsed_dict = cast(dict[str, object], parsed)
    for key in _HINT_KEYS:
        value = parsed_dict.get(key)
        if isinstance(value, str) and value.strip() and not is_sensitive_file(value):
            return shorten(value, width=80)
    for value in parsed_dict.values():
        if isinstance(value, str) and 0 < len(value) <= 100 and not is_sensitive_file(value):
            return shorten(value, width=80)
    return ""


def _parse_json_or_text(value: str) -> object:
    try:
        return cast(object, json.loads(value, strict=False))
    except (json.JSONDecodeError, TypeError):
        return value


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n… <truncated>"
