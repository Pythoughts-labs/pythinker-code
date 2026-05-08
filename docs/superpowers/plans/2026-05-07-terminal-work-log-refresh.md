# Terminal Work-Log Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an OpenCode-inspired, Pythinker-native terminal work-log renderer for live tool activity, completed output cards, plan panels, and status lines.

**Architecture:** Keep the existing Rich/prompt-toolkit and Wire event flow. Add a private `_worklog.py` render-helper module under `src/pythinker_code/ui/shell/visualize/`, then integrate it surgically into `_blocks.py` and `_live_view.py` without changing tool execution or protocol semantics.

**Tech Stack:** Python 3.14, Rich renderables, prompt-toolkit shell UI, Pythinker Wire event types, pytest with Rich console capture.

---

## File Structure

- Create `src/pythinker_code/ui/shell/visualize/_worklog.py`: private Rich render helpers for work-log rows, cards, tool style mapping, status classification, and display block rendering.
- Modify `src/pythinker_code/ui/shell/visualize/_blocks.py`: use `_worklog.py` from `_ToolCallBlock`, `_StatusBlock`, and content activity labels while preserving existing streaming and flush behavior.
- Modify `src/pythinker_code/ui/shell/visualize/_live_view.py`: align MCP, compaction, side-question, and plan panel labels/cards with the new work-log language.
- Modify `src/pythinker_code/ui/shell/visualize/__init__.py`: re-export private helpers used by tests only if needed.
- Keep `src/pythinker_code/ui/shell/__init__.py`: startup welcome already says `Welcome to Pythinker Code!`; do not broaden product renaming in this task.
- Create `tests/ui_and_conv/test_worklog_render.py`: pure render tests for `_worklog.py`.
- Modify `tests/ui_and_conv/test_tool_call_block.py`: cover `_ToolCallBlock` running/completed/error/subagent rendering through Rich capture.
- Modify `tests/ui_and_conv/test_status_block.py`: cover status footer behavior with MCP status snapshots.
- Keep `tests/ui_and_conv/test_shell_welcome_info.py`: validates startup product name.

## Task 1: Work-Log Helper Module

**Files:**
- Create: `src/pythinker_code/ui/shell/visualize/_worklog.py`
- Create: `tests/ui_and_conv/test_worklog_render.py`

- [ ] **Step 1: Write failing tests for tool style and plain row rendering**

Add this file:

```python
from __future__ import annotations

from rich.console import Console

from pythinker_code.ui.shell.visualize._worklog import (
    WorkLogState,
    render_worklog_entry,
    tool_style,
)


def _plain(renderable) -> str:
    console = Console(record=True, width=120, color_system=None)
    console.print(renderable)
    return console.export_text()


def test_tool_style_maps_common_tools_to_professional_labels():
    assert tool_style("ReadFile").label == "Read"
    assert tool_style("Grep").label == "Search"
    assert tool_style("Edit").label == "Edit"
    assert tool_style("ApplyPatch").label == "Patch"
    assert tool_style("Bash").label == "Shell"
    assert tool_style("TodoWrite").label == "Todo"
    assert tool_style("Agent").label == "Subagent"
    assert tool_style("AskUser").label == "Ask"
    assert tool_style("UnknownTool").label == "UnknownTool"


def test_running_entry_shows_state_label_tool_and_target():
    output = _plain(
        render_worklog_entry(
            label="Read",
            target="src/app.py",
            state=WorkLogState.RUNNING,
        )
    )

    assert "Read" in output
    assert "src/app.py" in output
    assert "running" in output.lower()


def test_failed_entry_shows_error_without_raw_payload_dump():
    output = _plain(
        render_worklog_entry(
            label="Shell",
            target="pytest tests/unit",
            state=WorkLogState.FAILED,
            detail="Command failed with exit code 1",
        )
    )

    assert "Shell" in output
    assert "pytest tests/unit" in output
    assert "failed" in output.lower()
    assert "Command failed with exit code 1" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ui_and_conv/test_worklog_render.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'pythinker_code.ui.shell.visualize._worklog'`.

- [ ] **Step 3: Implement minimal `_worklog.py` with states, style mapping, and entries**

Create `src/pythinker_code/ui/shell/visualize/_worklog.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text


class WorkLogState(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class ToolStyle:
    label: str
    icon: str
    style: str


_TOOL_STYLES: dict[str, ToolStyle] = {
    "Read": ToolStyle("Read", "→", "cyan"),
    "ReadFile": ToolStyle("Read", "→", "cyan"),
    "Grep": ToolStyle("Search", "✱", "blue"),
    "Glob": ToolStyle("Find", "✱", "blue"),
    "Edit": ToolStyle("Edit", "←", "magenta"),
    "Replace": ToolStyle("Edit", "←", "magenta"),
    "Write": ToolStyle("Write", "←", "magenta"),
    "WriteFile": ToolStyle("Write", "←", "magenta"),
    "ApplyPatch": ToolStyle("Patch", "◆", "magenta"),
    "Bash": ToolStyle("Shell", "$", "green"),
    "Shell": ToolStyle("Shell", "$", "green"),
    "TodoWrite": ToolStyle("Todo", "☑", "yellow"),
    "Agent": ToolStyle("Subagent", "│", "cyan"),
    "Task": ToolStyle("Subagent", "│", "cyan"),
    "AskUser": ToolStyle("Ask", "?", "yellow"),
    "FetchURL": ToolStyle("Fetch", "%", "blue"),
    "WebFetch": ToolStyle("Fetch", "%", "blue"),
    "WebSearch": ToolStyle("Search", "◈", "blue"),
    "Skill": ToolStyle("Skill", "◇", "cyan"),
}


_STATE_STYLE = {
    WorkLogState.RUNNING: "bright_white",
    WorkLogState.COMPLETED: "grey50",
    WorkLogState.FAILED: "red",
    WorkLogState.DENIED: "grey50 strike",
    WorkLogState.INTERRUPTED: "yellow",
}


def tool_style(name: str) -> ToolStyle:
    return _TOOL_STYLES.get(name, ToolStyle(name, "⚙", "blue"))


def denied_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        needle in lowered
        for needle in (
            "questionrejectederror",
            "rejected permission",
            "specified a rule",
            "user dismissed",
            "denied",
        )
    )


def render_worklog_entry(
    *,
    label: str,
    target: str | None = None,
    state: WorkLogState,
    detail: str | None = None,
    icon: str = "•",
    icon_style: str = "blue",
    children: list[RenderableType] | None = None,
) -> RenderableType:
    line = Text()
    line.append(icon, style=icon_style)
    line.append(" ")
    line.append(label, style="bold")
    if target:
        line.append(" ")
        line.append(target, style="grey70")
    line.append(" ")
    line.append(state.value, style=_STATE_STYLE[state])
    if detail:
        line.append(" · ", style="grey50")
        line.append(detail, style=_STATE_STYLE[state])
    if not children:
        return line
    return Group(line, *children)


def render_worklog_card(
    title: str,
    body: RenderableType,
    *,
    subtitle: str | None = None,
    border_style: str = "grey39",
) -> Panel:
    return Panel(
        body,
        title=title,
        title_align="left",
        subtitle=subtitle,
        subtitle_align="left",
        border_style=border_style,
        padding=(0, 1),
        expand=False,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ui_and_conv/test_worklog_render.py -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint if commits were explicitly requested**

Run only if the user explicitly requested commits: `git add src/pythinker_code/ui/shell/visualize/_worklog.py tests/ui_and_conv/test_worklog_render.py && git commit -m "feat(ui): add terminal work-log render helpers"`.

## Task 2: Display Block Cards

**Files:**
- Modify: `src/pythinker_code/ui/shell/visualize/_worklog.py`
- Modify: `tests/ui_and_conv/test_worklog_render.py`

- [ ] **Step 1: Add failing tests for todo, background task, brief, and diff cards**

Append these tests to `tests/ui_and_conv/test_worklog_render.py`:

```python
from pythinker_core.tooling import BriefDisplayBlock

from pythinker_code.tools.display import (
    BackgroundTaskDisplayBlock,
    DiffDisplayBlock,
    TodoDisplayBlock,
    TodoDisplayItem,
)
from pythinker_code.ui.shell.visualize._worklog import render_display_blocks


def test_todo_display_block_renders_statuses_as_card():
    output = _plain(
        render_display_blocks(
            [
                TodoDisplayBlock(
                    items=[
                        TodoDisplayItem(title="Inspect UI", status="done"),
                        TodoDisplayItem(title="Polish tools", status="in_progress"),
                        TodoDisplayItem(title="Run checks", status="pending"),
                    ]
                )
            ]
        )[0]
    )

    assert "Todos" in output
    assert "Inspect UI" in output
    assert "Polish tools" in output
    assert "Run checks" in output


def test_background_task_display_block_renders_compact_card():
    output = _plain(
        render_display_blocks(
            [
                BackgroundTaskDisplayBlock(
                    task_id="task-1",
                    kind="test",
                    status="running",
                    description="Run focused tests",
                )
            ]
        )[0]
    )

    assert "Background task" in output
    assert "task-1" in output
    assert "running" in output
    assert "Run focused tests" in output


def test_brief_display_block_renders_report_card_when_multiline():
    output = _plain(render_display_blocks([BriefDisplayBlock(text="Line one\n\nLine two")])[0])

    assert "Report" in output
    assert "Line one" in output
    assert "Line two" in output


def test_consecutive_diff_blocks_for_same_file_render_one_card():
    cards = render_display_blocks(
        [
            DiffDisplayBlock(path="src/app.py", old_text="a", new_text="b"),
            DiffDisplayBlock(path="src/app.py", old_text="x", new_text="x\ny"),
        ]
    )
    output = _plain(cards[0])

    assert len(cards) == 1
    assert "src/app.py" in output
    assert "+" in output
    assert "-" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ui_and_conv/test_worklog_render.py -q`

Expected: FAIL with `ImportError` or `AttributeError` for `render_display_blocks`.

- [ ] **Step 3: Implement display block renderer**

Add these imports and functions to `_worklog.py`:

```python
from pythinker_core.tooling import BriefDisplayBlock, DisplayBlock

from pythinker_code.tools.display import BackgroundTaskDisplayBlock, DiffDisplayBlock, TodoDisplayBlock
from pythinker_code.utils.rich.diff_render import collect_diff_hunks, render_diff_panel, render_diff_summary_panel
from pythinker_code.utils.rich.markdown import Markdown
```

Add this implementation below `render_worklog_card`:

```python
def render_display_blocks(display: list[DisplayBlock], *, is_error: bool = False) -> list[RenderableType]:
    rendered: list[RenderableType] = []
    idx = 0
    while idx < len(display):
        block = display[idx]
        if isinstance(block, DiffDisplayBlock):
            path = block.path
            diff_blocks: list[DiffDisplayBlock] = []
            while idx < len(display):
                candidate = display[idx]
                if not isinstance(candidate, DiffDisplayBlock) or candidate.path != path:
                    break
                diff_blocks.append(candidate)
                idx += 1
            if any(item.is_summary for item in diff_blocks):
                rendered.append(render_worklog_card("Diff", render_diff_summary_panel(path, diff_blocks), subtitle=path))
                continue
            hunks, added_total, removed_total = collect_diff_hunks(diff_blocks)
            if hunks:
                rendered.append(
                    render_worklog_card(
                        f"Diff +{added_total} -{removed_total}",
                        render_diff_panel(path, hunks, added_total, removed_total),
                        subtitle=path,
                    )
                )
            continue
        if isinstance(block, BriefDisplayBlock):
            text = block.text.strip()
            if text:
                title = "Error" if is_error else "Report"
                style = "red" if is_error else "grey70"
                if "\n" in text or len(text) > 100:
                    rendered.append(render_worklog_card(title, Markdown(text, style=style), border_style="red" if is_error else "grey39"))
                else:
                    rendered.append(Markdown(text, style=style))
            idx += 1
            continue
        if isinstance(block, TodoDisplayBlock):
            lines = []
            for todo in block.items:
                match todo.status:
                    case "done":
                        marker = "✓"
                    case "in_progress":
                        marker = "→"
                    case _:
                        marker = "·"
                lines.append(f"{marker} {todo.title}")
            rendered.append(render_worklog_card("Todos", Text("\n".join(lines), style="grey70")))
            idx += 1
            continue
        if isinstance(block, BackgroundTaskDisplayBlock):
            rendered.append(
                render_worklog_card(
                    "Background task",
                    Text(f"{block.task_id} [{block.status}] {block.kind}: {block.description}", style="grey70"),
                )
            )
            idx += 1
            continue
        idx += 1
    return rendered
```

- [ ] **Step 4: Run display renderer tests**

Run: `uv run pytest tests/ui_and_conv/test_worklog_render.py -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint if commits were explicitly requested**

Run only if the user explicitly requested commits: `git add src/pythinker_code/ui/shell/visualize/_worklog.py tests/ui_and_conv/test_worklog_render.py && git commit -m "feat(ui): render work-log display cards"`.

## Task 3: Integrate Tool Call Blocks

**Files:**
- Modify: `src/pythinker_code/ui/shell/visualize/_blocks.py`
- Modify: `tests/ui_and_conv/test_tool_call_block.py`

- [ ] **Step 1: Add failing tests for running, completed, failed, denied, and display-card tool calls**

Append to `tests/ui_and_conv/test_tool_call_block.py`:

```python
from rich.console import Console
from pythinker_core.message import ToolCall
from pythinker_core.tooling import BriefDisplayBlock, ToolError, ToolOk, ToolResult


def _plain(renderable) -> str:
    console = Console(record=True, width=120, color_system=None)
    console.print(renderable)
    return console.export_text()


def _tool_call(name: str, arguments: str = "{}") -> ToolCall:
    return ToolCall(id=f"tc-{name}", function=ToolCall.FunctionBody(name=name, arguments=arguments))


def test_tool_call_block_renders_running_worklog_entry():
    block = _ToolCallBlock(_tool_call("ReadFile", '{"file_path":"src/app.py"}'))
    output = _plain(block.compose())

    assert "Read" in output
    assert "src/app.py" in output
    assert "running" in output.lower()


def test_tool_call_block_renders_completed_worklog_entry():
    block = _ToolCallBlock(_tool_call("Grep", '{"pattern":"FIXME"}'))
    block.finish(ToolOk(output=""))
    output = _plain(block.compose())

    assert "Search" in output
    assert "FIXME" in output
    assert "completed" in output.lower()


def test_tool_call_block_renders_failed_worklog_entry():
    block = _ToolCallBlock(_tool_call("Bash", '{"command":"pytest"}'))
    block.finish(ToolError(message="exit code 1", brief="failed"))
    output = _plain(block.compose())

    assert "Shell" in output
    assert "pytest" in output
    assert "failed" in output.lower()
    assert "exit code 1" in output


def test_tool_call_block_renders_denied_as_denied_not_failed():
    block = _ToolCallBlock(_tool_call("Bash", '{"command":"rm -rf /"}'))
    block.finish(ToolError(message="user dismissed permission", brief="denied"))
    output = _plain(block.compose())

    assert "Shell" in output
    assert "denied" in output.lower()
    assert "failed" not in output.lower()


def test_tool_call_block_renders_display_cards_under_completed_entry():
    block = _ToolCallBlock(_tool_call("Bash", '{"command":"pytest"}'))
    block.finish(ToolOk(output="", display=[BriefDisplayBlock(text="Tests passed\n\nAll clear")]))
    output = _plain(block.compose())

    assert "Shell" in output
    assert "Report" in output
    assert "Tests passed" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ui_and_conv/test_tool_call_block.py -q`

Expected: FAIL because current `_ToolCallBlock` uses `Used/Using` text and does not render work-log states.

- [ ] **Step 3: Import work-log helpers in `_blocks.py`**

In `src/pythinker_code/ui/shell/visualize/_blocks.py`, add:

```python
from pythinker_code.ui.shell.visualize._worklog import (
    WorkLogState,
    denied_error,
    render_display_blocks,
    render_worklog_entry,
    tool_style,
)
```

- [ ] **Step 4: Replace `_ToolCallBlock._compose` result rendering**

In `_ToolCallBlock._compose`, keep the existing subagent collection logic but replace the final return section with this shape:

```python
        style = tool_style(self._tool_name)
        children = lines[1:]
        if self._result is None:
            return render_worklog_entry(
                label=style.label,
                target=self._argument,
                state=WorkLogState.RUNNING,
                icon=style.icon,
                icon_style=style.style,
                children=children,
            )

        error_message = self._result.message if self._result.is_error else ""
        if self._result.is_error and not error_message:
            error_message = getattr(self._result, "brief", "") or "Tool failed"
        state = (
            WorkLogState.DENIED
            if self._result.is_error and denied_error(error_message)
            else WorkLogState.FAILED
            if self._result.is_error
            else WorkLogState.COMPLETED
        )
        children.extend(render_display_blocks(self._result.display, is_error=self._result.is_error))
        return render_worklog_entry(
            label=style.label,
            target=self._argument,
            state=state,
            detail=error_message if self._result.is_error else None,
            icon=style.icon,
            icon_style=style.style,
            children=children,
        )
```

Then remove the old `display = self._result.display` loop from `_ToolCallBlock._compose`; `render_display_blocks` now owns display-block rendering.

- [ ] **Step 5: Update `_build_headline_text` or stop using it**

If `_compose` no longer uses `_build_headline_text`, remove `_build_headline_text`. Keep `_extract_full_url` because existing tests cover it.

- [ ] **Step 6: Run tool call block tests**

Run: `uv run pytest tests/ui_and_conv/test_tool_call_block.py tests/ui_and_conv/test_worklog_render.py -q`

Expected: PASS.

- [ ] **Step 7: Commit checkpoint if commits were explicitly requested**

Run only if the user explicitly requested commits: `git add src/pythinker_code/ui/shell/visualize/_blocks.py tests/ui_and_conv/test_tool_call_block.py && git commit -m "feat(ui): apply work-log tool rendering"`.

## Task 4: Live Activity And Status Lines

**Files:**
- Modify: `src/pythinker_code/ui/shell/visualize/_blocks.py`
- Modify: `src/pythinker_code/ui/shell/visualize/_live_view.py`
- Modify: `tests/ui_and_conv/test_status_block.py`
- Modify: `tests/ui_and_conv/test_streaming_content_block.py`

- [ ] **Step 1: Add failing tests for status footer with MCP data**

Append to `tests/ui_and_conv/test_status_block.py`:

```python
from pythinker_code.wire.types import MCPServerSnapshot, MCPStatusSnapshot


def test_status_block_shows_mcp_loading_summary():
    block = _StatusBlock(StatusUpdate())
    block.update(
        StatusUpdate(
            mcp_status=MCPStatusSnapshot(
                loading=True,
                connected=1,
                total=2,
                tools=7,
                servers=(
                    MCPServerSnapshot(name="github", status="connected", tools=("issue",)),
                    MCPServerSnapshot(name="docs", status="connecting", tools=()),
                ),
            )
        )
    )

    assert "MCP" in block.text.plain
    assert "1/2" in block.text.plain
    assert "7 tools" in block.text.plain
```

- [ ] **Step 2: Add failing test for composing label**

Append to `tests/ui_and_conv/test_streaming_content_block.py`:

```python
def test_composing_live_label_uses_professional_activity_wording():
    block = _ContentBlock(is_think=False)
    block.append("hello")
    renderable = block.compose()

    assert "Composing" in str(renderable.text)
    assert "tokens" in str(renderable.text)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/ui_and_conv/test_status_block.py tests/ui_and_conv/test_streaming_content_block.py -q`

Expected: FAIL for MCP status text if not rendered yet; the composing-label test may pass if current text already matches, which is acceptable because it locks behavior.

- [ ] **Step 4: Update `_StatusBlock` to retain and render MCP status**

In `_StatusBlock.__init__`, add:

```python
        self._mcp_status: MCPStatusSnapshot | None = None
```

In `_StatusBlock.update`, add handling before the final text update:

```python
        if status.mcp_status is not None:
            self._mcp_status = status.mcp_status
```

Replace the `if status.context_usage is not None:` render block with:

```python
        parts: list[str] = []
        if self._context_usage or self._max_context_tokens:
            parts.append(
                format_context_status(
                    self._context_usage,
                    self._context_tokens,
                    self._max_context_tokens,
                )
            )
        if self._mcp_status is not None and self._mcp_status.loading:
            parts.append(
                f"MCP {self._mcp_status.connected}/{self._mcp_status.total} · "
                f"{self._mcp_status.tools} tools"
            )
        self.text.plain = "  ".join(parts)
```

Make sure `_blocks.py` imports `MCPStatusSnapshot` from `pythinker_code.wire.types` if needed for typing.

- [ ] **Step 5: Align LiveView spinner labels**

In `_live_view.py`, update these cases:

```python
            case CompactionBegin():
                self._compacting_spinner = Spinner("dots", "Compacting context...")
                self.refresh_soon()
```

```python
            case MCPLoadingBegin():
                self._mcp_loading_spinner = Spinner("dots", "Connecting MCP servers...")
                self.refresh_soon()
```

```python
            case BtwBegin(question=question):
                truncated = (question[:40] + "...") if len(question) > 40 else question
                self._btw_question = question
                self._btw_spinner = Spinner("dots", f"Side question... {rich_escape(truncated)}")
                self.refresh_soon()
```

- [ ] **Step 6: Run live/status tests**

Run: `uv run pytest tests/ui_and_conv/test_status_block.py tests/ui_and_conv/test_streaming_content_block.py -q`

Expected: PASS.

- [ ] **Step 7: Commit checkpoint if commits were explicitly requested**

Run only if the user explicitly requested commits: `git add src/pythinker_code/ui/shell/visualize/_blocks.py src/pythinker_code/ui/shell/visualize/_live_view.py tests/ui_and_conv/test_status_block.py tests/ui_and_conv/test_streaming_content_block.py && git commit -m "feat(ui): polish live activity status"`.

## Task 5: Plan Panel Alignment

**Files:**
- Modify: `src/pythinker_code/ui/shell/visualize/_live_view.py`
- Create: `tests/ui_and_conv/test_plan_display_panel.py`

- [ ] **Step 1: Write failing test for plan panel rendering**

Create `tests/ui_and_conv/test_plan_display_panel.py`:

```python
from rich.console import Console

from pythinker_code.ui.shell.visualize import _LiveView
from pythinker_code.wire.types import PlanDisplay, StatusUpdate


def test_plan_display_uses_worklog_plan_title(monkeypatch):
    printed = []
    monkeypatch.setattr("pythinker_code.ui.shell.visualize._live_view.console.print", printed.append)
    view = _LiveView(StatusUpdate())

    view.display_plan(PlanDisplay(content="# Plan\n\n- Step one", file_path="plans/one.md"))

    console = Console(record=True, width=120, color_system=None)
    console.print(printed[0])
    output = console.export_text()

    assert "Plan" in output
    assert "plans/one.md" in output
    assert "Step one" in output
```

- [ ] **Step 2: Run test to verify it fails or locks current behavior**

Run: `uv run pytest tests/ui_and_conv/test_plan_display_panel.py -q`

Expected: PASS or FAIL depending on current panel output. If it passes, keep it as a regression test before the styling change.

- [ ] **Step 3: Use work-log card helper for plan display**

In `_live_view.py`, import:

```python
from pythinker_code.ui.shell.visualize._worklog import render_worklog_card
```

Replace the `Panel(...)` creation in `display_plan` with:

```python
        panel = render_worklog_card(
            "Plan",
            plan_body,
            subtitle=msg.file_path,
            border_style="cyan",
        )
```

- [ ] **Step 4: Run plan panel test**

Run: `uv run pytest tests/ui_and_conv/test_plan_display_panel.py -q`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint if commits were explicitly requested**

Run only if the user explicitly requested commits: `git add src/pythinker_code/ui/shell/visualize/_live_view.py tests/ui_and_conv/test_plan_display_panel.py && git commit -m "feat(ui): align plan display panel"`.

## Task 6: Regression Sweep And Formatting

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run focused UI tests**

Run:

```sh
uv run pytest \
  tests/ui_and_conv/test_worklog_render.py \
  tests/ui_and_conv/test_tool_call_block.py \
  tests/ui_and_conv/test_status_block.py \
  tests/ui_and_conv/test_streaming_content_block.py \
  tests/ui_and_conv/test_plan_display_panel.py \
  tests/ui_and_conv/test_shell_welcome_info.py
```

Expected: PASS.

- [ ] **Step 2: Run formatter**

Run: `make format`

Expected: command exits 0. If files are reformatted, inspect `git diff` and keep only relevant formatting changes.

- [ ] **Step 3: Run project checks**

Run: `make check`

Expected: command exits 0. If failures are unrelated to this work, capture the exact failing command and error before reporting.

- [ ] **Step 4: Run relevant broader tests**

Run: `uv run pytest tests/ui_and_conv -q`

Expected: PASS.

- [ ] **Step 5: Search for stale startup copy**

Run: `rg "Welcome to Pythinker CLI!" src tests`

Expected: only the negative assertion in `tests/ui_and_conv/test_shell_welcome_info.py`, or no matches if that assertion is later rewritten.

- [ ] **Step 6: Manual smoke test command**

Run: `uv run pythinker-code --help`

Expected: command exits 0 and confirms the CLI entry point still imports.

- [ ] **Step 7: Commit final checkpoint if commits were explicitly requested**

Run only if the user explicitly requested commits: `git add src/pythinker_code/ui/shell/visualize src/pythinker_code/ui/shell/__init__.py tests/ui_and_conv tests/e2e docs/superpowers && git commit -m "feat(ui): refresh terminal work log"`.

## Self-Review

Spec coverage:

- Startup welcome copy is covered by the existing welcome test and acceptance checks.
- Live activity labels are covered by Task 4.
- Tool states and display cards are covered by Tasks 1, 2, and 3.
- Plan panel alignment is covered by Task 5.
- Existing prompt-toolkit, Wire, approvals, and questions are preserved because the plan only changes render helpers and existing rendering methods.
- Verification is covered by Task 6.

Placeholder scan:

- The plan contains no placeholder markers.
- Every code-changing step includes exact files and code snippets.
- Each verification step includes exact commands and expected outcomes.

Type consistency:

- `WorkLogState`, `ToolStyle`, `tool_style`, `render_worklog_entry`, `render_worklog_card`, `denied_error`, and `render_display_blocks` are introduced before use.
- `render_display_blocks` consumes `DisplayBlock` lists from `ToolReturnValue.display`, matching existing `_ToolCallBlock` data.
- `_StatusBlock` continues rendering via `self.text`, preserving existing tests and callers.
