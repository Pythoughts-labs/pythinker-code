"""Tests for the TUI style resolver and the Config.tui section."""

from __future__ import annotations

import pytest

from pythinker_code.config import Config, TUIConfig
from pythinker_code.ui.tui_config import get_tui_style, is_card_style


@pytest.fixture
def _clear_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PYTHINKER_TUI_STYLE", raising=False)
    yield monkeypatch


def test_default_is_pythinker(_clear_env: pytest.MonkeyPatch):
    assert get_tui_style() == "pythinker"
    assert is_card_style() is False


def test_configured_card(_clear_env: pytest.MonkeyPatch):
    assert get_tui_style("card") == "card"
    assert is_card_style("card") is True


def test_legacy_pi_value_aliases_to_card(_clear_env: pytest.MonkeyPatch):
    """Older configs / env vars set to 'pi' transparently map to 'card'."""
    assert get_tui_style("pi") == "card"
    assert is_card_style("pi") is True


def test_env_overrides_config(_clear_env: pytest.MonkeyPatch):
    _clear_env.setenv("PYTHINKER_TUI_STYLE", "card")
    assert get_tui_style("pythinker") == "card"


def test_env_pythinker_overrides_config_card(_clear_env: pytest.MonkeyPatch):
    _clear_env.setenv("PYTHINKER_TUI_STYLE", "pythinker")
    assert get_tui_style("card") == "pythinker"


def test_invalid_env_falls_through(_clear_env: pytest.MonkeyPatch):
    _clear_env.setenv("PYTHINKER_TUI_STYLE", "garbage")
    # Falls through to configured, then to default.
    assert get_tui_style() == "pythinker"
    assert get_tui_style("card") == "card"


def test_invalid_configured_falls_through_to_default(_clear_env: pytest.MonkeyPatch):
    assert get_tui_style("not-a-style") == "pythinker"


def test_env_is_case_insensitive(_clear_env: pytest.MonkeyPatch):
    _clear_env.setenv("PYTHINKER_TUI_STYLE", "CARD")
    assert get_tui_style() == "card"


def test_config_has_tui_section_with_default():
    cfg = Config()
    assert isinstance(cfg.tui, TUIConfig)
    assert cfg.tui.style == "pythinker"


def test_config_accepts_card_style():
    cfg = Config(tui=TUIConfig(style="card"))
    assert cfg.tui.style == "card"
    assert get_tui_style(cfg.tui.style) == "card"


def test_active_style_global_is_used_when_no_args(_clear_env: pytest.MonkeyPatch):
    """set_active_tui_style controls get_tui_style() with no arguments —
    this is what the shell startup hook uses."""
    from pythinker_code.ui.tui_config import (
        get_active_tui_style,
        set_active_tui_style,
    )

    original = get_active_tui_style()
    try:
        set_active_tui_style("card")
        assert get_tui_style() == "card"
        assert get_active_tui_style() == "card"
        # Env still wins over the global.
        _clear_env.setenv("PYTHINKER_TUI_STYLE", "pythinker")
        assert get_tui_style() == "pythinker"
    finally:
        set_active_tui_style(original)


def test_active_style_invalid_value_falls_back_to_pythinker(
    _clear_env: pytest.MonkeyPatch,
):
    from pythinker_code.ui.tui_config import (
        get_active_tui_style,
        set_active_tui_style,
    )

    original = get_active_tui_style()
    try:
        set_active_tui_style("garbage")
        assert get_active_tui_style() == "pythinker"
    finally:
        set_active_tui_style(original)
