from rich import box

from pythinker_code.ui.shell.components.panel import brand_panel
from pythinker_code.ui.theme import set_active_theme


def test_brand_panel_is_rounded_and_uses_border_token():
    set_active_theme("dark")
    p = brand_panel("hello", title="Demo")
    assert p.box is box.ROUNDED
    # border style resolves to the slate border token
    assert "#3a506d" in str(p.border_style).lower()


def test_brand_panel_active_uses_accent_border():
    set_active_theme("dark")
    p = brand_panel("hi", active=True)
    # Active panels use the accent-family border_accent token (periwinkle).
    assert "#7c88de" in str(p.border_style).lower()
