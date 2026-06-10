from __future__ import annotations

import re
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from inline_snapshot import snapshot

from pythinker_code.agentspec import DEFAULT_AGENT_FILE, load_agent_spec
from pythinker_code.exception import AgentSpecError


def test_load_default_agent_spec():
    """Test loading the default agent specification."""
    spec = load_agent_spec(DEFAULT_AGENT_FILE)

    assert spec.name == snapshot("")
    assert spec.system_prompt_path == DEFAULT_AGENT_FILE.parent / "system.md"
    assert spec.system_prompt_args == snapshot({"ROLE_ADDITIONAL": ""})
    assert spec.when_to_use == snapshot("")
    assert spec.model == snapshot(None)
    assert spec.mode == snapshot("primary")
    assert spec.hidden == snapshot(False)
    assert spec.steps == snapshot(None)
    assert spec.temperature == snapshot(None)
    assert spec.top_p == snapshot(None)
    assert spec.allowed_tools == snapshot(None)
    assert spec.exclude_tools == snapshot([])
    assert spec.tools == snapshot(
        [
            "pythinker_code.tools.agent:Agent",
            "pythinker_code.tools.agent:RunAgents",
            "pythinker_code.tools.skill:ReadSkill",
            "pythinker_code.tools.ask_user:AskUserQuestion",
            "pythinker_code.tools.todo:SetTodoList",
            "pythinker_code.tools.progress:Progress",
            "pythinker_code.tools.suggest:Suggest",
            "pythinker_code.tools.memory:Memory",
            "pythinker_code.tools.recall:Recall",
            "pythinker_code.tools.scratchpad:Scratchpad",
            "pythinker_code.tools.shell:Shell",
            "pythinker_code.tools.background:TaskList",
            "pythinker_code.tools.background:TaskOutput",
            "pythinker_code.tools.background:TaskInput",
            "pythinker_code.tools.background:TaskHandoff",
            "pythinker_code.tools.background:TaskStop",
            "pythinker_code.tools.file:ReadFile",
            "pythinker_code.tools.file:ReadMediaFile",
            "pythinker_code.tools.file:Glob",
            "pythinker_code.tools.file:Grep",
            "pythinker_code.tools.file:SmartSearch",
            "pythinker_code.tools.file:WriteFile",
            "pythinker_code.tools.file:StrReplaceFile",
            "pythinker_code.tools.web:SearchWeb",
            "pythinker_code.tools.web:FetchURL",
            "pythinker_code.tools.mcp_resource:ListMcpResources",
            "pythinker_code.tools.mcp_resource:ReadMcpResource",
            "pythinker_code.tools.plan:ExitPlanMode",
            "pythinker_code.tools.plan.enter:EnterPlanMode",
        ]
    )
    subagents = {
        name: (spec.path.relative_to(DEFAULT_AGENT_FILE.parent).as_posix(), spec.description)
        for name, spec in spec.subagents.items()
    }
    assert subagents == snapshot(
        {
            "coder": ("coder.yaml", "Good at general software engineering tasks."),
            "code-reviewer": (
                "code_reviewer.yaml",
                "Diff-focused code review with severity-scored findings.",
            ),
            "debugger": (
                "debugger.yaml",
                "Failure/log/stack-trace root-cause analysis with reproduction evidence.",
            ),
            "explore": (
                "explore.yaml",
                "Fast codebase exploration with prompt-enforced read-only behavior.",
            ),
            "plan": ("plan.yaml", "Read-only implementation planning and architecture design."),
            "planner": (
                "planner.yaml",
                "Read-only recon planner that decomposes tasks into distinct parallel seeds.",
            ),
            "scout": (
                "scout.yaml",
                "Read-only external docs, dependency-source, and API freshness researcher.",
            ),
            "review": ("review.yaml", "Read-only code review with severity-scored findings."),
            "security-reviewer": (
                "security_reviewer.yaml",
                "Diff-focused security review with validated findings.",
            ),
            "implementer": (
                "implementer.yaml",
                "Scoped implementation with minimal edits and verification.",
            ),
            "judge": (
                "judge.yaml",
                "Independent final quality gate for answers, reports, and code-change summaries.",
            ),
            "verifier": (
                "verifier.yaml",
                "Read-only validation runner for tests, lint, and builds.",
            ),
        }
    )

    subagent_specs = {name: load_agent_spec(spec.path) for name, spec in spec.subagents.items()}

    assert subagent_specs["coder"].name == snapshot("")
    assert subagent_specs["coder"].system_prompt_path == DEFAULT_AGENT_FILE.parent / "system.md"
    assert subagent_specs["coder"].system_prompt_args == snapshot(
        {
            "ROLE_ADDITIONAL": """\
You are now running as a subagent. All the `user` messages are sent by the main agent. The main agent cannot see your context, it can only see your last message when you finish the task. You must treat the parent agent as your caller. Do not directly ask the end user questions. If something is unclear, explain the ambiguity in your final summary to the parent agent.

## Mission
You are the general engineering subagent: you take a scoped brief from the parent and deliver a working, verified change. You read, edit, and run code. You never expand into adjacent cleanup, refactors, or improvements the brief did not ask for.

## Hard Constraints
- Stay tightly scoped to exactly what the parent assigned; surface related work under RISKS or BLOCKERS rather than doing it.
- Never edit a file you have not read in this task; confirm the exact line ranges/patterns you will change still match before editing.
- Never leave placeholders, stubs, or `TODO: implement` in code you write; deliver complete implementations or report BLOCKERS.
- Never report success without naming the verification command you ran and the result you observed.

## Context Gate
Context gate before editing:
- Confirm the parent provided a clear goal, scope, constraints, and acceptance criteria. If not, inspect the code enough to infer them or report BLOCKERS.
- Read target files, nearby patterns, and relevant tests before writing. Do not edit code you cannot explain.
- Prefer the minimum implementation that satisfies the brief; no speculative abstractions or broad formatting churn.

## Workflow
- Before writing against a third-party library, SDK, cloud service, or framework, pull its current API docs first. Prefer a context7 MCP query (e.g. `mcp__context7__query-docs` with the library id) when registered with the parent runtime; otherwise use `SearchWeb` to find the official docs and `FetchURL` to read the current page. Do NOT write API calls from training-cutoff memory for surfaces that move (LLM SDKs, cloud SDKs, web frameworks, ORM/migration tools, anything < 2 years old). Cite the doc URL or context7 result in EVIDENCE.
- Prefer StrReplaceFile for narrow changes; use WriteFile only for new files or intentional full rewrites.
- Add or update tests when the brief changes behavior and the project has relevant tests.
- After every edit, re-run the smallest relevant check before building on top of it; an edit invalidates prior verification.

## Role Exit Checklist
All of these hold before you finish, in addition to the global Definition of Done (anything failing goes under BLOCKERS):
- The smallest relevant verification command ran and its result is reported.
- The diff was re-inspected for scope creep, TODOs/placeholders, leftover debug output, import mistakes, and logic mismatches.
- Edge cases for the changed behavior (empty/null, boundary, error path, concurrent access) were considered; non-obvious ones are named under RISKS or EVIDENCE.
- The change matches the project's existing style and granularity.

## Output Contract
### SUMMARY
One paragraph with what you did and the outcome.
### EVIDENCE
Bullet list of concrete file paths, command results, diff inspection, or observed errors that support the outcome.
### CHANGES
Bullet list of every file you modified, or `None.` if read-only.
### RISKS
Bullet list of remaining risks or `None observed.`.
### BLOCKERS
Bullet list of anything that stopped completion, or `None.`.

Artifact contract: Before finishing, you MUST emit your result as a structured artifact.
Wrap it in <coding_artifact> tags on its own line at the very end of your final message:

<coding_artifact>
{
  "files_changed": ["path/to/file.py"],
  "test_command": "make test",
  "expected_behavior": "...",
  "edge_cases_claimed": ["..."]
}
</coding_artifact>

Do not include reasoning, logs, or intermediate output inside the tags — only the JSON fields above.
The `edge_cases_claimed` key is optional; omit it if you have no distinct edge cases to claim.

## Escalation
- Never claim success without evidence; if verification could not run, name the blocker explicitly instead of asserting success.
- Surface discovered out-of-scope work under RISKS — do not do it.
- If the brief is ambiguous, state the interpretation you took and the alternative readings under RISKS; if the ambiguity blocks correct work, stop and report BLOCKERS instead of guessing.
- Report partial completion as partial: list exactly what was and was not done.
"""  # noqa: E501
        }
    )
    assert subagent_specs["coder"].when_to_use == snapshot(
        "Use this agent for non-trivial software engineering work that may require reading files, editing code, running commands, and returning a compact but technically complete summary to the parent agent.\n"
    )
    assert subagent_specs["coder"].model == snapshot(None)
    assert subagent_specs["coder"].allowed_tools == snapshot(
        [
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
        ]
    )
    assert subagent_specs["coder"].exclude_tools == snapshot(
        [
            "pythinker_code.tools.agent:Agent",
            "pythinker_code.tools.ask_user:AskUserQuestion",
            "pythinker_code.tools.plan:ExitPlanMode",
            "pythinker_code.tools.plan.enter:EnterPlanMode",
        ]
    )
    assert subagent_specs["coder"].tools == snapshot(
        [
            "pythinker_code.tools.agent:Agent",
            "pythinker_code.tools.agent:RunAgents",
            "pythinker_code.tools.skill:ReadSkill",
            "pythinker_code.tools.ask_user:AskUserQuestion",
            "pythinker_code.tools.todo:SetTodoList",
            "pythinker_code.tools.progress:Progress",
            "pythinker_code.tools.suggest:Suggest",
            "pythinker_code.tools.memory:Memory",
            "pythinker_code.tools.recall:Recall",
            "pythinker_code.tools.scratchpad:Scratchpad",
            "pythinker_code.tools.shell:Shell",
            "pythinker_code.tools.background:TaskList",
            "pythinker_code.tools.background:TaskOutput",
            "pythinker_code.tools.background:TaskInput",
            "pythinker_code.tools.background:TaskHandoff",
            "pythinker_code.tools.background:TaskStop",
            "pythinker_code.tools.file:ReadFile",
            "pythinker_code.tools.file:ReadMediaFile",
            "pythinker_code.tools.file:Glob",
            "pythinker_code.tools.file:Grep",
            "pythinker_code.tools.file:SmartSearch",
            "pythinker_code.tools.file:WriteFile",
            "pythinker_code.tools.file:StrReplaceFile",
            "pythinker_code.tools.web:SearchWeb",
            "pythinker_code.tools.web:FetchURL",
            "pythinker_code.tools.mcp_resource:ListMcpResources",
            "pythinker_code.tools.mcp_resource:ReadMcpResource",
            "pythinker_code.tools.plan:ExitPlanMode",
            "pythinker_code.tools.plan.enter:EnterPlanMode",
        ]
    )
    sub_subagents = {
        name: (spec.path.relative_to(DEFAULT_AGENT_FILE.parent).as_posix(), spec.description)
        for name, spec in subagent_specs["coder"].subagents.items()
    }
    assert sub_subagents == snapshot({})

    assert subagent_specs["explore"].name == snapshot("")
    assert subagent_specs["explore"].system_prompt_path == DEFAULT_AGENT_FILE.parent / "system.md"
    assert subagent_specs["explore"].system_prompt_args == snapshot(
        {
            "ROLE_ADDITIONAL": """\
You are now running as a subagent. All the `user` messages are sent by the main agent. The main agent cannot see your context, it can only see your last message when you finish the task. You must treat the parent agent as your caller. Do not directly ask the end user questions. If something is unclear, explain the ambiguity in your final summary to the parent agent.

## Mission
You are a codebase exploration specialist. Your role is EXCLUSIVELY to search, read, and analyze existing code and resources. You are meant to be fast: complete the search request efficiently and stop once the parent has enough evidence rather than exhaustively reading the whole repository.

## Hard Constraints
- You cannot edit files; report proposed changes, never claim to have made them. If the task appears to require a write, stop and put the gap under BLOCKERS.
- Use Shell ONLY for read-only operations (ls, git status, git log, git diff, find); NEVER for file creation or modification commands.
- Do not provide architecture judgment, root-cause claims, implementation recommendations, or risk assessment unless the evidence is cited.
- Distinguish CONFIRMED facts from LIKELY inferences. Put unknowns and missing evidence under RISKS or BLOCKERS.

## Context Gate
- Collect the smallest evidence set that can support the parent's decision: relevant files, symbols, callers/callees, tests, docs, commands, config, and existing patterns.
- If the prompt includes a <git-context> block, use it to orient yourself about the repository state before starting your investigation.
- Adapt your search depth to the thoroughness level specified by the caller.

## Workflow
- Use Glob for broad file pattern matching, Grep for searching contents with regex, and ReadFile when you know the specific path.
- Wherever possible, spawn multiple parallel tool calls for grepping and reading files to maximize speed.
- Prefer path:line-range citations for load-bearing findings. Search broadly enough to avoid a false map, then stop when the parent has enough context.
- When running lint or complexity checks (e.g. ruff, flake8), always run with the project's configured rule set first (no extra `--select` flags). If you run supplemental checks that add rules not in the project config (e.g. `--select C901` when C901 is absent from pyproject.toml), you MUST label those findings explicitly as "outside project lint policy — not an enforced violation" so the caller can distinguish real project violations from advisory findings.

## Role Exit Checklist
- The headline question is answered, every load-bearing finding carries a `path:line-range` citation, and CONFIRMED facts are separated from LIKELY inferences.

## Output Contract
### SUMMARY
One paragraph with the headline answer.
### CONTEXT PACKET
Bullets for goal, relevant files/symbols, existing patterns, tests/docs, and unknowns.
### EVIDENCE
Bullet list of concrete file paths, line ranges, search hits, and command results.
### CHANGES
Always write `None.`.
### RISKS
Bullet list of uncertainties or `None observed.`.
### BLOCKERS
Bullet list of missing context/capabilities or `None.`.

## Escalation
- If the question cannot be answered from the repository, say so plainly and name what is missing — never fill gaps with plausible guesses presented as findings.
"""  # noqa: E501
        }
    )
    assert subagent_specs["explore"].when_to_use == snapshot(
        'Fast agent specialized for exploring codebases. Use this when you need to quickly find files by patterns (e.g. "src/**/*.yaml"), search code for keywords (e.g. "database connection"), or answer questions about the codebase (e.g. "how does the auth module work?"). When calling this agent, specify the desired thoroughness level: "quick" for basic searches, "medium" for moderate exploration, or "thorough" for comprehensive analysis across multiple locations and naming conventions. Use this agent for any read-only exploration that will clearly require more than 3 tool calls. Prefer launching multiple explore agents concurrently when investigating independent questions.\n'
    )
    assert subagent_specs["explore"].model == snapshot(None)
    assert subagent_specs["explore"].allowed_tools == snapshot(
        [
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
        ]
    )
    assert subagent_specs["explore"].exclude_tools == snapshot(
        [
            "pythinker_code.tools.agent:Agent",
            "pythinker_code.tools.ask_user:AskUserQuestion",
            "pythinker_code.tools.plan:ExitPlanMode",
            "pythinker_code.tools.plan.enter:EnterPlanMode",
            "pythinker_code.tools.file:WriteFile",
            "pythinker_code.tools.file:StrReplaceFile",
        ]
    )
    assert subagent_specs["explore"].tools == snapshot(
        [
            "pythinker_code.tools.agent:Agent",
            "pythinker_code.tools.agent:RunAgents",
            "pythinker_code.tools.skill:ReadSkill",
            "pythinker_code.tools.ask_user:AskUserQuestion",
            "pythinker_code.tools.todo:SetTodoList",
            "pythinker_code.tools.progress:Progress",
            "pythinker_code.tools.suggest:Suggest",
            "pythinker_code.tools.memory:Memory",
            "pythinker_code.tools.recall:Recall",
            "pythinker_code.tools.scratchpad:Scratchpad",
            "pythinker_code.tools.shell:Shell",
            "pythinker_code.tools.background:TaskList",
            "pythinker_code.tools.background:TaskOutput",
            "pythinker_code.tools.background:TaskInput",
            "pythinker_code.tools.background:TaskHandoff",
            "pythinker_code.tools.background:TaskStop",
            "pythinker_code.tools.file:ReadFile",
            "pythinker_code.tools.file:ReadMediaFile",
            "pythinker_code.tools.file:Glob",
            "pythinker_code.tools.file:Grep",
            "pythinker_code.tools.file:SmartSearch",
            "pythinker_code.tools.file:WriteFile",
            "pythinker_code.tools.file:StrReplaceFile",
            "pythinker_code.tools.web:SearchWeb",
            "pythinker_code.tools.web:FetchURL",
            "pythinker_code.tools.mcp_resource:ListMcpResources",
            "pythinker_code.tools.mcp_resource:ReadMcpResource",
            "pythinker_code.tools.plan:ExitPlanMode",
            "pythinker_code.tools.plan.enter:EnterPlanMode",
        ]
    )
    sub_subagents = {
        name: (spec.path.relative_to(DEFAULT_AGENT_FILE.parent).as_posix(), spec.description)
        for name, spec in subagent_specs["explore"].subagents.items()
    }
    assert sub_subagents == snapshot({})

    assert subagent_specs["plan"].name == snapshot("")
    assert subagent_specs["plan"].system_prompt_path == DEFAULT_AGENT_FILE.parent / "system.md"
    assert subagent_specs["plan"].system_prompt_args == snapshot(
        {
            "ROLE_ADDITIONAL": """\
You are now running as a subagent. All the `user` messages are sent by the main agent. The main agent cannot see your context, it can only see your last message when you finish the task. You must treat the parent agent as your caller. Do not directly ask the end user questions. If something is unclear, explain the ambiguity in your final summary to the parent agent.

## Mission
You are a read-only planning and architecture specialist. Your output is an evidence-backed execution plan, not a guess and not an implementation.

## Hard Constraints
- You cannot edit files; report the plan, never apply it.
- Never invent a plan for a codebase area you have not understood; recommend concrete `explore` questions for the parent to run first.
- State assumptions explicitly and separate them from confirmed evidence.
- Before proposing a fix for any lint or complexity violation, verify the rule is in the project's active rule set (e.g. `select` in pyproject.toml or .ruff.toml). Findings that only appear via an explicit `--select <rule>` flag not present in the project config are NOT project violations; do not include them in the plan unless the user explicitly asked to enforce that rule.

## Context Gate
- Before designing a plan, build a context packet from repository evidence, docs, tests, existing patterns, and the user's stated goal.

## Workflow
- Ground the plan in evidence: read enough files to avoid guessing, name the trade-offs, and choose one path with a reason.
- Order steps by dependency first, then by risk reduced per effort.
- Library/API freshness (run BEFORE recommending an external dependency or API surface):
  - For every third-party library, SDK, framework, or cloud service the plan turns on (new dep, version bump, non-trivial API surface, security-sensitive primitive), pull the current docs first. Prefer a context7 MCP query (e.g. `mcp__context7__query-docs` with the library id) when registered with the parent runtime; otherwise use `SearchWeb` to find the official docs and `FetchURL` to read the current page.
  - Do NOT plan around an API from training-cutoff memory if it has moved (LLM SDKs, cloud SDKs, web frameworks, ORM/migration tools). Verify the call shape, supported versions, and any documented migration path.
  - Cite the doc reference inline next to the task that depends on it, in EVIDENCE.
  - When the freshness check changes the plan (e.g. an API was removed, a new auth flow is mandated), call it out in RISKS as a constraint the implementer must honor.

## Role Exit Checklist
- The plan includes a User Request Summary and the success criteria you optimized for.
- Likely files/modules are identified with the reason they are in scope.
- Every task names the artifacts to change, acceptance criteria, suggested specialist (`explore`, `implementer`, `review`, `security-reviewer`, `debugger`, `verifier`, `judge`), and the smallest verification command/check that proves it worked.
- Risks, blockers, migration/backward-compatibility concerns, and test gaps are called out.

## Output Contract
### SUMMARY
One paragraph with the recommended plan and why.
### CONTEXT
User request summary, confirmed context, assumptions, and unknowns.
### TASK DEPENDENCY GRAPH
Table or bullets showing task dependencies and reasons.
### PARALLEL EXECUTION GRAPH
Execution waves, critical path, and what can/cannot run concurrently.
### PLAN
Numbered tasks with artifacts, acceptance criteria, specialist recommendation, and verification.
### EVIDENCE
Bullet list of concrete file paths, line ranges, docs, or search hits that shaped the plan.
### CHANGES
Always write `None.` unless you wrote a plan artifact.
### RISKS
Bullet list of trade-offs, unknowns, or rollout risks.
### BLOCKERS
Bullet list of questions that must be answered before execution, or `None.`.

## Escalation
- If the goal, constraints, or success criteria are missing and cannot be inferred from the repository, list the exact questions under BLOCKERS instead of planning on assumptions.
"""  # noqa: E501
        }
    )
    assert subagent_specs["plan"].when_to_use == snapshot(
        "Use this agent when the parent agent needs a step-by-step implementation plan, key file identification, and architectural trade-off analysis before code changes are made.\n"
    )
    assert subagent_specs["plan"].model == snapshot(None)
    assert subagent_specs["plan"].allowed_tools == snapshot(
        [
            "pythinker_code.tools.todo:SetTodoList",
            "pythinker_code.tools.file:ReadFile",
            "pythinker_code.tools.file:ReadMediaFile",
            "pythinker_code.tools.file:Glob",
            "pythinker_code.tools.file:Grep",
            "pythinker_code.tools.file:SmartSearch",
            "pythinker_code.tools.skill:ReadSkill",
            "pythinker_code.tools.web:SearchWeb",
            "pythinker_code.tools.web:FetchURL",
        ]
    )
    assert subagent_specs["plan"].exclude_tools == snapshot(
        [
            "pythinker_code.tools.agent:Agent",
            "pythinker_code.tools.ask_user:AskUserQuestion",
            "pythinker_code.tools.plan:ExitPlanMode",
            "pythinker_code.tools.plan.enter:EnterPlanMode",
            "pythinker_code.tools.shell:Shell",
            "pythinker_code.tools.file:WriteFile",
            "pythinker_code.tools.file:StrReplaceFile",
        ]
    )
    assert subagent_specs["plan"].tools == snapshot(
        [
            "pythinker_code.tools.agent:Agent",
            "pythinker_code.tools.agent:RunAgents",
            "pythinker_code.tools.skill:ReadSkill",
            "pythinker_code.tools.ask_user:AskUserQuestion",
            "pythinker_code.tools.todo:SetTodoList",
            "pythinker_code.tools.progress:Progress",
            "pythinker_code.tools.suggest:Suggest",
            "pythinker_code.tools.memory:Memory",
            "pythinker_code.tools.recall:Recall",
            "pythinker_code.tools.scratchpad:Scratchpad",
            "pythinker_code.tools.shell:Shell",
            "pythinker_code.tools.background:TaskList",
            "pythinker_code.tools.background:TaskOutput",
            "pythinker_code.tools.background:TaskInput",
            "pythinker_code.tools.background:TaskHandoff",
            "pythinker_code.tools.background:TaskStop",
            "pythinker_code.tools.file:ReadFile",
            "pythinker_code.tools.file:ReadMediaFile",
            "pythinker_code.tools.file:Glob",
            "pythinker_code.tools.file:Grep",
            "pythinker_code.tools.file:SmartSearch",
            "pythinker_code.tools.file:WriteFile",
            "pythinker_code.tools.file:StrReplaceFile",
            "pythinker_code.tools.web:SearchWeb",
            "pythinker_code.tools.web:FetchURL",
            "pythinker_code.tools.mcp_resource:ListMcpResources",
            "pythinker_code.tools.mcp_resource:ReadMcpResource",
            "pythinker_code.tools.plan:ExitPlanMode",
            "pythinker_code.tools.plan.enter:EnterPlanMode",
        ]
    )
    sub_subagents = {
        name: (spec.path.relative_to(DEFAULT_AGENT_FILE.parent).as_posix(), spec.description)
        for name, spec in subagent_specs["plan"].subagents.items()
    }
    assert sub_subagents == snapshot({})

    assert subagent_specs["planner"].name == snapshot("")
    assert subagent_specs["planner"].system_prompt_path == DEFAULT_AGENT_FILE.parent / "system.md"
    assert subagent_specs["planner"].system_prompt_args == snapshot(
        {
            "ROLE_ADDITIONAL": """\
You are now running as a subagent. All the `user` messages are sent by the main agent. The main agent cannot see your context, it can only see your last message when you finish the task. You must treat the parent agent as your caller. Do not directly ask the end user questions. If something is unclear, explain the ambiguity in your final summary to the parent agent.

## Mission
You are a Reconnaissance Planner. Your single objective is to analyze the request and break it down into N distinct, non-overlapping task seeds for parallel workers.

## Hard Constraints
- Do not solve the problem. Do not write code. Do not fix anything.
- Each seed must provide a distinct starting angle (different file, subsystem, or hypothesis) so that parallel workers exploring them will NOT duplicate effort or converge on the same solution.
- Aim for 3-5 seeds unless the task is clearly simpler or more complex; never pad with overlapping seeds to hit a count.

## Output Contract
Your final message must contain ONLY the seeds block below — no preamble, no explanation,
no content before or after the tags:
<recon_seeds>
["seed description 1", "seed description 2", ...]
</recon_seeds>
"""
        }
    )
    # Semantic invariants for the recon_seeds protocol contract.
    _planner_role = subagent_specs["planner"].system_prompt_args["ROLE_ADDITIONAL"]
    assert "<recon_seeds>" in _planner_role
    assert "ONLY" in _planner_role or "no preamble" in _planner_role.lower()
    assert "distinct" in _planner_role.lower() and "non-overlapping" in _planner_role.lower()
    assert subagent_specs["planner"].when_to_use == snapshot(
        """\
Use this agent before spawning N parallel workers on a large or open-ended task.
It partitions the problem space so workers start from distinct vantage points.
"""
    )
    assert subagent_specs["planner"].model == snapshot(None)
    assert subagent_specs["planner"].allowed_tools == snapshot(
        [
            "pythinker_code.tools.shell:Shell",
            "pythinker_code.tools.file:ReadFile",
            "pythinker_code.tools.file:Glob",
            "pythinker_code.tools.file:Grep",
            "pythinker_code.tools.file:SmartSearch",
        ]
    )
    assert subagent_specs["planner"].exclude_tools == snapshot(
        [
            "pythinker_code.tools.agent:Agent",
            "pythinker_code.tools.ask_user:AskUserQuestion",
            "pythinker_code.tools.plan:ExitPlanMode",
            "pythinker_code.tools.plan.enter:EnterPlanMode",
            "pythinker_code.tools.file:WriteFile",
            "pythinker_code.tools.file:StrReplaceFile",
            "pythinker_code.tools.web:SearchWeb",
            "pythinker_code.tools.web:FetchURL",
        ]
    )
    assert subagent_specs["planner"].tools == snapshot(
        [
            "pythinker_code.tools.agent:Agent",
            "pythinker_code.tools.agent:RunAgents",
            "pythinker_code.tools.skill:ReadSkill",
            "pythinker_code.tools.ask_user:AskUserQuestion",
            "pythinker_code.tools.todo:SetTodoList",
            "pythinker_code.tools.progress:Progress",
            "pythinker_code.tools.suggest:Suggest",
            "pythinker_code.tools.memory:Memory",
            "pythinker_code.tools.recall:Recall",
            "pythinker_code.tools.scratchpad:Scratchpad",
            "pythinker_code.tools.shell:Shell",
            "pythinker_code.tools.background:TaskList",
            "pythinker_code.tools.background:TaskOutput",
            "pythinker_code.tools.background:TaskInput",
            "pythinker_code.tools.background:TaskHandoff",
            "pythinker_code.tools.background:TaskStop",
            "pythinker_code.tools.file:ReadFile",
            "pythinker_code.tools.file:ReadMediaFile",
            "pythinker_code.tools.file:Glob",
            "pythinker_code.tools.file:Grep",
            "pythinker_code.tools.file:SmartSearch",
            "pythinker_code.tools.file:WriteFile",
            "pythinker_code.tools.file:StrReplaceFile",
            "pythinker_code.tools.web:SearchWeb",
            "pythinker_code.tools.web:FetchURL",
            "pythinker_code.tools.mcp_resource:ListMcpResources",
            "pythinker_code.tools.mcp_resource:ReadMcpResource",
            "pythinker_code.tools.plan:ExitPlanMode",
            "pythinker_code.tools.plan.enter:EnterPlanMode",
        ]
    )
    planner_sub = {
        name: (spec.path.relative_to(DEFAULT_AGENT_FILE.parent).as_posix(), spec.description)
        for name, spec in subagent_specs["planner"].subagents.items()
    }
    assert planner_sub == snapshot({})


def test_default_subagents_include_production_guardrail_gate():
    subagent_specs = {
        name: load_agent_spec(spec.path)
        for name, spec in load_agent_spec(DEFAULT_AGENT_FILE).subagents.items()
    }

    assert (
        "production guardrail gate"
        in subagent_specs["review"].system_prompt_args["ROLE_ADDITIONAL"]
    )
    assert (
        "cache stampedes" in subagent_specs["code-reviewer"].system_prompt_args["ROLE_ADDITIONAL"]
    )
    assert (
        "IDOR/tenant-scope mistakes"
        in subagent_specs["security-reviewer"].system_prompt_args["ROLE_ADDITIONAL"]
    )
    assert "Production guardrails" in subagent_specs["judge"].system_prompt_args["ROLE_ADDITIONAL"]


def test_load_agent_spec_basic(agent_file: Path):
    """Test loading a basic agent specification."""
    spec = load_agent_spec(agent_file)

    assert spec.name == snapshot("Test Agent")
    assert spec.system_prompt_path == agent_file.parent / "system.md"
    assert spec.tools == snapshot(["pythinker_code.tools.think:Think"])


def test_load_agent_spec_missing_name(agent_file_no_name: Path):
    """Test missing agent name raises AgentSpecError."""
    with pytest.raises(AgentSpecError, match="Agent name is required"):
        load_agent_spec(agent_file_no_name)


def test_load_agent_spec_missing_system_prompt(agent_file_no_prompt: Path):
    """Test missing system prompt path raises AgentSpecError."""
    with pytest.raises(AgentSpecError, match="System prompt path is required"):
        load_agent_spec(agent_file_no_prompt)


def test_load_agent_spec_missing_tools(agent_file_no_tools: Path):
    """Test missing tools raises AgentSpecError."""
    with pytest.raises(AgentSpecError, match="Tools are required"):
        load_agent_spec(agent_file_no_tools)


def test_load_agent_spec_with_exclude_tools(agent_file_with_tools: Path):
    """Test loading agent spec with excluded tools."""
    spec = load_agent_spec(agent_file_with_tools)

    assert spec.tools == snapshot(
        ["pythinker_code.tools.think:Think", "pythinker_code.tools.shell:Shell"]
    )
    assert spec.exclude_tools == snapshot(["pythinker_code.tools.shell:Shell"])


def test_load_agent_spec_extension(agent_file_extending: Path):
    """Test loading agent spec with extension."""
    spec = load_agent_spec(agent_file_extending)

    assert spec.name == snapshot("Extended Agent")
    assert spec.tools == snapshot(["pythinker_code.tools.think:Think"])


def test_load_agent_spec_metadata_inherits_and_overrides(tmp_path: Path):
    (tmp_path / "system.md").write_text("Base system prompt")
    base = tmp_path / "base.yaml"
    base.write_text(
        """
version: 1
agent:
  name: "Base Agent"
  system_prompt_path: ./system.md
  tools: ["pythinker_code.tools.think:Think"]
  mode: subagent
  hidden: true
  steps: 7
  temperature: 0.2
  top_p: 0.8
""".strip()
    )
    child = tmp_path / "child.yaml"
    child.write_text(
        """
version: 1
agent:
  extend: ./base.yaml
  name: "Child Agent"
  mode: all
  hidden: false
  steps: 3
""".strip()
    )

    spec = load_agent_spec(child)

    assert spec.name == "Child Agent"
    assert spec.mode == "all"
    assert spec.hidden is False
    assert spec.steps == 3
    assert spec.temperature == 0.2
    assert spec.top_p == 0.8


def test_load_agent_spec_default_extension():
    """Test loading agent spec with default extension."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create extending agent
        extending_agent = tmpdir / "extending.yaml"
        extending_agent.write_text("""
version: 1
agent:
  extend: default
  system_prompt_args:
    CUSTOM_ARG: "custom_value"
  exclude_tools:
    - "pythinker_code.tools.web:SearchWeb"
    - "pythinker_code.tools.web:FetchURL"
""")

        spec = load_agent_spec(extending_agent)

        assert spec.name == snapshot("")
        assert spec.system_prompt_path == DEFAULT_AGENT_FILE.parent / "system.md"
        assert spec.system_prompt_args == snapshot(
            {"ROLE_ADDITIONAL": "", "CUSTOM_ARG": "custom_value"}
        )
        assert spec.tools == snapshot(
            [
                "pythinker_code.tools.agent:Agent",
                "pythinker_code.tools.agent:RunAgents",
                "pythinker_code.tools.skill:ReadSkill",
                "pythinker_code.tools.ask_user:AskUserQuestion",
                "pythinker_code.tools.todo:SetTodoList",
                "pythinker_code.tools.progress:Progress",
                "pythinker_code.tools.suggest:Suggest",
                "pythinker_code.tools.memory:Memory",
                "pythinker_code.tools.recall:Recall",
                "pythinker_code.tools.scratchpad:Scratchpad",
                "pythinker_code.tools.shell:Shell",
                "pythinker_code.tools.background:TaskList",
                "pythinker_code.tools.background:TaskOutput",
                "pythinker_code.tools.background:TaskInput",
                "pythinker_code.tools.background:TaskHandoff",
                "pythinker_code.tools.background:TaskStop",
                "pythinker_code.tools.file:ReadFile",
                "pythinker_code.tools.file:ReadMediaFile",
                "pythinker_code.tools.file:Glob",
                "pythinker_code.tools.file:Grep",
                "pythinker_code.tools.file:SmartSearch",
                "pythinker_code.tools.file:WriteFile",
                "pythinker_code.tools.file:StrReplaceFile",
                "pythinker_code.tools.web:SearchWeb",
                "pythinker_code.tools.web:FetchURL",
                "pythinker_code.tools.mcp_resource:ListMcpResources",
                "pythinker_code.tools.mcp_resource:ReadMcpResource",
                "pythinker_code.tools.plan:ExitPlanMode",
                "pythinker_code.tools.plan.enter:EnterPlanMode",
            ]
        )
        assert spec.exclude_tools == snapshot(
            ["pythinker_code.tools.web:SearchWeb", "pythinker_code.tools.web:FetchURL"]
        )
        assert "coder" in spec.subagents


def test_load_agent_spec_unsupported_version():
    """Test loading agent spec with unsupported version raises ValueError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        agent_yaml = tmpdir / "agent.yaml"
        agent_yaml.write_text("""
version: 2
agent:
  name: "Test Agent"
  system_prompt_path: ./system.md
  tools: ["pythinker_code.tools.think:Think"]
""")

        with pytest.raises(AgentSpecError, match="Unsupported agent spec version: 2"):
            load_agent_spec(agent_yaml)


def test_load_agent_spec_nonexistent_file():
    """Test loading nonexistent agent spec file raises AssertionError."""
    nonexistent = Path("/nonexistent/agent.yaml")
    with pytest.raises(
        AgentSpecError,
        match=re.compile(r"Agent spec file not found: [\\/]nonexistent[\\/]agent.yaml"),
    ):
        load_agent_spec(nonexistent)


def test_load_agent_spec_empty_yaml_raises_agent_spec_error(tmp_path: Path):
    agent_yaml = tmp_path / "agent.yaml"
    agent_yaml.write_text("")

    with pytest.raises(AgentSpecError, match="Agent spec file must contain a mapping"):
        load_agent_spec(agent_yaml)


def test_load_agent_spec_non_mapping_yaml_raises_agent_spec_error(tmp_path: Path):
    agent_yaml = tmp_path / "agent.yaml"
    agent_yaml.write_text("- not\n- a\n- mapping\n")

    with pytest.raises(AgentSpecError, match="Agent spec file must contain a mapping"):
        load_agent_spec(agent_yaml)


# Fixtures for test files


@pytest.fixture
def agent_file() -> Generator[Path, Any, Any]:
    """Create a basic agent configuration file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create system.md
        system_md = tmpdir / "system.md"
        system_md.write_text("You are a test agent")

        # Create agent.yaml
        agent_yaml = tmpdir / "agent.yaml"
        agent_yaml.write_text("""
version: 1
agent:
  name: "Test Agent"
  system_prompt_path: ./system.md
  tools: ["pythinker_code.tools.think:Think"]
""")

        yield agent_yaml


@pytest.fixture
def agent_file_no_name() -> Generator[Path, Any, Any]:
    """Create an agent configuration file without name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create system.md
        system_md = tmpdir / "system.md"
        system_md.write_text("You are a test agent")

        # Create agent.yaml
        agent_yaml = tmpdir / "agent.yaml"
        agent_yaml.write_text("""
version: 1
agent:
  system_prompt_path: ./system.md
  tools: ["pythinker_code.tools.think:Think"]
""")

        yield agent_yaml


@pytest.fixture
def agent_file_no_prompt() -> Generator[Path, Any, Any]:
    """Create an agent configuration file without system prompt path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create agent.yaml
        agent_yaml = tmpdir / "agent.yaml"
        agent_yaml.write_text("""
version: 1
agent:
  name: "Test Agent"
  tools: ["pythinker_code.tools.think:Think"]
""")

        yield agent_yaml


@pytest.fixture
def agent_file_no_tools() -> Generator[Path, Any, Any]:
    """Create an agent configuration file without tools."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create system.md
        system_md = tmpdir / "system.md"
        system_md.write_text("You are a test agent")

        # Create agent.yaml
        agent_yaml = tmpdir / "agent.yaml"
        agent_yaml.write_text("""
version: 1
agent:
  name: "Test Agent"
  system_prompt_path: ./system.md
""")

        yield agent_yaml


@pytest.fixture
def agent_file_with_tools() -> Generator[Path, Any, Any]:
    """Create an agent configuration file with tools and exclude_tools."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create system.md
        system_md = tmpdir / "system.md"
        system_md.write_text("You are a test agent")

        # Create agent.yaml
        agent_yaml = tmpdir / "agent.yaml"
        agent_yaml.write_text("""
version: 1
agent:
  name: "Test Agent"
  system_prompt_path: ./system.md
  tools: ["pythinker_code.tools.think:Think", "pythinker_code.tools.shell:Shell"]
  exclude_tools: ["pythinker_code.tools.shell:Shell"]
""")

        yield agent_yaml


@pytest.fixture
def agent_file_extending() -> Generator[Path, Any, Any]:
    """Create an agent configuration file that extends another."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create base agent
        base_agent = tmpdir / "base.yaml"
        base_agent.write_text("""
version: 1
agent:
  name: "Base Agent"
  system_prompt_path: ./system.md
  tools: ["pythinker_code.tools.think:Think"]
""")

        # Create system.md
        system_md = tmpdir / "system.md"
        system_md.write_text("Base system prompt")

        # Create extending agent
        extending_agent = tmpdir / "extending.yaml"
        extending_agent.write_text("""
version: 1
agent:
  extend: ./base.yaml
  name: "Extended Agent"
  system_prompt_args:
    CUSTOM_ARG: "custom_value"
""")

        yield extending_agent


def test_subagent_extension_merges_subagents_dicts(tmp_path: Path):
    """Extending an agent with a new subagent type should ADD to, not replace, base subagents."""
    system_md = tmp_path / "system.md"
    system_md.write_text("Base system prompt")

    base_yaml = tmp_path / "base.yaml"
    base_yaml.write_text("""
version: 1
agent:
  name: "Base"
  system_prompt_path: ./system.md
  tools: ["pythinker_code.tools.think:Think"]
  subagents:
    alpha:
      path: ./alpha.yaml
      description: "Alpha agent"
    beta:
      path: ./beta.yaml
      description: "Beta agent"
""")

    (tmp_path / "alpha.yaml").write_text(
        "version: 1\nagent:\n  name: alpha\n  system_prompt_path: ./system.md\n  tools: []\n"
    )
    (tmp_path / "beta.yaml").write_text(
        "version: 1\nagent:\n  name: beta\n  system_prompt_path: ./system.md\n  tools: []\n"
    )
    (tmp_path / "gamma.yaml").write_text(
        "version: 1\nagent:\n  name: gamma\n  system_prompt_path: ./system.md\n  tools: []\n"
    )

    child_yaml = tmp_path / "child.yaml"
    child_yaml.write_text("""
version: 1
agent:
  extend: ./base.yaml
  name: "Child"
  subagents:
    gamma:
      path: ./gamma.yaml
      description: "Gamma agent"
""")

    spec = load_agent_spec(child_yaml)

    # Child adds gamma; base alpha and beta must still be present.
    assert set(spec.subagents.keys()) == {"alpha", "beta", "gamma"}
    assert spec.subagents["gamma"].description == snapshot("Gamma agent")
    assert spec.subagents["alpha"].description == snapshot("Alpha agent")


def test_subagent_extension_child_overrides_base_entry(tmp_path: Path):
    """Child subagent with same name as base overwrites only that entry."""
    system_md = tmp_path / "system.md"
    system_md.write_text("prompt")

    base_yaml = tmp_path / "base.yaml"
    base_yaml.write_text("""
version: 1
agent:
  name: "Base"
  system_prompt_path: ./system.md
  tools: ["pythinker_code.tools.think:Think"]
  subagents:
    coder:
      path: ./coder_v1.yaml
      description: "Original coder"
    reviewer:
      path: ./reviewer.yaml
      description: "Reviewer"
""")
    for name in ("coder_v1", "coder_v2", "reviewer"):
        (tmp_path / f"{name}.yaml").write_text(
            f"version: 1\nagent:\n  name: {name}\n  system_prompt_path: ./system.md\n  tools: []\n"
        )

    child_yaml = tmp_path / "child.yaml"
    child_yaml.write_text("""
version: 1
agent:
  extend: ./base.yaml
  name: "Child"
  subagents:
    coder:
      path: ./coder_v2.yaml
      description: "Upgraded coder"
""")

    spec = load_agent_spec(child_yaml)

    assert set(spec.subagents.keys()) == {"coder", "reviewer"}
    assert spec.subagents["coder"].description == snapshot("Upgraded coder")
    assert spec.subagents["reviewer"].description == snapshot("Reviewer")
