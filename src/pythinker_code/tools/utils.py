import asyncio
import os
import re
import uuid
from enum import StrEnum
from pathlib import Path

from jinja2 import Undefined
from jinja2.sandbox import SandboxedEnvironment as Environment
from pythinker_core.tooling import BriefDisplayBlock, DisplayBlock, ToolError, ToolReturnValue
from pythinker_core.utils.typing import JsonType

from pythinker_code.utils.trust import UntrustedData


class _KeepPlaceholderUndefined(Undefined):
    def __str__(self) -> str:
        if self._undefined_name is None:
            return ""
        return f"${{{self._undefined_name}}}"

    __repr__ = __str__


def load_desc(path: Path, context: dict[str, object] | None = None) -> str:
    """Load a tool description from a file, rendered via Jinja2."""
    description = path.read_text(encoding="utf-8")
    env = Environment(
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
        variable_start_string="${",
        variable_end_string="}",
        undefined=_KeepPlaceholderUndefined,
    )
    template = env.from_string(description)
    return template.render(context or {})


def truncate_line(line: str, max_length: int, marker: str = "...") -> str:
    """
    Truncate a line if it exceeds `max_length`, preserving the beginning and the line break.
    The output may be longer than `max_length` if it is too short to fit the marker.
    """
    if len(line) <= max_length:
        return line

    # Find line breaks at the end of the line
    m = re.search(r"[\r\n]+$", line)
    linebreak = m.group(0) if m else ""
    end = marker + linebreak
    max_length = max(max_length, len(end))
    return line[: max_length - len(end)] + end


# Default output limits
DEFAULT_MAX_CHARS = 50_000
# Upper bound on the retained full output for disk spill, so a pathological
# stream cannot exhaust memory. ~100x the in-context limit — ample for recovery.
SPILL_MAX_CHARS = 5_000_000
DEFAULT_MAX_LINE_LENGTH = 2000


class ToolResultStatus(StrEnum):
    """Machine-readable status taxonomy for tool results.

    This supplements ToolReturnValue.is_error for compatibility with existing callers.
    """

    success = "success"
    error = "error"
    cancelled = "cancelled"
    denied = "denied"
    failure = "failure"
    launched = "launched"
    long_running_snapshot = "long_running_snapshot"


def tool_status_value(status: ToolResultStatus | str) -> str:
    return status.value if isinstance(status, ToolResultStatus) else status


def tool_status_line(status: ToolResultStatus | str) -> str:
    return f"tool_status: {tool_status_value(status)}"


class ToolResultBuilder:
    """
    Builder for tool results with character and line limits.
    """

    def __init__(
        self,
        max_chars: int = DEFAULT_MAX_CHARS,
        max_line_length: int | None = DEFAULT_MAX_LINE_LENGTH,
    ):
        self.max_chars = max_chars
        self.max_line_length = max_line_length
        self._marker = "[...truncated]"
        if max_line_length is not None:
            assert max_line_length > len(self._marker)
        self._buffer: list[str] = []
        self._n_chars = 0
        self._n_lines = 0
        self._truncation_happened = False
        self._wrap_untrusted = False
        self._display: list[DisplayBlock] = []
        self._extras: dict[str, JsonType] | None = None
        # Opt-in spill (enable_spill): when set, the complete untruncated output is
        # retained so it can be written to disk on truncation with a recovery hint.
        self._full_buffer: list[str] | None = None
        self._full_chars = 0
        self._spill_capped = False
        self._spill_dir: Path | None = None
        self._spill_tool = "tool"
        self._spill_hint: str | None = None

    def enable_spill(self, spill_dir: Path, tool_name: str) -> None:
        """Retain the full output and, on truncation, spill it to disk with a hint.

        For non-file-backed, non-idempotent tools (foreground Shell, web fetch) the
        truncated tail is otherwise unrecoverable — re-running a build/test is
        expensive or non-deterministic. When enabled, the complete untruncated
        output is written to ``spill_dir/<tool_name>-<id>.txt`` on truncation and
        the inline truncation marker is replaced with an actionable recovery hint
        (ReadFile/Grep the file, or delegate to a read-only explore subagent).
        Best-effort: a write failure degrades silently to the default behavior.

        Memory is bounded: the retained full output is capped at ``SPILL_MAX_CHARS``
        so a pathological stream cannot exhaust RAM (the spill file is then itself
        capped, noted in the hint). ``tool_name`` is sanitized to a safe filename
        stem so it can never escape ``spill_dir``.
        """
        self._full_buffer = []
        self._full_chars = 0
        self._spill_capped = False
        self._spill_dir = spill_dir
        self._spill_tool = re.sub(r"[^A-Za-z0-9_-]", "_", tool_name) or "tool"
        self._spill_hint = None

    def mark_untrusted(self) -> None:
        """Mark the accumulated output buffer as external, untrusted content.

        When set, ok()/error() wrap the (already line-/char-truncated) output in a
        single <untrusted_data> block so the model treats command, web, and search
        bytes as data, never instructions. Wrapping the joined buffer once — rather
        than per write() — keeps a single coherent block whose closing tag cannot be
        cut by truncation. Harness-authored result messages (the ``message`` arg)
        stay outside the wrapper and are unaffected.
        """
        self._wrap_untrusted = True

    @property
    def is_full(self) -> bool:
        """Check if output buffer is full due to character limit."""
        return self._n_chars >= self.max_chars

    @property
    def n_chars(self) -> int:
        """Get current character count."""
        return self._n_chars

    @property
    def n_lines(self) -> int:
        """Get current line count."""
        return self._n_lines

    def write(self, text: str) -> int:
        """
        Write text to the output buffer.

        Returns:
            int: Number of characters actually written
        """
        # Capture the complete stream first (even past the truncation limit) so the
        # full output can be spilled to disk on truncation — bounded by
        # SPILL_MAX_CHARS so a runaway stream cannot exhaust memory.
        if self._full_buffer is not None and not self._spill_capped:
            self._full_buffer.append(text)
            self._full_chars += len(text)
            if self._full_chars >= SPILL_MAX_CHARS:
                self._spill_capped = True

        if self.is_full:
            return 0

        lines = text.splitlines(keepends=True)
        if not lines:
            return 0

        chars_written = 0

        for line in lines:
            if self.is_full:
                break

            original_line = line
            remaining_chars = self.max_chars - self._n_chars
            limit = (
                min(remaining_chars, self.max_line_length)
                if self.max_line_length is not None
                else remaining_chars
            )
            line = truncate_line(line, limit, self._marker)
            if line != original_line:
                self._truncation_happened = True

            self._buffer.append(line)
            chars_written += len(line)
            self._n_chars += len(line)
            if line.endswith("\n"):
                self._n_lines += 1

        return chars_written

    def tail(self, max_lines: int = 5, max_line_len: int = 200) -> str:
        """Return the last non-empty lines from the buffer, joined with newlines.

        Useful for surfacing actionable error context (stderr) in tool result briefs.
        """
        collected: list[str] = []
        for chunk in reversed(self._buffer):
            for line in reversed(chunk.splitlines()):
                stripped = line.rstrip()
                if not stripped.strip():
                    continue
                if len(stripped) > max_line_len:
                    stripped = stripped[:max_line_len] + "..."
                collected.append(stripped)
                if len(collected) >= max_lines:
                    break
            if len(collected) >= max_lines:
                break
        return "\n".join(reversed(collected))

    def display(self, *blocks: DisplayBlock) -> None:
        """Add display blocks to the tool result."""
        self._display.extend(blocks)

    def extras(self, **extras: JsonType) -> None:
        """Add extra data to the tool result."""
        if self._extras is None:
            self._extras = {}
        self._extras.update(extras)

    def _spill_and_hint(self) -> str | None:
        """Spill the full output to disk once and return a recovery hint, or None.

        Idempotent: if ``ok()`` and ``error()`` are both somehow called, the file
        is written only once and the same hint is returned. Returns None when
        spill is disabled or the write fails (fail-soft, so the caller falls back
        to the plain truncation message). The spilled file holds raw, untrusted
        output for direct analysis — a consumer (ReadFile/Grep/explore subagent)
        re-applies trust handling, so it is intentionally written unwrapped.
        """
        if self._spill_hint is not None:
            return self._spill_hint
        if self._full_buffer is None or self._spill_dir is None:
            return None
        try:
            full = "".join(self._full_buffer)
            self._spill_dir.mkdir(parents=True, exist_ok=True)
            # Full uuid (not a short prefix) so concurrent spills cannot collide
            # and silently overwrite each other; tool stem is pre-sanitized.
            path = self._spill_dir / f"{self._spill_tool}-{uuid.uuid4().hex}.txt"
            # Atomic write: a recovery ReadFile must never observe a partial file, and a
            # cancelled/abandoned worker thread (cancellation does not stop a thread) must
            # not leave one behind. Write to a sibling temp, then os.replace() — the final
            # path appears only once it is complete.
            tmp = path.parent / f"{path.name}.tmp"
            tmp.write_text(full, encoding="utf-8", errors="replace")
            os.replace(tmp, path)
        except Exception as exc:  # fail-soft: never let spill break the tool result
            from pythinker_code.utils.logging import logger

            logger.debug("Tool-output spill failed: {error}", error=exc)
            return None
        capped_note = (
            f" (note: the saved output was itself capped at {SPILL_MAX_CHARS} chars)"
            if self._spill_capped
            else ""
        )
        self._spill_hint = (
            f"Output truncated to fit context; the full output ({len(full)} chars) was saved to "
            f'{path}{capped_note}. Recover it with ReadFile(path="{path}", line_offset=1) or Grep '
            "the file. For large outputs, an explore subagent (Agent tool) can process the file "
            "without spending your own context."
        )
        return self._spill_hint

    async def spill_to_disk(self) -> None:
        """Perform the on-truncation spill off the event loop, before building the result.

        ``ok()``/``error()`` are synchronous and run on the event-loop thread, so the
        multi-MB ``_spill_and_hint`` write would block the loop. Async tools (Shell, web
        fetch/search) ``await`` this after writing their output so the disk write happens
        in a worker thread (``asyncio.to_thread``). It is idempotent and caches the hint,
        so the subsequent ``ok()``/``error()`` reuses it without writing again; if a tool
        forgets to call it, ``ok()`` still spills synchronously (correct, just blocking).
        """
        if self._spill_hint is not None or not self._truncation_happened:
            return
        if self._full_buffer is None or self._spill_dir is None:
            return
        await asyncio.to_thread(self._spill_and_hint)

    def _truncation_message(self) -> str:
        """The recovery hint when spilling, else the plain truncation notice."""
        return self._spill_and_hint() or "Output is truncated to fit in the message."

    def ok(
        self,
        message: str = "",
        *,
        brief: str = "",
        status: ToolResultStatus | str = ToolResultStatus.success,
    ) -> ToolReturnValue:
        """Create a ToolReturnValue with is_error=False and the current output."""
        output = "".join(self._buffer)
        if self._wrap_untrusted and output:
            output = UntrustedData(output).render_for_prompt()

        final_message = message
        if final_message and not final_message.endswith("."):
            final_message += "."
        if self._truncation_happened:
            truncation_msg = self._truncation_message()
            if final_message:
                final_message += f" {truncation_msg}"
            else:
                final_message = truncation_msg
        return ToolReturnValue(
            is_error=False,
            output=output,
            message=final_message,
            display=([BriefDisplayBlock(text=brief)] if brief else []) + self._display,
            extras={**(self._extras or {}), "status": tool_status_value(status)},
        )

    def error(
        self,
        message: str,
        *,
        brief: str,
        status: ToolResultStatus | str = ToolResultStatus.error,
    ) -> ToolReturnValue:
        """Create a ToolReturnValue with is_error=True and the current output."""
        output = "".join(self._buffer)
        if self._wrap_untrusted and output:
            output = UntrustedData(output).render_for_prompt()

        final_message = message
        if self._truncation_happened:
            truncation_msg = self._truncation_message()
            if final_message:
                final_message += f" {truncation_msg}"
            else:
                final_message = truncation_msg

        return ToolReturnValue(
            is_error=True,
            output=output,
            message=final_message,
            display=([BriefDisplayBlock(text=brief)] if brief else []) + self._display,
            extras={**(self._extras or {}), "status": tool_status_value(status)},
        )


def tool_error(
    message: str,
    *,
    brief: str,
    status: ToolResultStatus | str = ToolResultStatus.error,
    output: str = "",
) -> ToolReturnValue:
    return ToolReturnValue(
        is_error=True,
        output=output,
        message=message,
        display=[BriefDisplayBlock(text=brief)] if brief else [],
        extras={"status": tool_status_value(status)},
    )


class ToolRejectedError(ToolError):
    has_feedback: bool = False

    def __init__(
        self,
        message: str | None = None,
        brief: str = "Rejected by user",
        has_feedback: bool = False,
    ):
        super().__init__(
            message=message
            or (
                "The tool call is rejected by the user. "
                "Stop what you are doing and wait for the user to tell you how to proceed."
            ),
            brief=brief,
        )
        self.extras = {"status": ToolResultStatus.denied.value}
        self.has_feedback = has_feedback
