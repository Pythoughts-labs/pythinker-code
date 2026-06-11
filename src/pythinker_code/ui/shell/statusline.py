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
        self._interval_s = max(
            interval_s if interval_s is not None else self._timeout_s,
            _MIN_REFRESH_INTERVAL_S if interval_s is None else interval_s,
        )
        self._task: asyncio.Task[None] | None = None
        self._warned = False
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

    async def stop(self) -> None:
        if self._task is None:
            return
        task = self._task
        self.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _refresh_loop(self) -> None:
        while True:
            await self.refresh_once()
            await asyncio.sleep(self._interval_s)

    async def refresh_once(self) -> None:
        """Run the command once and cache its first stdout line (or '')."""
        self.current_line = await self._run_command()

    async def _run_command(self) -> str:
        if not self._argv:
            self._warn_once("status command is empty or unparseable")
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
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), self._timeout_s)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            self._warn_once("status command timed out")
            return ""
        if proc.returncode != 0:
            self._warn_once(f"status command exited with {proc.returncode}")
            return ""
        first_line = stdout.decode("utf-8", errors="replace").split("\n", 1)[0].strip()
        return first_line[:_MAX_COMMAND_LINE_CHARS]

    def _warn_once(self, message: str) -> None:
        if not self._warned:
            self._warned = True
            logger.warning("statusline: {} (argv={})", message, self._argv)
