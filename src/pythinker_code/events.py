"""In-process event bus.

 . A
minimal pub/sub primitive that extension/plugin code can use to broadcast
state changes (assistant message, tool call started/ended, model changed,
etc.) without holding direct references to listeners.

Handlers may be sync or async. Async handlers are scheduled on the running
event loop; if no loop is running they're executed via ``asyncio.run``
(useful in tests). Exceptions in any handler are logged and swallowed so a
broken extension can't take down the host.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

from pythinker_code.utils.logging import logger

__all__ = [
    "EventBus",
    "EventHandler",
    "create_event_bus",
]


EventHandler = Callable[[Any], Any]


class EventBus:
    """Channel-keyed pub/sub.

    Use :func:`create_event_bus` rather than constructing directly — that
    keeps the constructor signature private and matches Pythinker's factory.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def emit(self, channel: str, data: Any = None) -> None:
        """Fire *data* on *channel*. Handlers run sequentially; failures log."""
        for handler in list(self._handlers.get(channel, ())):
            self._dispatch(channel, handler, data)

    def on(self, channel: str, handler: EventHandler) -> Callable[[], None]:
        """Subscribe *handler* to *channel*. Returns an unsubscribe fn."""
        self._handlers.setdefault(channel, []).append(handler)

        def _off() -> None:
            handlers = self._handlers.get(channel)
            if not handlers:
                return
            try:
                handlers.remove(handler)
            except ValueError:
                return
            if not handlers:
                self._handlers.pop(channel, None)

        return _off

    def clear(self) -> None:
        """Remove every handler on every channel. Intended for tests."""
        self._handlers.clear()

    # ----------------------------------------------------------------------

    def _dispatch(self, channel: str, handler: EventHandler, data: Any) -> None:
        try:
            result = handler(data)
        except Exception:  # noqa: BLE001 — extension must not crash host
            logger.exception("Event handler error on channel '{channel}'", channel=channel)
            return
        if inspect.iscoroutine(result):
            self._schedule_coro(channel, result)

    @staticmethod
    def _schedule_coro(channel: str, coro: Any) -> None:
        async def _runner() -> None:
            try:
                await coro
            except Exception:  # noqa: BLE001
                logger.exception("Async event handler error on '{channel}'", channel=channel)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — execute inline. Mostly hit in tests.
            try:
                asyncio.run(_runner())
            except Exception:  # noqa: BLE001
                logger.exception("Failed to run async handler for '{channel}'", channel=channel)
            return
        loop.create_task(_runner())


def create_event_bus() -> EventBus:
    """Factory mirroring the ``createEventBus()``."""
    return EventBus()
