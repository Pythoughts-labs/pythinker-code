"""Opt-in Pygments code-fence theme.

Default (``pythinker-ansi``) keeps today's terminal-adaptive, transparent look.
Setting ``config.tui.code_theme`` to a stock Pygments style renders assistant
code fences with that style on a solid dark background block, with zero change
to any other rendering.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from rich.console import Console

from pythinker_code.config import TUIConfig
from pythinker_code.ui.shell.components.markdown import PythinkerMarkdown
from pythinker_code.utils.rich.syntax import (
    PYTHINKER_ANSI_THEME,
    PYTHINKER_ANSI_THEME_NAME,
    get_active_code_theme,
    resolve_code_theme,
    set_active_code_theme,
)

# 24-bit background escape for Monokai's `#272822` (rgb 39,40,34).
_MONOKAI_BG = "48;2;39;40;34"
_FENCE = "```python\nimport os\n```\n"


@pytest.fixture(autouse=True)
def _restore_active_code_theme() -> Iterator[None]:
    """Keep the process-wide code theme from leaking between tests."""
    saved = get_active_code_theme()
    try:
        yield
    finally:
        set_active_code_theme(saved)


def _render_ansi(text: str, *, width: int = 60) -> str:
    console = Console(force_terminal=True, color_system="truecolor", width=width)
    with console.capture() as capture:
        console.print(PythinkerMarkdown(text))
    return capture.get()


def test_default_theme_keeps_transparent_ansi_look() -> None:
    set_active_code_theme(PYTHINKER_ANSI_THEME_NAME)
    output = _render_ansi(_FENCE)

    # No stock-style dark block; the ANSI theme carries no truecolor background.
    assert _MONOKAI_BG not in output
    assert "import" in output


def test_opt_in_stock_theme_paints_solid_dark_block() -> None:
    set_active_code_theme("monokai")
    output = _render_ansi(_FENCE)

    # Code fence now renders on Monokai's own background.
    assert _MONOKAI_BG in output
    assert "import" in output


def test_active_code_theme_round_trips() -> None:
    set_active_code_theme("dracula")
    assert get_active_code_theme() == "dracula"


def test_resolve_code_theme_maps_only_the_sentinel() -> None:
    # Sentinel resolves to the ANSI SyntaxTheme instance; stock names stay strings
    # (this string-vs-instance distinction is what the renderer branches on).
    assert resolve_code_theme(PYTHINKER_ANSI_THEME_NAME) is PYTHINKER_ANSI_THEME
    assert resolve_code_theme("monokai") == "monokai"


def test_tui_config_accepts_sentinel_and_stock_styles() -> None:
    assert TUIConfig().code_theme == PYTHINKER_ANSI_THEME_NAME
    assert TUIConfig(code_theme="monokai").code_theme == "monokai"
    # Case-insensitive convenience: a known style name is normalized to lower.
    assert TUIConfig(code_theme="Monokai").code_theme == "monokai"


def test_tui_config_rejects_unknown_code_theme() -> None:
    with pytest.raises(ValueError, match="Unknown code_theme"):
        TUIConfig(code_theme="definitely-not-a-real-style")
