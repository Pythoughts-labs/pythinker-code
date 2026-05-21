# TUI Card Spacing Enhancement

**Date:** 2026-05-21
**Status:** Approved
**Scope:** Card-style tool call rendering in the Pythinker shell TUI

---

## Problem

In the current TUI (card style), tool call cards have no vertical padding and no
spacer between the command header and the result body. Consecutive cards also run
together with only a single newline separating them. This makes it hard to visually
group a command with its output or to distinguish where one tool call ends and the
next begins.

---

## Goal

Add three layers of spacing to make the TUI easier to read:

1. **Card vertical padding** — breathing room above and below every card
2. **Header-to-results gap** — a blank line separating the command title from the output body
3. **Inter-card gap** — a guaranteed blank line before each card enters scrollback

---

## Design (Option B)

### Change 1 — Card vertical padding

**File:** `src/pythinker_code/ui/shell/components/tool_execution.py`
**Location:** `ToolExecutionComponent.render()`, final return statement

```python
# Before
return Padding(body, (0, 1), style=bg_style)

# After
return Padding(body, (1, 1), style=bg_style)
```

The `(1, 1)` tuple gives Rich's `Padding` 1 blank row top, 1 blank row bottom, 1 column
left, 1 column right. The background tint extends through the padding rows, preserving
the "colored block" appearance while adding vertical air.

### Change 2 — Header-to-results spacer

**File:** `src/pythinker_code/ui/shell/components/tool_execution.py`
**Location:** `ToolExecutionComponent.render()`, body assembly block

```python
# Before
body: RenderableType = children[0] if len(children) == 1 else Group(*children)

# After
if len(children) <= 1:
    body = children[0] if children else Text("")
else:
    body = Group(children[0], Text(""), *children[1:])
```

`children` is `[call]`, `[call, result]`, or `[call, result, key_hint]`. The blank
`Text("")` is inserted after `children[0]` (the command header) only when a result or
hint follows. When the tool is still running (only the header exists), behaviour is
unchanged.

### Change 3 — Explicit inter-card gap

**File:** `src/pythinker_code/ui/shell/visualize/_live_view.py`
**Locations:** `flush_finished_tool_calls()` and `cleanup()`

```python
# flush_finished_tool_calls
self._tool_call_blocks.pop(tool_call_id)
console.print()          # blank line before card
console.print(block.compose())

# cleanup
block = self._tool_call_blocks.pop(tool_call_id)
console.print()          # blank line before card
console.print(block.compose())
```

`console.print()` with no arguments emits a single blank line. Combined with the
bottom padding of the previous card and the top padding of the next, this produces a
3-line gap between consecutive cards — clear visual grouping regardless of card size.

---

## Resulting visual rhythm

```
[blank — top padding]
 find *.md in .agents (limit 100)
[blank — header-to-results spacer]
 skills/gen-rust/SKILL.md
 skills/release/SKILL.md
[blank — bottom padding]

[blank — explicit inter-card gap]
[blank — top padding]
 find *.md in .claude (limit 100)
[blank — header-to-results spacer]
 No files found matching pattern
[blank — bottom padding]
```

---

## Scope

- Card style only (`is_card_style() == True`). The worklog style path (`_ToolCallBlock._compose()`) is untouched.
- No changes to individual tool renderers.
- No new abstractions, no new dependencies.

## Files changed

| File | Change |
|------|--------|
| `src/pythinker_code/ui/shell/components/tool_execution.py` | Padding + spacer (changes 1 & 2) |
| `src/pythinker_code/ui/shell/visualize/_live_view.py` | Inter-card blank (change 3) |

## Testing

- Run existing TUI card renderer tests: `pytest tests/ui_and_conv/test_tui_card_tool_renderers.py`
- Visual spot-check: run Pythinker in card mode and observe a find/read/bash sequence
