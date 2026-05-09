from __future__ import annotations

from collections.abc import Callable

from pythinker_code.ui.shell.selector import SelectorConfig, SelectorItem, run_selector


def _build_theme_config(
    current_theme: str,
    available_themes: list[str],
    on_preview: Callable[[str], None] | None = None,
) -> SelectorConfig[str]:
    return SelectorConfig(
        title="Select theme",
        items=[
            SelectorItem(value=theme, label=theme, is_current=(theme == current_theme))
            for theme in available_themes
        ],
        on_change=on_preview,
    )


async def run_theme_selector(
    current_theme: str,
    available_themes: list[str],
    on_preview: Callable[[str], None] | None = None,
) -> str | None:
    return await run_selector(_build_theme_config(current_theme, available_themes, on_preview))
