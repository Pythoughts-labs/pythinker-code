"""Regression test for the `/login` `redraw_in_future` coroutine warning.

Root cause: setting `Application.min_redraw_interval` activates prompt_toolkit's
*coroutine-based* throttle path in `invalidate()` (`async def redraw_in_future`).
If `invalidate()` fires during an app/loop handoff (as happens when `/login`
swaps prompt sessions), that coroutine is constructed and then dropped
un-awaited -> `RuntimeWarning: coroutine '...redraw_in_future' was never awaited`.

`max_render_postpone_time` throttles redraws via a coroutine-free path
(`call_soon_threadsafe` only). It never constructs the coroutine, so the
"never awaited" warning is *impossible* on that path — proof by elimination
rather than by racing the garbage collector.

The tests poke prompt_toolkit internals on purpose: this bug lives exactly at
that boundary, so the regression guard has to exercise it there.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from prompt_toolkit.application import Application


async def _invalidate_constructs_coroutine(configure: Callable[[Application], None]) -> bool:
    """Return True iff `invalidate()` constructs a `redraw_in_future` coroutine.

    The coroutine is the *only* thing that can leak the warning, so whether it is
    constructed at all is the deterministic signal for the root cause.
    """
    app: Application = Application()
    app._is_running = True
    app.loop = asyncio.get_running_loop()
    app._invalidated = False
    app._redraw = lambda render_as_done=True: None  # keep the redraw path quiet
    # Force the throttle to engage: pretend we just redrew, so the next
    # invalidate falls inside the throttle window.
    app._last_redraw_time = time.time()
    configure(app)

    constructed: list[object] = []

    def spy(coro: object) -> None:
        constructed.append(coro)
        coro.close()  # consume it so the test itself never leaks a coroutine

    app.create_background_task = spy  # type: ignore[assignment, method-assign]

    app.invalidate()
    await asyncio.sleep(0.02)  # let the call_soon_threadsafe callback fire
    return bool(constructed)


async def test_min_redraw_interval_constructs_redraw_coroutine() -> None:
    """Documents the buggy path: min_redraw_interval builds the leak-prone coroutine."""

    def configure(app: Application) -> None:
        app.min_redraw_interval = 10  # large window guarantees the coroutine path

    assert await _invalidate_constructs_coroutine(configure), (
        "expected min_redraw_interval to construct redraw_in_future (the leak source)"
    )


async def test_max_render_postpone_time_constructs_no_coroutine() -> None:
    """The fix path: max_render_postpone_time never constructs the coroutine."""

    def configure(app: Application) -> None:
        app.max_render_postpone_time = 1 / 30

    assert not await _invalidate_constructs_coroutine(configure), (
        "max_render_postpone_time must not construct redraw_in_future; "
        "no coroutine means the 'never awaited' warning is impossible"
    )
