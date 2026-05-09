"""Tests for the in-process event bus."""

from __future__ import annotations

import asyncio
from typing import Any

from pythinker_code.events import create_event_bus


def test_emit_and_handle_sync():
    bus = create_event_bus()
    received: list[Any] = []
    bus.on("ping", received.append)
    bus.emit("ping", "hello")
    bus.emit("ping", "world")
    assert received == ["hello", "world"]


def test_unsubscribe_removes_handler():
    bus = create_event_bus()
    received: list[Any] = []
    off = bus.on("ping", received.append)
    bus.emit("ping", 1)
    off()
    bus.emit("ping", 2)
    assert received == [1]
    # idempotent
    off()


def test_emit_to_unknown_channel_is_noop():
    bus = create_event_bus()
    bus.emit("nobody-listens", 1)


def test_handler_exception_does_not_break_others():
    bus = create_event_bus()
    received: list[Any] = []

    def bad(_data: Any) -> None:
        raise RuntimeError("boom")

    bus.on("ev", bad)
    bus.on("ev", received.append)
    bus.emit("ev", "still ok")
    assert received == ["still ok"]


def test_clear_drops_all():
    bus = create_event_bus()
    received: list[Any] = []
    bus.on("a", received.append)
    bus.on("b", received.append)
    bus.clear()
    bus.emit("a", 1)
    bus.emit("b", 2)
    assert received == []


def test_async_handler_inside_running_loop():
    bus = create_event_bus()
    received: list[Any] = []

    async def handler(data: Any) -> None:
        await asyncio.sleep(0)
        received.append(data)

    async def driver() -> None:
        bus.on("async", handler)
        bus.emit("async", "x")
        # Yield so the scheduled task can run.
        await asyncio.sleep(0)

    asyncio.run(driver())
    assert received == ["x"]
