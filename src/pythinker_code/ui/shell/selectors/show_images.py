from __future__ import annotations

from pythinker_code.ui.shell.selector import SelectorConfig, SelectorItem, run_selector


def _build_show_images_config(current: bool) -> SelectorConfig[bool]:
    return SelectorConfig(
        title="Show images in responses?",
        items=[
            SelectorItem(
                value=True,
                label="Yes",
                description="Show images inline in terminal",
                is_current=current,
            ),
            SelectorItem(
                value=False,
                label="No",
                description="Show text placeholder instead",
                is_current=not current,
            ),
        ],
        enable_filter=False,
        hint="↑↓ navigate · Enter select · Esc cancel",
    )


async def run_show_images_selector(current: bool) -> bool | None:
    return await run_selector(_build_show_images_config(current))
