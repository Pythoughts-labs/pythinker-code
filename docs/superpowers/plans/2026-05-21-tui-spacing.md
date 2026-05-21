# TUI Card Spacing Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three layers of spacing to Pythinker's card-style TUI — vertical card padding, a header-to-results blank line, and an explicit inter-card gap — for improved readability.

**Architecture:** Two files change. `tool_execution.py` gains a `(1, 1)` padding tuple and a blank-line spacer between the command header child and the result children. `_live_view.py`'s two flush sites each gain a bare `console.print()` call before emitting a card to scrollback.

**Tech Stack:** Python 3.12, Rich (`Padding`, `Group`, `Text`, `Console`), pytest

---

## Files

| File | Change |
|------|--------|
| `src/pythinker_code/ui/shell/components/tool_execution.py` | Padding tuple + header-to-result spacer |
| `src/pythinker_code/ui/shell/visualize/_live_view.py` | Blank line before each card flush |
| `tests/ui_and_conv/test_tui_card_tool_renderers.py` | New spacing assertions |

---

## Task 1: Tests for card vertical padding

**Files:**
- Test: `tests/ui_and_conv/test_tui_card_tool_renderers.py`

- [ ] **Step 1: Add the failing test**

Open `tests/ui_and_conv/test_tui_card_tool_renderers.py` and append this test at the end of the file:

```python
# ---------------------------------------------------------------------------
# spacing
# ---------------------------------------------------------------------------


def test_card_has_top_and_bottom_padding():
    """Padding(body, (1, 1)) must produce a blank line above and below the card."""
    rendered = _render("Glob", {"pattern": "*.py", "directory": "/repo"}, output="foo.py")
    lines = [line.strip() for line in rendered.splitlines()]
    # first line is top padding — must be blank
    assert lines[0] == "", f"expected blank top padding, got {lines[0]!r}"
    # last blank line is bottom padding — find it after content
    content_indices = [i for i, l in enumerate(lines) if l]
    last_content = content_indices[-1]
    assert last_content < len(lines) - 1, "expected a blank line after the last content line"
    assert lines[last_content + 1] == "", f"expected blank bottom padding after content"
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
cd /home/ai/Projects/pythinker-code-main
python -m pytest tests/ui_and_conv/test_tui_card_tool_renderers.py::test_card_has_top_and_bottom_padding -v
```

Expected: `FAILED` — `AssertionError: expected blank top padding`

---

## Task 2: Implement card vertical padding

**Files:**
- Modify: `src/pythinker_code/ui/shell/components/tool_execution.py:183`

- [ ] **Step 1: Change the Padding tuple**

In `ToolExecutionComponent.render()`, the final return is:

```python
return Padding(body, (0, 1), style=bg_style)
```

Change it to:

```python
return Padding(body, (1, 1), style=bg_style)
```

- [ ] **Step 2: Run the padding test — expect PASS**

```bash
python -m pytest tests/ui_and_conv/test_tui_card_tool_renderers.py::test_card_has_top_and_bottom_padding -v
```

Expected: `PASSED`

- [ ] **Step 3: Run the full card renderer suite — all must still pass**

```bash
python -m pytest tests/ui_and_conv/test_tui_card_tool_renderers.py -v
```

Expected: all `PASSED`

- [ ] **Step 4: Commit**

```bash
git add src/pythinker_code/ui/shell/components/tool_execution.py \
        tests/ui_and_conv/test_tui_card_tool_renderers.py
git commit -m "feat(tui): add vertical padding to tool call cards"
```

---

## Task 3: Tests for header-to-results spacer

**Files:**
- Test: `tests/ui_and_conv/test_tui_card_tool_renderers.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/ui_and_conv/test_tui_card_tool_renderers.py`:

```python
def test_card_has_blank_line_between_header_and_result():
    """A blank line must appear between the command title and the result body."""
    rendered = _render("Glob", {"pattern": "*.py", "directory": "/repo"}, output="foo.py\nbar.py")
    lines = [line.strip() for line in rendered.splitlines()]
    # locate the header line (contains "find" and the pattern)
    header_idx = next(
        (i for i, l in enumerate(lines) if "find" in l and "*.py" in l), None
    )
    assert header_idx is not None, "header line not found in rendered output"
    # the line immediately after the header must be blank
    assert lines[header_idx + 1] == "", (
        f"expected blank spacer after header at index {header_idx}, "
        f"got {lines[header_idx + 1]!r}"
    )
    # the result must appear after the spacer
    result_lines = lines[header_idx + 2 :]
    assert any("foo.py" in l for l in result_lines), "result not found after spacer"
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
python -m pytest tests/ui_and_conv/test_tui_card_tool_renderers.py::test_card_has_blank_line_between_header_and_result -v
```

Expected: `FAILED` — blank line not present after header

---

## Task 4: Implement header-to-results spacer

**Files:**
- Modify: `src/pythinker_code/ui/shell/components/tool_execution.py:173-175`

- [ ] **Step 1: Replace the body assembly block**

In `ToolExecutionComponent.render()`, find this block (around line 173):

```python
if not children:
    return Text("")

body: RenderableType = children[0] if len(children) == 1 else Group(*children)
```

Replace it with:

```python
if not children:
    return Text("")

if len(children) <= 1:
    body: RenderableType = children[0] if children else Text("")
else:
    # Insert blank line between call header (children[0]) and result/hints.
    body = Group(children[0], Text(""), *children[1:])
```

- [ ] **Step 2: Run the spacer test — expect PASS**

```bash
python -m pytest tests/ui_and_conv/test_tui_card_tool_renderers.py::test_card_has_blank_line_between_header_and_result -v
```

Expected: `PASSED`

- [ ] **Step 3: Run the full card renderer suite — all must still pass**

```bash
python -m pytest tests/ui_and_conv/test_tui_card_tool_renderers.py -v
```

Expected: all `PASSED`

- [ ] **Step 4: Commit**

```bash
git add src/pythinker_code/ui/shell/components/tool_execution.py \
        tests/ui_and_conv/test_tui_card_tool_renderers.py
git commit -m "feat(tui): add blank line between command header and result body"
```

---

## Task 5: Implement explicit inter-card gap

**Files:**
- Modify: `src/pythinker_code/ui/shell/visualize/_live_view.py:670-671, 622-623`

There are exactly two sites where finished tool-call blocks are printed to scrollback.

- [ ] **Step 1: Add blank line in `flush_finished_tool_calls`**

Find `flush_finished_tool_calls` (around line 654). The inner loop currently ends with:

```python
            self._tool_call_blocks.pop(tool_call_id)
            console.print(block.compose())
            if self._last_tool_call_block == block:
                self._last_tool_call_block = None
            self.refresh_soon()
```

Change to:

```python
            self._tool_call_blocks.pop(tool_call_id)
            console.print()
            console.print(block.compose())
            if self._last_tool_call_block == block:
                self._last_tool_call_block = None
            self.refresh_soon()
```

- [ ] **Step 2: Add blank line in `cleanup`**

Find the `cleanup` method (around line 605). The drain loop currently contains:

```python
        for tool_call_id in list(self._tool_call_blocks.keys()):
            block = self._tool_call_blocks.pop(tool_call_id)
            console.print(block.compose())
```

Change to:

```python
        for tool_call_id in list(self._tool_call_blocks.keys()):
            block = self._tool_call_blocks.pop(tool_call_id)
            console.print()
            console.print(block.compose())
```

- [ ] **Step 3: Run the full test suite**

```bash
python -m pytest tests/ui_and_conv/ tests/core/ -v
```

Expected: all `PASSED`

- [ ] **Step 4: Commit**

```bash
git add src/pythinker_code/ui/shell/visualize/_live_view.py
git commit -m "feat(tui): emit blank line before each card in scrollback"
```

---

## Task 6: Final verification

- [ ] **Step 1: Run the complete test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all `PASSED`

- [ ] **Step 2: Visual spot-check**

Launch Pythinker in card mode and run a sequence of `find`/`read`/`bash` calls. Verify:
- Each card has a blank line above and below it
- The command title and output body are separated by a blank line
- Consecutive cards are separated by ~3 blank lines

---

## Result

Visual rhythm after all three changes:

```
                                        ← top padding (tinted)
 find *.py in src                       ← command header
                                        ← header-to-result spacer
 src/foo.py                             ← result lines
 src/bar.py
                                        ← bottom padding (tinted)
                                        ← explicit inter-card blank
                                        ← top padding of next card
 read src/foo.py                        ← next card header
 ...
```
