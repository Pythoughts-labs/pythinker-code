"""Status line segment resolution and the external status command runner.

Kept separate from ``prompt.py`` so the footer customization logic stays small,
pure, and independently testable. The render paths in ``prompt.py`` consult
``resolve_segments`` and read ``StatusLineCommandRunner.current_line`` — they
never run subprocesses themselves (the toolbar re-renders on every keystroke).
"""

from __future__ import annotations

import asyncio
import contextlib
import shlex
from dataclasses import dataclass, field

from pythinker_code.config import StatusLineConfig
from pythinker_code.ui.shell.components import sanitize_ansi
from pythinker_code.utils.logging import logger

DEFAULT_STATUSLINE_SEGMENTS: tuple[str, ...] = (
    "cwd",
    "git",
    "flags",
    "context",
    "tokens",
    "model",
)

_LINE1_SEGMENTS: frozenset[str] = frozenset({"cwd", "git", "flags"})
_LINE2_RIGHT_SEGMENTS: frozenset[str] = frozenset({"context", "tokens", "model"})

_MAX_COMMAND_LINE_CHARS = 200
_MIN_REFRESH_INTERVAL_S = 0.5
# Floor for explicitly-passed intervals: keeps tests fast while preventing a
# zero/negative interval from busy-looping subprocess spawns.
_MIN_EXPLICIT_INTERVAL_S = 0.01
_MAX_COMMAND_OUTPUT_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class StatusLineLayout:
    """Which footer segments to render, split by footer zone."""

    line1: list[str] = field(default_factory=list[str])
    line2_right: list[str] = field(default_factory=list[str])
    show_command: bool = False


def resolve_segments(cfg: StatusLineConfig) -> StatusLineLayout:
    """Map a :class:`StatusLineConfig` to the footer zones.

    When customization is disabled the stock layout is returned so render
    paths behave exactly as before. The ``command`` segment only shows when an
    external command is actually configured.
    """
    segments = list(DEFAULT_STATUSLINE_SEGMENTS) if not cfg.enabled else list(cfg.segments)
    show_command = cfg.enabled and "command" in segments and bool(cfg.command)
    return StatusLineLayout(
        line1=[s for s in segments if s in _LINE1_SEGMENTS],
        line2_right=[s for s in segments if s in _LINE2_RIGHT_SEGMENTS],
        show_command=show_command,
    )


class StatusLineCommandRunner:
    """Runs the user's status command on a cadence and caches one line.

    Fails closed: any timeout, non-zero exit, spawn failure, or empty output
    leaves :attr:`current_line` empty so the footer simply omits the segment.
    The refresh task has an explicit lifecycle (``start``/``stop``) and is
    cancelled cleanly when the prompt session shuts down.
    """

    def __init__(self, command: str, timeout_ms: int, interval_s: float | None = None):
        self._argv = self._parse_argv(command)
        self._timeout_s = max(timeout_ms, 1) / 1000
        if interval_s is None:
            self._interval_s = max(self._timeout_s, _MIN_REFRESH_INTERVAL_S)
        else:
            self._interval_s = max(interval_s, _MIN_EXPLICIT_INTERVAL_S)
        self._task: asyncio.Task[None] | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._warned: set[str] = set()
        self.current_line: str = ""

    @staticmethod
    def _parse_argv(command: str) -> list[str]:
        try:
            return shlex.split(command)
        except ValueError:
            return []

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running:
            return
        self._task = asyncio.get_running_loop().create_task(self._refresh_loop())

    def cancel(self) -> None:
        """Synchronous fire-and-forget cancellation (for sync shutdown paths)."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None
        # Sync shutdown may never re-enter the event loop, so the
        # CancelledError handler in _run_command can't kill the child —
        # do it here as well to avoid orphaning the user's command.
        proc = self._proc
        if proc is not None and proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()

    async def stop(self) -> None:
        if self._task is None:
            return
        task = self._task
        self.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _refresh_loop(self) -> None:
        while True:
            try:
                await self.refresh_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # One bad refresh must not silently kill the loop — the
                # footer would freeze with no indication of failure.
                logger.exception("statusline: refresh failed (argv={})", self._argv)
                self.current_line = ""
            await asyncio.sleep(self._interval_s)

    async def refresh_once(self) -> None:
        """Run the command once and cache its first stdout line (or '')."""
        self.current_line = await self._run_command()

    async def _run_command(self) -> str:
        if not self._argv:
            self._warn_once("status command is empty or unparsable")
            return ""
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                stdin=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            self._warn_once(f"status command failed to start: {exc}")
            return ""
        self._proc = proc
        capped = False
        try:
            assert proc.stdout is not None
            # Bounded read instead of communicate(): a command that streams
            # endlessly can't grow the buffer past the cap. We only need the
            # first line anyway.
            stdout = await asyncio.wait_for(
                proc.stdout.read(_MAX_COMMAND_OUTPUT_BYTES), self._timeout_s
            )
            capped = len(stdout) >= _MAX_COMMAND_OUTPUT_BYTES
            if capped:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
            with contextlib.suppress(ProcessLookupError):
                await asyncio.wait_for(proc.wait(), self._timeout_s)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
                await proc.wait()
            self._warn_once("status command timed out")
            return ""
        except asyncio.CancelledError:
            # Session shutdown cancels the refresh task mid-read();
            # without this the user's command keeps running as an orphan.
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
                await proc.wait()
            raise
        finally:
            self._proc = None
        if proc.returncode != 0 and not capped:
            self._warn_once(f"status command exited with {proc.returncode}")
            return ""
        first_line = stdout.decode("utf-8", errors="replace").split("\n", 1)[0].strip()
        return sanitize_ansi(first_line)[:_MAX_COMMAND_LINE_CHARS]

    def _warn_once(self, message: str) -> None:
        """Log each distinct failure once so changing errors stay visible
        without spamming the log on every refresh."""
        if message not in self._warned:
            self._warned.add(message)
            logger.warning("statusline: {} (argv={})", message, self._argv)
