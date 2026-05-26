"""Reusable selector framework for Pythinker.

Provides a generic, prompt_toolkit-backed selector that mirrors the shape of
the existing :mod:`pythinker_code.ui.shell.model_picker` but works on any
list of items. Specific dialogs (theme, thinking, settings, oauth-provider)
build on this so they all share the same key bindings, search filter
behavior, header/footer chrome, and theme tokens.

Why a new framework rather than reuse ``prompt_toolkit.shortcuts.choice_input``?

* ChoiceInput doesn't support type-to-filter, which we want for any
  selector with > 5 items.
* It doesn't theme via Pythinker's :func:`get_prompt_style` palette so the
  visual treatment drifts from the rest of the shell.
* It doesn't expose a header line for explanatory text or a hint footer.

Public API:

* :class:`SelectorItem` — one row.
* :class:`SelectorConfig` — title + items + optional preselection / hint.
* :func:`run_selector` — async; returns the selected value or ``None``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app_or_none
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension

from pythinker_code.ui.shell.components.render_utils import cell_width, truncate_to_width
from pythinker_code.ui.shell.glyphs import TRANSCRIPT_PROMPT_MARKER
from pythinker_code.ui.theme import get_prompt_style, get_toolbar_colors

__all__ = [
    "SelectorConfig",
    "SelectorHeader",
    "SelectorItem",
    "run_selector",
]


@dataclass(frozen=True, slots=True)
class SelectorItem[T]:
    """A row in a selector.

    Attributes:
        value: Returned by :func:`run_selector` when this item is chosen.
        label: Bold primary column, e.g. ``"dark"`` or ``"claude-opus-4-7"``.
        description: Optional muted secondary column shown to the right.
        is_current: Marks the item as the active selection — pre-selected
            on open and labelled ``(current)`` in the description.
    """

    value: T
    label: str
    description: str = ""
    is_current: bool = False


@dataclass(frozen=True, slots=True)
class SelectorHeader:
    """A non-selectable divider row in a selector."""

    label: str


@dataclass(frozen=True, slots=True)
class SelectorConfig[T]:
    """Static configuration for a selector dialog."""

    title: str
    items: Sequence[SelectorItem[T] | SelectorHeader]
    """Source rows. May be empty — the selector will show a placeholder."""

    hint: str = "↑↓ navigate · Enter select · Esc cancel · type to filter"
    """Footer shown below the item list."""

    enable_filter: bool = True
    """When False, type-to-filter is disabled (useful for tiny selectors)."""

    max_visible: int = 12
    """Maximum selectable/list rows rendered before the list scrolls."""

    on_change: Callable[[T], None] | None = None
    """Called whenever the cursor moves to a different SelectorItem."""


def _format_item_line[T](
    item: SelectorItem[T],
    *,
    is_selected: bool,
    width: int,
) -> StyleAndTextTuples:
    """One row in the selector — marker + label + description.

    Reuses the same ``slash-completion-menu`` style classes as the prompt's
    completion menu so the visual treatment is consistent.
    """
    marker = f"{TRANSCRIPT_PROMPT_MARKER} " if is_selected else "  "
    marker_style = (
        "class:slash-completion-menu.marker.current"
        if is_selected
        else "class:slash-completion-menu.marker"
    )
    label_style = (
        "class:slash-completion-menu.command.current"
        if is_selected
        else "class:slash-completion-menu.command"
    )
    meta_style = (
        "class:slash-completion-menu.meta.current"
        if is_selected
        else "class:slash-completion-menu.meta"
    )
    row_bg = (
        "class:slash-completion-menu.row.current" if is_selected else "class:slash-completion-menu"
    )

    desc_parts: list[str] = []
    if item.is_current:
        desc_parts.append("(current)")
    if item.description:
        desc_parts.append(item.description)
    description = " ".join(desc_parts)

    gap = "  "
    min_desc_width = 10 if description else 0
    marker_width = cell_width(marker)
    gap_width = cell_width(gap)
    label_budget = max(1, width - marker_width - gap_width - min_desc_width)
    label = truncate_to_width(item.label, label_budget)
    remaining = max(0, width - marker_width - cell_width(label) - gap_width)
    description = truncate_to_width(description, remaining, ellipsis="")
    pad = max(0, width - marker_width - cell_width(label) - gap_width - cell_width(description))
    return [
        (marker_style, marker),
        (label_style, label),
        (row_bg, gap),
        (meta_style, description),
        (row_bg, " " * pad),
        ("", "\n"),
    ]


class _SelectorState[T]:
    """Internal state for the selector application."""

    def __init__(self, config: SelectorConfig[T]) -> None:
        self.config = config
        self.filter = ""
        self.selected_idx = 0
        self.visible: list[SelectorItem[T] | SelectorHeader] = []
        self.result: T | None = None
        self.cancelled = False
        self._refilter(initial=True)

    @staticmethod
    def _fuzzy_match(needle: str, haystack: str) -> bool:
        if not needle:
            return True
        pos = 0
        for ch in needle.lower():
            found = haystack.find(ch, pos)
            if found < 0:
                return False
            pos = found + 1
        return True

    def _matches(self, item: SelectorItem[T]) -> bool:
        if not self.filter:
            return True
        haystack = f"{item.label} {item.description}".lower()
        return self._fuzzy_match(self.filter, haystack)

    def _selectable_indices(self) -> list[int]:
        return [i for i, item in enumerate(self.visible) if isinstance(item, SelectorItem)]

    def _refilter(self, *, initial: bool = False) -> None:
        previous_value: T | None = None
        if not initial and self.visible and 0 <= self.selected_idx < len(self.visible):
            current = self.visible[self.selected_idx]
            if isinstance(current, SelectorItem):
                previous_value = current.value

        if not self.filter:
            self.visible = list(self.config.items)
        else:
            self.visible = [
                item
                for item in self.config.items
                if isinstance(item, SelectorItem) and self._matches(item)
            ]

        selectable = self._selectable_indices()
        if not selectable:
            self.selected_idx = 0
            return

        if previous_value is not None:
            for i, item in enumerate(self.visible):
                if isinstance(item, SelectorItem) and item.value == previous_value:
                    self.selected_idx = i
                    return

        if initial:
            for i, item in enumerate(self.visible):
                if isinstance(item, SelectorItem) and item.is_current:
                    self.selected_idx = i
                    return

        self.selected_idx = selectable[0]

    def move(self, delta: int) -> None:
        selectable = self._selectable_indices()
        if not selectable:
            return
        try:
            pos = selectable.index(self.selected_idx)
        except ValueError:
            pos = 0
        new_idx = selectable[(pos + delta) % len(selectable)]
        changed = new_idx != self.selected_idx
        self.selected_idx = new_idx
        if changed and self.config.on_change is not None:
            item = self.visible[new_idx]
            if isinstance(item, SelectorItem):
                self.config.on_change(item.value)

    def commit(self) -> bool:
        if not self.visible or self.selected_idx >= len(self.visible):
            return False
        item = self.visible[self.selected_idx]
        if not isinstance(item, SelectorItem):
            return False
        self.result = item.value
        return True

    def append_filter(self, ch: str) -> None:
        self.filter += ch
        self._refilter()

    def backspace_filter(self) -> None:
        if self.filter:
            self.filter = self.filter[:-1]
            self._refilter()

    def clear_filter(self) -> None:
        if self.filter:
            self.filter = ""
            self._refilter()

    def visible_window(self) -> tuple[int, int]:
        if not self.visible:
            return (0, 0)
        max_visible = max(1, self.config.max_visible)
        if len(self.visible) <= max_visible:
            return (0, len(self.visible))
        start = max(0, min(self.selected_idx - max_visible // 2, len(self.visible) - max_visible))
        end = min(start + max_visible, len(self.visible))
        return (start, end)


def _build_application[T](state: _SelectorState[T]) -> Application[None]:
    config = state.config

    def _current_width(default: int = 80) -> int:
        app = get_app_or_none()
        if app is None:
            return default
        try:
            return max(20, app.output.get_size().columns)
        except Exception:  # noqa: BLE001 - selector rendering must be defensive
            return default

    def _selectable_count(rows: Sequence[SelectorItem[T] | SelectorHeader]) -> int:
        return sum(1 for item in rows if isinstance(item, SelectorItem))

    def border_text() -> StyleAndTextTuples:
        width = _current_width()
        return [(get_toolbar_colors().separator, "─" * width)]

    def header_text() -> StyleAndTextTuples:
        width = _current_width()
        total = _selectable_count(config.items)
        visible = _selectable_count(state.visible)
        count = f" {visible} of {total}" if state.filter else f" {total}"
        title = truncate_to_width(f" {config.title} ", max(1, width - cell_width(count)))
        pad = max(0, width - cell_width(title) - cell_width(count))
        out: StyleAndTextTuples = [
            ("class:slash-completion-menu.command.current", title),
            ("class:slash-completion-menu.meta", " " * pad + count),
            ("", "\n"),
        ]
        if config.enable_filter:
            filter_display = state.filter or "(type to filter)"
            line = truncate_to_width(f"  Search: {filter_display}", width)
            out.append(("class:slash-completion-menu.meta", line))
        else:
            out.append(("class:slash-completion-menu.meta", "  ↑↓ navigate · Enter select"))
        return out

    def items_text() -> StyleAndTextTuples:
        width = _current_width()
        if not state.visible:
            return [
                ("class:slash-completion-menu.meta", "  no matches"),
                ("", "\n"),
            ]
        rows: StyleAndTextTuples = []
        start, end = state.visible_window()
        for i in range(start, end):
            item = state.visible[i]
            if isinstance(item, SelectorHeader):
                label = truncate_to_width(f"  {item.label}", width)
                rows.extend(
                    [
                        ("class:slash-completion-menu.meta", label),
                        ("", "\n"),
                    ]
                )
            else:
                rows.extend(
                    _format_item_line(item, is_selected=i == state.selected_idx, width=width)
                )
        if start > 0 or end < len(state.visible):
            selected_pos = max(1, _selectable_count(state.visible[: state.selected_idx + 1]))
            total = _selectable_count(state.visible)
            scroll = truncate_to_width(f"  ({selected_pos}/{total})", width)
            rows.append(("class:slash-completion-menu.meta", scroll))
            rows.append(("", "\n"))
        return rows

    def hint_text() -> StyleAndTextTuples:
        width = _current_width()
        return [("class:slash-completion-menu.meta", truncate_to_width(config.hint, width))]

    bindings = KeyBindings()

    def on_up(event: KeyPressEvent) -> None:
        state.move(-1)
        event.app.invalidate()

    def on_down(event: KeyPressEvent) -> None:
        state.move(1)
        event.app.invalidate()

    def on_page_up(event: KeyPressEvent) -> None:
        state.move(-max(1, config.max_visible))
        event.app.invalidate()

    def on_page_down(event: KeyPressEvent) -> None:
        state.move(max(1, config.max_visible))
        event.app.invalidate()

    def on_enter(event: KeyPressEvent) -> None:
        if state.commit():
            event.app.exit()

    def on_cancel(event: KeyPressEvent) -> None:
        state.cancelled = True
        event.app.exit()

    bindings.add("up")(on_up)
    bindings.add("down")(on_down)
    bindings.add("pageup")(on_page_up)
    bindings.add("pagedown")(on_page_down)
    bindings.add("enter")(on_enter)
    bindings.add("escape", eager=True)(on_cancel)
    bindings.add("c-c")(on_cancel)
    bindings.add("c-d")(on_cancel)

    if config.enable_filter:

        def on_backspace(event: KeyPressEvent) -> None:
            state.backspace_filter()
            event.app.invalidate()

        def on_clear(event: KeyPressEvent) -> None:
            state.clear_filter()
            event.app.invalidate()

        def on_any(event: KeyPressEvent) -> None:
            ch = event.data
            if ch and len(ch) == 1 and ch.isprintable():
                state.append_filter(ch)
                event.app.invalidate()

        bindings.add("backspace")(on_backspace)
        bindings.add("c-u")(on_clear)
        bindings.add("<any>")(on_any)

    layout = Layout(
        HSplit(
            [
                Window(
                    FormattedTextControl(border_text),
                    height=1,
                    style="class:slash-completion-menu",
                ),
                Window(
                    FormattedTextControl(header_text),
                    height=Dimension(min=2, max=2),
                    style="class:slash-completion-menu",
                ),
                Window(
                    FormattedTextControl(items_text),
                    height=Dimension(preferred=min(max(1, config.max_visible), 12), min=1),
                    style="class:slash-completion-menu",
                ),
                Window(
                    FormattedTextControl(hint_text),
                    height=Dimension(min=1, max=1),
                    style="class:slash-completion-menu",
                ),
                Window(
                    FormattedTextControl(border_text),
                    height=1,
                    style="class:slash-completion-menu",
                ),
            ]
        )
    )

    return Application(
        layout=layout,
        key_bindings=bindings,
        full_screen=False,
        style=get_prompt_style(),
        mouse_support=False,
    )


async def run_selector[T](config: SelectorConfig[T]) -> T | None:
    """Show *config* as an interactive selector. Returns the chosen value
    or ``None`` if the user cancelled.

    Empty selectors (no items, no items match the filter) still let the user
    cancel — they just can't commit.
    """
    state: _SelectorState[T] = _SelectorState(config)
    app = _build_application(state)
    await app.run_async()
    if state.cancelled or state.result is None:
        return None
    return state.result
