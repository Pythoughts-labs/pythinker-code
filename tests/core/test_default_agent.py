from __future__ import annotations

# ruff: noqa

import platform

import pytest
from inline_snapshot import snapshot

from pythinker_code.agentspec import DEFAULT_AGENT_FILE
from pythinker_code.soul.agent import Runtime, load_agent


@pytest.mark.skipif(platform.system() == "Windows", reason="Skipping test on Windows")
async def test_default_agent(runtime: Runtime):
    agent = await load_agent(DEFAULT_AGENT_FILE, runtime, mcp_configs=[])
    # Identity invariants — targeted checks so unrelated prompt edits don't break this test.
    assert "## Product Identity" in agent.system_prompt
    assert "Pythinker" in agent.system_prompt
    assert "Pythoughts-labs" in agent.system_prompt
    assert "Do not name or describe the underlying language model" in agent.system_prompt

    builtin_types = [
        (
            name,
            type_def.description,
            type_def.agent_file.name,
            type_def.default_model,
            type_def.tool_policy.mode,
            type_def.tool_policy.tools,
        )
        for name, type_def in runtime.labor_market.builtin_types.items()
    ]
    assert builtin_types == snapshot(
        [
            (
                "mocker",
                "The mock agent for testing purposes.",
                "mocker-agent.yaml",
                None,
                "inherit",
                (),
            ),
            (
                "coder",
                "Good at general software engineering tasks.",
                "coder.yaml",
                None,
                "allowlist",
                (
                    "pythinker_code.tools.shell:Shell",
                    "pythinker_code.tools.todo:SetTodoList",
                    "pythinker_code.tools.file:ReadFile",
                    "pythinker_code.tools.file:ReadMediaFile",
                    "pythinker_code.tools.file:Glob",
                    "pythinker_code.tools.file:Grep",
                    "pythinker_code.tools.file:SmartSearch",
                    "pythinker_code.tools.file:WriteFile",
                    "pythinker_code.tools.file:StrReplaceFile",
                    "pythinker_code.tools.web:SearchWeb",
                    "pythinker_code.tools.web:FetchURL",
                ),
            ),
            (
                "code-reviewer",
                "Diff-focused code review with severity-scored findings.",
                "code_reviewer.yaml",
                None,
                "allowlist",
                (
                    "pythinker_code.tools.shell:Shell",
                    "pythinker_code.tools.todo:SetTodoList",
                    "pythinker_code.tools.file:ReadFile",
                    "pythinker_code.tools.file:Grep",
                    "pythinker_code.tools.skill:ReadSkill",
                    "pythinker_code.tools.web:SearchWeb",
                    "pythinker_code.tools.web:FetchURL",
                ),
            ),
            (
                "debugger",
                "Failure/log/stack-trace root-cause analysis with reproduction evidence.",
                "debugger.yaml",
                None,
                "allowlist",
                (
                    "pythinker_code.tools.shell:Shell",
                    "pythinker_code.tools.todo:SetTodoList",
                    "pythinker_code.tools.file:ReadFile",
                    "pythinker_code.tools.file:Grep",
                ),
            ),
            (
                "explore",
                "Fast codebase exploration with prompt-enforced read-only behavior.",
                "explore.yaml",
                None,
                "allowlist",
                (
                    "pythinker_code.tools.shell:Shell",
                    "pythinker_code.tools.todo:SetTodoList",
                    "pythinker_code.tools.file:ReadFile",
                    "pythinker_code.tools.file:ReadMediaFile",
                    "pythinker_code.tools.file:Glob",
                    "pythinker_code.tools.file:Grep",
                    "pythinker_code.tools.file:SmartSearch",
                    "pythinker_code.tools.skill:ReadSkill",
                    "pythinker_code.tools.web:SearchWeb",
                    "pythinker_code.tools.web:FetchURL",
                ),
            ),
            (
                "plan",
                "Read-only implementation planning and architecture design.",
                "plan.yaml",
                None,
                "allowlist",
                (
                    "pythinker_code.tools.todo:SetTodoList",
                    "pythinker_code.tools.file:ReadFile",
                    "pythinker_code.tools.file:ReadMediaFile",
                    "pythinker_code.tools.file:Glob",
                    "pythinker_code.tools.file:Grep",
                    "pythinker_code.tools.file:SmartSearch",
                    "pythinker_code.tools.skill:ReadSkill",
                    "pythinker_code.tools.web:SearchWeb",
                    "pythinker_code.tools.web:FetchURL",
                ),
            ),
            (
                "review",
                "Read-only code review with severity-scored findings.",
                "review.yaml",
                None,
                "allowlist",
                (
                    "pythinker_code.tools.shell:Shell",
                    "pythinker_code.tools.todo:SetTodoList",
                    "pythinker_code.tools.file:ReadFile",
                    "pythinker_code.tools.file:ReadMediaFile",
                    "pythinker_code.tools.file:Glob",
                    "pythinker_code.tools.file:Grep",
                    "pythinker_code.tools.file:SmartSearch",
                    "pythinker_code.tools.skill:ReadSkill",
                    "pythinker_code.tools.web:SearchWeb",
                    "pythinker_code.tools.web:FetchURL",
                ),
            ),
            (
                "security-reviewer",
                "Diff-focused security review with validated findings.",
                "security_reviewer.yaml",
                None,
                "allowlist",
                (
                    "pythinker_code.tools.shell:Shell",
                    "pythinker_code.tools.todo:SetTodoList",
                    "pythinker_code.tools.file:ReadFile",
                    "pythinker_code.tools.file:Grep",
                    "pythinker_code.tools.web:SearchWeb",
                    "pythinker_code.tools.web:FetchURL",
                ),
            ),
            (
                "implementer",
                "Scoped implementation with minimal edits and verification.",
                "implementer.yaml",
                None,
                "allowlist",
                (
                    "pythinker_code.tools.shell:Shell",
                    "pythinker_code.tools.todo:SetTodoList",
                    "pythinker_code.tools.file:ReadFile",
                    "pythinker_code.tools.file:ReadMediaFile",
                    "pythinker_code.tools.file:Glob",
                    "pythinker_code.tools.file:Grep",
                    "pythinker_code.tools.file:SmartSearch",
                    "pythinker_code.tools.file:WriteFile",
                    "pythinker_code.tools.file:StrReplaceFile",
                    "pythinker_code.tools.skill:ReadSkill",
                    "pythinker_code.tools.web:SearchWeb",
                    "pythinker_code.tools.web:FetchURL",
                ),
            ),
            (
                "judge",
                "Independent final quality gate for answers, reports, and code-change summaries.",
                "judge.yaml",
                None,
                "allowlist",
                (
                    "pythinker_code.tools.shell:Shell",
                    "pythinker_code.tools.todo:SetTodoList",
                    "pythinker_code.tools.file:ReadFile",
                    "pythinker_code.tools.file:ReadMediaFile",
                    "pythinker_code.tools.file:Glob",
                    "pythinker_code.tools.file:Grep",
                    "pythinker_code.tools.file:SmartSearch",
                    "pythinker_code.tools.skill:ReadSkill",
                ),
            ),
            (
                "verifier",
                "Read-only validation runner for tests, lint, and builds.",
                "verifier.yaml",
                None,
                "allowlist",
                (
                    "pythinker_code.tools.shell:Shell",
                    "pythinker_code.tools.todo:SetTodoList",
                    "pythinker_code.tools.file:ReadFile",
                    "pythinker_code.tools.file:ReadMediaFile",
                    "pythinker_code.tools.file:Glob",
                    "pythinker_code.tools.file:Grep",
                    "pythinker_code.tools.file:SmartSearch",
                    "pythinker_code.tools.skill:ReadSkill",
                ),
            ),
        ]
    )


@pytest.mark.skipif(platform.system() == "Windows", reason="Skipping test on Windows")
async def test_default_agent_background_bash_guardrails(runtime: Runtime):
    agent = await load_agent(DEFAULT_AGENT_FILE, runtime, mcp_configs=[])

    assert "the only task-management slash command is `/task`" in agent.system_prompt
    assert "Do not tell users to run `/task list`, `/task output`, `/task stop`, `/tasks`" in (
        agent.system_prompt
    )

    tool_names = [tool.name for tool in agent.toolset.tools]
    assert tool_names == snapshot(
        [
            "Agent",
            "RunAgents",
            "ReadSkill",
            "AskUserQuestion",
            "SetTodoList",
            "Memory",
            "Scratchpad",
            "Shell",
            "TaskList",
            "TaskOutput",
            "TaskInput",
            "TaskHandoff",
            "TaskStop",
            "ReadFile",
            "ReadMediaFile",
            "Glob",
            "Grep",
            "SmartSearch",
            "WriteFile",
            "StrReplaceFile",
            "SearchWeb",
            "FetchURL",
            "ExitPlanMode",
            "EnterPlanMode",
        ]
    )
    assert agent.toolset.tools[0].description == snapshot(
        """\
Start a subagent instance to work on a focused task.

The Agent tool can either create a new subagent instance or resume an existing one by `agent_id`.
Each instance keeps its own context history under the current session, so repeated use of the same
instance can preserve previous findings and work.

**Available Built-in Agent Types**

- `mocker`: The mock agent for testing purposes. (Tools: *, Model: inherit, Background: yes).
- `coder`: Good at general software engineering tasks. (Tools: Shell, SetTodoList, ReadFile, ReadMediaFile, Glob, Grep, SmartSearch, WriteFile, StrReplaceFile, SearchWeb, FetchURL, Model: inherit, Background: yes). When to use: Use this agent for non-trivial software engineering work that may require reading files, editing code, running commands, and returning a compact but technically complete summary to the parent agent.
- `code-reviewer`: Diff-focused code review with severity-scored findings. (Tools: Shell, SetTodoList, ReadFile, Grep, ReadSkill, SearchWeb, FetchURL, Model: inherit, Background: yes). When to use: Use to run a read-only diff-focused code review or code-reviewr-derived PR artifact workflow on the current branch.
- `debugger`: Failure/log/stack-trace root-cause analysis with reproduction evidence. (Tools: Shell, SetTodoList, ReadFile, Grep, Model: inherit, Background: yes). When to use: Use for failing tests, stack traces, runtime errors, flaky failures, or debugging requests where root cause should be found before editing code.
- `explore`: Fast codebase exploration with prompt-enforced read-only behavior. (Tools: Shell, SetTodoList, ReadFile, ReadMediaFile, Glob, Grep, SmartSearch, ReadSkill, SearchWeb, FetchURL, Model: inherit, Background: yes). When to use: Fast agent specialized for exploring codebases. Use this when you need to quickly find files by patterns (e.g. "src/**/*.yaml"), search code for keywords (e.g. "database connection"), or answer questions about the codebase (e.g. "how does the auth module work?"). When calling this agent, specify the desired thoroughness level: "quick" for basic searches, "medium" for moderate exploration, or "thorough" for comprehensive analysis across multiple locations and naming conventions. Use this agent for any read-only exploration that will clearly require more than 3 tool calls. Prefer launching multiple explore agents concurrently when investigating independent questions.
- `plan`: Read-only implementation planning and architecture design. (Tools: SetTodoList, ReadFile, ReadMediaFile, Glob, Grep, SmartSearch, ReadSkill, SearchWeb, FetchURL, Model: inherit, Background: yes). When to use: Use this agent when the parent agent needs a step-by-step implementation plan, key file identification, and architectural trade-off analysis before code changes are made.
- `review`: Read-only code review with severity-scored findings. (Tools: Shell, SetTodoList, ReadFile, ReadMediaFile, Glob, Grep, SmartSearch, ReadSkill, SearchWeb, FetchURL, Model: inherit, Background: yes). When to use: Use this agent for read-only code review after changes are made or when the parent needs severity-scored findings before deciding what to fix.
- `security-reviewer`: Diff-focused security review with validated findings. (Tools: Shell, SetTodoList, ReadFile, Grep, SearchWeb, FetchURL, Model: inherit, Background: yes). When to use: Use to run a diff-only security review on the current branch. Can run in parallel with `code-reviewer`.
- `implementer`: Scoped implementation with minimal edits and verification. (Tools: Shell, SetTodoList, ReadFile, ReadMediaFile, Glob, Grep, SmartSearch, WriteFile, StrReplaceFile, ReadSkill, SearchWeb, FetchURL, Model: inherit, Background: yes). When to use: Use this agent when the required code change is already specified and should be implemented with minimal edits and a quick verification pass.
- `judge`: Independent final quality gate for answers, reports, and code-change summaries. (Tools: Shell, SetTodoList, ReadFile, ReadMediaFile, Glob, Grep, SmartSearch, ReadSkill, Model: inherit, Background: yes). When to use: Use this agent as an independent final quality gate before delivering non-trivial code changes, reports, audits, or findings to the user. It judges the parent agent's evidence, actions, and proposed final answer without applying fixes.
- `verifier`: Read-only validation runner for tests, lint, and builds. (Tools: Shell, SetTodoList, ReadFile, ReadMediaFile, Glob, Grep, SmartSearch, ReadSkill, Model: inherit, Background: yes). When to use: Use this agent when the parent needs tests, lint, type checks, builds, or other validation gates run and reported without applying fixes.

**Usage**

- Always provide a short `description` (3-5 words).
- Use `subagent_type` to select a built-in agent type. If omitted, `coder` is used.
- Use `model` when you need to override the built-in type's default model or the parent agent's current model.
- Use `resume` when you want to continue an existing instance instead of starting a new one.
- If an existing subagent already has relevant context or the task is a continuation of its prior work, prefer `resume` over creating a new instance.
- Default to foreground execution. Use `run_in_background=true` only when the task can continue independently, you do not need the result immediately, and there is a clear benefit to returning control before it finishes.
- Be explicit about whether the subagent should write code, only research, review, or verify.
- Provide the subagent all required context and success criteria. New subagents do not inherit your transcript automatically.
- Brief the agent like a capable teammate joining mid-task: state the goal, why it matters, what you already learned or ruled out, exact paths/commands when known, and the output format you need.
- Include a prompt packet for non-trivial work: Goal, Evidence/Context, Scope and non-goals, Constraints, Expected Output, Verification, and Risks/Blockers.
- For review or fix orchestration, prefer durable feature/finding IDs when available (`pythinker review map`, `review`, `next`, `show`). They make delegated work bounded, resumable, and evidence-checkable.
- Keep each delegated prompt to one objective. Split unrelated goals into separate agents so each result is reviewable.
- Do not delegate synthesis with vague prompts such as "based on your findings, fix it". First understand the finding yourself, then give the subagent a concrete scoped task.
- Spawn multiple subagents in the same turn when they can investigate independent regions concurrently, but keep background launches within available task slots.
- For thorough large-codebase exploration, prefer scoped questions over one broad scan, and pass an explicit longer `timeout` (for example 1800-3600 seconds) when using background agents. If an agent times out, do not relaunch the same broad prompt unchanged; use targeted direct scans or resume the saved agent with a narrower continuation prompt.
- Cross-check at least one load-bearing subagent finding before making changes from it.
- The subagent result is only visible to you. If the user should see it, summarize it yourself.

**Agent Workflow Design**

Use subagents as focused logical roles, not just extra tool capacity:

- `explore` / scout: collect facts, relevant files, constraints, and risks. Read-only.
- `plan`: turn gathered context into an implementation plan. Read-only.
- `coder`: general software engineering work when the brief still needs judgment.
- `implementer`: land a specific, already-scoped change with minimum edits.
- `review`: read and grade changed code with severity-scored findings.
- `verifier`: run validation gates and report PASS / FAIL / FLAKY without fixing.
- `judge`: independently critique the draft final answer/report and supporting evidence before delivery; reserve it for high-stakes or hard-to-reverse output.

Recommended workflows:

- Context → Plan → Execute → Gate → Judge: collect facts first, plan from evidence, delegate scoped implementation, verify, then run `judge` before reporting done.
- Scout → Plan → Implement: run `explore`, then `plan` with the explorer's findings, then `implementer` or `coder` with the plan.
- Implement → Review → Fix → Verify → Judge: run `implementer`, then `review`, then resume/launch `implementer` to apply feedback, then `verifier` for the relevant gate, then `judge` for final answer/report quality.
- Parallel scouting: launch multiple `explore` agents for independent questions, then synthesize their findings before editing. If a background batch exceeds available slots, RunAgents launches what fits and reports deferred children for a follow-up batch.
- Parallel review/verification: when review and tests do not depend on each other, run `review` and `verifier` concurrently, then pass both summaries to `judge`.
- Stateful review loop: for repo-wide quality work, map feature slices first, review bounded slices, triage findings, then dispatch one fix at a time with the finding ID and minimum fix scope. Revalidate before claiming fixed.

When chaining manually, include the previous agent's summary in the next agent prompt. Newly-created
subagents do not see your current context automatically.

**Explore Agent — Preferred for Codebase Research**

When you need to understand the codebase before making changes, fixing bugs, or planning features,
prefer `subagent_type="explore"` over doing the search yourself. The explore agent is optimized for
fast, read-only codebase investigation. Use it when:
- Your task will clearly require more than 3 search queries
- You need to understand how a module, feature, or code path works
- You are about to enter plan mode and want to gather context first
- You want to investigate multiple independent questions — launch multiple explore agents concurrently

When calling explore, specify the desired thoroughness in the prompt:
- "quick": targeted lookups — find a specific file, function, or config value
- "medium": understand a module — how does auth work, what calls this API
- "thorough": cross-cutting analysis — architecture overview, dependency mapping, multi-module investigation

**When Not To Use Agent**

- Reading a known file path
- Searching a small number of known files
- Tasks that can be completed in one or two direct tool calls
"""
    )
    assert agent.toolset.tools[0].parameters == snapshot(
        {
            "properties": {
                "description": {
                    "description": "A short (3-5 word) description of the task",
                    "type": "string",
                },
                "prompt": {
                    "description": "The task for the agent to perform. Include a single goal, relevant context/evidence, scope boundaries, constraints, expected output format, and verification criteria.",
                    "type": "string",
                },
                "subagent_type": {
                    "default": "coder",
                    "description": "The built-in agent type to use. Defaults to `coder`.",
                    "type": "string",
                },
                "model": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "description": "Optional model override. Selection priority is: this parameter, then the built-in type default model, then the parent agent's current model.",
                },
                "resume": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "description": "Optional agent ID to resume instead of creating a new instance.",
                },
                "run_in_background": {
                    "default": False,
                    "description": "Whether to run the agent in the background. Prefer false unless the task can continue independently and there is a clear benefit to returning control before the result is needed.",
                    "type": "boolean",
                },
                "timeout": {
                    "anyOf": [
                        {"maximum": 3600, "minimum": 30, "type": "integer"},
                        {"type": "null"},
                    ],
                    "default": None,
                    "description": "Timeout in seconds for the agent task. Foreground: no default timeout (runs until completion), max 3600s (1hr). Background: default from config (1hr), max 3600s (1hr). For thorough large-codebase exploration, pass an explicit longer timeout near the max and scope the prompt narrowly. The agent is stopped if it exceeds this limit.",
                },
                "dependencies": {
                    "description": "Optional background task IDs this task depends on. Metadata only; the parent agent should launch dependent tasks after prerequisites are ready.",
                    "items": {"type": "string"},
                    "type": "array",
                },
                "budget_seconds": {
                    "anyOf": [
                        {"maximum": 3600, "minimum": 1, "type": "integer"},
                        {"type": "null"},
                    ],
                    "default": None,
                    "description": "Optional budget in seconds for planning/synthesis metadata.",
                },
                "isolation": {
                    "default": "none",
                    "description": "Optional isolation request for background agents. `worktree` records a git-worktree isolation intent for orchestration/recovery; unsupported callers should leave `none`.",
                    "enum": ["none", "worktree"],
                    "type": "string",
                },
            },
            "required": ["description", "prompt"],
            "type": "object",
        }
    )


@pytest.mark.skipif(platform.system() == "Windows", reason="Skipping test on Windows")
async def test_default_agent_scratchpad_guardrails(runtime: Runtime):
    agent = await load_agent(DEFAULT_AGENT_FILE, runtime, mcp_configs=[])
    assert ".pythinker/scratch/<session-id>-*.md" in agent.system_prompt
    assert "current session only" in agent.system_prompt
    assert "Do not paste full logs" in agent.system_prompt
    assert "Subagents do not create their own scratch files" in agent.system_prompt
    assert "Do NOT read or reference scratch files from other sessions" in agent.system_prompt


import dataclasses

from pythinker_code.scratchpad import ScratchpadStatus, render_scratchpad_section


@pytest.mark.skipif(platform.system() == "Windows", reason="Skipping test on Windows")
async def test_default_agent_unavailable_scratchpad_guard_only(runtime: Runtime):
    guard = render_scratchpad_section(
        ScratchpadStatus(False, "disabled_tracked", True, True, False)
    )
    runtime.builtin_args = dataclasses.replace(
        runtime.builtin_args,
        PYTHINKER_SCRATCHPAD_SECTION=guard,
    )
    agent = await load_agent(DEFAULT_AGENT_FILE, runtime, mcp_configs=[])

    assert "do not create or edit `.pythinker/scratch.md`" in agent.system_prompt
    assert "minimal session memory" not in agent.system_prompt


from pythinker_code.scratchpad import (
    DEFAULT_SCRATCHPAD_SECTION,
    refresh_system_prompt_scratchpad_section,
)


def test_refresh_resumed_prompt_replaces_stale_available_section():
    old_prompt = (
        "Intro\n\n"
        "<!-- PYTHINKER_SCRATCHPAD_SECTION_START -->\n"
        f"{DEFAULT_SCRATCHPAD_SECTION}\n"
        "<!-- PYTHINKER_SCRATCHPAD_SECTION_END -->\n\n"
        "Before every tool response, batch independent work."
    )
    guard = "Scratchpad unavailable this session; do not create or edit `.pythinker/scratch.md`."
    refreshed = refresh_system_prompt_scratchpad_section(old_prompt, guard)

    assert guard in refreshed
    assert DEFAULT_SCRATCHPAD_SECTION not in refreshed


def test_refresh_resumed_prompt_replaces_stale_guard_with_available_section():
    guard = "Scratchpad unavailable this session; do not create or edit `.pythinker/scratch.md`."
    old_prompt = (
        "Intro\n\n"
        "<!-- PYTHINKER_SCRATCHPAD_SECTION_START -->\n"
        f"{guard}\n"
        "<!-- PYTHINKER_SCRATCHPAD_SECTION_END -->\n\n"
        "Before every tool response, batch independent work."
    )
    refreshed = refresh_system_prompt_scratchpad_section(old_prompt, DEFAULT_SCRATCHPAD_SECTION)

    assert DEFAULT_SCRATCHPAD_SECTION in refreshed
    assert guard not in refreshed


def test_refresh_resumed_legacy_prompt_inserts_guard():
    old_prompt = "Intro\n\nBefore every tool response, batch independent work."
    guard = "Scratchpad unavailable this session; do not create or edit `.pythinker/scratch.md`."
    refreshed = refresh_system_prompt_scratchpad_section(old_prompt, guard)

    assert guard in refreshed
    assert refreshed.index(guard) < refreshed.index("Before every tool response")
