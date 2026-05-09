"""Tests for the simple Tier-1 selectors.

All tests exercise config construction and _SelectorState behavior directly
— no TTY, no Application instantiation.
"""

from __future__ import annotations

from pythinker_code.ui.shell.selector import (
    SelectorItem,
    _SelectorState,  # type: ignore[reportPrivateUsage]
)


def _selected[T](state: _SelectorState[T]) -> SelectorItem[T]:
    item = state.visible[state.selected_idx]
    assert isinstance(item, SelectorItem)
    return item


# ---------------------------------------------------------------------------
# theme
# ---------------------------------------------------------------------------


def test_theme_selector_marks_current():
    from pythinker_code.ui.shell.selectors.theme import _build_theme_config

    config = _build_theme_config(
        current_theme="light",
        available_themes=["dark", "light", "auto"],
    )
    state = _SelectorState(config)
    selected = _selected(state)
    assert selected.value == "light"
    assert selected.is_current is True


def test_theme_selector_non_current_items_not_marked():
    from pythinker_code.ui.shell.selectors.theme import _build_theme_config

    config = _build_theme_config(
        current_theme="dark",
        available_themes=["dark", "light"],
    )
    assert not any(
        item.is_current
        for item in config.items
        if isinstance(item, SelectorItem) and item.value != "dark"
    )


def test_theme_selector_on_preview_wired_as_on_change():
    from pythinker_code.ui.shell.selectors.theme import _build_theme_config

    previews: list[str] = []
    callback = (
        previews.append
    )  # capture once — bound methods are not `is`-identical across accesses
    config = _build_theme_config(
        current_theme="dark",
        available_themes=["dark", "light"],
        on_preview=callback,
    )
    assert config.on_change is callback


# ---------------------------------------------------------------------------
# thinking
# ---------------------------------------------------------------------------


def test_thinking_selector_all_six_levels_have_descriptions():
    from pythinker_code.ui.shell.selectors.thinking import LEVEL_DESCRIPTIONS

    for level in ("off", "minimal", "low", "medium", "high", "xhigh"):
        assert level in LEVEL_DESCRIPTIONS
        assert LEVEL_DESCRIPTIONS[level]  # non-empty string


def test_thinking_selector_marks_current_level():
    from pythinker_code.ui.shell.selectors.thinking import _build_thinking_config

    config = _build_thinking_config(
        current_level="medium",
        available_levels=["off", "low", "medium", "high"],
    )
    state = _SelectorState(config)
    selected = _selected(state)
    assert selected.value == "medium"
    assert selected.is_current is True


def test_thinking_selector_description_populated():
    from pythinker_code.ui.shell.selectors.thinking import (
        LEVEL_DESCRIPTIONS,
        _build_thinking_config,
    )

    config = _build_thinking_config(
        current_level="off",
        available_levels=["off", "high"],
    )
    for item in config.items:
        if isinstance(item, SelectorItem):
            assert item.description == LEVEL_DESCRIPTIONS[item.value]


# ---------------------------------------------------------------------------
# show_images
# ---------------------------------------------------------------------------


def test_show_images_has_exactly_two_items():
    from pythinker_code.ui.shell.selectors.show_images import _build_show_images_config

    assert len(_build_show_images_config(current=True).items) == 2


def test_show_images_filter_disabled():
    from pythinker_code.ui.shell.selectors.show_images import _build_show_images_config

    assert _build_show_images_config(current=False).enable_filter is False


def test_show_images_marks_true_when_current_true():
    from pythinker_code.ui.shell.selectors.show_images import _build_show_images_config

    state = _SelectorState(_build_show_images_config(current=True))
    assert _selected(state).value is True


def test_show_images_marks_false_when_current_false():
    from pythinker_code.ui.shell.selectors.show_images import _build_show_images_config

    state = _SelectorState(_build_show_images_config(current=False))
    assert _selected(state).value is False


# ---------------------------------------------------------------------------
# extension
# ---------------------------------------------------------------------------


def test_extension_selector_items_match_options():
    from pythinker_code.ui.shell.selectors.extension import _build_extension_config

    config = _build_extension_config(title="Pick", options=["alpha", "beta", "gamma"])
    assert [item.value for item in config.items if isinstance(item, SelectorItem)] == [
        "alpha",
        "beta",
        "gamma",
    ]


def test_extension_selector_marks_current():
    from pythinker_code.ui.shell.selectors.extension import _build_extension_config

    state = _SelectorState(
        _build_extension_config(title="Pick", options=["a", "b", "c"], current="b")
    )
    assert _selected(state).value == "b"


def test_extension_selector_no_current_starts_at_first():
    from pythinker_code.ui.shell.selectors.extension import _build_extension_config

    state = _SelectorState(_build_extension_config(title="Pick", options=["x", "y"]))
    assert _selected(state).value == "x"


def test_extension_selector_timeout_returns_none(monkeypatch):
    import asyncio as _asyncio

    from pythinker_code.ui.shell.selectors.extension import run_extension_selector

    async def _raise_timeout(*args, **kwargs):
        raise TimeoutError

    monkeypatch.setattr(_asyncio, "wait_for", _raise_timeout)
    result = _asyncio.run(run_extension_selector("t", ["a"], timeout=0.001))
    assert result is None


# ---------------------------------------------------------------------------
# oauth
# ---------------------------------------------------------------------------


def test_oauth_selector_items_use_provider_name_as_label():
    from pythinker_code.ui.shell.selectors.oauth import (
        OAuthProviderEntry,
        OAuthProviderStatus,
        _build_oauth_config,
    )

    providers = [
        OAuthProviderEntry(id="openai", name="OpenAI", auth_type="oauth"),
        OAuthProviderEntry(id="anthropic", name="Anthropic", auth_type="api_key"),
    ]
    config = _build_oauth_config(
        providers,
        lambda _: OAuthProviderStatus(source="unconfigured"),
        action="login",
    )
    assert config.items[0].label == "OpenAI"
    assert config.items[1].label == "Anthropic"


def test_oauth_selector_status_configured():
    from pythinker_code.ui.shell.selectors.oauth import (
        OAuthProviderStatus,
        _format_status_indicator,
    )

    assert "✓" in _format_status_indicator(OAuthProviderStatus(source="configured"))


def test_oauth_selector_status_unconfigured():
    from pythinker_code.ui.shell.selectors.oauth import (
        OAuthProviderStatus,
        _format_status_indicator,
    )

    assert "•" in _format_status_indicator(OAuthProviderStatus(source="unconfigured"))


def test_oauth_selector_status_environment():
    from pythinker_code.ui.shell.selectors.oauth import (
        OAuthProviderStatus,
        _format_status_indicator,
    )

    indicator = _format_status_indicator(OAuthProviderStatus(source="environment", label="API key"))
    assert "✓" in indicator
    assert "env" in indicator


def test_oauth_selector_login_title():
    from pythinker_code.ui.shell.selectors.oauth import (
        OAuthProviderEntry,
        OAuthProviderStatus,
        _build_oauth_config,
    )

    config = _build_oauth_config(
        [OAuthProviderEntry(id="x", name="X", auth_type="api_key")],
        lambda _: OAuthProviderStatus(source="unconfigured"),
        action="login",
    )
    assert "log in" in config.title.lower() or "login" in config.title.lower()


def test_oauth_selector_logout_title():
    from pythinker_code.ui.shell.selectors.oauth import (
        OAuthProviderEntry,
        OAuthProviderStatus,
        _build_oauth_config,
    )

    config = _build_oauth_config(
        [OAuthProviderEntry(id="x", name="X", auth_type="api_key")],
        lambda _: OAuthProviderStatus(source="unconfigured"),
        action="logout",
    )
    assert "log out" in config.title.lower() or "logout" in config.title.lower()
