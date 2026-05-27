# Agent Live Tool Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show in-flight subagent tool calls as shimmering live rows with streamed output inside the parent Agent card while the agent is running.

**Architecture:** Two surgical changes: (1) add three new fields and two new methods to `_ToolCallBlock` in `_blocks.py` so it can accumulate sub-tool output; (2) update `_compose()` to render ongoing calls as shimmer rows with output preview; (3) wire `ToolExecutionStarted` and `ToolOutputPart` subagent events through `_live_view.py` to the block.

**Tech Stack:** Python, Rich (renderables, Text, Group), existing `ActivityRow`/`render_activity_tree` and `_tail_lines`/`_truncate_to_display_width` helpers already in `_blocks.py`.

---

## File Map

| File | Change |
|---|---|
| `src/pythinker_code/ui/shell/visualize/_blocks.py` | New constants, fields, methods on `_ToolCallBlock`; updated `_compose()` |
| `src/pythinker_code/ui/shell/visualize/_live_view.py` | Split `ToolExecutionStarted \| ToolOutputPart` case in `handle_subagent_event` |
| `tests/ui_and_conv/test_tool_call_block.py` | New unit tests for new methods and running-row rendering |
| `tests/ui_and_conv/test_subagent_live_stream.py` | New integration tests for end-to-end event dispatch |

---

### Task 1: State fields and cleanup

**Files:**
- Modify: `src/pythinker_code/ui/shell/visualize/_blocks.py`
- Test: `tests/ui_and_conv/test_tool_call_block.py`

- [ ] **Step 1: Write failing tests for new fields and methods**

Add to `tests/ui_and_conv/test_tool_call_block.py`:

```python
def test_append_sub_output_part_accumulates_text():
    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    call = _tool_call_with_id("sub-1", "Bash", '{"command":"ls"}')
    block.append_sub_tool_call(call)
    block.append_sub_output_part("sub-1", "file1.py\n")
    block.append_sub_output_part("sub-1", "file2.py\n")
    combined = "".join(block._subagent_output_parts["sub-1"])
    assert "file1.py" in combined
    assert "file2.py" in combined


def test_append_sub_output_part_discards_unknown_call_id():
    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    # no append_sub_tool_call — id is unknown
    block.append_sub_output_part("ghost-id", "should be ignored\n")
    assert "ghost-id" not in block._subagent_output_parts


def test_append_sub_output_part_caps_buffer_at_200_chars():
    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    call = _tool_call_with_id("sub-1", "Bash", '{"command":"find ."}')
    block.append_sub_tool_call(call)
    # Fill with >200 chars in one shot
    block.append_sub_output_part("sub-1", "x" * 300)
    combined = "".join(block._subagent_output_parts["sub-1"])
    assert len(combined) <= 200


def test_append_sub_output_part_tracks_stderr():
    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    call = _tool_call_with_id("sub-1", "Bash", '{"command":"cat missing"}')
    block.append_sub_tool_call(call)
    block.append_sub_output_part("sub-1", "No such file\n", stream="stderr")
    assert block._subagent_output_had_stderr.get("sub-1") is True


def test_mark_sub_execution_started_records_id():
    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    call = _tool_call_with_id("sub-1", "Bash", '{"command":"ls"}')
    block.append_sub_tool_call(call)
    block.mark_sub_execution_started("sub-1")
    assert "sub-1" in block._subagent_execution_started


def test_mark_sub_execution_started_discards_unknown_id():
    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    block.mark_sub_execution_started("ghost-id")  # should not raise
    assert "ghost-id" not in block._subagent_execution_started


def test_finish_sub_tool_call_cleans_up_output_state():
    from pythinker_code.wire.types import ToolResult
    from pythinker_core.tooling import ToolOk

    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    call = _tool_call_with_id("sub-1", "Bash", '{"command":"ls"}')
    block.append_sub_tool_call(call)
    block.append_sub_output_part("sub-1", "output\n")
    block.mark_sub_execution_started("sub-1")
    block.finish_sub_tool_call(ToolResult(tool_call_id="sub-1", return_value=ToolOk(output="")))
    assert "sub-1" not in block._subagent_output_parts
    assert "sub-1" not in block._subagent_output_had_stderr
    assert "sub-1" not in block._subagent_execution_started
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ai/Projects/pythinker-code-main
python -m pytest tests/ui_and_conv/test_tool_call_block.py::test_append_sub_output_part_accumulates_text tests/ui_and_conv/test_tool_call_block.py::test_mark_sub_execution_started_records_id tests/ui_and_conv/test_tool_call_block.py::test_finish_sub_tool_call_cleans_up_output_state -v 2>&1 | tail -20
```

Expected: `AttributeError` — `_ToolCallBlock` has no `_subagent_output_parts`.

- [ ] **Step 3: Add constants and new fields to `_ToolCallBlock`**

In `src/pythinker_code/ui/shell/visualize/_blocks.py`, add two constants near the top (after the existing `MAX_SUBAGENT_TOOL_CALLS_TO_SHOW = 4` line):

```python
_MAX_RUNNING_ROWS = 2
_MAX_SUB_OUTPUT_CHARS = 200
```

In `_ToolCallBlock.__init__`, after the `self._is_background_pending: bool = False` line, add:

```python
self._subagent_output_parts: dict[str, list[str]] = {}
self._subagent_output_had_stderr: dict[str, bool] = {}
self._subagent_execution_started: set[str] = set()
```

- [ ] **Step 4: Add `mark_sub_execution_started` method**

Add after the existing `set_subagent_metadata` method (~line 506):

```python
def mark_sub_execution_started(self, tool_call_id: str) -> None:
    if tool_call_id not in self._ongoing_subagent_tool_calls:
        return
    self._subagent_execution_started.add(tool_call_id)
    self._renderable = self._compose()
```

- [ ] **Step 5: Add `append_sub_output_part` method**

Add directly after `mark_sub_execution_started`:

```python
def append_sub_output_part(
    self, tool_call_id: str, text: str, *, stream: str = "output"
) -> None:
    if tool_call_id not in self._ongoing_subagent_tool_calls:
        return
    parts = self._subagent_output_parts.setdefault(tool_call_id, [])
    parts.append(text)
    if stream == "stderr":
        self._subagent_output_had_stderr[tool_call_id] = True
    combined = "".join(parts)
    if len(combined) > _MAX_SUB_OUTPUT_CHARS:
        self._subagent_output_parts[tool_call_id] = [combined[-_MAX_SUB_OUTPUT_CHARS:]]
    self._renderable = self._compose()
```

- [ ] **Step 6: Update `finish_sub_tool_call` to clean up new state**

In the existing `finish_sub_tool_call` method, add three cleanup lines right after `self._last_subagent_tool_call = None`:

```python
def finish_sub_tool_call(self, tool_result: ToolResult):
    self._last_subagent_tool_call = None
    self._subagent_output_parts.pop(tool_result.tool_call_id, None)      # NEW
    self._subagent_output_had_stderr.pop(tool_result.tool_call_id, None) # NEW
    self._subagent_execution_started.discard(tool_result.tool_call_id)   # NEW
    sub_tool_call = self._ongoing_subagent_tool_calls.pop(tool_result.tool_call_id, None)
    if sub_tool_call is None:
        return
    self._finished_subagent_tool_calls.append(
        _ToolCallBlock.FinishedSubCall(
            call=sub_tool_call,
            result=tool_result.return_value,
        )
    )
    self._n_finished_subagent_tool_calls += 1
    self._renderable = self._compose()
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd /home/ai/Projects/pythinker-code-main
python -m pytest tests/ui_and_conv/test_tool_call_block.py -v 2>&1 | tail -25
```

Expected: all tests pass including all 7 new ones.

- [ ] **Step 8: Commit**

```bash
git add src/pythinker_code/ui/shell/visualize/_blocks.py tests/ui_and_conv/test_tool_call_block.py
git commit -m "feat(blocks): add subagent output tracking state and methods to _ToolCallBlock"
```

---

### Task 2: Render running rows and output preview in `_compose()`

**Files:**
- Modify: `src/pythinker_code/ui/shell/visualize/_blocks.py`
- Test: `tests/ui_and_conv/test_tool_call_block.py`

- [ ] **Step 1: Write failing tests for running-row rendering**

Add to `tests/ui_and_conv/test_tool_call_block.py`:

```python
def test_running_agent_shows_ongoing_sub_tool_calls():
    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    call = _tool_call_with_id("sub-1", "Read", '{"file_path":"src/app.py"}')
    block.append_sub_tool_call(call)
    output = _plain(block.compose())
    assert "Read" in output
    assert "src/app.py" in output


def test_running_agent_shows_streamed_output_preview():
    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    call = _tool_call_with_id("sub-1", "Bash", '{"command":"grep -r TODO ."}')
    block.append_sub_tool_call(call)
    block.append_sub_output_part("sub-1", "src/app.py:42: # TODO: fix\n")
    output = _plain(block.compose())
    assert "src/app.py:42" in output


def test_running_agent_shows_only_last_4_output_lines():
    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    call = _tool_call_with_id("sub-1", "Bash", '{"command":"find ."}')
    block.append_sub_tool_call(call)
    lines = [f"line{i}\n" for i in range(10)]
    block.append_sub_output_part("sub-1", "".join(lines))
    output = _plain(block.compose())
    # Only last 4 lines should appear
    assert "line9" in output
    assert "line6" in output
    assert "line5" not in output
    assert "line0" not in output


def test_running_agent_caps_visible_running_rows_at_2():
    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    for i in range(5):
        call = _tool_call_with_id(f"sub-{i}", "Read", f'{{"file_path":"src/file{i}.py"}}')
        block.append_sub_tool_call(call)
    output = _plain(block.compose())
    # "… N more running" indicator must appear
    assert "more running" in output


def test_finished_sub_tool_calls_not_shown_in_output_preview():
    from pythinker_code.wire.types import ToolResult
    from pythinker_core.tooling import ToolOk

    block = _ToolCallBlock(_tool_call("Agent", '{"description":"scan"}'))
    call = _tool_call_with_id("sub-1", "Bash", '{"command":"ls"}')
    block.append_sub_tool_call(call)
    block.append_sub_output_part("sub-1", "SHOULD_NOT_APPEAR\n")
    block.finish_sub_tool_call(ToolResult(tool_call_id="sub-1", return_value=ToolOk(output="")))
    output = _plain(block.compose())
    assert "SHOULD_NOT_APPEAR" not in output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ai/Projects/pythinker-code-main
python -m pytest tests/ui_and_conv/test_tool_call_block.py::test_running_agent_shows_ongoing_sub_tool_calls tests/ui_and_conv/test_tool_call_block.py::test_running_agent_shows_streamed_output_preview -v 2>&1 | tail -20
```

Expected: FAIL — ongoing sub-tool calls are not yet rendered.

- [ ] **Step 3: Update `_compose()` to render running rows and output preview**

In `src/pythinker_code/ui/shell/visualize/_blocks.py`, find the block starting with:
```python
if not (style.label == "Subagent" and self._result is not None):
    rows: list[ActivityRow] = []
    for sub_call, sub_result in self._finished_subagent_tool_calls:
        ...
    if rows:
        children.append(render_activity_tree(rows, width=current_console_width()))
```

Replace the entire `if not (style.label == "Subagent" and self._result is not None):` block with:

```python
if not (style.label == "Subagent" and self._result is not None):
    # Finished sub-tool call rows
    rows: list[ActivityRow] = []
    for sub_call, sub_result in self._finished_subagent_tool_calls:
        argument = extract_key_argument(
            sub_call.function.arguments or "", sub_call.function.name
        )
        detail = sub_call.function.name
        if argument:
            detail = f"{detail} {argument}"
        rows.append(
            ActivityRow(
                label="agent",
                detail=detail,
                state="failed" if sub_result.is_error else "completed",
            )
        )

    # Running sub-tool call rows (shown above finished rows)
    ongoing = list(self._ongoing_subagent_tool_calls.values())
    n_hidden_running = max(0, len(ongoing) - _MAX_RUNNING_ROWS)
    visible_running = ongoing[-_MAX_RUNNING_ROWS:]
    running_rows: list[ActivityRow] = []
    for call in visible_running:
        argument = extract_key_argument(
            call.function.arguments or "", call.function.name
        )
        detail = call.function.name
        if argument:
            detail = f"{detail} {argument}"
        running_rows.append(ActivityRow(label="agent", detail=detail, state="running"))

    if n_hidden_running:
        children.append(fg("muted", f"… {n_hidden_running} more running"))

    combined_rows = running_rows + rows
    if combined_rows:
        children.append(render_activity_tree(combined_rows, width=current_console_width()))

    # Output preview for the most-recent ongoing call that has streamed output
    latest = self._last_subagent_tool_call
    if latest is not None and latest.id in self._subagent_output_parts:
        combined_output = "".join(self._subagent_output_parts[latest.id]).rstrip("\n")
        if combined_output:
            is_stderr = self._subagent_output_had_stderr.get(latest.id, False)
            output_style = "error" if is_stderr else "muted"
            preview = _tail_lines(combined_output, 4)
            max_line_width = max(1, current_console_width() - 6)
            for line in preview.splitlines():
                truncated = _truncate_to_display_width(line, max_line_width)
                children.append(fg(output_style, f"│  {truncated}"))
```

- [ ] **Step 4: Run all tool_call_block tests**

```bash
cd /home/ai/Projects/pythinker-code-main
python -m pytest tests/ui_and_conv/test_tool_call_block.py -v 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 5: Run the full UI test suite to check for regressions**

```bash
cd /home/ai/Projects/pythinker-code-main
python -m pytest tests/ui_and_conv/ -v 2>&1 | tail -40
```

Expected: all pass. If any snapshot tests fail due to changed rendering, update them with `pytest --snapshot-update` — but review the diff first to make sure the new output is correct.

- [ ] **Step 6: Commit**

```bash
git add src/pythinker_code/ui/shell/visualize/_blocks.py tests/ui_and_conv/test_tool_call_block.py
git commit -m "feat(blocks): render running subagent tool calls and output preview in Agent card"
```

---

### Task 3: Wire events through `_live_view.py`

**Files:**
- Modify: `src/pythinker_code/ui/shell/visualize/_live_view.py`
- Test: `tests/ui_and_conv/test_subagent_live_stream.py` (new file)

- [ ] **Step 1: Write failing integration tests**

Create `tests/ui_and_conv/test_subagent_live_stream.py`:

```python
"""Integration tests for subagent ToolOutputPart and ToolExecutionStarted wiring."""

from __future__ import annotations

from pythinker_core.message import ToolCall
from pythinker_core.tooling import ToolOk
from rich.console import Console

from pythinker_code.ui.shell.visualize import _LiveView
from pythinker_code.wire.types import (
    StatusUpdate,
    SubagentEvent,
    ToolCall as WireToolCall,
    ToolExecutionStarted,
    ToolOutputPart,
    ToolResult,
    TurnBegin,
)


def _render(view: _LiveView, *, width: int = 100) -> str:
    console = Console(width=width, record=True, highlight=False, color_system=None)
    console.print(view.compose())
    return console.export_text()


def _agent_call(call_id: str = "agent-1") -> WireToolCall:
    return WireToolCall(
        id=call_id,
        function=WireToolCall.FunctionBody(
            name="Agent",
            arguments='{"description":"security scan","subagent_type":"security-reviewer","prompt":"check it"}',
        ),
    )


def _sub_tool_call(sub_id: str, name: str, args: str) -> ToolCall:
    return ToolCall(
        id=sub_id,
        function=ToolCall.FunctionBody(name=name, arguments=args),
    )


def test_subagent_tool_output_part_appears_in_live_view():
    view = _LiveView(StatusUpdate(context_tokens=1000))
    view.dispatch_wire_message(TurnBegin(user_input="scan"))
    view.dispatch_wire_message(_agent_call())

    sub_call = _sub_tool_call("sub-1", "Bash", '{"command":"grep -r TODO ."}')
    view.dispatch_wire_message(
        SubagentEvent(
            parent_tool_call_id="agent-1",
            agent_id="a1",
            subagent_type="security-reviewer",
            event=sub_call,
        )
    )
    view.dispatch_wire_message(
        SubagentEvent(
            parent_tool_call_id="agent-1",
            agent_id="a1",
            subagent_type="security-reviewer",
            event=ToolOutputPart(tool_call_id="sub-1", text="src/app.py:42: # TODO\n"),
        )
    )

    output = _render(view)
    assert "src/app.py:42" in output


def test_subagent_tool_execution_started_tracked():
    view = _LiveView(StatusUpdate(context_tokens=1000))
    view.dispatch_wire_message(TurnBegin(user_input="scan"))
    view.dispatch_wire_message(_agent_call())

    sub_call = _sub_tool_call("sub-1", "Read", '{"file_path":"src/app.py"}')
    view.dispatch_wire_message(
        SubagentEvent(
            parent_tool_call_id="agent-1",
            agent_id="a1",
            subagent_type="security-reviewer",
            event=sub_call,
        )
    )
    view.dispatch_wire_message(
        SubagentEvent(
            parent_tool_call_id="agent-1",
            agent_id="a1",
            subagent_type="security-reviewer",
            event=ToolExecutionStarted(tool_call_id="sub-1"),
        )
    )

    block = view._tool_call_blocks["agent-1"]
    assert "sub-1" in block._subagent_execution_started


def test_output_part_for_unknown_parent_is_silently_ignored():
    view = _LiveView(StatusUpdate(context_tokens=1000))
    view.dispatch_wire_message(TurnBegin(user_input="scan"))
    # No agent tool call dispatched — parent_tool_call_id won't resolve
    view.dispatch_wire_message(
        SubagentEvent(
            parent_tool_call_id="nonexistent-agent",
            agent_id="a1",
            subagent_type="security-reviewer",
            event=ToolOutputPart(tool_call_id="sub-1", text="should be ignored\n"),
        )
    )
    # Must not raise; compose must still work
    output = _render(view)
    assert "should be ignored" not in output


def test_output_cleared_after_sub_tool_call_finishes():
    view = _LiveView(StatusUpdate(context_tokens=1000))
    view.dispatch_wire_message(TurnBegin(user_input="scan"))
    view.dispatch_wire_message(_agent_call())

    sub_call = _sub_tool_call("sub-1", "Bash", '{"command":"ls"}')
    view.dispatch_wire_message(
        SubagentEvent(
            parent_tool_call_id="agent-1",
            agent_id="a1",
            subagent_type="security-reviewer",
            event=sub_call,
        )
    )
    view.dispatch_wire_message(
        SubagentEvent(
            parent_tool_call_id="agent-1",
            agent_id="a1",
            subagent_type="security-reviewer",
            event=ToolOutputPart(tool_call_id="sub-1", text="SHOULD_DISAPPEAR\n"),
        )
    )
    view.dispatch_wire_message(
        SubagentEvent(
            parent_tool_call_id="agent-1",
            agent_id="a1",
            subagent_type="security-reviewer",
            event=ToolResult(tool_call_id="sub-1", return_value=ToolOk(output="")),
        )
    )

    output = _render(view)
    assert "SHOULD_DISAPPEAR" not in output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ai/Projects/pythinker-code-main
python -m pytest tests/ui_and_conv/test_subagent_live_stream.py -v 2>&1 | tail -20
```

Expected: `test_subagent_tool_output_part_appears_in_live_view` FAILS because the output text is never forwarded.

- [ ] **Step 3: Update `handle_subagent_event` in `_live_view.py`**

In `src/pythinker_code/ui/shell/visualize/_live_view.py`, find the `handle_subagent_event` method. Locate the match arm:

```python
case ToolExecutionStarted() | ToolOutputPart():
    # Nested subagent execution/output streaming is intentionally
    # summarized at the parent Agent-card level for now.
    self.refresh_soon()
```

Replace it with two separate arms:

```python
case ToolExecutionStarted() as started:
    block.mark_sub_execution_started(started.tool_call_id)
    self.refresh_soon()
case ToolOutputPart() as output_part:
    block.append_sub_output_part(
        output_part.tool_call_id,
        output_part.text,
        stream=output_part.stream,
    )
    self.refresh_soon()
```

- [ ] **Step 4: Run new integration tests**

```bash
cd /home/ai/Projects/pythinker-code-main
python -m pytest tests/ui_and_conv/test_subagent_live_stream.py -v 2>&1 | tail -20
```

Expected: all 4 tests pass.

- [ ] **Step 5: Run the full test suite**

```bash
cd /home/ai/Projects/pythinker-code-main
python -m pytest tests/ -x -q 2>&1 | tail -30
```

Expected: all pass. If snapshot tests diverge, inspect the diffs and update snapshots only if the new output is correct.

- [ ] **Step 6: Commit**

```bash
git add src/pythinker_code/ui/shell/visualize/_live_view.py tests/ui_and_conv/test_subagent_live_stream.py
git commit -m "feat(live-view): stream subagent ToolOutputPart and ToolExecutionStarted into Agent card"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task covering it |
|---|---|
| §1: Forward `ToolExecutionStarted` and `ToolOutputPart` via new block methods | Task 3 |
| §2: `_subagent_output_parts`, `_subagent_output_had_stderr`, `_subagent_execution_started` fields | Task 1 |
| §2: `mark_sub_execution_started`, `append_sub_output_part` methods | Task 1 |
| §2: `finish_sub_tool_call` cleans up new fields | Task 1 |
| §3: Running rows rendered above finished rows with shimmer | Task 2 |
| §3: Output preview — last 4 lines, `│  ` prefix, muted/error style | Task 2 |
| §3: Cap at 2 running rows, show `… N more running` | Task 2 |
| §3: Output buffer discarded on finish | Task 1 (method) + Task 2 (test) |
| §4: Partial args → show bare tool name | Covered by `extract_key_argument` returning `None` — Task 2 test indirectly |
| §4: `ToolOutputPart` for unknown call discarded | Task 3 test `test_output_part_for_unknown_parent_is_silently_ignored` |
| §4: Buffer capped at 200 chars | Task 1 test `test_append_sub_output_part_caps_buffer_at_200_chars` |
| §4: Card style unchanged | `_compose_card()` not touched — confirmed |

**Placeholder scan:** No TBDs, TODOs, or "similar to" references found.

**Type consistency:**
- `mark_sub_execution_started(tool_call_id: str)` — used by name in Task 3 wiring ✓
- `append_sub_output_part(tool_call_id, text, *, stream)` — used by name in Task 3 wiring ✓
- `_subagent_execution_started: set[str]` — checked in Task 3 test ✓
- `_MAX_RUNNING_ROWS = 2`, `_MAX_SUB_OUTPUT_CHARS = 200` — defined in Task 1 §3, used in Task 2 §3 ✓
