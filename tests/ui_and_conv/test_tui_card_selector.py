"""Tests for the selector framework.

Selector exposes a public ``run_selector`` async function that drives a
prompt_toolkit Application. We test the underlying state machine
directly — the prompt_toolkit layer is glue, and exercising it requires a
TTY which pytest doesn't have.
"""

from __future__ import annotations

from prompt_toolkit.formatted_text import StyleAndTextTuples

from pythinker_code.ui.shell.selector import (
    SelectorConfig,
    SelectorItem,
    _format_item_line,  # type: ignore[reportPrivateUsage]
    _SelectorState,  # type: ignore[reportPrivateUsage]
)


def _plain(fragments: StyleAndTextTuples) -> str:
    return "".join(fragment[1] for fragment in fragments)


def _make_state(items: list[SelectorItem[str]], *, enable_filter: bool = True):
    return _SelectorState(
        SelectorConfig(title="Pick one", items=items, enable_filter=enable_filter)
    )


def _selected(state: _SelectorState[str]) -> SelectorItem[str]:
    item = state.visible[state.selected_idx]
    assert isinstance(item, SelectorItem)
    return item


def _values(state: _SelectorState[str]) -> list[str]:
    return [item.value for item in state.visible if isinstance(item, SelectorItem)]


def test_initial_state_picks_current_item():
    state = _make_state(
        [
            SelectorItem(value="a", label="A"),
            SelectorItem(value="b", label="B", is_current=True),
            SelectorItem(value="c", label="C"),
        ]
    )
    assert state.selected_idx == 1
    assert _selected(state).value == "b"


def test_initial_state_falls_back_to_first_when_no_current():
    state = _make_state(
        [
            SelectorItem(value="a", label="A"),
            SelectorItem(value="b", label="B"),
        ]
    )
    assert state.selected_idx == 0


def test_move_wraps_around():
    state = _make_state(
        [
            SelectorItem(value="a", label="A"),
            SelectorItem(value="b", label="B"),
        ]
    )
    state.move(1)
    assert state.selected_idx == 1
    state.move(1)
    assert state.selected_idx == 0
    state.move(-1)
    assert state.selected_idx == 1


def test_filter_narrows_visible_items():
    state = _make_state(
        [
            SelectorItem(value="a", label="alpha"),
            SelectorItem(value="b", label="beta"),
            SelectorItem(value="c", label="gamma"),
        ]
    )
    state.append_filter("a")
    # alpha + beta + gamma all contain 'a'
    assert set(_values(state)) == {"a", "b", "c"}
    state.append_filter("l")
    # only alpha contains 'al'
    assert _values(state) == ["a"]


def test_filter_matches_description_too():
    state = _make_state(
        [
            SelectorItem(value="a", label="A", description="quick lookup"),
            SelectorItem(value="b", label="B", description="batch run"),
        ]
    )
    state.append_filter("batch")
    assert _values(state) == ["b"]


def test_backspace_widens_filter():
    state = _make_state(
        [
            SelectorItem(value="a", label="alpha"),
            SelectorItem(value="b", label="beta"),
        ]
    )
    state.append_filter("a")
    state.append_filter("l")
    assert _values(state) == ["a"]
    state.backspace_filter()
    # Both back in view.
    assert set(_values(state)) == {"a", "b"}


def test_clear_filter_resets_to_all():
    state = _make_state(
        [
            SelectorItem(value="a", label="alpha"),
            SelectorItem(value="b", label="beta"),
        ]
    )
    state.append_filter("be")
    assert len(state.visible) == 1
    state.clear_filter()
    assert len(state.visible) == 2


def test_filter_preserves_selected_value_across_edits():
    state = _make_state(
        [
            SelectorItem(value="a", label="alpha"),
            SelectorItem(value="b", label="beta"),
            SelectorItem(value="c", label="ample"),
        ]
    )
    state.move(1)  # select beta
    assert _selected(state).value == "b"
    state.append_filter("a")  # all three still match
    # beta still selected.
    assert _selected(state).value == "b"


def test_commit_returns_false_for_empty_visible():
    state = _make_state([SelectorItem(value="a", label="alpha")])
    state.append_filter("nope")
    assert state.commit() is False
    assert state.result is None


def test_commit_sets_result():
    state = _make_state(
        [
            SelectorItem(value="a", label="A"),
            SelectorItem(value="b", label="B"),
        ]
    )
    state.move(1)
    assert state.commit() is True
    assert state.result == "b"


def test_format_item_line_marks_selected_with_arrow():
    line = _format_item_line(
        SelectorItem(value="a", label="alpha", description="first"),
        is_selected=True,
        width=40,
    )
    flat = _plain(line)
    assert "❯" in flat
    assert "alpha" in flat
    assert "first" in flat


def test_format_item_line_includes_current_marker():
    line = _format_item_line(
        SelectorItem(value="a", label="alpha", is_current=True),
        is_selected=False,
        width=40,
    )
    flat = _plain(line)
    assert "(current)" in flat
