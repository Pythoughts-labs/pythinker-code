# Selector Family Port — Plan A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `selector.py` with `SelectorHeader` + `on_change`, then ship five ready-to-use selectors (theme, thinking, show_images, extension, oauth) behind a new `selectors/` package, and wire them into `/theme`, `/thinking`, and `/login`.

**Architecture:** Each selector is a thin async wrapper around `run_selector()`, exposing a private `_build_*_config()` helper for unit-testability. `selector.py` gains two additive features: a `SelectorHeader` sentinel that appears in the render but is skipped by cursor nav, and an `on_change` callback that fires on cursor movement. The `selectors/` package re-exports all `run_*()` functions from a single `__init__.py`.

**Tech Stack:** Python 3.12+, prompt_toolkit, pytest (`.venv/bin/pytest`)

**Spec:** `docs/superpowers/specs/2026-05-07-selector-family-design.md` §§1–3, 6 (partial), 7 (partial)

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `src/pythinker_code/ui/shell/selector.py` | Add `SelectorHeader`; update `SelectorConfig` (items type + `on_change`); update `_SelectorState` + `items_text()` render |
| Create | `src/pythinker_code/ui/shell/selectors/__init__.py` | Re-exports all `run_*` functions |
| Create | `src/pythinker_code/ui/shell/selectors/theme.py` | `run_theme_selector()` |
| Create | `src/pythinker_code/ui/shell/selectors/thinking.py` | `run_thinking_selector()`, `ThinkingLevel`, `LEVEL_DESCRIPTIONS` |
| Create | `src/pythinker_code/ui/shell/selectors/show_images.py` | `run_show_images_selector()` |
| Create | `src/pythinker_code/ui/shell/selectors/extension.py` | `run_extension_selector()` |
| Create | `src/pythinker_code/ui/shell/selectors/oauth.py` | `run_oauth_selector()`, `OAuthProviderEntry`, `OAuthProviderStatus` |
| Create | `tests/ui_and_conv/test_selector_groups.py` | `SelectorHeader` nav + `on_change` unit tests |
| Create | `tests/ui_and_conv/test_selectors_simple.py` | Tier-1 selector config + behavior unit tests |
| Modify | `src/pythinker_code/ui/shell/slash.py` | Upgrade `/theme`; add `/thinking`; replace `ChoiceInput` in `/model` |
| Modify | `src/pythinker_code/ui/shell/oauth.py` | Replace numeric text prompt in `/login` with `run_oauth_selector()` |

---

### Task 1: selector.py — SelectorHeader sentinel + updated items type

**Files:**
- Modify: `src/pythinker_code/ui/shell/selector.py`
- Test: `tests/ui_and_conv/test_selector_groups.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/ui_and_conv/test_selector_groups.py`:

```python
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
    return _SelectorState(
        SelectorConfig(title="test", items=items, enable_filter=enable_filter)
    )


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
    # Start at a1 (idx 1); move down twice:
    #   a1 -> a2, then a2 -> b1 (skips header at idx 3)
    state.move(1)
    assert state.visible[state.selected_idx].value == "a2"
    state.move(1)
    assert state.visible[state.selected_idx].value == "b1"


def test_move_up_wraps_from_first_to_last_item():
    state = _make_grouped_state()
    # Start at a1; move up wraps to b1 (last selectable)
    state.move(-1)
    assert state.visible[state.selected_idx].value == "b1"


def test_move_wraps_from_last_to_first_item():
    state = _make_grouped_state()
    state.move(-1)  # a1 -> b1 (wrap)
    state.move(1)   # b1 -> a1 (wrap)
    assert state.visible[state.selected_idx].value == "a1"


def test_headers_hidden_during_filtering():
    state = _make_grouped_state(enable_filter=True)
    state.append_filter("a")
    # Only SelectorItems matching "a" visible; headers stripped
    assert all(isinstance(item, SelectorItem) for item in state.visible)
    assert {item.value for item in state.visible} == {"a1", "a2"}


def test_commit_returns_selected_item_value():
    state = _make_grouped_state()
    assert state.commit()
    assert state.result == "a1"
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/ui_and_conv/test_selector_groups.py -q 2>&1 | head -15
```

Expected: `ImportError` — `SelectorHeader` does not exist yet.

- [ ] **Step 3: Add SelectorHeader dataclass to selector.py**

In `selector.py`, insert after the `SelectorItem` class (before `SelectorConfig`):

```python
@dataclass(frozen=True, slots=True)
class SelectorHeader:
    """A non-selectable divider row in a selector.

    Attributes:
        label: Displayed using the meta style; skipped by cursor navigation.
    """

    label: str
```

- [ ] **Step 4: Update SelectorConfig.items type**

Replace the `SelectorConfig` class body so `items` accepts headers:

```python
@dataclass(frozen=True, slots=True)
class SelectorConfig[T]:
    """Static configuration for a selector dialog."""

    title: str
    items: Sequence[SelectorItem[T] | SelectorHeader]
    """Source rows. May include SelectorHeader dividers — rendered but skipped
    by cursor navigation."""

    hint: str = "↑↓ navigate · Enter select · Esc cancel · type to filter"
    """Footer shown below the item list."""

    enable_filter: bool = True
    """When False, type-to-filter is disabled (useful for tiny selectors)."""
```

- [ ] **Step 5: Update __all__**

```python
__all__ = [
    "SelectorConfig",
    "SelectorHeader",
    "SelectorItem",
    "run_selector",
]
```

- [ ] **Step 6: Replace _SelectorState with the header-aware version**

Replace the entire `_SelectorState` class:

```python
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

    def _matches(self, item: SelectorItem[T]) -> bool:
        if not self.filter:
            return True
        needle = self.filter.lower()
        return needle in item.label.lower() or needle in item.description.lower()

    def _selectable_indices(self) -> list[int]:
        return [i for i, item in enumerate(self.visible) if isinstance(item, SelectorItem)]

    def _refilter(self, *, initial: bool = False) -> None:
        previous_value: T | None = None
        if not initial and self.visible and 0 <= self.selected_idx < len(self.visible):
            current = self.visible[self.selected_idx]
            if isinstance(current, SelectorItem):
                previous_value = current.value

        if not self.filter:
            # Include headers only when unfiltered.
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

        # Try to preserve the selected value across filter edits.
        if previous_value is not None:
            for i, item in enumerate(self.visible):
                if isinstance(item, SelectorItem) and item.value == previous_value:
                    self.selected_idx = i
                    return

        # On initial open, prefer the item flagged is_current.
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
        self.selected_idx = selectable[(pos + delta) % len(selectable)]

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
```

- [ ] **Step 7: Update items_text() in _build_application to render headers**

Replace the `items_text` inner function inside `_build_application`:

```python
    def items_text() -> StyleAndTextTuples:
        if not state.visible:
            return [
                ("class:slash-completion-menu.meta", "  no matches"),
                ("", "\n"),
            ]
        width = 80
        rows: StyleAndTextTuples = []
        for i, item in enumerate(state.visible):
            if isinstance(item, SelectorHeader):
                rows.extend([
                    ("class:slash-completion-menu.meta", f"  {item.label}"),
                    ("", "\n"),
                ])
            else:
                rows.extend(
                    _format_item_line(item, is_selected=i == state.selected_idx, width=width)
                )
        return rows
```

- [ ] **Step 8: Run all selector tests**

```bash
.venv/bin/pytest tests/ui_and_conv/test_selector_groups.py tests/ui_and_conv/test_tui_card_selector.py -q
```

Expected: all 20 pass (12 existing + 8 new).

---

### Task 2: selector.py — on_change callback

**Files:**
- Modify: `src/pythinker_code/ui/shell/selector.py`
- Test: `tests/ui_and_conv/test_selector_groups.py` (extend)

- [ ] **Step 1: Write failing tests for on_change**

Append to `tests/ui_and_conv/test_selector_groups.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/ui_and_conv/test_selector_groups.py::test_on_change_fires_when_cursor_moves -q
```

Expected: FAIL — `SelectorConfig` has no `on_change` attribute.

- [ ] **Step 3: Add Callable to imports**

In `selector.py`, update the import line:

```python
from collections.abc import Callable, Sequence
```

- [ ] **Step 4: Add on_change field to SelectorConfig**

Add `on_change` as the last field (after `enable_filter`) in `SelectorConfig`:

```python
    on_change: Callable[[T], None] | None = None
    """Called whenever the cursor moves to a different SelectorItem."""
```

- [ ] **Step 5: Update move() to fire the callback on selection change**

Replace `move()` in `_SelectorState`:

```python
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
```

- [ ] **Step 6: Run all selector tests**

```bash
.venv/bin/pytest tests/ui_and_conv/test_selector_groups.py tests/ui_and_conv/test_tui_card_selector.py -q
```

Expected: all 23 pass.

- [ ] **Step 7: Commit**

```bash
git add src/pythinker_code/ui/shell/selector.py tests/ui_and_conv/test_selector_groups.py
git commit -m "feat(ui): SelectorHeader sentinel + on_change callback in selector.py"
```

---

### Task 3: selectors/ package — theme, thinking, show_images, extension

**Files:**
- Create: `src/pythinker_code/ui/shell/selectors/__init__.py`
- Create: `src/pythinker_code/ui/shell/selectors/theme.py`
- Create: `src/pythinker_code/ui/shell/selectors/thinking.py`
- Create: `src/pythinker_code/ui/shell/selectors/show_images.py`
- Create: `src/pythinker_code/ui/shell/selectors/extension.py`
- Test: `tests/ui_and_conv/test_selectors_simple.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/ui_and_conv/test_selectors_simple.py`:

```python
"""Tests for the simple Tier-1 selectors.

All tests exercise config construction and _SelectorState behavior directly
— no TTY, no Application instantiation.
"""
from __future__ import annotations

import asyncio

from pythinker_code.ui.shell.selector import (
    SelectorItem,
    _SelectorState,  # type: ignore[reportPrivateUsage]
)


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
    assert state.visible[state.selected_idx].value == "light"
    assert state.visible[state.selected_idx].is_current is True


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
    config = _build_theme_config(
        current_theme="dark",
        available_themes=["dark", "light"],
        on_preview=previews.append,
    )
    assert config.on_change is previews.append


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
    assert state.visible[state.selected_idx].value == "medium"
    assert state.visible[state.selected_idx].is_current is True


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
    assert state.visible[state.selected_idx].value is True


def test_show_images_marks_false_when_current_false():
    from pythinker_code.ui.shell.selectors.show_images import _build_show_images_config

    state = _SelectorState(_build_show_images_config(current=False))
    assert state.visible[state.selected_idx].value is False


# ---------------------------------------------------------------------------
# extension
# ---------------------------------------------------------------------------

def test_extension_selector_items_match_options():
    from pythinker_code.ui.shell.selectors.extension import _build_extension_config

    config = _build_extension_config(title="Pick", options=["alpha", "beta", "gamma"])
    assert [item.value for item in config.items] == ["alpha", "beta", "gamma"]


def test_extension_selector_marks_current():
    from pythinker_code.ui.shell.selectors.extension import _build_extension_config

    state = _SelectorState(
        _build_extension_config(title="Pick", options=["a", "b", "c"], current="b")
    )
    assert state.visible[state.selected_idx].value == "b"


def test_extension_selector_no_current_starts_at_first():
    from pythinker_code.ui.shell.selectors.extension import _build_extension_config

    state = _SelectorState(_build_extension_config(title="Pick", options=["x", "y"]))
    assert state.visible[state.selected_idx].value == "x"


def test_extension_selector_timeout_returns_none(monkeypatch):
    import asyncio as _asyncio

    from pythinker_code.ui.shell.selectors.extension import run_extension_selector

    async def _raise_timeout(*args, **kwargs):
        raise _asyncio.TimeoutError

    monkeypatch.setattr(_asyncio, "wait_for", _raise_timeout)
    result = _asyncio.run(run_extension_selector("t", ["a"], timeout=0.001))
    assert result is None
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/ui_and_conv/test_selectors_simple.py -q 2>&1 | head -10
```

Expected: `ImportError` — `selectors` package does not exist.

- [ ] **Step 3: Create the selectors/ package skeleton**

```bash
mkdir src/pythinker_code/ui/shell/selectors
```

Create `src/pythinker_code/ui/shell/selectors/__init__.py` (skeleton — filled in Task 4):

```python
"""Selector dialogs for Pythinker.

Each sub-module exposes one run_*() async function. Import from this package:

    from pythinker_code.ui.shell.selectors import run_theme_selector
"""
```

- [ ] **Step 4: Create theme.py**

Create `src/pythinker_code/ui/shell/selectors/theme.py`:

```python
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
    return await run_selector(
        _build_theme_config(current_theme, available_themes, on_preview)
    )
```

- [ ] **Step 5: Create thinking.py**

Create `src/pythinker_code/ui/shell/selectors/thinking.py`:

```python
from __future__ import annotations

from typing import Literal

from pythinker_code.ui.shell.selector import SelectorConfig, SelectorItem, run_selector

ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]

LEVEL_DESCRIPTIONS: dict[str, str] = {
    "off": "No reasoning",
    "minimal": "Very brief reasoning (~1k tokens)",
    "low": "Light reasoning (~2k tokens)",
    "medium": "Moderate reasoning (~8k tokens)",
    "high": "Deep reasoning (~16k tokens)",
    "xhigh": "Maximum reasoning (~32k tokens)",
}


def _build_thinking_config(
    current_level: ThinkingLevel,
    available_levels: list[ThinkingLevel],
) -> SelectorConfig[ThinkingLevel]:
    return SelectorConfig(
        title="Select thinking level",
        items=[
            SelectorItem(
                value=level,
                label=level,
                description=LEVEL_DESCRIPTIONS.get(level, ""),
                is_current=(level == current_level),
            )
            for level in available_levels
        ],
        hint="↑↓ navigate · Enter select · Esc cancel",
    )


async def run_thinking_selector(
    current_level: ThinkingLevel,
    available_levels: list[ThinkingLevel],
) -> ThinkingLevel | None:
    return await run_selector(_build_thinking_config(current_level, available_levels))
```

- [ ] **Step 6: Create show_images.py**

Create `src/pythinker_code/ui/shell/selectors/show_images.py`:

```python
from __future__ import annotations

from pythinker_code.ui.shell.selector import SelectorConfig, SelectorItem, run_selector


def _build_show_images_config(current: bool) -> SelectorConfig[bool]:
    return SelectorConfig(
        title="Show images in responses?",
        items=[
            SelectorItem(value=True, label="Yes", description="Show images", is_current=current),
            SelectorItem(
                value=False, label="No", description="Hide images", is_current=not current
            ),
        ],
        enable_filter=False,
        hint="↑↓ navigate · Enter select · Esc cancel",
    )


async def run_show_images_selector(current: bool) -> bool | None:
    return await run_selector(_build_show_images_config(current))
```

- [ ] **Step 7: Create extension.py**

Create `src/pythinker_code/ui/shell/selectors/extension.py`:

```python
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
        items=[
            SelectorItem(value=opt, label=opt, is_current=(opt == current))
            for opt in options
        ],
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
        except asyncio.TimeoutError:
            return None
    return await coro
```

- [ ] **Step 8: Run the Tier-1 tests (theme through extension)**

```bash
.venv/bin/pytest tests/ui_and_conv/test_selectors_simple.py -q
```

Expected: the oauth tests will fail (not yet implemented); theme/thinking/show_images/extension should all pass. If any non-oauth tests fail, fix before continuing.

---

### Task 4: selectors/oauth.py + __init__.py re-exports

**Files:**
- Create: `src/pythinker_code/ui/shell/selectors/oauth.py`
- Modify: `src/pythinker_code/ui/shell/selectors/__init__.py`
- Test: `tests/ui_and_conv/test_selectors_simple.py` (extend)

- [ ] **Step 1: Write failing oauth tests**

Append to `tests/ui_and_conv/test_selectors_simple.py`:

```python
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

    indicator = _format_status_indicator(
        OAuthProviderStatus(source="environment", label="API key")
    )
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
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/ui_and_conv/test_selectors_simple.py -k oauth -q 2>&1 | head -10
```

Expected: `ImportError` — `selectors/oauth.py` does not exist.

- [ ] **Step 3: Create selectors/oauth.py**

Create `src/pythinker_code/ui/shell/selectors/oauth.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pythinker_code.ui.shell.selector import SelectorConfig, SelectorItem, run_selector


@dataclass(frozen=True, slots=True)
class OAuthProviderEntry:
    id: str
    name: str
    auth_type: Literal["oauth", "api_key"]


@dataclass(frozen=True, slots=True)
class OAuthProviderStatus:
    source: Literal[
        "environment",
        "runtime",
        "fallback",
        "models_json_key",
        "models_json_command",
        "configured",
        "unconfigured",
    ]
    label: str | None = None


def _format_status_indicator(status: OAuthProviderStatus) -> str:
    if status.source == "unconfigured":
        return "• unconfigured"
    if status.source == "environment":
        return f"✓ env: {status.label or 'API key'}"
    return f"✓ {status.label or 'configured'}"


def _build_oauth_config(
    providers: list[OAuthProviderEntry],
    get_status: Callable[[str], OAuthProviderStatus],
    *,
    action: Literal["login", "logout"] = "login",
) -> SelectorConfig[str]:
    items = [
        SelectorItem(
            value=provider.id,
            label=provider.name,
            description=_format_status_indicator(get_status(provider.id)),
        )
        for provider in providers
    ]
    title = "Select provider to log in" if action == "login" else "Select provider to log out"
    return SelectorConfig(title=title, items=items)


async def run_oauth_selector(
    providers: list[OAuthProviderEntry],
    get_status: Callable[[str], OAuthProviderStatus],
    *,
    action: Literal["login", "logout"] = "login",
) -> str | None:
    return await run_selector(_build_oauth_config(providers, get_status, action=action))
```

- [ ] **Step 4: Run all simple selector tests**

```bash
.venv/bin/pytest tests/ui_and_conv/test_selectors_simple.py -q
```

Expected: all pass.

- [ ] **Step 5: Update selectors/__init__.py with full re-exports**

Replace `src/pythinker_code/ui/shell/selectors/__init__.py`:

```python
"""Selector dialogs for Pythinker.

Each sub-module exposes one run_*() async function. Import from this package:

    from pythinker_code.ui.shell.selectors import run_theme_selector
"""

from pythinker_code.ui.shell.selectors.extension import run_extension_selector
from pythinker_code.ui.shell.selectors.oauth import (
    OAuthProviderEntry,
    OAuthProviderStatus,
    run_oauth_selector,
)
from pythinker_code.ui.shell.selectors.show_images import run_show_images_selector
from pythinker_code.ui.shell.selectors.theme import run_theme_selector
from pythinker_code.ui.shell.selectors.thinking import (
    LEVEL_DESCRIPTIONS,
    ThinkingLevel,
    run_thinking_selector,
)

__all__ = [
    "LEVEL_DESCRIPTIONS",
    "OAuthProviderEntry",
    "OAuthProviderStatus",
    "ThinkingLevel",
    "run_extension_selector",
    "run_oauth_selector",
    "run_show_images_selector",
    "run_theme_selector",
    "run_thinking_selector",
]
```

- [ ] **Step 6: Verify package import works**

```bash
.venv/bin/python -c "from pythinker_code.ui.shell.selectors import run_theme_selector, run_oauth_selector; print('ok')"
```

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add src/pythinker_code/ui/shell/selectors/ tests/ui_and_conv/test_selectors_simple.py
git commit -m "feat(ui): selectors/ package — theme, thinking, show_images, extension, oauth"
```

---

### Task 5: Slash-command wiring — /theme upgrade + /thinking command

**Files:**
- Modify: `src/pythinker_code/ui/shell/slash.py`

- [ ] **Step 1: Make /theme async and add selector for no-args invocation**

The existing `/theme` command at line ~655 is `def theme` (sync). Replace the entire function (lines `@registry.command` through `raise Reload(...)`) with an async version:

```python
@registry.command
@shell_mode_registry.command
async def theme(app: Shell, args: str) -> None:
    """Switch terminal color theme — interactive picker when no args given"""
    from pythinker_code.ui.theme import get_active_theme

    soul = ensure_pythinker_soul(app)
    if soul is None:
        return

    current = get_active_theme()
    arg = args.strip().lower()

    if not arg:
        from pythinker_code.ui.shell.selectors.theme import run_theme_selector

        chosen = await run_theme_selector(
            current_theme=current,
            available_themes=["dark", "light"],
        )
        if chosen is None or chosen == current:
            return
        arg = chosen

    if arg not in ("dark", "light"):
        console.print(f"[red]Unknown theme: {arg}. Use 'dark' or 'light'.[/red]")
        return

    if arg == current:
        console.print(f"[yellow]Already using {arg} theme.[/yellow]")
        return

    config_file = soul.runtime.config.source_file
    if config_file is None:
        console.print(
            "[yellow]Theme switching requires a config file; "
            "restart without --config to persist this setting.[/yellow]"
        )
        return

    try:
        config_for_save = load_config(config_file)
        config_for_save.theme = arg  # type: ignore[assignment]
        save_config(config_for_save, config_file)
    except (ConfigError, OSError) as exc:
        console.print(f"[red]Failed to save config: {exc}[/red]")
        return

    from pythinker_code.telemetry import track

    track("theme_switch", theme=arg)
    console.print(f"[green]Switched to {arg} theme. Reloading...[/green]")
    raise Reload(session_id=soul.runtime.session.id)
```

- [ ] **Step 2: Add /thinking command**

Insert the following block immediately after the `/theme` function (before the `/keys` command):

```python
@registry.command
@shell_mode_registry.command
async def thinking(app: Shell, args: str) -> None:
    """Switch thinking level — interactive picker"""
    soul = ensure_pythinker_soul(app)
    if soul is None:
        return

    from pythinker_code.ui.shell.selectors.thinking import ThinkingLevel, run_thinking_selector

    curr_level: ThinkingLevel = "high" if soul.thinking else "off"
    level = await run_thinking_selector(
        current_level=curr_level,
        available_levels=["off", "minimal", "low", "medium", "high", "xhigh"],
    )
    if level is None:
        return

    new_thinking = level != "off"
    if new_thinking == soul.thinking:
        console.print("[yellow]Thinking setting unchanged.[/yellow]")
        return

    config_file = soul.runtime.config.source_file
    if config_file is None:
        console.print(
            "[yellow]Thinking requires a config file; "
            "restart without --config to persist this setting.[/yellow]"
        )
        return

    try:
        config_for_save = load_config(config_file)
        config_for_save.default_thinking = new_thinking
        save_config(config_for_save, config_file)
    except (ConfigError, OSError) as exc:
        console.print(f"[red]Failed to save config: {exc}[/red]")
        return

    from pythinker_code.telemetry import track

    track("thinking_toggle", enabled=new_thinking)
    console.print(
        f"[green]Thinking {'enabled' if new_thinking else 'disabled'}. Reloading...[/green]"
    )
    raise Reload(session_id=soul.runtime.session.id)
```

- [ ] **Step 3: Replace ChoiceInput in /model with run_thinking_selector**

In the `/model` command, find the `elif "thinking" in capabilities:` branch (~line 203). Remove the `thinking_choices` / `ChoiceInput` block and replace it:

Remove this block (lines ~204–220):

```python
        thinking_choices: list[tuple[str, str]] = [
            ("off", "off" + (" (current)" if not curr_thinking else "")),
            ("on", "on" + (" (current)" if curr_thinking else "")),
        ]
        try:
            thinking_selection = await ChoiceInput(
                message="Enable thinking mode? (↑↓ navigate, Enter select, Ctrl+C cancel):",
                options=thinking_choices,
                default="on" if curr_thinking else "off",
            ).prompt_async()
        except (EOFError, KeyboardInterrupt):
            return

        if not thinking_selection:
            return

        new_thinking = thinking_selection == "on"
```

Replace with:

```python
        from pythinker_code.ui.shell.selectors.thinking import ThinkingLevel, run_thinking_selector

        _curr_level: ThinkingLevel = "high" if curr_thinking else "off"
        _level = await run_thinking_selector(
            current_level=_curr_level,
            available_levels=["off", "minimal", "low", "medium", "high", "xhigh"],
        )
        if _level is None:
            return

        new_thinking = _level != "off"
```

- [ ] **Step 4: Verify imports load cleanly**

```bash
.venv/bin/python -c "from pythinker_code.ui.shell.slash import theme, thinking; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Run existing selector tests to check for regressions**

```bash
.venv/bin/pytest tests/ui_and_conv/test_selector_groups.py tests/ui_and_conv/test_selectors_simple.py tests/ui_and_conv/test_tui_card_selector.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/pythinker_code/ui/shell/slash.py
git commit -m "feat(ui): /theme interactive selector; add /thinking command; replace ChoiceInput in /model"
```

---

### Task 6: /login selector upgrade

**Files:**
- Modify: `src/pythinker_code/ui/shell/oauth.py`

- [ ] **Step 1: Add selectors import to oauth.py**

In `src/pythinker_code/ui/shell/oauth.py`, add after the existing imports (before `async def _render_oauth_events`):

```python
from pythinker_code.ui.shell.selectors.oauth import (
    OAuthProviderEntry,
    OAuthProviderStatus,
    run_oauth_selector,
)
```

- [ ] **Step 2: Replace _LOGIN_PROVIDER_OPTIONS and _prompt_login_provider()**

Remove the `_LOGIN_PROVIDER_OPTIONS` tuple and the entire `_prompt_login_provider()` function. Replace both with:

```python
_SELECTOR_PROVIDER_ENTRIES: list[OAuthProviderEntry] = [
    OAuthProviderEntry(id="browser", name="OpenAI ChatGPT (browser)", auth_type="oauth"),
    OAuthProviderEntry(id="headless", name="OpenAI ChatGPT (device code)", auth_type="oauth"),
    OAuthProviderEntry(id="api-key", name="OpenAI API key", auth_type="api_key"),
    OAuthProviderEntry(id="opencode-go", name="OpenCode Go", auth_type="api_key"),
    OAuthProviderEntry(id="minimax", name="MiniMax", auth_type="api_key"),
    OAuthProviderEntry(id="deepseek", name="DeepSeek", auth_type="api_key"),
    OAuthProviderEntry(id="anthropic", name="Anthropic", auth_type="api_key"),
    OAuthProviderEntry(id="openrouter", name="OpenRouter", auth_type="api_key"),
    OAuthProviderEntry(id="lm-studio", name="LM Studio", auth_type="api_key"),
    OAuthProviderEntry(id="ollama", name="Ollama", auth_type="api_key"),
]


def _get_provider_status(provider_id: str) -> OAuthProviderStatus:
    # Status checking wired in Plan B when provider config is queryable.
    return OAuthProviderStatus(source="unconfigured")
```

- [ ] **Step 3: Update login() to call run_oauth_selector**

In `login()`, replace:

```python
    if mode == "":
        chosen = await _prompt_login_provider()
        if chosen is None:
            return
        mode = chosen
```

With:

```python
    if mode == "":
        chosen = await run_oauth_selector(
            _SELECTOR_PROVIDER_ENTRIES,
            _get_provider_status,
            action="login",
        )
        if chosen is None:
            return
        mode = chosen
```

- [ ] **Step 4: Verify the module imports cleanly**

```bash
.venv/bin/python -c "from pythinker_code.ui.shell.oauth import login; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Run full test suite for the affected area**

```bash
.venv/bin/pytest tests/ui_and_conv/ -q 2>&1 | tail -10
```

Expected: all pass (no regressions).

- [ ] **Step 6: Commit**

```bash
git add src/pythinker_code/ui/shell/oauth.py
git commit -m "feat(ui): /login uses run_oauth_selector — replaces numeric text prompt"
```
