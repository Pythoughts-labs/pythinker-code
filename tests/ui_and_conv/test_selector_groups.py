"""Tests for SelectorHeader sentinel in the selector framework."""

from __future__ import annotations

from pythinker_code.ui.shell.selector import (
    SelectorConfig,
    SelectorHeader,  # type: ignore[reportPrivateUsage]
    SelectorItem,
    _SelectorState,  # type: ignore[reportPrivateUsage]
)


def _make_grouped_state(*, enable_filter: bool = False) -> _SelectorState[str]:
    items = [
        SelectorHeader(label="Group A"),
        SelectorItem(value="a1", label="a1"),
        SelectorItem(value="a2", label="a2"),
        SelectorHeader(label="Group B"),
        SelectorItem(value="b1", label="b1"),
    ]
    return _SelectorState(SelectorConfig(title="test", items=items, enable_filter=enable_filter))


def test_headers_appear_in_visible_when_no_filter():
    state = _make_grouped_state()
    assert len(state.visible) == 5
    assert isinstance(state.visible[0], SelectorHeader)
    assert isinstance(state.visible[3], SelectorHeader)


def test_initial_selection_is_first_selector_item_not_header():
    state = _make_grouped_state()
    assert isinstance(state.visible[state.selected_idx], SelectorItem)
    assert state.visible[state.selected_idx].value == "a1"


def test_move_down_skips_header():
    state = _make_grouped_state()
    state.move(1)
    assert state.visible[state.selected_idx].value == "a2"
    state.move(1)
    assert state.visible[state.selected_idx].value == "b1"


def test_move_up_wraps_from_first_to_last_item():
    state = _make_grouped_state()
    state.move(-1)
    assert state.visible[state.selected_idx].value == "b1"


def test_move_wraps_from_last_to_first_item():
    state = _make_grouped_state()
    state.move(-1)  # a1 -> b1 (wrap)
    state.move(1)  # b1 -> a1 (wrap)
    assert state.visible[state.selected_idx].value == "a1"


def test_headers_hidden_during_filtering():
    state = _make_grouped_state(enable_filter=True)
    state.append_filter("a")
    assert all(isinstance(item, SelectorItem) for item in state.visible)
    assert {item.value for item in state.visible} == {"a1", "a2"}


def test_commit_returns_selected_item_value():
    state = _make_grouped_state()
    assert state.commit()
    assert state.result == "a1"


def test_on_change_fires_when_cursor_moves():
    called: list[str] = []
    items = [
        SelectorItem(value="x", label="x"),
        SelectorItem(value="y", label="y"),
        SelectorItem(value="z", label="z"),
    ]
    config = SelectorConfig(title="t", items=items, on_change=called.append)
    state = _SelectorState(config)
    state.move(1)
    assert called == ["y"]
    state.move(1)
    assert called == ["y", "z"]


def test_on_change_does_not_fire_when_selection_unchanged():
    called: list[str] = []
    items = [SelectorItem(value="only", label="only")]
    config = SelectorConfig(title="t", items=items, on_change=called.append)
    state = _SelectorState(config)
    state.move(1)  # wraps to same item — no change
    assert called == []


def test_on_change_none_by_default_no_error():
    items = [SelectorItem(value="a", label="a"), SelectorItem(value="b", label="b")]
    config = SelectorConfig(title="t", items=items)
    assert config.on_change is None
    state = _SelectorState(config)
    state.move(1)  # must not raise
