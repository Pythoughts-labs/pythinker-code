from __future__ import annotations

import asyncio

from pythinker_code.ui.shell.selector import SelectorConfig, SelectorItem, run_selector


def _build_extension_config(
    title: str,
    options: list[str],
    *,
    current: str | None = None,
) -> SelectorConfig[str]:
    return SelectorConfig(
        title=title,
        items=[SelectorItem(value=opt, label=opt, is_current=(opt == current)) for opt in options],
    )


async def run_extension_selector(
    title: str,
    options: list[str],
    *,
    current: str | None = None,
    timeout: float | None = None,
) -> str | None:
    coro = run_selector(_build_extension_config(title, options, current=current))
    if timeout is not None:
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError:
            # Real ``asyncio.wait_for`` cancels/awaits the coroutine on timeout;
            # tests may monkeypatch it to raise directly, so close the coroutine
            # here to avoid an un-awaited-coroutine warning.
            coro.close()
            return None
    return await coro
