# Manage your todo list for tracking task progress during execution.

**When to set todos (Update mode):**
Set the todo list **only after the user has explicitly agreed on the plan**. The todo list marks the start of execution — it is not a planning scratch-pad. Do not call this tool while exploring, gathering context, presenting options, or waiting for user feedback. The moment the user says "yes", "do it", "go ahead", or otherwise confirms the approach, set the list and begin.

**Usage modes:**

- **Update mode**: Pass `todos` to set the entire todo list. The previous list is replaced.
- **Query mode**: Omit `todos` (or pass null) to retrieve the current todo list without changes.
- **Clear mode**: Pass an empty array `[]` to clear all todos when work is fully done.

Once the todo list is set, it is the single source of truth for in-progress work. During execution, update item statuses as you complete work (`pending` → `in_progress` → `done`). When scope evidence makes a planned item irrelevant, mark it `cancelled` (do not silently delete it) so the on-screen plan history stays honest for the watching user — this is the in-list way to express the scope change you should first surface to the user. Only restructure or replace the list when evidence genuinely changes the scope — not for convenience replanning. When in doubt, surface the new evidence to the user before changing the plan.

Once you finish a subtask/milestone, update its status before moving to the next item.

At most one item can be in_progress at a time — lists with more than one are rejected. Do not jump an item from `pending` to `done`: set it `in_progress` first, and do not batch-complete multiple items after the fact.

**Do NOT use this tool:**

- During the planning or exploration phase, before the user has confirmed the approach.
- When the user asks a question or requests a review without agreeing to a concrete plan.
- When the task only takes a few steps/tool calls. E.g. "Fix the unit test function 'test_xxx'".
- When the user prompt is very specific and fully self-contained. E.g. "Replace xxx to yyy in file zzz".

**IMPORTANT:** Do not call this tool repeatedly without making real progress between calls. Use Query mode to check current state before updating. If you cannot advance any task, surface the blocker to the user instead of replanning. Repeated todo updates without real work are counterproductive.
