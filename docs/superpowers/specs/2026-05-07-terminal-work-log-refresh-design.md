# Terminal Work-Log Refresh Design

## Goal

Enhance the Pythinker Code terminal UI so users get a more professional, readable view while the agent is working, using tools, applying changes, and showing reports. The design should be inspired by OpenCode's clear session timeline, but adapted to Pythinker's existing Rich and prompt-toolkit shell instead of copying OpenCode's TUI architecture.

## Scope

This redesign targets the current shell UI in `src/pythinker_code/ui/shell/visualize/`, primarily `_blocks.py` and `_live_view.py`.

Included:

- Live agent activity states for thinking, composing, tool execution, compaction, MCP loading, and side questions.
- Tool call rendering for running, completed, failed, denied, and interrupted states.
- Professional cards for substantial outputs: diffs, shell commands, todos, background tasks, plans, and report-like brief output.
- Clear subagent activity summaries nested under parent agent tool calls.
- Consistent status language and visual hierarchy across live and flushed history output.

Not included in the first pass:

- Replacing prompt-toolkit or Rich Live.
- Rebuilding the event protocol.
- Changing agent behavior or tool execution semantics.
- Copying OpenCode's Solid/OpenTUI components directly.

## Design Direction

Use an "inspired adaptation" approach. Pythinker keeps its identity, keyboard behavior, approvals, questions, and Rich rendering. The UI adopts OpenCode's stronger work-log structure: concise running rows, polished completed cards, consistent labels, and easier scanning of what changed.

The default startup copy should use the product name `Pythinker Code`, while internal protocol names and compatibility-facing labels can remain `Pythinker CLI` where changing them would be broader than the UI request.

## Architecture

The existing wire flow remains the source of truth:

- `_LiveView` consumes `TurnBegin`, `StepBegin`, content parts, tool calls, tool results, status updates, approval/question requests, notifications, and `TurnEnd`.
- `_ContentBlock` owns streaming assistant text and thinking indicators.
- `_ToolCallBlock` owns the live and final representation of one tool call.
- `_StatusBlock` owns the compact context/status footer.
- Tool results expose display blocks through `ToolReturnValue.display`.

The redesign adds small render helpers inside the shell visualize layer rather than adding backend dependencies:

- `WorkLogEntry`: common layout for one-line or multi-line activity rows.
- `WorkLogCard`: common bordered panel for substantial tool/report output.
- `ToolStyle`: mapping from tool names to label, icon, color, and action wording.
- `DisplayBlockRenderer`: local renderer for display blocks and grouped diff blocks.
- `StatusLine`: clearer status footer backed by `_StatusBlock`.

These helpers should be private to the shell UI until a concrete reuse need appears.

## Component Behavior

### Live Activity

Thinking and composing stay lightweight, but the labels should read like deliberate work states instead of raw spinner text. Examples:

- `Thinking ... 4s · 1.2k tokens · 46 tok/s`
- `Composing ... 8s · 520 tokens`
- `Connecting MCP servers ... 2/3 connected · 18 tools` when status data is available.
- `Compacting context ...`

The existing hidden-thinking behavior remains. If `show_thinking_stream` is enabled, the reasoning preview still works.

### Tool Entries

Each tool call should render as a work-log entry with:

- State icon or spinner.
- Human label: `Read`, `Search`, `Edit`, `Patch`, `Shell`, `Todo`, `Subagent`, `Fetch`, `Ask`, `Skill`, or fallback tool name.
- Target/detail extracted from streamed arguments using existing `extract_key_argument` behavior.
- Status color: running, completed, failed, denied, interrupted.
- Optional child content for display blocks.

Completed tools should prefer concise rows unless they produced meaningful display blocks. Failed tools should show a concise error line. Denials and user dismissals should be subdued and not styled like crashes.

### Output Cards

Substantial tool outputs should render as cards with consistent padding, border style, and titles:

- Diffs: group consecutive `DiffDisplayBlock` entries by file as today, but wrap them in a clearer card with file path and `+N -N` summary.
- Shell: show command, working directory if known, and output preview. Long output can keep existing pager/expansion behavior where available.
- Todos: show statuses with consistent symbols and muted completed items.
- Background tasks: show task id, state, kind, and description in a compact card.
- Brief reports: render markdown in a report card when the brief is substantial; keep simple brief text inline when short.
- Plans: keep `PlanDisplay` as a bordered panel, but align title, subtitle, padding, and border color with the work-log card language.

### Subagents

Subagent activity stays nested under the parent agent tool call. The parent entry should show:

- Subagent type and id when known.
- Current or latest sub-tool call.
- A compact summary of completed sub-tool calls, capped to avoid overwhelming the main timeline.
- Error state if any sub-tool result failed.

The first pass does not need multi-level nested subagent visualization beyond the current parent-child relationship.

### Approvals And Questions

Approvals and questions remain top-priority interactive panels. The first pass does not need to restructure their behavior, but their border colors and typography should not conflict with the new work-log style. Existing keyboard behavior and pager behavior must be preserved.

## Data Flow

No protocol changes are required for the first pass.

- `ToolCall` creates a running `WorkLogEntry`.
- `ToolCallPart` updates the target/detail as arguments stream.
- `ToolResult` finalizes the entry and renders display blocks.
- `SubagentEvent` updates the parent tool entry with nested activity.
- `StatusUpdate` updates the status footer and any MCP-loading detail.
- `PlanDisplay` flushes active content/tool output before printing a work-log-style plan panel.
- `Notification` remains short-lived in the live area and flushes into history.

If future UX work needs richer summaries, add optional display block metadata from tools. Do not block the first pass on backend changes.

## Error Handling

Failures should be explicit and concise:

- Tool errors render red work-log entries with the tool label, target, and concise message.
- Permission rejections, dismissed questions, and policy/rule denials use a muted denied/interrupted style.
- Interrupted runs finalize unfinished tools as interrupted, matching existing cleanup behavior.
- Unknown display blocks are ignored as today, but unknown tool names still get a generic work-log entry.

The UI should avoid dumping large raw payloads into the main timeline unless the user asks for details through existing expansion/pager behavior.

## Testing

Add focused tests for pure rendering behavior before implementation changes:

- Tool label and target formatting for representative tools.
- Running, completed, failed, denied, and interrupted work-log states.
- Grouped diff display blocks with add/remove totals.
- Todo display block rendering.
- Plan panel title/subtitle copy.
- Startup welcome copy using `Pythinker Code`.

Use Rich console capture for render assertions where practical. Keep tests close to `tests/ui_and_conv/` because this is shell UI behavior.

Manual smoke test after implementation:

- Start `pythinker-code` in a sample repository.
- Trigger read, grep, edit, apply patch, shell, todo, plan, subagent, approval, question, compaction, and interrupt flows.
- Confirm the terminal remains readable on narrow and wide widths.

## Acceptance Criteria

- The startup welcome says `Welcome to Pythinker Code!`.
- Running tools are easy to distinguish from completed and failed tools.
- Diffs, todos, shell output, plans, and report-like output share a consistent visual language.
- Existing approvals, questions, queued input, steering input, and interrupt behavior continue to work.
- Existing wire protocol compatibility is preserved.
- Focused UI tests pass, and broader `make check` / relevant pytest targets are run before completion.
